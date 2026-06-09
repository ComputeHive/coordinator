import dataclasses

from core.domain.models import ComputeHeartbeat
from core.repositories import IComputeNodeRepository, IRedisRepository


class HeartbeatService:
    HEARTBEAT_PERIOD = 30
    HEARTBEAT_TTL = 2.5 * HEARTBEAT_PERIOD
    NODE_KEY_PREFIX = "node:"

    def __init__(
        self, cache_repo: IRedisRepository, db_repo: IComputeNodeRepository
    ):
        self._cache_repo = cache_repo
        self._db_repo = db_repo

    @property
    async def active_nodes(self):
        nodes = await self._cache_repo.scan_all(self.NODE_KEY_PREFIX)
        if nodes is None:
            return []
        node_ids = list(map(lambda x: x[0], nodes))
        # TODO: Add function to update the assigned tasks
        ips = self._db_repo.get_nodes_ip(node_ids)
        # if len(ips) != len(node_ids):
        #     raise RuntimeError(f"")
        for entry, ip in zip(nodes, ips):
            entry[1]["ip_address"] = ip
        return nodes

    async def add_alive_node(self, node_status: ComputeHeartbeat):
        node_status_dict = dataclasses.asdict(node_status)
        node_id = node_status_dict.pop("node_id")
        added = await self._cache_repo.set_hash(
            str(self.NODE_KEY_PREFIX + node_id), node_status_dict
        )
        if not added:
            raise RuntimeError(
                f"Cannot add node {node_id} to the active nodes list"
            )
