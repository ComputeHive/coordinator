from __future__ import annotations

import json
import os

from flask import Blueprint, jsonify, make_response, request

from core.services.supabase_service import BUCKET_NAME, SupabaseBlobStorage
from core.services.user_service import UserService


def create_user_blueprint(
    user_service: UserService,
    supabase_service: SupabaseBlobStorage,
    auth_required,
) -> Blueprint:
    bp = Blueprint("user", __name__, url_prefix="/users")

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    @bp.post("/signup")
    def signup():
        body = request.json or {}
        username = body.get("username", "").strip()
        password = body.get("password", "")
        user_service.register(username, password)
        return make_response("", 201)

    @bp.post("/signin")
    def signin():
        body = request.json or {}
        username = body.get("username", "").strip()
        password = body.get("password", "")
        token = user_service.authenticate(username, password)
        return jsonify({"token": token}), 200

    # ------------------------------------------------------------------
    # User state
    # ------------------------------------------------------------------

    @bp.get("/me/state")
    @auth_required
    def get_state(username: str):
        state = user_service.get_state(username)
        return jsonify({"state": state}), 200

    @bp.get("/me/wallet")
    @auth_required
    def get_wallet_address(username: str):
        return jsonify({"cera_wallet_address": os.environ["ADDRESS"]}), 200

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------

    @bp.get("/me/files")
    @auth_required
    def list_files(username: str):
        files = user_service.get_active_contracts(username)
        return jsonify(files), 200

    @bp.post("/me/files")
    @auth_required
    def create_file(username: str):
        payload = request.json
        user_service.create_file(username, payload)
        return make_response("", 201)

    @bp.get("/me/files/pending")
    @auth_required
    def get_pending_file_info(username: str):
        info = user_service.get_file_info(username)
        return jsonify(info), 200

    @bp.patch("/me/files/pending/done")
    @auth_required
    def file_done_uploading(username: str):
        user_service.file_done_uploading(username)
        return make_response("", 204)

    # ------------------------------------------------------------------
    # Shards
    # ------------------------------------------------------------------

    @bp.patch("/me/files/pending/shards/done")
    @auth_required
    def shard_done_uploading(username: str):
        body = request.json or {}
        shard_id = body.get("shard_id")
        audits = body.get("audits")
        user_service.shard_done_uploading(username, shard_id, audits)
        return make_response("", 204)

    @bp.patch("/me/files/pending/shards/reassign")
    @auth_required
    def shard_failed_uploading(username: str):
        body = request.json or {}
        shard_id = body.get("shard_id")
        new_connection = user_service.shard_failed_uploading(
            username, shard_id
        )
        return jsonify(new_connection), 200

    # ------------------------------------------------------------------
    # Downloads
    # ------------------------------------------------------------------

    @bp.post("/me/files/<string:filename>/downloads")
    @auth_required
    def start_download(username: str, filename: str):
        result = user_service.start_download(username, filename)
        return jsonify(result), 200

    @bp.get("/me/files/pending/price")
    @auth_required
    def get_price(username: str):
        download_count = int(request.args["download_count"])
        duration_in_months = int(request.args["duration_in_months"])
        file_size = int(request.args["file_size"])
        price = user_service.get_price(
            download_count, duration_in_months, file_size
        )
        return jsonify({"price": price}), 200

    # ------------------------------------------------------------------
    # Contract / payment
    # ------------------------------------------------------------------

    @bp.get("/me/contracts/pending")
    @auth_required
    def get_contract(username: str):
        contract = user_service.get_contract(username)
        return jsonify(contract), 200

    @bp.post("/me/contracts/pending/payment")
    @auth_required
    def pay_contract(username: str):
        user_service.pay_contract(username)
        return make_response("", 204)

    @bp.post("/me/transactions/verify")
    @auth_required
    def verify_transaction(username: str):
        body = request.json or {}
        tx_hash = body.get("transactionHash")
        user_service.verify_transaction(username, tx_hash)
        return make_response("", 204)

    @bp.post("/generate-links")
    @auth_required
    def generate_signed_links(username: str):
        body = request.get_json()
        try:
            names = body.get("files", [])

            object_links = supabase_service.generate_presigned_upload_url(
                BUCKET_NAME, names
            )
            print(object_links)
            return jsonify({"links": object_links})
        except Exception as exc:
            if isinstance(exc, TypeError):
                return jsonify({"message": "Bad Request"}), 400
            return jsonify({"message": str(exc)}), 400

    return bp
