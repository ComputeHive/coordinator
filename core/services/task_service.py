from pathlib import Path

from core.domain.enums import ComputeStatusEnum
from core.domain.models import (
    TaskCreateRequest,
    TaskFinishedRequest,
    TaskPayload,
)
from core.services.encryption_service import AES
from infrastructure.async_executor import AsyncExecutor
from infrastructure.database.mongo_repositories import (
    MongoComputeTaskRepository,
)
from core.services.keygenerator_service import ECDHKeyGenerator
from utils.lib import extract_zip_file
from utils.task_processor import TaskProcessor


class ComputeTaskService:
    def __init__(
        self, db_repo: MongoComputeTaskRepository, executor: AsyncExecutor
    ):
        self._db_repo = db_repo
        self._executor = executor

    async def _async_add_task(
        self,
        task_payload: TaskPayload,
        requester_ip_address: str,
        json_path: Path,
    ):
        scheduler = self._executor.scheduler
        await scheduler.add_task(task_payload, requester_ip_address, json_path)

    async def _assign_task_finished(self, finished_task: TaskFinishedRequest):
        task_status = ComputeStatusEnum.FINISHED
        self._db_repo.update(
            finished_task.task_id,
            fields={
                "task_output_link": finished_task.output_link,
                "task_status": task_status,
            },
        )
        await self._executor.scheduler.on_task_finished(
            finished_task, task_status
        )

    def create_task(
        self,
        task: TaskCreateRequest,
        requester_username: str,
        requester_ip_address: str,
    ):
        self._db_repo.create(task, requester_username, requester_ip_address)
        package_path = TaskProcessor.download_task_package(
            task.task_link, task.task_id
        )
        shared_key = ECDHKeyGenerator.get_shared_aes_key(requester_username)
        aes = AES(shared_key)
        del shared_key
        decrypted_zip_bytes = aes.decrypt(package_path.read_bytes())
        # Design Choice: Write the decrypted zip file instead of original
        package_path.write_bytes(decrypted_zip_bytes)
        parent_dir = extract_zip_file(package_path)
        json_path = parent_dir / f"task_{task.task_id}.json"
        task_payload = TaskProcessor.load_task_json(str(json_path))
        self._executor.run(
            self._async_add_task(task_payload, requester_ip_address, json_path)
        )

    def assign_task_finished(self, finished_task: TaskFinishedRequest):
        self._executor.run(self._assign_task_finished(finished_task))
