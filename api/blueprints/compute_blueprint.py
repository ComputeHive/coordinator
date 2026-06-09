import json

from flask import Blueprint, jsonify, make_response, request

from api.blueprints.storage_blueprint import IP_RE, WALLET_RE
from core.domain.exceptions import ValidationError
from core.domain.models import ComputeHeartbeat, ComputeNodeCreateRequest
from core.services.compute_node_service import ComputeNodeService


def create_compute_node_blueprint(
    compute_service: ComputeNodeService, auth_required
) -> Blueprint:
    bp = Blueprint("compute", __name__, url_prefix="/compute-nodes")

    @bp.post("/heartbeat")
    @auth_required
    async def heartbeat(username: str):
        body = request.get_json()
        try:

            print()
            node_status = ComputeHeartbeat(**body)
            await compute_service.heartbeat_service.add_alive_node(
                username, node_status
            )
            return jsonify({"message": "Successful heartbeat"}), 200
        except Exception as exc:
            if isinstance(exc, TypeError):
                print(exc)
                return jsonify({"message": "Bad Request"}), 400
            return jsonify({"message": str(exc)}), 400

    @bp.post("/signup")
    def signup():
        body = request.get_json()

        try:
            compute_node_data = ComputeNodeCreateRequest(**body)
            if not WALLET_RE.match(compute_node_data.wallet_address):
                raise ValidationError("Invalid wallet address.")
            if not isinstance(
                compute_node_data.ip_address, str
            ) or not IP_RE.match(compute_node_data.ip_address):
                raise ValidationError("Invalid IP address.")
            compute_service.create_compute_node(compute_node_data)
            return make_response(""), 200
        except Exception as exc:
            if isinstance(exc, TypeError):
                return jsonify({"message": "Bad Request"}), 400
            return jsonify({"message": str(exc)}), 400

    @bp.post("/signin")
    def signin():
        body = request.get_json()
        try:
            username = body.get("username", "")
            password = body.get("password", "")
            token = compute_service.authenticate_compute_node(
                username, password
            )

            return jsonify({"token": token}), 200
        except Exception as exc:
            if isinstance(exc, TypeError):
                return jsonify({"message": "Bad Request"}), 400
            return jsonify({"message": str(exc)}), 400

    return bp
