from __future__ import annotations

import asyncio
import atexit
import signal
import threading

import pymongo
from cryptography.fernet import Fernet
from flask import Flask
from redis.asyncio import ConnectionPool, Redis
from supabase import create_client

import config as cfg
import blockchain.web3_lib as web3_library
from api.blueprints.compute_node_blueprint import create_compute_node_blueprint
from api.blueprints.storage_blueprint import create_storage_blueprint
from api.blueprints.user_blueprint import create_user_blueprint
from api.middleware.auth import (
    make_auth_decorator,
    register_error_handlers,
    make_async_auth_decorator,
)
from api.swagger import register_swagger
from core.services.auth_service import AuthService
from core.services.compute_node_service import ComputeNodeService
from core.services.heartbeat_service import HeartbeatService
from core.services.scheduler_service import Scheduler
from core.services.storage_service import StorageService
from core.services.supabase_service import SupabaseBlobStorage
from core.services.task_service import ComputeTaskService
from core.services.user_service import UserService
from core.services.workflow_service import WorkflowService
from infrastructure.async_executor import AsyncExecutor
from infrastructure.database.mongo_repositories import (
    MongoComputeNodeRepository,
    MongoComputeTaskRepository,
    MongoComputeWorkflowRepository,
    MongoFileRepository,
    MongoStorageRepository,
    MongoTransactionRepository,
    MongoUserRepository,
)
from infrastructure.database.redis_repositories import RedisRepository
from infrastructure.regeneration.client import RegenerationClient
from infrastructure.storage_network.client import StorageNetworkClient


def create_app(env: str = "dev") -> Flask:
    """Build and return a configured Flask application."""
    app = Flask(__name__)

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    config_map = {
        "prod": cfg.ProductionConfig,
        "dev": cfg.DevelopmentConfig,
    }
    if env not in config_map:
        raise ValueError(
            f"Unknown environment: {env!r}. Choose 'dev' or 'prod'."
        )

    app.config.from_object(config_map[env])

    # ------------------------------------------------------------------
    # Infrastructure
    # ------------------------------------------------------------------

    mongo_client = pymongo.MongoClient(app.config["DATABASE_URI"])
    db = mongo_client[app.config["DATABASE_NAME"]]

    pool = ConnectionPool.from_url(
        app.config["REDIS_DATABASE_URI"],
        max_connections=20,
        decode_responses=True,
    )
    redis_client = Redis(connection_pool=pool)
    supabase_client = create_client(
        app.config["SUPABASE_PROJECT"], app.config["SUPABASE_KEY"]
    )
    supabase_storage = SupabaseBlobStorage(supabase_client)

    # SHARD_ID_KEY is a Fernet key: already base64-encoded, so encode to bytes
    # but do NOT re-encode if it was stored as bytes already.
    shard_id_key = app.config["SHARD_ID_KEY"]
    if isinstance(shard_id_key, str):
        shard_id_key = shard_id_key.encode()
    fernet = Fernet(shard_id_key)

    network = StorageNetworkClient()

    # ------------------------------------------------------------------
    # Repositories
    # ------------------------------------------------------------------

    user_repo = MongoUserRepository(db)
    storage_repo = MongoStorageRepository(db)
    file_repo = MongoFileRepository(db)
    tx_repo = MongoTransactionRepository(db)
    compute_node_repo = MongoComputeNodeRepository(db)
    compute_task_repo = MongoComputeTaskRepository(db)
    compute_workflow_repo = MongoComputeWorkflowRepository(db)
    redis_repo = RedisRepository(redis_client)

    # ------------------------------------------------------------------
    # Services
    # ------------------------------------------------------------------

    auth_service = AuthService(app.config["SECRET_KEY"])

    user_service = UserService(
        user_repo=user_repo,
        file_repo=file_repo,
        tx_repo=tx_repo,
        auth_service=auth_service,
        blockchain=web3_library,
        network=network,
        fernet=fernet,
        storage_repo=storage_repo,
    )

    heartbeat_service = HeartbeatService(redis_repo, compute_node_repo)
    compute_node_service = ComputeNodeService(
        heartbeat_service, auth_service, compute_node_repo, redis_repo
    )
    regeneration_client = RegenerationClient(file_repo)
    # file_repo.create(
    #     File(
    #         id="file123",
    #         username="user1",
    #         filename="test.txt",
    #         file_size=1024,
    #         download_count=0,
    #         duration_in_months=12,
    #         contract_address="0xFAKE_CONTRACT",
    #         price=10.0,
    #         paid=False,
    #         segments=[
    #             {
    #                 "shards": [
    #                     {"shard_id": "gAAAAAB..."}
    #                 ]
    #             }
    #         ],
    #         done_uploading=False
    #     ).__dict__
    # )
    storage_service = StorageService(
        storage_repo=storage_repo,
        file_repo=file_repo,
        auth_service=auth_service,
        blockchain=web3_library,
        network=network,
        fernet=fernet,
        regeneration=regeneration_client.start_regeneration_job,
    )

    #########################################
    # Scheduler
    #########################################
    scheduler = Scheduler(
        heartbeat_service,
        redis_repo,
        supabase_storage,
        compute_workflow_repo,
        compute_task_repo,
    )

    ##########################################
    # Background Loop
    ##########################################
    bg_loop = asyncio.new_event_loop()
    executor = AsyncExecutor(bg_loop, scheduler)

    def start_background_loop():
        asyncio.set_event_loop(bg_loop)
        # bg_loop.run_until_complete() put here the state load function in
        # scheduler
        try:
            bg_loop.run_until_complete(scheduler.load_state())
            bg_loop.run_until_complete(scheduler.run())
        except asyncio.CancelledError:
            pass

    thread = threading.Thread(target=start_background_loop, daemon=True)
    thread.start()

    workflow_service = WorkflowService(compute_workflow_repo, executor)
    task_service = ComputeTaskService(compute_task_repo, executor)
    heartbeat_service.executor = executor
    # ------------------------------------------------------------------
    # Auth decorators (one per node type)
    # ------------------------------------------------------------------

    user_auth = make_auth_decorator(auth_service, user_service.verify_exists)
    storage_auth = make_auth_decorator(
        auth_service, storage_service.verify_active
    )
    compute_node_auth = make_async_auth_decorator(
        auth_service, compute_node_service.verify_exists
    )

    # ------------------------------------------------------------------
    # Blueprints
    # ------------------------------------------------------------------

    app.register_blueprint(create_user_blueprint(user_service, user_auth))
    app.register_blueprint(
        create_storage_blueprint(storage_service, storage_auth)
    )
    app.register_blueprint(
        create_compute_node_blueprint(
            compute_node_service, compute_node_auth, executor
        )
    )

    def shutdown_background_loop():
        bg_loop.call_soon_threadsafe(scheduler.stop)
        thread.join(timeout=5)
        bg_loop.close()

    atexit.register(shutdown_background_loop)
    signal.signal(
        signal.SIGTERM, lambda sig, frame: shutdown_background_loop()
    )
    # ------------------------------------------------------------------
    # Error handlers
    # ------------------------------------------------------------------

    register_error_handlers(app)

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------

    @app.after_request
    def inject_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = (
            "DELETE, GET, HEAD, OPTIONS, POST, PUT, PATCH"
        )
        response.headers["Access-Control-Allow-Headers"] = (
            "Origin, Content-Type, User-Agent, Content-Range, Token, Code, Authorization, authorization "
        )
        response.headers["Access-Control-Expose-Headers"] = (
            "DAV, content-length, Allow"
        )
        return response

    register_swagger(app)

    return app
