import dataclasses
import json
import os
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote, urlparse

import httpx

from config import BaseConfig
from core.domain.models import (
    DecoratorParams,
    InputFileMetaData,
    InputItem,
    TaskPayload,
)
from core.services.encryption_service import AES
from core.services.keygenerator_service import ECDHKeyGenerator
from core.services.supabase_service import BUCKET_NAME, SupabaseBlobStorage
from utils.lib import zip_directory


class TaskProcessor:
    BASE_DIR = Path(BaseConfig.KEYSTORE_DIR).parent / "downloads"

    @staticmethod
    def load_task_json(json_path: str) -> TaskPayload:
        with open(json_path, "r") as f:
            task_payload_dict: dict = json.loads(f.read())
            task_payload_dict["resources"] = DecoratorParams(
                **task_payload_dict["resources"]
            )
            if task_payload_dict.get("input_files") is not None:
                task_payload_dict["input_files"] = list(
                    map(
                        lambda x: InputFileMetaData(**x),
                        task_payload_dict["input_files"],
                    )
                )
            if task_payload_dict.get("inputs") is not None:
                task_payload_dict["inputs"] = {
                    k: InputItem(**v)
                    for k, v in task_payload_dict["inputs"].items()
                }
            return TaskPayload(**task_payload_dict)

    @staticmethod
    def update_task_payload(
        task: TaskPayload, input_files: Optional[List[InputFileMetaData]]
    ) -> TaskPayload:
        if input_files is None:
            return task
        task_dict = dataclasses.asdict(task)
        if task.inputs:
            task_dict.pop("inputs")
        if task_dict["input_files"] is None:
            task_dict["input_files"] = []
        task_dict["input_files"].extend(input_files)
        return TaskPayload(**task_dict)

    @staticmethod
    def download_task_package(url: str, task_id: str) -> Path:
        os.makedirs(TaskProcessor.BASE_DIR, exist_ok=True)
        file_name = unquote(Path(urlparse(url).path).name)
        file_path = TaskProcessor.BASE_DIR / task_id / file_name
        response = httpx.get(url)
        response.raise_for_status()
        file_path.write_bytes(response.content)
        return file_path

    @staticmethod
    def prepare_task_package(
        bucket_service: SupabaseBlobStorage,
        task_payload_json: TaskPayload,
        task_json_path: Path,
        node_id: str,
    ) -> str:
        task_payload_dict = json.dumps(task_payload_json)
        task_json_path.write_bytes(task_payload_dict.encode())
        parent_dir = task_json_path.parent
        zip_filepath = zip_directory(parent_dir, str(task_payload_json.id))
        zip_file_bytes = zip_filepath.read_bytes()
        shared_key = ECDHKeyGenerator.get_shared_aes_key(node_id)
        aes = AES(shared_key)
        del shared_key
        enc_zip_bytes = aes.encrypt(zip_file_bytes)
        enc_zip_path = Path(str(zip_filepath) + ".enc")
        del aes
        bucket_name = BUCKET_NAME
        bucket_service.upload(bucket_name, enc_zip_path.name, enc_zip_bytes)
        return bucket_service.generate_presigned_url(
            bucket_name, enc_zip_path.name
        )
