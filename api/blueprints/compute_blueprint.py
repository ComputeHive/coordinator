from flask import Blueprint, jsonify, request

from core.domain.models import ComputeHeartbeat
from core.services.compute_service import ComputeService


def create_compute_blueprint(
    compute_service: ComputeService, auth_required
) -> Blueprint:
    bp = Blueprint("compute", __name__, url_prefix="compute")

    @bp.post("/heartbeat")
    @auth_required
    async def heartbeat():
        body = request.json or {}
        node_status = ComputeHeartbeat(**body)
        try:
            await compute_service.heartbeat_service.add_alive_node(node_status)
            return jsonify({"message": "Successful heartbeat"}), 200
        except Exception as exc:
            return jsonify({"message": exc}), 400

    return bp
