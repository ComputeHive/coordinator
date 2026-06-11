from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class IBlobStorage(ABC):

    @abstractmethod
    def create_bucket(
        self, bucket_name: str, options: Optional[Dict[str, Any]] = None
    ) -> Any:
        pass

    @abstractmethod
    def upload(
        self,
        bucket_name: str,
        object_name: str,
        data: bytes,
        options: Optional[Dict[str, Any]] = None,
    ) -> Any:
        pass

    @abstractmethod
    def download(self, bucket_name: str, object_name: str) -> bytes:
        pass

    @abstractmethod
    def delete_object(self, bucket_name: str, object_name: str) -> Any:
        pass

    @abstractmethod
    def generate_presigned_url(
        self, bucket_name: str, object_name: str, expires_in: int = 3600
    ) -> str:
        pass

    # @abstractmethod
    # def put_bucket_cors(
    #     self, bucket_name: str, cors_configuration: Dict[str, Any]
    # ) -> Any:
    #     pass
