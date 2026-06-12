from __future__ import annotations

import dataclasses
import datetime
from typing import List, Optional
from uuid import uuid4

from bson.objectid import ObjectId
from pymongo.database import Database

from core.domain.enums import ComputeStatusEnum
from core.domain.exceptions import DatabaseError
from core.domain.models import (
    ComputeNode,
    ComputeNodeCreateRequest,
    ComputeTask,
    ComputeWorkflow,
    File,
    StorageContract,
    StorageNode,
    TaskCreateRequest,
    UserNode,
)
from core.repositories import (
    IComputeNodeRepository,
    IComputeTaskRepository,
    IComputeWorkflowRepository,
    IFileRepository,
    IStorageRepository,
    ITransactionRepository,
    IUserRepository,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _str_to_oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise DatabaseError(f"Invalid document id: {id_str!r}")


# ---------------------------------------------------------------------------
# User repository
# ---------------------------------------------------------------------------


class MongoUserRepository(IUserRepository):
    def __init__(self, db: Database) -> None:
        self._col = db["user_nodes"]

    def find_by_username(self, username: str) -> Optional[UserNode]:
        doc = self._col.find_one({"username": username})
        if not doc:
            return None
        return UserNode(
            username=doc["username"],
            password_hash=doc["password"],
            seeds=doc.get("seeds", 0),
            pending_contract=doc.get("pending_contract", False),
            pending_contract_paid=doc.get("pending_contract_paid", False),
        )

    def create(self, username: str, password_hash: str) -> None:
        self._col.insert_one(
            {
                "username": username,
                "password": password_hash,
                "seeds": 0,
                "pending_contract": False,
                "pending_contract_paid": False,
            }
        )

    def update(self, username: str, **fields) -> None:
        self._col.update_one({"username": username}, {"$set": fields})

    def increment_seeds(self, username: str, amount: int = 1) -> None:
        self._col.update_one(
            {"username": username}, {"$inc": {"seeds": amount}}
        )


# ---------------------------------------------------------------------------
# Storage repository
# ---------------------------------------------------------------------------


class MongoStorageRepository(IStorageRepository):
    def __init__(self, db: Database) -> None:
        self._col = db["storage_nodes"]

    def find_by_username(self, username: str) -> Optional[StorageNode]:
        doc = self._col.find_one({"username": username})
        return self._from_doc(doc) if doc else None

    def find_available(self, min_space: int) -> List[StorageNode]:
        cursor = self._col.find(
            {
                "available_space": {"$gt": min_space},
                "last_heartbeat": {"$ne": -1},
                "is_terminated": False,
            }
        )
        return [self._from_doc(d) for d in cursor]

    def create(
        self,
        username: str,
        password_hash: str,
        wallet_address: str,
        available_space: int,
    ) -> None:
        self._col.insert_one(
            {
                "username": username,
                "password": password_hash,
                "wallet_address": wallet_address,
                "available_space": available_space,
                "heartbeats": 0,
                "last_heartbeat": -1,
                "ip_address": "155.155.155.155",
                "port": "50000",
                "is_terminated": False,
                "active_contracts": [],
            }
        )

    def update(self, username: str, **fields) -> None:
        self._col.update_one({"username": username}, {"$set": fields})

    def push_active_contract(self, username: str, contract: dict) -> None:
        self._col.update_one(
            {"username": username}, {"$push": {"active_contracts": contract}}
        )

    def pull_active_contract(self, username: str, shard_id: str) -> None:
        self._col.update_one(
            {"username": username},
            {"$pull": {"active_contracts": {"shard_id": shard_id}}},
        )

    @staticmethod
    def _from_doc(doc: dict) -> StorageNode:
        contracts = [
            StorageContract(
                shard_id=c["shard_id"],
                contract_address=c["contract_address"],
                next_payment_date=c["next_payment_date"],
                payments_count_left=c["payments_count_left"],
                payment_per_interval=c["payment_per_interval"],
            )
            for c in doc.get("active_contracts", [])
        ]
        return StorageNode(
            username=doc["username"],
            password_hash=doc["password"],
            wallet_address=doc["wallet_address"],
            available_space=doc["available_space"],
            heartbeats=doc.get("heartbeats", 0),
            last_heartbeat=doc.get("last_heartbeat", -1),
            ip_address=doc.get("ip_address", ""),
            port=doc.get("port", "50000"),
            is_terminated=doc.get("is_terminated", False),
            active_contracts=contracts,
        )


# ---------------------------------------------------------------------------
# File repository
# ---------------------------------------------------------------------------


class MongoFileRepository(IFileRepository):
    def __init__(self, db: Database) -> None:
        self._col = db["files"]

    def find_by_id(self, file_id: str) -> Optional[File]:
        doc = self._col.find_one({"_id": _str_to_oid(file_id)})
        return self._from_doc(doc) if doc else None

    def find_pending(self, username: str) -> Optional[File]:
        doc = self._col.find_one(
            {"username": username, "done_uploading": False}
        )
        return self._from_doc(doc) if doc else None

    def find_active(self, username: str) -> List[File]:
        return [
            self._from_doc(d)
            for d in self._col.find(
                {"username": username, "done_uploading": True}
            )
        ]

    def find_all_uploaded(self) -> List[File]:
        return [
            self._from_doc(d) for d in self._col.find({"done_uploading": True})
        ]

    def find_by_contract_addresses(self, addresses: List[str]) -> List[File]:
        return [
            self._from_doc(d)
            for d in self._col.find({"contract": {"$in": addresses}})
        ]

    def create(self, file: dict) -> str:
        result = self._col.insert_one(file)
        return str(result.inserted_id)

    def update_segments(self, file_id: str, segments: list) -> None:
        self._col.update_one(
            {"_id": _str_to_oid(file_id)}, {"$set": {"segments": segments}}
        )

    def mark_paid(self, username: str) -> None:
        self._col.update_one(
            {"username": username, "done_uploading": False, "paid": False},
            {"$set": {"paid": True}},
        )

    def mark_done_uploading(self, username: str) -> None:
        self._col.update_one(
            {"username": username, "done_uploading": False},
            {"$set": {"done_uploading": True}},
        )

    def update_shard(
        self, file_id: str, segment_no: int, shard_no: int, **fields
    ) -> None:
        set_doc = {
            f"segments.{segment_no}.shards.{shard_no}.{k}": v
            for k, v in fields.items()
        }
        self._col.update_one({"_id": _str_to_oid(file_id)}, {"$set": set_doc})

    def decrement_downloads(self, username: str, filename: str) -> None:
        self._col.update_one(
            {"username": username, "filename": filename},
            {"$inc": {"download_count": -1}},
        )

    @staticmethod
    def _from_doc(doc: dict) -> File:
        return File(
            id=str(doc["_id"]),
            username=doc["username"],
            filename=doc["filename"],
            file_size=doc["file_size"],
            download_count=doc["download_count"],
            duration_in_months=doc["duration_in_months"],
            contract_address=doc["contract"],
            price=doc["price"],
            done_uploading=doc["done_uploading"],
            paid=doc["paid"],
            segments=doc.get("segments", []),
        )


# ---------------------------------------------------------------------------
# Transaction repository
# ---------------------------------------------------------------------------


class MongoTransactionRepository(ITransactionRepository):
    def __init__(self, db: Database) -> None:
        self._col = db["transactions"]

    def exists(self, transaction_hash: str) -> bool:
        return (
            self._col.find_one({"transaction": transaction_hash}) is not None
        )

    def record(self, transaction_hash: str) -> None:
        self._col.insert_one({"transaction": transaction_hash})


#####################################
# Compute Node repository
#####################################


class MongoComputeNodeRepository(IComputeNodeRepository):
    def __init__(self, db: Database):
        self._col = db["compute_nodes"]

    def create(self, compute_node_data: ComputeNodeCreateRequest) -> None:
        compute_node_dict = {
            "node_id": str(uuid4()),
            "created_at": datetime.datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            **dataclasses.asdict(compute_node_data),
        }
        try:
            compute_node = ComputeNode(**compute_node_dict)
            self._col.insert_one(
                MongoComputeNodeRepository.computenode_to_document(
                    compute_node
                )
            )
        except Exception as exc:
            print(exc)

    def get_nodes_ip(self, compute_node_ids: List[str]):
        compute_node_object_ids = list(
            map(lambda x: _str_to_oid(x), compute_node_ids)
        )
        document = self._col.find(
            {"_id": {"$in": compute_node_object_ids}}, {"ip_address": 1}
        )
        if not document:
            raise ValueError("No Nodes with these ips")
        return list(map(lambda x: x["ip_address"], list(document)))

    def find_by_username(self, username) -> Optional[ComputeNode]:
        document = self._col.find_one({"username": username})
        return (
            MongoComputeNodeRepository.document_to_compute_node(document)
            if document
            else None
        )

    def get_node_id_by_username(self, username) -> Optional[str]:
        document = self._col.find_one({"username": username}, {"_id": 1})
        if not document:
            raise ValueError("No node with this username")
        return document["_id"]

    # def update(self) -> None: ...
    @staticmethod
    def computenode_to_document(node: ComputeNode) -> dict:
        document = dataclasses.asdict(node)
        document["_id"] = document.pop("node_id")
        return document

    @staticmethod
    def document_to_compute_node(document: dict) -> ComputeNode:
        document["node_id"] = document.pop("_id")
        return ComputeNode(**document)


class MongoComputeTaskRepository(IComputeTaskRepository):
    def __init__(self, db: Database):
        self._col = db["compute_tasks"]

    def create(
        self,
        task: TaskCreateRequest,
        requester_username: str,
        requester_ip_address: str,
    ) -> None:
        compute_task_dict = {
            **dataclasses.asdict(task),
            "task_status": ComputeStatusEnum.RECEIVED,
            "requester_username": requester_username,
            "requester_ip_address": requester_ip_address,
            "task_contract": None,
            "assigned_node_id": None,
            "task_output_link": None,
        }
        compute_task = ComputeTask(**compute_task_dict)
        self._col.insert_one(
            MongoComputeTaskRepository.computetask_to_doc(compute_task)
        )

    def update(self, task_id: str, **fields) -> None:
        self._col.update_one({"_id": _str_to_oid(task_id)}, {"$set": fields})

    def cancel(self, task_id: str) -> None:
        self._col.update_one(
            {"_id": _str_to_oid(task_id)},
            {"$set": {"task_type": ComputeStatusEnum.CANCELLED}},
        )

    @staticmethod
    def doc_to_computetask(document: dict) -> ComputeTask:
        document["task_id"] = document.pop("_id")
        return ComputeTask(**document)

    @staticmethod
    def computetask_to_doc(compute_task: ComputeTask) -> dict:
        document = dataclasses.asdict(compute_task)
        document["_id"] = document.pop("task_id")
        return document


class MongoComputeWorkflowRepository(IComputeWorkflowRepository):
    def __init__(self, db: Database):
        self._col = db["compute_workflows"]

    def create_workflow(self, compute_workflow: ComputeWorkflow) -> None:
        self._col.insert_one(
            MongoComputeWorkflowRepository.computeworkflow_to_doc(
                compute_workflow
            )
        )

    def update(self, workflow_id: str, **fields) -> None:
        self._col.update_one(
            {"_id": _str_to_oid(workflow_id)}, {"$set": fields}
        )

    def cancel(self, workflow_id: str) -> None:
        self._col.update_one(
            {"_id": _str_to_oid(workflow_id)},
            {"$set": {"workflow_status": ComputeStatusEnum.CANCELLED}},
        )

    @staticmethod
    def doc_to_computeworkflow(document: dict) -> ComputeWorkflow:
        document["workflow_id"] = document.pop("_id")
        return ComputeWorkflow(**document)

    @staticmethod
    def computeworkflow_to_doc(compute_workflow: ComputeWorkflow) -> dict:
        document = dataclasses.asdict(compute_workflow)
        document["_id"] = document.pop("workflow_id")
        return document
