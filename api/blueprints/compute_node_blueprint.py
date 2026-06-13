from flask import Blueprint, jsonify, make_response, request

from api.blueprints.storage_blueprint import IP_RE, WALLET_RE
from core.domain.exceptions import ValidationError
from core.domain.models import ComputeHeartbeat, ComputeNodeCreateRequest
from core.services.compute_node_service import ComputeNodeService


def create_compute_node_blueprint(
    compute_service: ComputeNodeService, auth_required, executor
) -> Blueprint:
    bp = Blueprint("compute", __name__, url_prefix="/compute-nodes")
    compute_service._executor = executor

    @bp.post("/heartbeat")
    @auth_required
    def heartbeat(username: str):
        body = request.get_json()

        try:

            node_status = ComputeHeartbeat(**body)
            compute_service.heartbeat_service.add_alive_node(
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

    @bp.get("/assigned-tasks")
    @auth_required
    def get_assigned_tasks(username: str):
        num_tasks = request.args.get("tasks_number", type=int, default=3)
        try:
            tasks = compute_service.get_assigned_tasks(username, num_tasks)
            print(tasks)
            return jsonify({"tasks": tasks}), 200
        except Exception as exc:
            if isinstance(exc, TypeError):
                return jsonify({"message": "Bad Request"}), 400
            return jsonify({"message": str(exc)}), 400

    return bp
