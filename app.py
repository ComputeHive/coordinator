from __future__ import annotations

import importlib

import pymongo
from cryptography.fernet import Fernet
from flask import Flask

import config as cfg
from api.blueprints.user_blueprint import create_user_blueprint
from api.blueprints.storage_blueprint import create_storage_blueprint
from api.swagger import register_swagger
from api.middleware.auth import make_auth_decorator, register_error_handlers
from core.domain.models import File
from core.services.auth_service import AuthService
from core.services.user_service import UserService
from core.services.storage_service import StorageService
from infrastructure.database.mongo_repositories import (
    MongoFileRepository,
    MongoStorageRepository,
    MongoTransactionRepository,
    MongoUserRepository,
)
from infrastructure.storage_network.client import StorageNetworkClient
from infrastructure.regeneration.client import RegenerationClient
import blockchain.web3_lib as web3_library

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
        raise ValueError(f"Unknown environment: {env!r}. Choose 'dev' or 'prod'.")

    app.config.from_object(config_map[env])

    # ------------------------------------------------------------------
    # Infrastructure
    # ------------------------------------------------------------------

    mongo_client = pymongo.MongoClient(app.config["DATABASE_URI"])
    db = mongo_client[app.config["DATABASE_NAME"]]

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

    # ------------------------------------------------------------------
    # Auth decorators (one per node type)
    # ------------------------------------------------------------------

    user_auth = make_auth_decorator(auth_service, user_service.verify_exists)
    storage_auth = make_auth_decorator(auth_service, storage_service.verify_active)

    # ------------------------------------------------------------------
    # Blueprints
    # ------------------------------------------------------------------

    app.register_blueprint(create_user_blueprint(user_service, user_auth))
    app.register_blueprint(create_storage_blueprint(storage_service, storage_auth))

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
        response.headers["Access-Control-Expose-Headers"] = "DAV, content-length, Allow"
        return response

    register_swagger(app)

    return app