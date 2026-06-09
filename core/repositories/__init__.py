from __future__ import annotations

import abc
from typing import Any, Dict, List, Optional, Tuple

from core.domain.models import (
    ComputeHeartbeat,
    ComputeNodeCreateRequest,
    File,
    StorageNode,
    TaskCreateRequest,
    UserNode,
)


class IUserRepository(abc.ABC):
    @abc.abstractmethod
    def find_by_username(self, username: str) -> Optional[UserNode]: ...

    @abc.abstractmethod
    def create(self, username: str, password_hash: str) -> None:
        """Raise ConflictError if username already exists."""
        ...

    @abc.abstractmethod
    def update(self, username: str, **fields) -> None: ...

    @abc.abstractmethod
    def increment_seeds(self, username: str, amount: int = 1) -> None: ...


class IStorageRepository(abc.ABC):
    @abc.abstractmethod
    def find_by_username(self, username: str) -> Optional[StorageNode]: ...

    @abc.abstractmethod
    def find_available(self, min_space: int) -> List[StorageNode]:
        """Return active nodes with available_space > min_space."""
        ...

    @abc.abstractmethod
    def create(
        self,
        username: str,
        password_hash: str,
        wallet_address: str,
        available_space: int,
    ) -> None: ...

    @abc.abstractmethod
    def update(self, username: str, **fields) -> None: ...

    @abc.abstractmethod
    def push_active_contract(self, username: str, contract: dict) -> None: ...

    @abc.abstractmethod
    def pull_active_contract(self, username: str, shard_id: str) -> None: ...


class IFileRepository(abc.ABC):
    @abc.abstractmethod
    def find_by_id(self, file_id: str) -> Optional[File]: ...

    @abc.abstractmethod
    def find_pending(self, username: str) -> Optional[File]:
        """The in-progress (not done_uploading) file for this user."""
        ...

    @abc.abstractmethod
    def find_active(self, username: str) -> List[File]:
        """All done_uploading=True files for this user."""
        ...

    @abc.abstractmethod
    def find_all_uploaded(self) -> List[File]: ...

    @abc.abstractmethod
    def find_by_contract_addresses(
        self, addresses: List[str]
    ) -> List[File]: ...

    @abc.abstractmethod
    def create(self, file: File) -> str:
        """Insert and return the new document id."""
        ...

    @abc.abstractmethod
    def update_segments(self, file_id: str, segments: list) -> None: ...

    @abc.abstractmethod
    def mark_paid(self, username: str) -> None: ...

    @abc.abstractmethod
    def mark_done_uploading(self, username: str) -> None: ...

    @abc.abstractmethod
    def update_shard(
        self, file_id: str, segment_no: int, shard_no: int, **fields
    ) -> None: ...

    @abc.abstractmethod
    def decrement_downloads(self, username: str, filename: str) -> None: ...


class ITransactionRepository(abc.ABC):
    @abc.abstractmethod
    def exists(self, transaction_hash: str) -> bool: ...

    @abc.abstractmethod
    def record(self, transaction_hash: str) -> None: ...


class IComputeNodeRepository(abc.ABC):
    @abc.abstractmethod
    def create(self, compute_node_data: ComputeNodeCreateRequest) -> None: ...

    @abc.abstractmethod
    def heartbeat(self, heartbeat: ComputeHeartbeat) -> None: ...
    @abc.abstractmethod
    def get_nodes_ip(self, compute_node_ids: List[str]) -> List[Any]: ...

    # @abc.abstractmethod
    # def update(self) -> None: ...


class IComputeTaskRepository(abc.ABC):
    @abc.abstractmethod
    def create(self, task: TaskCreateRequest, requester_id: str) -> None: ...
    @abc.abstractmethod
    def update(self, task_id: str, **fields) -> None: ...

    @abc.abstractmethod
    def cancel(self, task_id: str) -> None: ...


class IComputeWorkflowRepository(abc.ABC):

    @abc.abstractmethod
    def create(self, tasks_id: List[str], requester_id: str) -> None: ...

    @abc.abstractmethod
    def update(self, workflow_id: str, **fields) -> None: ...

    @abc.abstractmethod
    def cancel(self, workflow_id: str) -> None: ...


class IRedisRepository(abc.ABC):

    async def set_hash(
        self, key: str, fields: dict, ttl_seconds: Optional[int] = None
    ) -> bool: ...

    async def get(self, key: str) -> Optional[Dict]: ...

    async def delete(self, key: str) -> bool: ...

    async def scan_all(self, key_prefix: str) -> List[Tuple[str, Dict]]: ...

    async def queue_push(self, key: str, raw: str) -> bool: ...

    async def queue_pop(
        self, key: str, timeout: int = 10
    ) -> Optional[str | bytes]: ...

    async def queue_length(self, key: str) -> int: ...

    async def queue_clear(self, key: str) -> bool: ...
