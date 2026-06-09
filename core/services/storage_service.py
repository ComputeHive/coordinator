from __future__ import annotations

import datetime
import math
import random
import socket
import json
from typing import List, Optional, Tuple

from core.domain.exceptions import (
    AuthenticationError,
    AuditFailedError,
    ConflictError,
    DatabaseError,
    NotFoundError,
    PaymentError,
    StorageUnavailableError,
    TerminatedError,
    ValidationError,
)
from core.domain.models import StorageNode
from core.repositories import IFileRepository, IStorageRepository
from core.services.auth_service import AuthService


# ------------------------------------------------------------------
# Configuration constants  (mirrors utils/configuration.py)
# ------------------------------------------------------------------

INTERHEARTBEAT_MINUTES = 10
CERA_EPOCH = datetime.datetime(2026, 1, 1)
RESETTING_MONTHS = 2
MINIMUM_AVAILABILITY_THRESHOLD = 70
MINIMUM_REGENERATION_THRESHOLD = 0
STORAGE_NODE_SHARE = 0.75
FULL_PAYMENT_THRESHOLD = 0.95


class StorageService:
    def __init__(
        self,
        storage_repo: IStorageRepository,
        file_repo: IFileRepository,
        auth_service: AuthService,
        blockchain,          # IBlockchainClient
        network,             # IStorageNetworkClient
        fernet,
        regeneration,        # callable(file_id, seg_no)
    ) -> None:
        self._storage = storage_repo
        self._files = file_repo
        self._auth = auth_service
        self._blockchain = blockchain
        self._network = network
        self._fernet = fernet
        self._regeneration = regeneration

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def register(
        self,
        username: str,
        password: str,
        wallet_address: str,
        available_space: int,
    ) -> None:
        if not all([username, password, wallet_address, available_space]):
            raise ValidationError("All fields are required.")
        if self._storage.find_by_username(username):
            raise ConflictError("Username already exists.")
        hashed = self._auth.hash_password(password)
        self._storage.create(username, hashed, wallet_address, available_space)

    def authenticate(self, username: str, password: str) -> str:
        node = self._storage.find_by_username(username)
        if not node or not self._auth.verify_password(password, node.password_hash):
            raise AuthenticationError("Wrong username or password.")
        return self._auth.issue_token(username)

    def verify_active(self, username: str) -> bool:
        """Return True only if the node exists and is not terminated."""
        node = self._storage.find_by_username(username)
        return node is not None and not node.is_terminated

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    def heartbeat(self, username: str) -> None:
        node = self._storage.find_by_username(username)
        if not node:
            raise NotFoundError("Storage node not found.")

        now = datetime.datetime.utcnow()
        years_since_epoch = now.year - CERA_EPOCH.year
        months_since_epoch = now.month - CERA_EPOCH.month
        last_interval_start = _last_interval_start(now, years_since_epoch, months_since_epoch)
        next_interval_start = _next_interval_start(now, years_since_epoch, months_since_epoch)

        new_last_heartbeat = _quantised_heartbeat(now)
        if new_last_heartbeat >= next_interval_start:
            new_last_heartbeat = -2

        lhb = node.last_heartbeat
        if lhb == -1:
            heartbeats = math.ceil(
                (now - last_interval_start) / datetime.timedelta(minutes=INTERHEARTBEAT_MINUTES)
            )
        elif lhb == -2 or (isinstance(lhb, datetime.datetime) and lhb < last_interval_start):
            heartbeats = 1
        elif isinstance(lhb, datetime.datetime) and lhb < now:
            heartbeats = node.heartbeats + 1
        else:
            raise ValidationError("Heartbeat already recorded for this interval.")

        self._run_random_checks()
        self._storage.update(username, last_heartbeat=new_last_heartbeat, heartbeats=heartbeats)

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    def get_availability(self, username: str) -> float:
        node = self._storage.find_by_username(username)
        if not node:
            raise NotFoundError("Storage node not found.")
        return _compute_availability(node)

    # ------------------------------------------------------------------
    # Active contracts
    # ------------------------------------------------------------------

    def get_active_contracts(self, username: str) -> List[str]:
        node = self._storage.find_by_username(username)
        if not node:
            raise NotFoundError("Storage node not found.")
        return [c.shard_id for c in node.active_contracts]

    def get_storage_info(self, username: str) -> Tuple[float, List[dict]]:
        node = self._storage.find_by_username(username)
        if not node:
            raise NotFoundError("Storage node not found.")
        availability = _compute_availability(node)
        info = [
            {
                "shard_id": c.shard_id,
                "next_payment_date": c.next_payment_date,
                "payment_left": availability * c.payment_per_interval * c.payments_count_left / 100,
                "payment_per_interval": c.payment_per_interval,
            }
            for c in node.active_contracts
        ]
        return availability, info

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def update_connection(self, username: str, ip_address: str, port: str) -> None:
        self._storage.update(username, ip_address=ip_address, port=port)

    # ------------------------------------------------------------------
    # Shard upload acknowledgement
    # ------------------------------------------------------------------

    def shard_done_uploading(self, shard_id_enc: str) -> None:
        # print("Shard done uploading: ", shard_id_enc)
        # encrypted = self._fernet.encrypt(b"file123$DCNTRG$0$DCNTRG$1").decode()
        # print("Encrypted: ", encrypted)

        raw = self._fernet.decrypt(shard_id_enc.encode()).decode()
        parts = raw.split("$DCNTRG$")
        file_id, seg_no, shard_no = parts[0], int(parts[1]), int(parts[2])

        file = self._files.find_by_id(file_id)
        if not file:
            raise NotFoundError("File not found.")

        shard = file.segments[seg_no]["shards"][shard_no]
        if shard["shard_id"] != shard_id_enc:
            raise DatabaseError("Shard ID mismatch.")

        updates = {"storage_node_done": True, "done_uploading": True}
        self._files.update_shard(file_id, seg_no, shard_no, **updates)

        # Add storage node wallet address to on-chain contract
        try:
            node = self._storage.find_by_username(shard["shard_node_username"])
            contract = self._blockchain.get_contract(file.contract_address)
            self._blockchain.add_node(contract, node.wallet_address)
        except Exception:
            pass  # Non-fatal; logged separately

    # ------------------------------------------------------------------
    # Withdraw
    # ------------------------------------------------------------------

    def withdraw(self, username: str, shard_id_enc: str) -> None:
        node = self._storage.find_by_username(username)
        if not node or node.is_terminated:
            raise NotFoundError("Storage node not found or terminated.")

        if self._should_terminate(node):
            raise TerminatedError("Storage node terminated due to low availability.")

        availability = _compute_availability(node)
        if availability >= FULL_PAYMENT_THRESHOLD * 100:
            availability = 100.0

        contract_info = next(
            (c for c in node.active_contracts if c.shard_id == shard_id_enc), None
        )
        if not contract_info:
            raise NotFoundError("No contract found for this shard.")

        now = datetime.datetime.utcnow()
        next_payment_date = contract_info.next_payment_date
        payments_left = contract_info.payments_count_left
        payment = 0.0
        withdrawn = False

        while next_payment_date < now and payments_left > 0:
            payment += availability * contract_info.payment_per_interval / 100
            payments_left -= 1
            next_payment_date += datetime.timedelta(minutes=5)
            withdrawn = True

        if not withdrawn:
            raise PaymentError("No payment is available yet.")

        # Verify audit before paying
        raw = self._fernet.decrypt(shard_id_enc.encode()).decode()
        parts = raw.split("$DCNTRG$")
        file = self._files.find_by_id(parts[0])
        if not file:
            raise NotFoundError("Associated file not found.")

        shard = file.segments[int(parts[1])]["shards"][int(parts[2])]
        audit_ok = self._network.send_audit(shard, node.ip_address, int(node.port))
        if not audit_ok:
            self._terminate_node(node)
            raise AuditFailedError("Audit failed. Node terminated.")

        contract = self._blockchain.get_contract(contract_info.contract_address)
        in_contract = self._blockchain.node_in_contract(contract, node.wallet_address)

        if availability > MINIMUM_AVAILABILITY_THRESHOLD and in_contract:
            self._blockchain.pay_storage_node(contract, node.wallet_address, payment)
            updated_contracts = [
                {
                    **vars(c),
                    "next_payment_date": next_payment_date,
                    "payments_count_left": payments_left,
                }
                if c.shard_id == shard_id_enc else vars(c)
                for c in node.active_contracts
            ]
            self._storage.update(username, active_contracts=updated_contracts)
        else:
            raise PaymentError("Availability or contract requirement not met.")

    # ------------------------------------------------------------------
    # Termination & audit checks
    # ------------------------------------------------------------------

    def _run_random_checks(self) -> None:
        """Randomly audit one storage node and one file per heartbeat cycle."""
        nodes = list(self._storage.find_available(0))  # All non-terminated nodes
        if nodes:
            node = random.choice(nodes)
            self._should_terminate(node)

        files = self._files.find_all_uploaded()
        if files:
            file = random.choice(files)
            self._check_regeneration(file)

    def _should_terminate(self, node: StorageNode) -> bool:
        availability = _compute_availability(node)
        if availability < MINIMUM_AVAILABILITY_THRESHOLD:
            self._terminate_node(node)
            return True
        return False

    def _terminate_node(self, node: StorageNode) -> None:
        contract_addresses = [c.contract_address for c in node.active_contracts]
        files = self._files.find_by_contract_addresses(contract_addresses)
        for file in files:
            for seg_idx, segment in enumerate(file.segments):
                for sh_idx, shard in enumerate(segment["shards"]):
                    if shard["shard_node_username"] == node.username:
                        self._files.update_shard(file.id, seg_idx, sh_idx, shard_lost=True)
        self._storage.update(node.username, is_terminated=True, available_space=0)

    def _check_regeneration(self, file) -> None:
        for seg_no, segment in enumerate(file.segments):
            active = 0
            for shard in segment["shards"]:
                if shard.get("shard_lost"):
                    continue
                node = self._storage.find_by_username(shard["shard_node_username"])
                if not node:
                    continue
                if self._should_terminate(node):
                    continue
                audit_ok = self._network.send_audit(shard, node.ip_address, int(node.port))
                if audit_ok:
                    active += 1
                else:
                    self._terminate_node(node)

            if active < segment["k"]:
                pass  # Segment is lost — could raise an alert here

            if (active - segment["k"]) <= MINIMUM_REGENERATION_THRESHOLD:
                self._regeneration(file.id, seg_no)


