"""
User-node service.

All business logic for user-node operations.  No Flask, no MongoDB, no
socket I/O — those details live in the infrastructure layer.  The service
receives abstractions (repositories, blockchain client, network client) via
constructor injection.
"""

from __future__ import annotations

import json
import random
import string
from typing import List

from core.domain.exceptions import (
    AuthenticationError,
    ConflictError,
    DatabaseError,
    FileUnavailableError,
    FileLostError,
    NotFoundError,
    PaymentError,
    StorageUnavailableError,
    ValidationError,
)
from core.domain.models import File, Segment, Shard, UserNode, calculate_price
from core.repositories import IFileRepository, ITransactionRepository, IUserRepository
from core.services.auth_service import AuthService


_REQUIRED_FILE_FIELDS = (
    "segments", "segments_count", "download_count",
    "file_size", "filename", "duration_in_months",
)
_REQUIRED_SEGMENT_FIELDS = ("k", "m", "shard_size")
_SHARD_ID_SEPARATOR = "$DCNTRG$"


def _random_auth_key(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.SystemRandom().choice(alphabet) for _ in range(length))


class UserService:
    def __init__(
        self,
        user_repo: IUserRepository,
        file_repo: IFileRepository,
        tx_repo: ITransactionRepository,
        auth_service: AuthService,
        blockchain,          # IBlockchainClient
        network,             # IStorageNetworkClient
        fernet,              # cryptography.fernet.Fernet
        storage_repo,        # IStorageRepository
    ) -> None:
        self._users = user_repo
        self._files = file_repo
        self._txs = tx_repo
        self._auth = auth_service
        self._blockchain = blockchain
        self._network = network
        self._fernet = fernet
        self._storage = storage_repo

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def register(self, username: str, password: str) -> None:
        if not username or not password:
            raise ValidationError("username and password are required.")
        if self._users.find_by_username(username):
            raise ConflictError("Username already exists.")
        hashed = self._auth.hash_password(password)
        self._users.create(username, hashed)

    def authenticate(self, username: str, password: str) -> str:
        """Return JWT token."""
        if not username or not password:
            raise ValidationError("username and password are required.")
        user = self._users.find_by_username(username)
        if not user or not self._auth.verify_password(password, user.password_hash):
            raise AuthenticationError("Wrong username or password.")
        return self._auth.issue_token(username)

    def verify_exists(self, username: str) -> bool:
        return self._users.find_by_username(username) is not None

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self, username: str) -> str:
        """
        State codes:
          1 - pending contract paid
          2 - pending contract not yet paid
          3 - no pending contract, has seeds
          4 - no pending contract, no seeds
        """
        user = self._users.find_by_username(username)
        if not user:
            return "4"
        if user.pending_contract_paid:
            return "1"
        if user.pending_contract:
            return "2"
        if user.seeds > 0:
            return "3"
        return "4"

    def get_active_contracts(self, username: str) -> List[dict]:
        files = self._files.find_active(username)
        return [
            {
                "filename": f.filename,
                "size": f.file_size,
                "download_count": f.download_count,
                "duration_in_months": f.duration_in_months,
            }
            for f in files
        ]

    # ------------------------------------------------------------------
    # Pricing
    # ------------------------------------------------------------------

    def get_price(
        self, download_count: int, duration_in_months: int, file_size: int
    ) -> int:
        return calculate_price(download_count, duration_in_months, file_size)

    # ------------------------------------------------------------------
    # Upload flow
    # ------------------------------------------------------------------

    def create_file(self, username: str, payload: dict) -> None:
        """Validate the upload manifest and create a file document with shard IDs."""
        if self.get_state(username) != "3":
            raise PaymentError("No contract requests available.")

        if not all(f in payload for f in _REQUIRED_FILE_FIELDS):
            raise ValidationError("Missing required fields in file manifest.")
        for seg in payload["segments"]:
            if not all(f in seg for f in _REQUIRED_SEGMENT_FIELDS):
                raise ValidationError("Missing required fields in segment.")

        filename = payload["filename"]

        if self._files.find_active(username):
            # Check for exact duplicate
            existing = [f for f in self._files.find_active(username) if f.filename == filename]
            if existing:
                raise ConflictError("Duplicate filename.")

        price = calculate_price(
            payload["download_count"],
            payload["duration_in_months"],
            payload["file_size"],
        )
        contract = self._blockchain.create_contract(price - 10)

        file_doc = {
            "filename": filename,
            "segments_count": payload["segments_count"],
            "file_size": payload["file_size"],
            "download_count": payload["download_count"],
            "duration_in_months": payload["duration_in_months"],
            "contract": contract.address,
            "username": username,
            "done_uploading": False,
            "paid": False,
            "price": price,
        }
        file_id = self._files.create(file_doc)

        segments = self._build_segments(file_id, payload["segments"])
        self._files.update_segments(file_id, segments)
        self._users.update(username, pending_contract=True)
        self._users.increment_seeds(username, -1)

    def _build_segments(self, file_id: str, segment_specs: list) -> list:
        segments = []
        for seg_no, spec in enumerate(segment_specs):
            shards = []
            for shard_no in range(spec["m"]):
                raw_id = f"{file_id}{_SHARD_ID_SEPARATOR}{seg_no}{_SHARD_ID_SEPARATOR}{shard_no}"
                encrypted_id = self._fernet.encrypt(raw_id.encode()).decode()
                shards.append(
                    {
                        "shard_id": encrypted_id,
                        "shard_node_username": "",
                        "done_uploading": False,
                        "shard_lost": False,
                        "user_node_done": False,
                        "storage_node_done": False,
                    }
                )
            segments.append(
                {
                    "k": spec["k"],
                    "m": spec["m"],
                    "shard_size": spec["shard_size"],
                    "regeneration_count": 0,
                    "shards": shards,
                }
            )
        return segments

    def get_file_info(self, username: str) -> dict:
        file = self._files.find_pending(username)
        if not file:
            raise NotFoundError("No file being uploaded.")
        return {"file_size": file.file_size, "segments": file.segments}

    def get_contract(self, username: str) -> dict:
        file = self._files.find_pending(username)
        if not file or file.paid:
            raise NotFoundError("No unpaid contract.")
        return {
            "contract_address": file.contract_address,
            "filename": file.filename,
            "price": file.price,
        }

    def pay_contract(self, username: str) -> None:
        """Verify on-chain payment and assign storage nodes to each shard."""
        file = self._files.find_pending(username)
        if not file:
            raise NotFoundError("No unpaid file being uploaded.")

        contract = self._blockchain.get_contract(file.contract_address)
        balance = self._blockchain.get_balance(contract)
        if balance < file.price:
            raise PaymentError("Contract is not paid yet.")

        import datetime
        now = datetime.datetime.utcnow()
        next_payment_date = now + datetime.timedelta(minutes=5)

        total_shards = sum(seg["m"] for seg in file.segments)
        storage_share = 0.75
        total_payment = storage_share * file.price / total_shards
        payments_count_left = file.duration_in_months * 4
        payment_per_interval = total_payment / payments_count_left

        segments = list(file.segments)
        for i, segment in enumerate(segments):
            segments[i] = self._assign_storage_nodes(
                segment=segment,
                segment_index=i,
                contract_address=file.contract_address,
                next_payment_date=next_payment_date,
                payments_count_left=payments_count_left,
                payment_per_interval=payment_per_interval,
            )

        self._files.mark_paid(username)
        self._files.update_segments(file.id, segments)
        self._users.update(username, pending_contract_paid=True)

    def _assign_storage_nodes(
        self,
        segment: dict,
        segment_index: int,
        contract_address: str,
        next_payment_date,
        payments_count_left: int,
        payment_per_interval: float,
    ) -> dict:
        shards = segment["shards"]
        shard_size = segment["shard_size"]
        unassigned = segment["m"]
        retry_count = 100

        while unassigned > 0 and retry_count > 0:
            candidates = self._storage.find_available(shard_size)
            if not candidates:
                raise StorageUnavailableError("No storage nodes available.")

            random.shuffle(candidates)
            reserved = candidates[:unassigned]
            spares = candidates[unassigned:]
            spare_idx = 0

            for node in reserved:
                auth_key = _random_auth_key()
                shard_id = shards[unassigned - 1]["shard_id"]
                port = self._network.request_upload_slot(node, shard_id, auth_key, shard_size)

                # Fallback to spare nodes if primary unreachable
                while not port and spare_idx < len(spares):
                    node = spares[spare_idx]
                    spare_idx += 1
                    port = self._network.request_upload_slot(node, shard_id, auth_key, shard_size)

                if not port:
                    continue  # Will retry in next iteration

                self._storage.push_active_contract(
                    node.username,
                    {
                        "shard_id": shard_id,
                        "contract_address": contract_address,
                        "next_payment_date": next_payment_date,
                        "payments_count_left": payments_count_left,
                        "payment_per_interval": payment_per_interval,
                    },
                )
                self._storage.update(
                    node.username,
                    available_space=node.available_space - shard_size,
                )

                shards[unassigned - 1].update(
                    ip_address=node.ip_address,
                    port=port,
                    shard_node_username=node.username,
                    shared_authentication_key=auth_key,
                )
                unassigned -= 1

            retry_count -= 1

        if unassigned > 0:
            raise StorageUnavailableError("Failed to assign storage nodes to all shards.")

        segment["shards"] = shards
        return segment

    def file_done_uploading(self, username: str) -> None:
        self._files.mark_done_uploading(username)
        self._users.update(username, pending_contract=False, pending_contract_paid=False)

    def shard_done_uploading(self, username: str, shard_id_enc: str, audits: list) -> None:
        if not shard_id_enc or not audits:
            raise ValidationError("shard_id and audits are required.")

        file = self._files.find_pending(username)
        if not file:
            raise NotFoundError("No in-progress file found.")

        segment_no, shard_no = self._decode_shard_id(shard_id_enc)
        shard = file.segments[segment_no]["shards"][shard_no]

        if shard["shard_id"] != shard_id_enc:
            raise DatabaseError("Shard ID mismatch.")

        updates = {"user_node_done": True, "audits": audits}
        if shard.get("storage_node_done"):
            updates["done_uploading"] = True

        self._files.update_shard(file.id, segment_no, shard_no, **updates)

    def shard_failed_uploading(self, username: str, shard_id_enc: str) -> dict:
        if not shard_id_enc:
            raise ValidationError("shard_id is required.")

        file = self._files.find_pending(username)
        if not file:
            raise NotFoundError("No in-progress file found.")

        segment_no, shard_no = self._decode_shard_id(shard_id_enc)
        shard_size = file.segments[segment_no]["shard_size"]

        existing_nodes = {
            shard["shard_node_username"]
            for seg in file.segments
            for shard in seg["shards"]
        }
        candidates = self._storage.find_available(shard_size)
        # Prefer nodes not already in use for this file
        preferred = [n for n in candidates if n.username not in existing_nodes]
        pool = preferred if preferred else candidates

        for _ in range(10):
            if not pool:
                break
            node = random.choice(pool)
            auth_key = _random_auth_key()
            port = self._network.request_upload_slot(node, shard_id_enc, auth_key, shard_size)
            if not port:
                continue

            self._files.update_shard(
                file.id, segment_no, shard_no,
                shard_node_username=node.username,
                ip_address=node.ip_address,
                port=port,
                shared_authentication_key=auth_key,
            )
            return {
                "shard_node_username": node.username,
                "ip_address": node.ip_address,
                "port": port,
                "shared_authentication_key": auth_key,
            }

        raise StorageUnavailableError("Could not find a replacement storage node.")

    # ------------------------------------------------------------------
    # Download flow
    # ------------------------------------------------------------------

    def start_download(self, username: str, filename: str) -> dict:
        files = self._files.find_active(username)
        file = next((f for f in files if f.filename == filename), None)
        if not file:
            raise NotFoundError("File not found.")
        if file.download_count < 1:
            raise PaymentError("No downloads remaining.")

        segments_out = []
        for seg_no, segment in enumerate(file.segments):
            shards_out = self._collect_download_shards(segment, seg_no)
            segments_out.append(
                {
                    "shards": shards_out,
                    "m": segment["m"],
                    "k": segment["k"],
                    "shard_size": segment["shard_size"],
                }
            )

        self._files.decrement_downloads(username, filename)
        return {"segments": segments_out}

    def _collect_download_shards(self, segment: dict, seg_no: int) -> list:
        needed = segment["k"]
        acquired = 0
        temporarily_down = 0
        shards_out = []

        for sh_no, shard in enumerate(segment["shards"]):
            if acquired == needed:
                break
            if shard.get("shard_lost"):
                continue

            node = self._storage.find_by_username(shard["shard_node_username"])
            if not node:
                temporarily_down += 1
                continue

            auth_key = _random_auth_key()
            port = self._network.request_download_slot(
                node.ip_address, int(node.port),
                shard["shard_id"], segment["shard_size"], auth_key,
            )
            if port == 0:
                temporarily_down += 1
                continue

            raw_id = self._fernet.decrypt(shard["shard_id"].encode()).decode()
            parts = raw_id.split(_SHARD_ID_SEPARATOR)
            if int(parts[1]) != seg_no or int(parts[2]) != sh_no:
                raise DatabaseError("Shard ID / position mismatch.")

            shards_out.append(
                {
                    "ip_address": node.ip_address,
                    "port": port,
                    "segment_no": parts[1],
                    "shard_id": shard["shard_id"],
                    "shard_no": parts[2],
                    "auth": auth_key,
                }
            )
            acquired += 1

        if acquired < needed:
            missing = needed - acquired
            if missing <= temporarily_down:
                raise FileUnavailableError("File temporarily unavailable.")
            raise FileLostError("File is lost — too many shards missing.")

        return shards_out

    # ------------------------------------------------------------------
    # Transactions / seeds
    # ------------------------------------------------------------------

    def verify_transaction(self, username: str, tx_hash: str) -> None:
        receipt = self._blockchain.get_transaction_receipt(tx_hash)
        if not receipt:
            raise PaymentError("Transaction has not been mined yet.")
        if self._txs.exists(tx_hash):
            raise ConflictError("Transaction already used.")
        self._txs.record(tx_hash)
        self._users.increment_seeds(username, 1)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _decode_shard_id(self, encrypted: str):
        raw = self._fernet.decrypt(encrypted.encode()).decode()
        parts = raw.split(_SHARD_ID_SEPARATOR)
        return int(parts[1]), int(parts[2])
