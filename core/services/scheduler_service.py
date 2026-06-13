import asyncio
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from core.domain.models import (
    ActiveComputeNode,
    ComputeStatusEnum,
    InputFileMetaData,
    TaskCreateRequest,
    TaskFinishedRequest,
    TaskPayload,
    TaskState,
    WorkflowTemplate,
)
from core.repositories import (
    IComputeTaskRepository,
    IComputeWorkflowRepository,
    IRedisRepository,
)
from core.services.heartbeat_service import HeartbeatService
from core.services.supabase_service import SupabaseBlobStorage
from utils.lib import NodeScoreCalculator
from utils.task_processor import TaskProcessor
from core.domain.enums import TaskTypeEnum

NODE_TASK_QUEUE_PREFIX = "node:{node_id}:tasks"

EXT = {
    TaskTypeEnum.MAP: ".tsv",
    TaskTypeEnum.SHUFFLE_SORT: ".tsv",
    TaskTypeEnum.FUNCTION_WITH_FILES: ".csv",
    TaskTypeEnum.FUNCTION_WITH_INPUT: ".txt",
    TaskTypeEnum.REDUCE: ".csv",
}


class Scheduler:
    REFRESH_INTERVAL = 15

    def __init__(
        self,
        heartbeat_service: HeartbeatService,
        cache_repo: IRedisRepository,
        bucket_service: SupabaseBlobStorage,
        workflow_db_repo: IComputeWorkflowRepository,
        task_db_repo: IComputeTaskRepository,
    ):
        self._heartbeat = heartbeat_service
        self._redis = cache_repo
        self._bucket_service = bucket_service
        self._workflow_repo = workflow_db_repo
        self._task_repo = task_db_repo

        self._tasks: Dict[str, TaskState] = {}
        self._children: Dict[str, List[str]] = defaultdict(list)
        self._ready_tasks: Set[str] = set()
        self._active_nodes: Dict[str, ActiveComputeNode] = {}
        self._lock = asyncio.Lock()
        self._shutdown_event = asyncio.Event()

    async def async_load_state(self):
        docs = self._task_repo.find_incomplete()
        for doc in docs:
            tid = doc["task_id"]
            task_payload = TaskProcessor.load_task_json(doc["json_path"])
            pending = set(doc.get("pending_deps", []))
            state = TaskState(
                payload=task_payload,
                ip_address=doc["requester_ip_address"],
                json_path=Path(doc["json_path"]),
                status=ComputeStatusEnum(doc["task_status"]),
                assigned_node_id=doc.get("assigned_node_id"),
                pending_deps=pending,
            )
            self._tasks[tid] = state
            for parent_id in pending:
                self._children[parent_id].append(tid)
            if self._tasks[tid].status in (
                ComputeStatusEnum.SCHEDULED,
                ComputeStatusEnum.EXECUTING,
            ):
                self._tasks[tid].status = ComputeStatusEnum.RECEIVED
                self.assigned_node_id = None
                self._ready_tasks.add(tid)
            elif self._tasks[tid].status in ComputeStatusEnum.RECEIVED:
                self._ready_tasks.add(tid)

    async def add_task(
        self,
        task: TaskPayload,
        requester_ip_address: str,
        task_json_path: Path,
        parent_ids: Optional[List[str]] = None,
    ):
        tid = str(task.id)
        async with self._lock:
            self._tasks[tid] = TaskState(
                payload=task,
                ip_address=requester_ip_address,
                json_path=task_json_path,
                status=ComputeStatusEnum.RECEIVED,
                assigned_node_id=None,
                pending_deps=set(parent_ids or []),
            )
            self._persist_task(tid)
            if not parent_ids:
                self._ready_tasks.add(tid)
                asyncio.create_task(self._schedule_task(tid))
            else:
                for p in parent_ids:
                    self._children[p].append(tid)

    async def add_workflow(
        self,
        workflow: WorkflowTemplate,
        tasks_meta: Dict[str, Dict[str, Any]],
    ):
        for task_relation in workflow.tasks:
            tid = task_relation.task_id
            if tid not in tasks_meta:
                raise ValueError(f"Missing metadata for task {tid}")
            await self.add_task(
                tasks_meta[tid]["task"],
                tasks_meta[tid]["ip_address"],
                tasks_meta[tid]["json_path"],
                task_relation.parents,
            )

    async def on_task_finished(
        self,
        finished_task: TaskFinishedRequest,
        task_status: ComputeStatusEnum,
    ):
        await self._process_completion(
            finished_task.task_id, task_status, finished_task.output_link
        )

    async def run(self):
        nodes = await self._heartbeat.active_nodes
        async with self._lock:
            self._active_nodes = {n.node_id: n for n in nodes}
        for tid in list(self._ready_tasks):
            asyncio.create_task(self._schedule_task(tid))
        tasks = [
            asyncio.create_task(self._periodic_node_refresh()),
        ]
        try:
            await self._shutdown_event.wait()
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def stop(self):
        self._shutdown_event.set()

    def _choose_best_node(self, task: TaskState) -> Optional[str]:
        nodes: List[ActiveComputeNode] = list(self._active_nodes.values())
        best_node_id, best_score = None, float("-inf")
        for node in nodes:
            score = NodeScoreCalculator.node_score(
                task.payload, node, task.ip_address
            )
            if score > best_score:
                best_score = score
                best_node_id = node.node_id
        return best_node_id

    async def _schedule_task(self, task_id: str):
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.status in (
                ComputeStatusEnum.SCHEDULED,
                ComputeStatusEnum.EXECUTING,
                ComputeStatusEnum.FINISHED,
            ):
                return

            best_node_id = self._choose_best_node(task)
            if best_node_id is None:
                print(
                    "No Suitable node for task %s, retrying next node refresh",
                    task_id,
                )
                return
            task.assigned_node_id = best_node_id
            task.status = ComputeStatusEnum.SCHEDULED
            self._ready_tasks.discard(task_id)
            self._persist_task(task_id)
        try:
            encrypted_package_link = TaskProcessor.prepare_task_package(
                self._bucket_service,
                task.payload,
                task.json_path,
                best_node_id,
            )
        except Exception:
            print("Failed to prepare package for task %s", task_id)
            async with self._lock:
                # Rollback assignement
                task.assigned_node_id = None
                task.status = ComputeStatusEnum.RECEIVED
                self._ready_tasks.add(task_id)
                self._persist_task(task_id)
                asyncio.create_task(self._schedule_task(task_id))
            return
        node_queue = NODE_TASK_QUEUE_PREFIX.format(node_id=best_node_id)
        payload = TaskCreateRequest(
            task_id=task_id,
            task_link=encrypted_package_link,
            task_type=task.payload.type,
        )
        await self._redis.queue_push(node_queue, json.dumps(payload))
        print("Task %s assigned to node %s", task_id, best_node_id)

    async def _process_completion(
        self,
        task_id: str,
        task_status: ComputeStatusEnum,
        output_link: Optional[str],
    ):
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            task.status = task_status
            task.assigned_node_id = None
            if task_status == ComputeStatusEnum.FINISHED:
                task_type = task.payload.type
                for child_id in self._children.get(task_id, []):
                    child = self._tasks.get(child_id)
                    if child and task_id in child.pending_deps:
                        input_files = [
                            InputFileMetaData(
                                file_name=f"out_{task_id}{EXT[task_type]}",
                                link=output_link,
                            )
                        ]
                        child.payload = TaskProcessor.update_task_payload(
                            child.payload, input_files
                        )
                        child.pending_deps.discard(task_id)
                        self._persist_task(child_id)
                        if not child.pending_deps:
                            self._ready_tasks.add(child_id)
                            asyncio.create_task(self._schedule_task(child_id))

    async def _periodic_node_refresh(self):
        while not self._shutdown_event.is_set():
            try:
                nodes = await asyncio.wait_for(
                    self._heartbeat.active_nodes, timeout=self.REFRESH_INTERVAL
                )
                async with self._lock:
                    self._active_nodes = {n.node_id: n for n in nodes}
                    active_ids = set(self._active_nodes.keys())
                    for tid, task in self._tasks.items():
                        if (
                            task.assigned_node_id
                            and task.assigned_node_id not in active_ids
                            and task.status
                            in (
                                ComputeStatusEnum.SCHEDULED,
                                ComputeStatusEnum.EXECUTING,
                            )
                        ):
                            task.assigned_node_id = None
                            task.status = ComputeStatusEnum.RECEIVED
                            self._ready_tasks.add(tid)
                            self._persist_task(tid)
            except asyncio.TimeoutError:
                pass
            except Exception:
                print("Failed to refresh active nodes")
            async with self._lock:
                for tid in list(self._ready_tasks):
                    asyncio.create_task(self._schedule_task(tid))
            await asyncio.sleep(self.REFRESH_INTERVAL)

    def _persist_task(self, task_id: str):
        task = self._tasks[task_id]
        self._task_repo.update(
            task_id,
            task_status=task.status,
            assigned_node_id=task.assigned_node_id,
            pending_deps=list(task.pending_deps),
            json_path=str(task.json_path),
        )
