from typing import BinaryIO, Optional, Union, Dict, Any
from core.services.Iblob_service import IBlobStorage
from supabase import Client


class SupabaseBlobStorage(IBlobStorage):

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    def create_bucket(
        self,
        bucket_id: str,
        bucket_name: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> Any:
        return self.client.storage.create_bucket(
            id=bucket_id, name=bucket_name, options=options
        )

    def upload(
        self,
        bucket_name: str,
        object_name: str,
        data: bytes,
        options: Optional[Dict[str, Any]] = None,
    ) -> Any:
        return self.client.storage.from_(bucket_name).upload(
            path=object_name, file=data, file_options=options
        )

    def download(self, bucket_name: str, object_name: str) -> bytes:
        return self.client.storage.from_(bucket_name).download(object_name)

    def delete_object(self, bucket_name: str, object_name: str) -> Any:
        return self.client.storage.from_(bucket_name).remove([object_name])

    def generate_presigned_url(
        self, bucket_name: str, object_name: str, expires_in: int = 3600
    ) -> str:
        response = self.client.storage.from_(bucket_name).create_signed_url(
            path=object_name, expires_in=expires_in
        )

        if isinstance(response, dict):
            return response.get("signedUrl", response.get("signedURL", ""))
        return str(response)
