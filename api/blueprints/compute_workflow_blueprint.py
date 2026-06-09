from flask import Blueprint


def create_compute_workflow_blueprint() -> Blueprint:
    bp = Blueprint(
        "compute-workflows", __name__, url_prefix="/compute-workflows"
    )

    @bp.post("/upload")
    def upload_workflow(): ...
    @bp.get("/workflow-result/<workflow_id>")
    def get_workflow_result(workflow_id: str): ...

    return bp
