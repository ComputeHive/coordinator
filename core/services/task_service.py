from collections import defaultdict
from pathlib import Path
from typing import Dict, Tuple

from core.domain.models import TaskCreateRequest, TaskMetadata, TaskPayload
from core.services.encryption_service import AES
from infrastructure.database.mongo_repositories import (
    MongoComputeTaskRepository,
)
from core.services.keygenerator_service import ECDHKeyGenerator
from script_test import Scheduler
from utils.task_processor import TaskProcessor
import threading


class ComputeTaskService:
    def __init__(
        self, db_repo: MongoComputeTaskRepository, scheduler: Scheduler
    ):
        self._db_repo = db_repo
        self.not_processed_tasks = defaultdict(str)
        self.processed_tasks: Dict[str, Tuple[TaskPayload, Path]] = {}
        self.assigned_tasks = defaultdict(str)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._periodic_task, daemon=True
        )
        self._thread.start()
        self._task_lock = threading.Lock()
        self._scheduler = scheduler

    def create_task(self, task: TaskCreateRequest, requester_username: str):
        self.not_processed_tasks[task.task_id] = task.task_link
        self._db_repo.create(task, requester_username)

    def process_task(self, task_id: str, requester_username: str):
        if not self.not_processed_tasks.get(task_id):
            return False
        package_path = TaskProcessor.download_task_package(
            self.not_processed_tasks[task_id], task_id
        )
        del self.not_processed_tasks[task_id]
        shared_key = ECDHKeyGenerator.get_shared_aes_key(requester_username)
        aes = AES(shared_key)
        del shared_key
        decrypted_zip_bytes = aes.decrypt(package_path.read_bytes())
        # Design Choice: Write the decrypted zip file instead of original
        package_path.write_bytes(decrypted_zip_bytes)
        json_path = package_path / f"task_{task_id}.json"
        task_payload = TaskProcessor.load_task_json(str(json_path))
        self.processed_tasks[task_id] = (task_payload, json_path)

    def _periodic_task(self, interval=3):
        while not self._stop_event.is_set():
            self._stop_event.wait(interval)
            with self._task_lock:
                for (
                    task_payload,
                    task_json_path,
                ) in self.processed_tasks.values():
                    self._scheduler.add_task(task_payload, task_json_path)
