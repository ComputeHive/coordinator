"""
Domain models for Cera.

These frozen dataclasses are the canonical data shapes inside the application.
Nothing outside core/ should reach into MongoDB documents or raw dicts —
all data is translated to/from these models at the repository boundary.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Shard / Segment
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Shard:
    shard_id: str               # Fernet-encrypted opaque token
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
    k: int                       # Minimum shards needed for reconstruction
    m: int                       # Total shards in segment
    shard_size: int              # Bytes per shard
    regeneration_count: int
    shards: List[Shard] = field(default_factory=list)


# ---------------------------------------------------------------------------
# File
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class File:
    id: str                      # MongoDB ObjectId as string
    username: str
    filename: str
    file_size: int
    download_count: int
    duration_in_months: int
    contract_address: str
    price: int                   # Wei
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
    last_heartbeat: object       # -1 (never), -2 (transition), or datetime
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
WEI_PER_ETHER = 10 ** 18


def calculate_price(download_count: int, duration_in_months: int, file_size_kb: int) -> int:
    """Return storage + download price in Wei."""
    storage_per_kb = STORAGE_PRICE_PER_TERA_USD / (ETHER_IN_USD * KB_PER_TERA)
    download_per_kb = DOWNLOAD_PRICE_PER_TERA_USD / (ETHER_IN_USD * KB_PER_TERA)
    price_ether = (
        storage_per_kb * file_size_kb * duration_in_months
        + download_per_kb * file_size_kb * download_count
    )
    return int(price_ether * WEI_PER_ETHER)
