from flask import Blueprint, jsonify, request

from core.services.task_service import ComputeTaskService
from core.services.user_service import UserService


def create_compute_task_blueprint(
    task_service: ComputeTaskService,
    user_node_service: UserService,
    auth_required,
) -> Blueprint:
    bp = Blueprint("compute-tasks", __name__, url_prefix="/compute-tasks")

    @bp.post("/upload")
    @auth_required
    async def upload_task(username: str):
        body = request.get_json()
        try:
            pass
        except Exception as exc:
            if isinstance(exc, TypeError):
                print(exc)
                return jsonify({"message": "Bad Request"}), 400
            return jsonify({"message": str(exc)}), 400

    @bp.get("/task-result/<task_id>")
    def get_task_result(task_id: str):
        pass

    return bp
