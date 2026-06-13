from pathlib import Path
from typing import Any, Dict

from core.domain.enums import ComputeStatusEnum
from core.domain.models import ComputeWorkflow, WorkflowCreateRequest
from core.repositories import IComputeWorkflowRepository
from core.services.encryption_service import AES
from core.services.keygenerator_service import ECDHKeyGenerator
from infrastructure.async_executor import AsyncExecutor
from utils.lib import extract_zip_file
from utils.task_processor import TaskProcessor
from utils.workflow_processor import WorkflowProcessor


class WorkflowService:
    def __init__(
        self, db_repo: IComputeWorkflowRepository, executor: AsyncExecutor
    ):
        self._db_repo = db_repo
        self._executor = executor

    def create_workflow(
        self,
        workflow: WorkflowCreateRequest,
        requester_username: str,
        requester_ip_address: str,
    ):
        # TODO: Check if this workflow already exists.
        package_path = WorkflowProcessor.download_workflow_package(
            workflow.workflow_link, workflow.workflow_id
        )
        shared_key = ECDHKeyGenerator.get_shared_aes_key(requester_username)
        aes = AES(shared_key)
        del shared_key
        decrypted_zip_bytes = aes.decrypt(package_path.read_bytes())
        # Design Choice: Write the decrypted zip file instead of original
        package_path.write_bytes(decrypted_zip_bytes)
        parent_dir = extract_zip_file(package_path)
        tasks_id = [
            f.name.removeprefix("task_").removesuffix(".json")
            for f in parent_dir.glob("task_*")
            if f.is_file()
        ]
        compute_workflow = ComputeWorkflow(
            requester_username,
            requester_ip_address,
            workflow.workflow_id,
            tasks_id,
            ComputeStatusEnum.RECEIVED,
            None,
        )

        self._db_repo.create_workflow(compute_workflow)
        workflow_json_path = (
            Path(parent_dir) / f"workflow_{workflow.workflow_id}.json"
        )

        workflow_template = WorkflowProcessor.load_workflow_template(
            str(workflow_json_path)
        )

        tasks: Dict[str, Dict[str, Any]] = {}
        for task in Path(parent_dir).rglob("task_*.json"):
            task_payload = TaskProcessor.load_task_json(str(task))
            task_dict = {
                "task": task_payload,
                "json_path": str(task),
                "ip_address": requester_ip_address,
            }
            tasks[str(task_payload.id)] = task_dict
        self._executor.run(self._async_add_workflow(workflow_template, tasks))

    async def _async_add_workflow(self, workflow, tasks):
        scheduler = self._executor.scheduler
        await scheduler.add_workflow(workflow, tasks)
