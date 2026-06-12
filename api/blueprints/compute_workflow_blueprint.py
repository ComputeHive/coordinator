from flask import Blueprint, jsonify, request

from core.domain.models import WorkflowCreateRequest
from core.services.workflow_service import WorkflowService


def create_compute_workflow_blueprint(
    workflow_service: WorkflowService, auth_required
) -> Blueprint:
    bp = Blueprint(
        "compute-workflows", __name__, url_prefix="/compute-workflows"
    )

    @bp.post("/upload")
    @auth_required
    def upload_workflow(username):
        body = request.get_json()
        ip_addr = ""
        if request.headers.getlist("X-Forwarded-For"):
            ip_addr = request.headers.getlist("X-Forwarded-For")[0]
        else:
            ip_addr = request.remote_addr
        try:
            workflow = WorkflowCreateRequest(**body)
            workflow_service.create_workflow(workflow, username)
            return jsonify({"message": "Workflow Created Successfully"}), 204
        except Exception as exc:
            if isinstance(exc, TypeError):
                print(exc)
                return jsonify({"message": "Bad Request"}), 400
            return jsonify({"message": str(exc)}), 400

    @bp.get("/workflow-result/<workflow_id>")
    def get_workflow_result(workflow_id: str): ...

    return bp
