from __future__ import annotations

import re

from flask import Blueprint, jsonify, make_response, request

from core.services.storage_service import StorageService
from core.domain.exceptions import ValidationError


_IP_RE = re.compile(
    r"^((25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(25[0-5]|2[0-4]\d|[01]?\d\d?)$"
)
_PORT_RE = re.compile(
    r"^([0-9]{1,4}|[1-5]\d{4}|6[0-4]\d{3}|65[0-4]\d{2}|655[0-2]\d|6553[0-5])$"
)
_WALLET_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


def create_storage_blueprint(storage_service: StorageService, auth_required) -> Blueprint:
    bp = Blueprint("storage", __name__, url_prefix="/storage-nodes")

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    @bp.post("/signup")
    def signup():
        body = request.json or {}
        username = body.get("username", "").strip()
        password = body.get("password", "")
        wallet_address = body.get("wallet_address", "")
        available_space = body.get("available_space")

        if not _WALLET_RE.match(wallet_address):
            raise ValidationError("Invalid wallet address.")

        storage_service.register(username, password, wallet_address, available_space)
        return make_response("", 201)

    @bp.post("/signin")
    def signin():
        body = request.json or {}
        username = body.get("username", "").strip()
        password = body.get("password", "")
        token = storage_service.authenticate(username, password)
        return jsonify({"token": token}), 200

    # ------------------------------------------------------------------
    # Node status
    # ------------------------------------------------------------------

    @bp.post("/me/heartbeat")
    @auth_required
    def heartbeat(username: str):
        storage_service.heartbeat(username)
        return make_response("", 204)

    @bp.get("/me/availability")
    @auth_required
    def get_availability(username: str):
        availability = storage_service.get_availability(username)
        return jsonify({"availability": availability}), 200

    @bp.get("/me")
    @auth_required
    def get_storage_info(username: str):
        availability, contracts_info = storage_service.get_storage_info(username)
        return jsonify({"availability": availability, "contracts": contracts_info}), 200

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    @bp.patch("/me/connection")
    @auth_required
    def update_connection(username: str):
        body = request.json or {}
        ip_address = body.get("ip_address", "")
        port = body.get("port", "")

        if not isinstance(ip_address, str) or not _IP_RE.match(ip_address):
            raise ValidationError("Invalid IP address.")
        if not isinstance(port, str) or not _PORT_RE.match(port):
            raise ValidationError("Invalid port number.")

        storage_service.update_connection(username, ip_address, port)
        return make_response("", 204)

    # ------------------------------------------------------------------
    # Contracts
    # ------------------------------------------------------------------

    @bp.get("/me/contracts")
    @auth_required
    def list_contracts(username: str):
        shards = storage_service.get_active_contracts(username)
        return jsonify({"shards": shards}), 200

    @bp.post("/me/contracts/<string:shard_id>/withdrawal")
    @auth_required
    def withdraw(username: str, shard_id: str):
        storage_service.withdraw(username, shard_id)
        return make_response("", 204)

    # ------------------------------------------------------------------
    # Shards
    # ------------------------------------------------------------------

    @bp.patch("/me/shards/done")
    @auth_required
    def shard_done_uploading(username: str):
        body = request.json or {}
        shard_id = body.get("shard_id")
        if not shard_id:
            raise ValidationError("shard_id is required.")
        storage_service.shard_done_uploading(shard_id)
        return make_response("", 204)

    return bp