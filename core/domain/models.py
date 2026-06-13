from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

import datetime

from pathlib import Path

from core.domain.enums import (
    ComputeStatusEnum,
    TaskTypeEnum,
    InputSourceTypeEnum,
    WorkflowTypeEnum,
)

# ---------------------------------------------------------------------------
# Shard / Segment
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Shard:
    shard_id: str  # Fernet-encrypted opaque token
    shard_node_username: str
    done_uploading: bool
    shard_lost: bool
    user_node_done: bool
    storage_node_done: bool
    ip_address: str = ""
    port: int = 0
    shared_authentication_key: str = ""
    audits: List[dict] = field(default_factory=list)


@dataclass(frozen=True)
class Segment:
    k: int  # Minimum shards needed for reconstruction
    m: int  # Total shards in segment
    shard_size: int  # Bytes per shard
    regeneration_count: int
    shards: List[Shard] = field(default_factory=list)


# ---------------------------------------------------------------------------
# File
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class File:
    id: str  # MongoDB ObjectId as string
    username: str
    filename: str
    file_size: int
    download_count: int
    duration_in_months: int
    contract_address: str
    price: int  # Wei
    done_uploading: bool
    paid: bool
    segments: List[Segment] = field(default_factory=list)


# ---------------------------------------------------------------------------
# User node
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UserNode:
    username: str
    password_hash: str
    seeds: int
    pending_contract: bool
    pending_contract_paid: bool


# ---------------------------------------------------------------------------
# Storage node
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StorageContract:
    shard_id: str
    contract_address: str
    next_payment_date: datetime.datetime
    payments_count_left: int
    payment_per_interval: float


@dataclass(frozen=True)
class StorageNode:
    username: str
    password_hash: str
    wallet_address: str
    available_space: int
    heartbeats: int
    last_heartbeat: object  # -1 (never), -2 (transition), or datetime
    ip_address: str
    port: str
    is_terminated: bool
    active_contracts: List[StorageContract] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

ETHER_IN_USD = 10_000
STORAGE_PRICE_PER_TERA_USD = 3
DOWNLOAD_PRICE_PER_TERA_USD = 7
KB_PER_TERA = 1_073_741_824
WEI_PER_ETHER = 10**18


def calculate_price(
    download_count: int, duration_in_months: int, file_size_kb: int
) -> int:
    """Return storage + download price in Wei."""
    storage_per_kb = STORAGE_PRICE_PER_TERA_USD / (ETHER_IN_USD * KB_PER_TERA)
    download_per_kb = DOWNLOAD_PRICE_PER_TERA_USD / (
        ETHER_IN_USD * KB_PER_TERA
    )
    price_ether = (
        storage_per_kb * file_size_kb * duration_in_months
        + download_per_kb * file_size_kb * download_count
    )
    return int(price_ether * WEI_PER_ETHER)


########################################
# Tasks
########################################


@dataclass(frozen=True)
class TaskContract:  # TODO: WIP
    pass


@dataclass(frozen=True)
class TaskFinishedRequest:
    task_id: str
    output_link: str


@dataclass(frozen=True)
class TaskCreateRequest:
    task_id: str
    task_link: str
    task_type: TaskTypeEnum


@dataclass(frozen=True)
class TaskSnapShot:
    task_id: str  # mongodb ObjectId
    task_type: TaskTypeEnum
    task_status: ComputeStatusEnum


@dataclass(frozen=True)
class ComputeTask(TaskSnapShot):
    assigned_node_id: str  # ObjectID
    requester_username: str
    task_link: str
    task_contract: TaskContract
    task_output_link: str
    requester_ip_address: str


@dataclass(frozen=True)
class InputItem:
    source: InputSourceTypeEnum
    value: Any
    type: str


@dataclass(frozen=True)
class InputFileMetaData:
    file_name: str
    link: Optional[str] = None
    file_path: Optional[str] = None


@dataclass(frozen=True)
class DecoratorParams:
    ram_mb: int = 256
    disk_mb: int = 512
    cpu_cores: int = 1
    timeout_seconds: int = 30
    max_retries: int = 3
    num_of_partitions: Optional[int] = None
    balanced_partition: bool = False


@dataclass(frozen=True)
class TaskPayload:
    id: UUID
    type: TaskTypeEnum
    name: Optional[str] = None
    resources: DecoratorParams = field(default_factory=DecoratorParams)
    inputs: Optional[Dict[str, InputItem]] = None
    input_files: Optional[List[InputFileMetaData]] = None
    output_schema: Optional[Dict[str, str]] = None
    hash_sha256: Optional[str] = None


#####################################
# Compute Node
#####################################


@dataclass(frozen=True)
class ComputeNodeCreateRequest:
    username: str
    password: str
    wallet_address: str
    ip_address: str
    cpu_model: str
    total_cpu_cores: int
    total_ram_mb: int
    total_disk_mb: int


@dataclass(frozen=True)
class ComputeHeartbeat:
    cpu_load: int
    cpu_cores: int
    available_ram_mb: int
    available_disk_mb: int
    assigned_tasks: list[TaskSnapShot]


@dataclass(frozen=True)
class ComputeNode(ComputeNodeCreateRequest):
    node_id: str
    created_at: datetime.datetime


@dataclass(frozen=True)
class ActiveComputeNode(ComputeHeartbeat):
    node_id: str
    ip_address: str


########################################
# Workflows
########################################


@dataclass(frozen=True)
class WorkflowContract:  # TODO: WIP
    pass


@dataclass(frozen=True)
class ComputeWorkflow:
    requester_username: str
    requester_ip_address: str
    workflow_id: str
    tasks_id: List[str]
    workflow_status: ComputeStatusEnum
    workflow_contract: Optional[WorkflowContract]


@dataclass(frozen=True)
class WorkflowCreateRequest:
    workflow_id: str
    workflow_link: str
    workflow_type: WorkflowTypeEnum


@dataclass(frozen=True)
class TaskParents:
    task_id: str
    task_type: Optional[TaskTypeEnum]
    parents: List[str]


@dataclass(frozen=True)
class WorkflowTemplate:
    workflow_id: str
    workflow_type: WorkflowTypeEnum
    tasks: List[TaskParents]


#############################
# Scheduler
#############################


@dataclass
class TaskState:
    payload: TaskPayload
    ip_address: str
    json_path: Path
    status: ComputeStatusEnum
    assigned_node_id: Optional[str] = None
    pending_deps: Set[str] = field(default_factory=set)
