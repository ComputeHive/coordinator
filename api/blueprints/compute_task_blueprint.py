from flask import Blueprint, jsonify, request

from core.domain.models import TaskCreateRequest, TaskFinishedRequest
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
        ip_addr = ""
        if request.headers.getlist("X-Forwarded-For"):
            ip_addr = request.headers.getlist("X-Forwarded-For")[0]
        else:
            ip_addr = request.remote_addr
        try:
            task = TaskCreateRequest(**body)
            task_service.create_task(task, username, str(ip_addr))
            return jsonify({"message": "Task Created Successfully"}), 204
        except Exception as exc:
            if isinstance(exc, TypeError):
                print(exc)
                return jsonify({"message": "Bad Request"}), 400
            return jsonify({"message": str(exc)}), 400

    @bp.post("/finished-task")
    @auth_required
    async def assign_task_finished(username: str):
        body = request.json()
        try:
            finished_task = TaskFinishedRequest(**body)
            await task_service._assign_task_finished(finished_task)
            return (
                jsonify(
                    {
                        "message": f"{finished_task.task_id} assigned as"
                        "finished successfully"
                    }
                ),
                200,
            )
        except Exception as exc:
            if isinstance(exc, TypeError):
                print(exc)
                return jsonify({"message": "Bad Request"}), 400
            return jsonify({"message": str(exc)}), 400

    @bp.get("/task-result/<task_id>")
    def get_task_result(task_id: str):
        pass

    return bp
