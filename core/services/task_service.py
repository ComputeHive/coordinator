from pathlib import Path
from typing import Dict, Tuple

from core.domain.enums import ComputeStatusEnum
from core.domain.models import (
    TaskCreateRequest,
    TaskFinishedRequest,
    TaskPayload,
)
from core.services.encryption_service import AES
from infrastructure.database.mongo_repositories import (
    MongoComputeTaskRepository,
)
from core.services.keygenerator_service import ECDHKeyGenerator
from script_test import Scheduler
from utils.lib import extract_zip_file
from utils.task_processor import TaskProcessor
import threading


class ComputeTaskService:
    def __init__(
        self, db_repo: MongoComputeTaskRepository, scheduler: Scheduler
    ):
        self._db_repo = db_repo
        self._scheduler = scheduler
        self.not_processed_tasks: Dict[str, Tuple[str, str]] = {}
        self.processed_tasks: Dict[str, Tuple[TaskPayload, str, Path]] = {}
        # self.assigned_tasks = defaultdict(str)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._periodic_add_task_to_scheduler, daemon=True
        )
        self._task_lock = threading.Lock()
        self._thread.start()

    def create_task(
        self,
        task: TaskCreateRequest,
        requester_username: str,
        requester_ip_address: str,
    ):
        self.not_processed_tasks[task.task_id] = (
            task.task_link,
            requester_ip_address,
        )
        self._db_repo.create(task, requester_username, requester_ip_address)

    def process_task(self, task_id: str, requester_username: str):
        if not self.not_processed_tasks.get(task_id):
            return False
        package_path = TaskProcessor.download_task_package(
            self.not_processed_tasks[task_id][0], task_id
        )
        requester_ip_address = self.not_processed_tasks[task_id][1]
        shared_key = ECDHKeyGenerator.get_shared_aes_key(requester_username)
        aes = AES(shared_key)
        del shared_key
        decrypted_zip_bytes = aes.decrypt(package_path.read_bytes())
        # Design Choice: Write the decrypted zip file instead of original
        package_path.write_bytes(decrypted_zip_bytes)
        parent_dir = extract_zip_file(package_path)
        json_path = parent_dir / f"task_{task_id}.json"
        task_payload = TaskProcessor.load_task_json(str(json_path))
        self.processed_tasks[task_id] = (
            task_payload,
            requester_ip_address,
            json_path,
        )

    def _periodic_add_task_to_scheduler(self, interval=3):
        while not self._stop_event.is_set():
            self._stop_event.wait(interval)
            with self._task_lock:
                pending_tasks = self.processed_tasks.copy()
                self.processed_tasks.clear()
                for (
                    task_payload,
                    ip_address,
                    task_json_path,
                ) in pending_tasks.values():
                    self._scheduler.add_task(
                        task_payload, ip_address, task_json_path
                    )

    async def assign_task_finished(self, finished_task: TaskFinishedRequest):
        task_status = ComputeStatusEnum.FINISHED
        self._db_repo.update(
            finished_task.task_id,
            fields={
                "task_output_link": finished_task.output_link,
                "task_status": task_status,
            },
        )
        await self._scheduler.add_to_completed_queue(
            finished_task, task_status
        )
