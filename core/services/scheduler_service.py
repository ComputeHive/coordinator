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

READY_QUEUE = "scheduler:ready_tasks"
COMPLETED_QUEUE = "scheduler:completed_tasks"
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
    FAILURE_CHECK_INTERVAL = 30

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

        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._parents: Dict[str, List[str]] = defaultdict(list)
        self._children: Dict[str, List[str]] = defaultdict(list)
        self._status: Dict[str, ComputeStatusEnum] = {}
        self._assigned_node: Dict[str, str] = {}
        self._pending_deps: Dict[str, Set[str]] = defaultdict(set)
        self._active_nodes: Dict[str, ActiveComputeNode] = {}
        self._nodes_lock = asyncio.Lock()
        self._state_lock = asyncio.Lock()
        self._shutdown_event = asyncio.Event()

    async def async_load_state(self):
        pass

    async def add_task(
        self,
        task: TaskPayload,
        requester_ip_address: str,
        task_json_path: Path,
        parent_ids: Optional[List[str]] = None,
    ):
        tid = str(task.id)
        async with self._state_lock:
            self._tasks[tid] = {
                "task": task,
                "ip_address": requester_ip_address,
                "json_path": task_json_path,
            }
            self._parents[tid] = parent_ids or []
            self._status[tid] = ComputeStatusEnum.RECEIVED
            if not parent_ids:
                self._pending_deps[tid] = set()
                await self._push_ready(tid)
            else:
                for p in parent_ids:
                    self._children[p].append(tid)
                self._pending_deps[tid] = set(parent_ids)

    async def add_workflow(
        self,
        workflow: WorkflowTemplate,
        tasks_meta: Dict[str, Dict[str, Any]],
    ):
        async with self._state_lock:
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

    async def add_to_completed_queue(
        self,
        finished_task: TaskFinishedRequest,
        task_status: ComputeStatusEnum,
    ):
        payload = {
            "task_id": finished_task.task_id,
            "task_status": task_status,
            "task_output_link": finished_task.output_link,
        }

        await self._redis.queue_push(COMPLETED_QUEUE, json.dumps(payload))

    async def run(self):
        nodes = await self._heartbeat.active_nodes
        async with self._nodes_lock:
            self._active_nodes = {n.node_id: n for n in nodes}
        tasks = [
            asyncio.create_task(self._dispatch_ready()),
            asyncio.create_task(self._handle_completions()),
            asyncio.create_task(self._periodic_node_refresh()),
            asyncio.create_task(self._monitor_node_failures()),
        ]
        try:
            await self._shutdown_event.wait()
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def stop(self):
        self._shutdown_event.set()

    async def _dispatch_ready(self):
        while not self._shutdown_event.is_set():
            try:
                raw = self._redis.queue_pop(READY_QUEUE, timeout=1)
                if raw is None:
                    continue
                task_id = raw.decode() if isinstance(raw, bytes) else str(raw)
                await self._schedule_task(task_id)
            except Exception:
                print("Bad ready queue message")

    async def _choose_best_node(self, task: Dict[str, Any]) -> Optional[str]:
        async with self._nodes_lock:
            nodes: List[ActiveComputeNode] = list(self._active_nodes.values())
        best_node_id, best_score = None, float("-inf")
        for node in nodes:
            score = NodeScoreCalculator.node_score(
                task["task"], node, task["ip_address"]
            )
            if score > best_score:
                best_score = score
                best_node_id = node.node_id
        return best_node_id

    async def _schedule_task(self, task_id: str):
        async with self._state_lock:
            task = self._tasks[task_id]
            if not task:
                print("Unknown task %s in ready queue", task_id)
                return
            current_status = self._status[task_id]
            if current_status in (
                ComputeStatusEnum.SCHEDULED,
                ComputeStatusEnum.EXECUTING,
                ComputeStatusEnum.FINISHED,
            ):
                print("Task %s already in progress, skipping", task_id)
                return
            best_node_id = await self._choose_best_node(task)
            if best_node_id is None:
                print("No Suitable node for task %s, re-queuing", task_id)
                # TODO: No Need to Re Add
                await self._push_ready(task_id)
                return
            self._assigned_node[task_id] = best_node_id
            self._status[task_id] = ComputeStatusEnum.SCHEDULED
            # TODO: Remove from Ready Queue
            # TODO: Remove Redis Queues (unnecessary complexity)
        try:
            encrypted_package_link = TaskProcessor.prepare_task_package(
                self._bucket_service,
                task["task"],
                task["json_path"],
                best_node_id,
            )
        except Exception:
            print("Failed to prepare package for task %s", task_id)
            async with self._state_lock:
                # Rollback assignement
                self._assigned_node.pop(task_id)
                self._status[task_id] = ComputeStatusEnum.RECEIVED
                # TODO: Already in Ready Queue
                await self._push_ready(task_id)
            return
        node_queue = NODE_TASK_QUEUE_PREFIX.format(node_id=best_node_id)
        payload = TaskCreateRequest(
            task_id=task_id,
            task_link=encrypted_package_link,
            task_type=task["task"].type,
        )
        await self._redis.queue_push(node_queue, json.dumps(payload))
        print("Task %s assigned to node %s", task_id, best_node_id)

    async def _handle_completions(self):
        while not self._shutdown_event.is_set():
            try:
                raw = await self._redis.queue_pop(COMPLETED_QUEUE, timeout=1)
                if not raw:
                    continue
                payload = json.loads(raw)
                task_id = payload["task_id"]
                task_status = ComputeStatusEnum(payload["task_status"])
            except Exception:
                print("Invalid Completion Message")
                continue
            async with self._state_lock:
                task = self._tasks[task_id]
                if not task:
                    print("Unknown completed task %s", task_id)
                    continue
                self._status[task_id] = task_status
                self._assigned_node.pop(task_id, None)
                if task_status == ComputeStatusEnum.FINISHED:
                    task_type = self._tasks[task_id]["task"].type
                    children = self._children.get(task_id, [])
                    for child_id in children:
                        child_deps = self._pending_deps[child_id]
                        if child_deps and task_id in child_deps:
                            input_files = [
                                InputFileMetaData(
                                    file_name=f"out_{payload["task_id"]}"
                                    f"{EXT[task_type]}",
                                    link=payload["task_output_link"],
                                )
                            ]
                            child_task = self._tasks[child_id]["task"]
                            try:
                                self._tasks[child_id]["task"] = (
                                    TaskProcessor.update_task_payload(
                                        child_task, input_files
                                    )
                                )
                            except Exception as e:
                                print("Failed to update child payload: %s", e)
                            child_deps.discard(task_id)
                            if not child_deps:
                                if self._status[child_id] not in (
                                    ComputeStatusEnum.SCHEDULED,
                                    ComputeStatusEnum.EXECUTING,
                                ):
                                    await self._push_ready(child_id)
                        else:
                            # TODO: Supposed to be ignored
                            pass

    async def _periodic_node_refresh(self):
        while not self._shutdown_event.is_set():
            try:
                nodes = await asyncio.wait_for(
                    self._heartbeat.active_nodes, timeout=self.REFRESH_INTERVAL
                )
                async with self._nodes_lock:
                    self._active_nodes = {n.node_id: n for n in nodes}
            except asyncio.TimeoutError:
                pass
            except Exception:
                print("Failed to refresh active nodes")
            await asyncio.sleep(self.REFRESH_INTERVAL)

    async def _monitor_node_failures(self):
        while not self._shutdown_event.is_set():
            await asyncio.sleep(self.FAILURE_CHECK_INTERVAL)
            try:
                active = await self._heartbeat.active_nodes
                active_ids = {n.node_id for n in active}
            except Exception:
                print("Node Failure check failed, skipping cycle")
                continue
            async with self._state_lock:
                for task_id, node_id in list(self._assigned_node.items()):
                    if node_id not in active_ids:
                        status = self._status[task_id]
                        if status in (
                            ComputeStatusEnum.SCHEDULED,
                            ComputeStatusEnum.EXECUTING,
                        ):
                            self._assigned_node.pop(task_id)
                            self._status[task_id] = ComputeStatusEnum.RECEIVED
                            await self._push_ready(task_id)
                            print(
                                "Node %s dead, rescheduling task %s",
                                node_id,
                                task_id,
                            )

    async def _push_ready(self, task_id: str):
        try:
            await self._redis.queue_push(READY_QUEUE, task_id)
        except Exception:
            print("Failed to push task %s to ready queue", task_id)