# ------------------------------------------------------------------
# Pure date/time helpers
# ------------------------------------------------------------------

def _last_interval_start(now, years_since_epoch, months_since_epoch) -> datetime.datetime:
    months_lag = (years_since_epoch * 12 + months_since_epoch) % RESETTING_MONTHS
    year = now.year + math.floor((now.month - months_lag) / 12)
    month = (now.month - months_lag) % 12 or 12
    return datetime.datetime(year, month, 1)


def _next_interval_start(now, years_since_epoch, months_since_epoch) -> datetime.datetime:
    months_ahead = RESETTING_MONTHS - (years_since_epoch * 12 + months_since_epoch) % RESETTING_MONTHS
    year = now.year + math.floor((now.month + months_ahead) / 12)
    month = (now.month + months_ahead) % 12 or 12
    return datetime.datetime(year, month, 1)


def _quantised_heartbeat(now: datetime.datetime) -> datetime.datetime:
    delta = datetime.timedelta(
        minutes=now.minute % INTERHEARTBEAT_MINUTES - INTERHEARTBEAT_MINUTES,
        seconds=now.second,
        microseconds=now.microsecond,
    )
    return now - delta


def _compute_availability(node: StorageNode) -> float:
    lhb = node.last_heartbeat
    if lhb == -1:
        return 100.0

    now = datetime.datetime.utcnow()
    yse = now.year - CERA_EPOCH.year
    mse = now.month - CERA_EPOCH.month
    last_start = _last_interval_start(now, yse, mse)
    next_start = _next_interval_start(now, yse, mse)

    if (now - last_start) < datetime.timedelta(days=1):
        return 100.0

    full_heartbeats = math.ceil(
        (now - last_start) / datetime.timedelta(minutes=INTERHEARTBEAT_MINUTES)
    )
    if full_heartbeats == 0:
        return 100.0

    percentage = min(100.0, max(0.0, (node.heartbeats + 1) / full_heartbeats * 100))

    if lhb == -2:
        if now - last_start <= datetime.timedelta(minutes=INTERHEARTBEAT_MINUTES):
            return 100.0
        if next_start - now <= datetime.timedelta(minutes=INTERHEARTBEAT_MINUTES):
            return percentage
        return 0.0

    return percentage
