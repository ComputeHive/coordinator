# CERA Coordinator

The **Coordinator** is the central Flask service for the CERA decentralised storage network. It acts as the control plane between end users, storage nodes, and the Ethereum smart contract layer — handling authentication, file orchestration, shard distribution, availability tracking, payments, and automated regeneration of degraded data.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
  - [User Flow](#user-flow)
  - [Storage Node Flow](#storage-node-flow)
  - [Availability & Termination](#availability--termination)
  - [Regeneration](#regeneration)
  - [Blockchain Integration](#blockchain-integration)
- [API Reference](#api-reference)
- [Configuration](#configuration)
- [Running the Service](#running-the-service)
- [Dependencies](#dependencies)

---

## Architecture Overview

```
  User Node                   Coordinator                Storage Nodes
     │                            │                            │
     │──── POST /users/signup ───>│                            │
     │──── POST /users/signin ───>│──── JWT ──────────────────>│
     │                            │                            │
     │──── POST /users/me/files ─>│── assign shards ──────────>│
     │                            │                            │
     │<─── shard locations ───────│                            │
     │──── upload shards directly ────────────────────────────>│
     │──── PATCH shards/done ────>│<─── PATCH shards/done ─────│
     │                            │                            │
     │                     verify on-chain                     │
     │                     contract payment                    │
     │                            │                            │
     │                     periodic heartbeats ───────────────>│
     │                     audits & availability checks        │
     │                            │                            │
     │                     trigger regeneration ──> Regen Worker
```

The coordinator never touches the actual file data. Raw shards travel directly between the user node and storage nodes over a private TCP channel. The coordinator's role is to orchestrate, verify, and enforce the economic contract around that data.

---

## Project Structure

```
coordinator/
├── app.py                          # Application factory (create_app)
├── run.py                          # CLI entry point
├── config.py                       # Dev / prod config classes
├── .env                            # Environment variables (not committed)
│
├── api/
│   ├── blueprints/
│   │   ├── user_blueprint.py       # /users/* routes
│   │   └── storage_blueprint.py   # /storage-nodes/* routes
│   ├── middleware/
│   │   └── auth.py                 # JWT decorator & error handlers
│   └── swagger.py                  # Auto-generated OpenAPI 3 spec + Swagger UI
│
├── core/
│   ├── domain/
│   │   ├── models.py               # Dataclasses: File, Segment, Shard, StorageNode, ...
│   │   └── exceptions.py           # Typed exception hierarchy
│   ├── repositories/
│   │   └── __init__.py             # Abstract repository interfaces (I*Repository)
│   └── services/
│       ├── auth_service.py         # Password hashing, JWT issue/decode
│       ├── user_service.py         # File lifecycle, pricing, downloads, payments
│       └── storage_service.py      # Heartbeats, availability, withdrawals, audits
│
├── infrastructure/
│   ├── database/
│   │   └── mongo_repositories.py  # MongoDB implementations of I*Repository
│   ├── storage_network/
│   │   └── client.py               # TCP client: upload slots, download slots, audits
│   └── regeneration/
│       └── client.py               # HTTP client: dispatches regeneration jobs
│
└── blockchain/
    └── web3_lib.py                 # web3.py v6 wrapper for the CERA smart contract
```

---

## How It Works

### User Flow

1. **Sign up / sign in** — A user registers with a username and password. On sign-in a JWT is issued, which must be sent in the `TOKEN` header on all subsequent requests.

2. **Price check** — Before creating a file the user can query `GET /users/me/files/pending/price` with `file_size`, `download_count`, and `duration_in_months` to get a Wei-denominated cost.

3. **Create file job** — `POST /users/me/files` with a file metadata payload. The coordinator allocates storage nodes, generates a Fernet-encrypted shard ID per shard, and creates a pending on-chain contract.

4. **Get pending file info** — `GET /users/me/files/pending` returns the full shard assignment list including the IP, port, and shared authentication key for each target storage node.

5. **Direct upload** — The user node opens a TCP connection to each storage node directly, using the upload slot negotiated through the coordinator. The coordinator is not in the data path.

6. **Acknowledge shards** — As each shard lands, both the user node (`PATCH /users/me/files/pending/shards/done`) and the storage node (`PATCH /storage-nodes/me/shards/done`) confirm receipt. The storage node acknowledgement also registers the node's wallet address into the on-chain contract.

7. **Shard reassignment** — If a storage node is unreachable during upload, `PATCH /users/me/files/pending/shards/reassign` picks a replacement node.

8. **Mark file done** — `PATCH /users/me/files/pending/done` finalises the upload.

9. **Pay contract** — The user pays the on-chain contract and calls `POST /users/me/contracts/pending/payment`. The coordinator verifies the on-chain transaction via `POST /users/me/transactions/verify`.

10. **Download** — `POST /users/me/files/{filename}/downloads` checks availability, runs audits, and returns download slot info for each shard's storage node.

---

### Storage Node Flow

1. **Sign up / sign in** — Storage nodes register with a username, password, wallet address, and available space (in KB).

2. **Update connection** — `PATCH /storage-nodes/me/connection` publishes the node's current public IP and CERA TCP port so the coordinator can route users to it.

3. **Heartbeat** — `POST /storage-nodes/me/heartbeat` must be called every **10 minutes**. The coordinator quantises the timestamp to the nearest interval boundary and accumulates a count for the current billing epoch (every 2 months). Each heartbeat also triggers a random background audit of a random node and file.

4. **Withdraw** — `POST /storage-nodes/me/contracts/{shard_id}/withdrawal` pays out accumulated earnings for a shard. The coordinator runs an on-demand audit, checks availability, verifies the node is still registered in the on-chain contract, and calls `payStorageNode` on-chain.

---

### Availability & Termination

Availability is computed as the ratio of heartbeats received in the current epoch to the total heartbeats that could have been sent since the epoch start:

```
availability = (heartbeats_received + 1) / expected_heartbeats * 100
```

A one-day grace period at the start of each epoch keeps availability at 100% while nodes are catching up.

| Threshold | Effect |
|---|---|
| `< 70%` | Node is **terminated**: all its shards are marked `shard_lost`, its `available_space` is set to 0, and it is excluded from future assignments. |
| `< 95%` | Node is paid proportionally (`availability% × payment_per_interval`). |
| `≥ 95%` | Node receives the full `payment_per_interval`. |

Termination checks run both on every heartbeat (random sampling of all active nodes) and on every withdrawal attempt.

---

### Regeneration

When a file's segment falls below a safe redundancy level — `active_shards - k ≤ MINIMUM_REGENERATION_THRESHOLD` — the coordinator dispatches a regeneration job to an external worker service.

The `RegenerationClient` POSTs `{ "file_id": "...", "seg_no": N }` to `REGENERATION_SERVICE_URL/jobs` before firing the request, it increments `regeneration_count` for the segment in the database so the worker receives the correct metadata.

The call is fire-and-forget: timeouts, connection errors, and HTTP errors are all caught, logged, and swallowed so that a downed regeneration service never blocks a storage node heartbeat cycle.

---

### Blockchain Integration

The coordinator interacts with a deployed Solidity contract that tracks the list of storage node wallet addresses and controls ETH payments. The `blockchain/web3_lib.py` module wraps all on-chain calls using **web3.py v6**.

| Function | On-chain action |
|---|---|
| `create_contract(payment_limit)` | Deploy a new payment contract for a file |
| `get_contract(address)` | Load an existing contract by address |
| `add_node(contract, wallet)` | Register a storage node wallet |
| `delete_node(contract, wallet)` | Remove a storage node wallet |
| `swap_nodes(contract, wallet, index)` | Replace a node at a given index |
| `pay_storage_node(contract, wallet, amount)` | Transfer ETH to a node |
| `node_in_contract(contract, wallet)` | Check if a wallet is registered |
| `terminate(contract)` | Terminate the contract and sweep funds |
| `get_storage_nodes(contract)` | List all registered wallet addresses |
| `get_balance(contract)` | Query contract ETH balance |

All mutating calls are signed with the coordinator's private key (`PRIVATE_KEY`) and submitted via `send_raw_transaction`.

---

## API Reference

Interactive documentation is available at runtime:

| URL | Description |
|---|---|
| `GET /docs` | Swagger UI |
| `GET /docs/openapi.json` | Raw OpenAPI 3 JSON spec |

The spec is built programmatically from `api/swagger.py` and is always in sync with the codebase. Adding a new endpoint means adding one entry to `_build_spec()` in that file.

**Authentication:** All protected routes expect a `TOKEN: <jwt>` header. The token is issued by the relevant `/signin` endpoint and is valid for the lifetime configured in `AuthService`.

### User routes (`/users`)

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/users/signup` | — | Register a user node |
| `POST` | `/users/signin` | — | Authenticate, receive JWT |
| `GET` | `/users/me/state` | ✓ | Get account state (1–4) |
| `GET` | `/users/me/wallet` | ✓ | Get coordinator Ethereum address |
| `GET` | `/users/me/files` | ✓ | List active files |
| `POST` | `/users/me/files` | ✓ | Create a file upload job |
| `GET` | `/users/me/files/pending` | ✓ | Get pending file + shard assignments |
| `PATCH` | `/users/me/files/pending/done` | ✓ | Mark file fully uploaded |
| `GET` | `/users/me/files/pending/price` | ✓ | Calculate storage price |
| `POST` | `/users/me/files/{filename}/downloads` | ✓ | Start a file download |
| `PATCH` | `/users/me/files/pending/shards/done` | ✓ | Acknowledge shard upload |
| `PATCH` | `/users/me/files/pending/shards/reassign` | ✓ | Reassign a failed shard |
| `GET` | `/users/me/contracts/pending` | ✓ | Get pending contract details |
| `POST` | `/users/me/contracts/pending/payment` | ✓ | Record contract payment |
| `POST` | `/users/me/transactions/verify` | ✓ | Verify an Ethereum transaction |

### Storage node routes (`/storage-nodes`)

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/storage-nodes/signup` | — | Register a storage node |
| `POST` | `/storage-nodes/signin` | — | Authenticate, receive JWT |
| `GET` | `/storage-nodes/me` | ✓ | Get node info (availability + contracts) |
| `POST` | `/storage-nodes/me/heartbeat` | ✓ | Send liveness heartbeat |
| `GET` | `/storage-nodes/me/availability` | ✓ | Get availability percentage |
| `PATCH` | `/storage-nodes/me/connection` | ✓ | Update public IP and port |
| `GET` | `/storage-nodes/me/contracts` | ✓ | List active shard contracts |
| `POST` | `/storage-nodes/me/contracts/{shard_id}/withdrawal` | ✓ | Withdraw shard earnings |
| `PATCH` | `/storage-nodes/me/shards/done` | ✓ | Acknowledge shard upload |

---

## Configuration

All configuration is read from environment variables. Copy `.env` and fill in the values before running.

```env
# Flask / JWT secret key
SECRET_KEY=<random-32-byte-hex>

# Fernet key used to encrypt shard IDs (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
SHARD_ID_KEY=<fernet-key>

# MongoDB
MONGODB_DEV_URI=mongodb://localhost:27017
MONGODB_DEV_NAME=cera_dev
MONGODB_PROD_URI=mongodb://username:password@host:27017
MONGODB_PROD_NAME=cera_prod

# Ethereum
INFURA_URL=https://mainnet.infura.io/v3/<project-id>
ADDRESS=0x<coordinator-wallet-address>
PRIVATE_KEY=<coordinator-private-key>

# Regeneration worker
REGENERATION_SERVICE_URL=http://regen-worker:8080

# Email (optional — used for notifications)
MAIL_PASSWORD=<zoho-app-password>
```

> **Security note:** Never commit `.env` to version control. The `.gitignore` already excludes it.

---

## Running the Service

**Prerequisites:** Python 3.11+, MongoDB, a funded Ethereum wallet, and a reachable regeneration worker.

```bash
# Install dependencies (using Poetry)
poetry install

# Development server
python run.py --env dev

# Production server
python run.py --env prod
```

The server binds to `0.0.0.0:5000`. Use a reverse proxy (nginx, Caddy) in production.

Once running, open `http://localhost:5000/docs` for the interactive API documentation.

---

## Dependencies

| Package | Purpose |
|---|---|
| `Flask` | HTTP framework |
| `pymongo` | MongoDB driver |
| `web3` | Ethereum / smart contract interaction |
| `cryptography` | Fernet encryption for shard IDs |
| `PyJWT` | JWT issue and verification |
| `bcrypt` | Password hashing |
| `requests` | HTTP client for the regeneration worker |
| `python-dotenv` | `.env` file loading |
| `PyYAML` | YAML parsing (regeneration workflow manifests) |
| `click` | CLI argument parsing for `run.py` |
