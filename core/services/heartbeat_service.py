from typing import Dict

from core.domain.models import ComputeNode


class HeartbeatService:
    def __init__(self):
        self._active_nodes: Dict[str, ComputeNode] = {}

    @property
    def active_nodes(self):
        return self._active_nodes
