from pathlib import Path
import threading
from typing import Any, Dict, Tuple

from core.domain.enums import ComputeStatusEnum
from core.domain.models import ComputeWorkflow, WorkflowCreateRequest
from core.repositories import IComputeWorkflowRepository
from core.services.encryption_service import AES
from core.services.keygenerator_service import ECDHKeyGenerator
from script_test import Scheduler
from utils.lib import extract_zip_file
from utils.task_processor import TaskProcessor
from utils.workflow_processor import WorkflowProcessor


class WorkflowService:
    def __init__(
        self, db_repo: IComputeWorkflowRepository, scheduler: Scheduler
    ):
        self._db_repo = db_repo
        self._workflows: Dict[str, Tuple[str, str]] = {}
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._periodic_add_workflow_to_scheduler, daemon=True
        )
        self._workflow_lock = threading.Lock()
        self._scheduler = scheduler
        self._thread.start()

    def create_workflow(
        self,
        workflow: WorkflowCreateRequest,
        requester_username: str,
        requester_ip_address: str,
    ):
        # TODO: Check if this workflow already exists.
        # TODO: Edit the IP Address Point inside the Scheduler and Endpoint
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

        self._workflows[workflow.workflow_id] = (
            str(parent_dir),
            requester_ip_address,
        )

        self._db_repo.create_workflow(compute_workflow)

    def _periodic_add_workflow_to_scheduler(self, interval=3):
        while not self._stop_event.is_set():
            self._stop_event.wait(interval)
            with self._workflow_lock:
                pending_workflows = self._workflows.copy()
                self._workflows.clear()
                for workflow_id, (
                    parent_dir,
                    requester_ip_address,
                ) in pending_workflows.items():
                    workflow_json_path = (
                        Path(parent_dir) / f"workflow_{workflow_id}.json"
                    )

                    workflow_template = (
                        WorkflowProcessor.load_workflow_template(
                            str(workflow_json_path)
                        )
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
                    self._scheduler.add_workflow(workflow_template, tasks)
