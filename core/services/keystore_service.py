import os
from pathlib import Path

from config import BaseConfig
from hashlib import sha256

BASE_DIR = BaseConfig.KEYSTORE_DIR


class KeystoreService:

    @staticmethod
    def _final_file_path(key: str, key_type: str) -> Path:
        sha = sha256()
        sha.update(key.encode("utf-8"))
        os.makedirs(BASE_DIR, exist_ok=True)
        file_name = Path(BASE_DIR) / f"{sha.hexdigest()}_{key_type}-key.txt"
        return file_name

    @staticmethod
    def has_key(node_id: str, key_type: str) -> bool:
        file_name = KeystoreService._final_file_path(node_id, key_type)
        return os.path.exists(file_name) and os.path.getsize(file_name) > 0

    @staticmethod
    def save_key(node_id: str, key_bytes: bytes, key_type: str):
        file_name = KeystoreService._final_file_path(node_id, key_type)
        with open(file_name, "wb") as f:
            f.write(key_bytes)

    @staticmethod
    def load_key(node_id: str, key_type: str) -> bytes:
        file_name = KeystoreService._final_file_path(node_id, key_type)
        key_bytes = None
        with open(file_name, "rb") as f:
            key_bytes = f.read()
        return key_bytes
