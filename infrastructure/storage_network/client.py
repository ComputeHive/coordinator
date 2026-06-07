from __future__ import annotations

import json
import random
import socket
import string
import logging

logger = logging.getLogger(__name__)

_SOCKET_TIMEOUT_SECONDS = 2
_RECV_BUFFER = 1024


class StorageNetworkClient:
    """Handles upload-slot requests, download-slot requests, and audit probes."""

    def request_upload_slot(
        self, node, shard_id: str, auth_key: str, shard_size: int
    ) -> int:
        """Ask a storage node to open an upload port. Returns port or 0 on failure."""
        return self._negotiate(
            ip=node.ip_address,
            port=int(node.port),
            payload={
                "type": "upload",
                "port": 0,
                "shard_id": shard_id,
                "auth": auth_key,
                "size": shard_size,
            },
        )

    def request_download_slot(
        self,
        ip_address: str,
        cera_port: int,
        shard_id: str,
        shard_size: int,
        auth_key: str,
    ) -> int:
        """Ask a storage node to open a download port. Returns port or 0 on failure."""
        return self._negotiate(
            ip=ip_address,
            port=cera_port,
            payload={
                "type": "download",
                "port": 0,
                "shard_id": shard_id,
                "auth": auth_key,
                "size": shard_size,
            },
        )

    def send_audit(self, shard: dict, ip_address: str, port: int) -> bool:
        """Send a random audit challenge. Returns True if the response matches."""
        audits = shard.get("audits", [])
        if not audits:
            return False

        audit = random.choice(audits)
        payload = {"type": "audit", "salt": audit["salt"], "shard_id": shard["shard_id"]}

        try:
            with socket.socket() as sock:
                sock.settimeout(_SOCKET_TIMEOUT_SECONDS)
                sock.connect((ip_address, port))
                sock.sendall(json.dumps(payload).encode())
                result = sock.recv(_RECV_BUFFER).decode()
            return result == audit["hash"]
        except socket.error as exc:
            logger.debug("Audit socket error (%s:%s): %s", ip_address, port, exc)
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _negotiate(ip: str, port: int, payload: dict) -> int:
        """Open TCP connection, send JSON payload, return port number or 0."""
        try:
            with socket.socket() as sock:
                sock.settimeout(_SOCKET_TIMEOUT_SECONDS)
                sock.connect((ip, port))
                sock.sendall(json.dumps(payload).encode())
                response = sock.recv(_RECV_BUFFER).decode()
            return int(response)
        except (socket.error, ValueError) as exc:
            logger.debug("Storage node unreachable (%s:%s): %s", ip, port, exc)
            return 0
