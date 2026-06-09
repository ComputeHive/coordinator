from pathlib import Path

from config import BaseConfig
from hashlib import sha256

BASE_DIR = BaseConfig.KEYSTORE_DIR


class KeystoreService:

    @staticmethod
    def _final_file_path(key: str) -> Path:
        sha = sha256()
        sha.update(key.encode("utf-8"))
        file_name = Path(BASE_DIR) / f"{sha.hexdigest()}.txt"
        return file_name

    @staticmethod
    def save_key(node_id: str, key_bytes: bytes):
        file_name = KeystoreService._final_file_path(node_id)
        with open(file_name, "wb") as f:
            f.write(key_bytes)

    @staticmethod
    def load_key(node_id: str):
        file_name = KeystoreService._final_file_path(node_id)
        key_bytes = None
        with open(file_name, "rb") as f:
            key_bytes = f.read()
        return key_bytes
