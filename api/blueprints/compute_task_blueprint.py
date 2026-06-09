from flask import Blueprint


def create_compute_task_blueprint() -> Blueprint:
    bp = Blueprint("compute-tasks", __name__, url_prefix="/compute-tasks")

    @bp.post("/upload")
    def upload_task(): ...
    @bp.get("/task-result/<task_id>")
    def get_task_result(task_id: str): ...

    return bp
