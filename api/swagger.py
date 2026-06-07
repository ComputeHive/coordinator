"""
Automatic OpenAPI 3 documentation for the Coordinator API.

This module builds the complete OpenAPI spec programmatically from a single
source-of-truth dictionary.  Whenever a route, parameter, or response schema
changes, update the spec here and the Swagger UI at /docs will reflect it
immediately — no manual YAML editing required.

Usage
-----
Call ``register_swagger(app)`` from ``create_app()`` in ``app.py``.
The Swagger UI is then available at ``GET /docs`` and the raw JSON spec at
``GET /docs/openapi.json``.
"""
from __future__ import annotations

from flask import Flask, jsonify, render_template_string, Blueprint

# ---------------------------------------------------------------------------
# Reusable schema fragments
# ---------------------------------------------------------------------------

_TOKEN_HEADER = {
    "in": "header",
    "name": "TOKEN",
    "required": True,
    "schema": {"type": "string"},
    "description": "JWT issued by /signin",
}

_SHARD_ID_PARAM = {
    "in": "path",
    "name": "shard_id",
    "required": True,
    "schema": {"type": "string"},
    "description": "Fernet-encrypted shard identifier",
}

_ERR_SCHEMA = {
    "type": "object",
    "properties": {"error": {"type": "string"}},
}

def _err(description: str) -> dict:
    return {"description": description, "content": {"application/json": {"schema": _ERR_SCHEMA}}}


def _ok(description: str, schema: dict | None = None) -> dict:
    if schema is None:
        return {"description": description}
    return {
        "description": description,
        "content": {"application/json": {"schema": schema}},
    }


# ---------------------------------------------------------------------------
# Full OpenAPI 3.0 spec
# ---------------------------------------------------------------------------

def _build_spec(app: Flask) -> dict:
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "CERA Coordinator API",
            "version": "1.0.0",
            "description": (
                "REST API for the CERA decentralised storage coordinator. "
                "Handles user node auth, file management, storage-node auth, "
                "heartbeats, and contract withdrawals."
            ),
        },
        "servers": [{"url": app.config.get("SERVER_PATH", "/"), "description": "Current server"}],
        "components": {
            "securitySchemes": {
                "TokenAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "TOKEN",
                    "description": "JWT returned by /signin",
                }
            },
            "schemas": {
                "Error": _ERR_SCHEMA,
                "TokenResponse": {
                    "type": "object",
                    "properties": {"token": {"type": "string"}},
                },
                "AvailabilityResponse": {
                    "type": "object",
                    "properties": {"availability": {"type": "number", "format": "float"}},
                },
                "StorageInfoResponse": {
                    "type": "object",
                    "properties": {
                        "availability": {"type": "number", "format": "float"},
                        "contracts": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "shard_id": {"type": "string"},
                                    "next_payment_date": {"type": "string", "format": "date-time"},
                                    "payment_left": {"type": "number"},
                                    "payment_per_interval": {"type": "number"},
                                },
                            },
                        },
                    },
                },
                "ContractsResponse": {
                    "type": "object",
                    "properties": {"shards": {"type": "array", "items": {"type": "string"}}},
                },
                "PriceResponse": {
                    "type": "object",
                    "properties": {"price": {"type": "integer", "description": "Price in Wei"}},
                },
                "WalletResponse": {
                    "type": "object",
                    "properties": {"decentorage_wallet_address": {"type": "string"}},
                },
                "StateResponse": {
                    "type": "object",
                    "properties": {"state": {"type": "string"}},
                },
            },
        },
        "paths": {
            # ----------------------------------------------------------------
            # Users — auth
            # ----------------------------------------------------------------
            "/users/signup": {
                "post": {
                    "tags": ["Users — Auth"],
                    "summary": "Register a new user node",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["username", "password"],
                                    "properties": {
                                        "username": {"type": "string"},
                                        "password": {"type": "string", "format": "password"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "201": _ok("User created"),
                        "409": _err("Username already exists"),
                        "400": _err("Validation error"),
                    },
                }
            },
            "/users/signin": {
                "post": {
                    "tags": ["Users — Auth"],
                    "summary": "Authenticate a user node and receive a JWT",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["username", "password"],
                                    "properties": {
                                        "username": {"type": "string"},
                                        "password": {"type": "string", "format": "password"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": _ok("JWT token", {"$ref": "#/components/schemas/TokenResponse"}),
                        "401": _err("Invalid credentials"),
                    },
                }
            },
            # ----------------------------------------------------------------
            # Users — state & wallet
            # ----------------------------------------------------------------
            "/users/me/state": {
                "get": {
                    "tags": ["Users — Profile"],
                    "summary": "Get the current user node state",
                    "security": [{"TokenAuth": []}],
                    "responses": {
                        "200": _ok("User state", {"$ref": "#/components/schemas/StateResponse"}),
                        "401": _err("Unauthorised"),
                    },
                }
            },
            "/users/me/wallet": {
                "get": {
                    "tags": ["Users — Profile"],
                    "summary": "Get the coordinator Ethereum wallet address",
                    "security": [{"TokenAuth": []}],
                    "responses": {
                        "200": _ok("Wallet address", {"$ref": "#/components/schemas/WalletResponse"}),
                        "401": _err("Unauthorised"),
                    },
                }
            },
            # ----------------------------------------------------------------
            # Users — files
            # ----------------------------------------------------------------
            "/users/me/files": {
                "get": {
                    "tags": ["Users — Files"],
                    "summary": "List all active files (contracts) for the user",
                    "security": [{"TokenAuth": []}],
                    "responses": {
                        "200": _ok("Array of active file objects"),
                        "401": _err("Unauthorised"),
                    },
                },
                "post": {
                    "tags": ["Users — Files"],
                    "summary": "Create a new file upload job",
                    "security": [{"TokenAuth": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "description": "JSON-encoded file metadata payload",
                                }
                            }
                        },
                    },
                    "responses": {
                        "201": _ok("File job created"),
                        "400": _err("Validation error"),
                        "401": _err("Unauthorised"),
                        "409": _err("Pending file already exists"),
                    },
                },
            },
            "/users/me/files/pending": {
                "get": {
                    "tags": ["Users — Files"],
                    "summary": "Get info for the currently pending file",
                    "security": [{"TokenAuth": []}],
                    "responses": {
                        "200": _ok("Pending file info including shard assignments"),
                        "401": _err("Unauthorised"),
                        "404": _err("No pending file"),
                    },
                }
            },
            "/users/me/files/pending/done": {
                "patch": {
                    "tags": ["Users — Files"],
                    "summary": "Mark the pending file as fully uploaded",
                    "security": [{"TokenAuth": []}],
                    "responses": {
                        "204": _ok("Marked as done"),
                        "401": _err("Unauthorised"),
                        "404": _err("No pending file"),
                    },
                }
            },
            "/users/me/files/pending/price": {
                "get": {
                    "tags": ["Users — Files"],
                    "summary": "Calculate storage price for a file",
                    "security": [{"TokenAuth": []}],
                    "parameters": [
                        {
                            "in": "query",
                            "name": "download_count",
                            "required": True,
                            "schema": {"type": "integer"},
                        },
                        {
                            "in": "query",
                            "name": "duration_in_months",
                            "required": True,
                            "schema": {"type": "integer"},
                        },
                        {
                            "in": "query",
                            "name": "file_size",
                            "required": True,
                            "schema": {"type": "integer", "description": "File size in KB"},
                        },
                    ],
                    "responses": {
                        "200": _ok("Price in Wei", {"$ref": "#/components/schemas/PriceResponse"}),
                        "401": _err("Unauthorised"),
                    },
                }
            },
            "/users/me/files/{filename}/downloads": {
                "post": {
                    "tags": ["Users — Files"],
                    "summary": "Start a download for a file",
                    "security": [{"TokenAuth": []}],
                    "parameters": [
                        {
                            "in": "path",
                            "name": "filename",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {
                        "200": _ok("Download slot info including shard locations"),
                        "401": _err("Unauthorised"),
                        "402": _err("File not paid"),
                        "404": _err("File not found"),
                        "503": _err("Not enough active storage nodes"),
                    },
                }
            },
            # ----------------------------------------------------------------
            # Users — shards
            # ----------------------------------------------------------------
            "/users/me/files/pending/shards/done": {
                "patch": {
                    "tags": ["Users — Shards"],
                    "summary": "Acknowledge a shard upload completion (user side)",
                    "security": [{"TokenAuth": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["shard_id", "audits"],
                                    "properties": {
                                        "shard_id": {"type": "string"},
                                        "audits": {
                                            "type": "array",
                                            "items": {"type": "object"},
                                            "description": "Audit challenge/response pairs",
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "204": _ok("Acknowledged"),
                        "400": _err("Validation error"),
                        "401": _err("Unauthorised"),
                    },
                }
            },
            "/users/me/files/pending/shards/reassign": {
                "patch": {
                    "tags": ["Users — Shards"],
                    "summary": "Reassign a failed shard to a different storage node",
                    "security": [{"TokenAuth": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["shard_id"],
                                    "properties": {"shard_id": {"type": "string"}},
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": _ok("New storage node connection details"),
                        "401": _err("Unauthorised"),
                        "503": _err("No available storage node"),
                    },
                }
            },
            # ----------------------------------------------------------------
            # Users — contracts & transactions
            # ----------------------------------------------------------------
            "/users/me/contracts/pending": {
                "get": {
                    "tags": ["Users — Contracts"],
                    "summary": "Get the pending on-chain contract details",
                    "security": [{"TokenAuth": []}],
                    "responses": {
                        "200": _ok("Contract address and payment amount"),
                        "401": _err("Unauthorised"),
                        "404": _err("No pending contract"),
                    },
                }
            },
            "/users/me/contracts/pending/payment": {
                "post": {
                    "tags": ["Users — Contracts"],
                    "summary": "Mark the pending contract as paid",
                    "security": [{"TokenAuth": []}],
                    "responses": {
                        "204": _ok("Payment recorded"),
                        "401": _err("Unauthorised"),
                        "402": _err("Contract not yet paid on-chain"),
                    },
                }
            },
            "/users/me/transactions/verify": {
                "post": {
                    "tags": ["Users — Contracts"],
                    "summary": "Verify an Ethereum transaction hash",
                    "security": [{"TokenAuth": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["transactionHash"],
                                    "properties": {"transactionHash": {"type": "string"}},
                                }
                            }
                        },
                    },
                    "responses": {
                        "204": _ok("Transaction verified"),
                        "400": _err("Invalid or unrecognised transaction"),
                        "401": _err("Unauthorised"),
                    },
                }
            },
            # ================================================================
            # Storage nodes
            # ================================================================
            "/storage-nodes/signup": {
                "post": {
                    "tags": ["Storage Nodes — Auth"],
                    "summary": "Register a new storage node",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["username", "password", "wallet_address", "available_space"],
                                    "properties": {
                                        "username": {"type": "string"},
                                        "password": {"type": "string", "format": "password"},
                                        "wallet_address": {
                                            "type": "string",
                                            "pattern": "^0x[a-fA-F0-9]{40}$",
                                            "example": "0xAbCd...1234",
                                        },
                                        "available_space": {
                                            "type": "integer",
                                            "description": "Available space in KB",
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "201": _ok("Storage node registered"),
                        "400": _err("Validation error (e.g. invalid wallet)"),
                        "409": _err("Username already exists"),
                    },
                }
            },
            "/storage-nodes/signin": {
                "post": {
                    "tags": ["Storage Nodes — Auth"],
                    "summary": "Authenticate a storage node and receive a JWT",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["username", "password"],
                                    "properties": {
                                        "username": {"type": "string"},
                                        "password": {"type": "string", "format": "password"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": _ok("JWT token", {"$ref": "#/components/schemas/TokenResponse"}),
                        "401": _err("Invalid credentials"),
                    },
                }
            },
            "/storage-nodes/me": {
                "get": {
                    "tags": ["Storage Nodes — Status"],
                    "summary": "Get storage node info (availability + contracts)",
                    "security": [{"TokenAuth": []}],
                    "responses": {
                        "200": _ok("Storage info", {"$ref": "#/components/schemas/StorageInfoResponse"}),
                        "401": _err("Unauthorised"),
                    },
                }
            },
            "/storage-nodes/me/heartbeat": {
                "post": {
                    "tags": ["Storage Nodes — Status"],
                    "summary": "Send a heartbeat to prove node liveness",
                    "security": [{"TokenAuth": []}],
                    "responses": {
                        "204": _ok("Heartbeat recorded"),
                        "400": _err("Heartbeat already recorded for this interval"),
                        "401": _err("Unauthorised"),
                    },
                }
            },
            "/storage-nodes/me/availability": {
                "get": {
                    "tags": ["Storage Nodes — Status"],
                    "summary": "Get the node's current availability percentage",
                    "security": [{"TokenAuth": []}],
                    "responses": {
                        "200": _ok(
                            "Availability percentage",
                            {"$ref": "#/components/schemas/AvailabilityResponse"},
                        ),
                        "401": _err("Unauthorised"),
                    },
                }
            },
            "/storage-nodes/me/connection": {
                "patch": {
                    "tags": ["Storage Nodes — Connection"],
                    "summary": "Update the node's public IP and CERA port",
                    "security": [{"TokenAuth": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["ip_address", "port"],
                                    "properties": {
                                        "ip_address": {
                                            "type": "string",
                                            "pattern": r"^((25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(25[0-5]|2[0-4]\d|[01]?\d\d?)$",
                                        },
                                        "port": {
                                            "type": "string",
                                            "pattern": r"^([0-9]{1,4}|[1-5]\d{4}|6[0-4]\d{3}|65[0-4]\d{2}|655[0-2]\d|6553[0-5])$",
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "204": _ok("Connection updated"),
                        "400": _err("Invalid IP or port"),
                        "401": _err("Unauthorised"),
                    },
                }
            },
            "/storage-nodes/me/contracts": {
                "get": {
                    "tags": ["Storage Nodes — Contracts"],
                    "summary": "List active shard contracts for this node",
                    "security": [{"TokenAuth": []}],
                    "responses": {
                        "200": _ok("Shard IDs", {"$ref": "#/components/schemas/ContractsResponse"}),
                        "401": _err("Unauthorised"),
                    },
                }
            },
            "/storage-nodes/me/contracts/{shard_id}/withdrawal": {
                "post": {
                    "tags": ["Storage Nodes — Contracts"],
                    "summary": "Withdraw earnings for a shard contract",
                    "security": [{"TokenAuth": []}],
                    "parameters": [_SHARD_ID_PARAM],
                    "responses": {
                        "204": _ok("Withdrawal processed"),
                        "400": _err("Audit failed"),
                        "401": _err("Unauthorised or node terminated"),
                        "402": _err("No payment available yet or availability too low"),
                        "404": _err("Contract not found"),
                    },
                }
            },
            "/storage-nodes/me/shards/done": {
                "patch": {
                    "tags": ["Storage Nodes — Shards"],
                    "summary": "Acknowledge a shard upload completion (storage node side)",
                    "security": [{"TokenAuth": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["shard_id"],
                                    "properties": {"shard_id": {"type": "string"}},
                                }
                            }
                        },
                    },
                    "responses": {
                        "204": _ok("Acknowledged"),
                        "400": _err("Validation or shard mismatch error"),
                        "401": _err("Unauthorised"),
                        "404": _err("File not found"),
                    },
                }
            },
        },
    }


# ---------------------------------------------------------------------------
# Swagger UI HTML (served from CDN — no static files needed)
# ---------------------------------------------------------------------------

_SWAGGER_UI_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>CERA Coordinator API Docs</title>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.17.14/swagger-ui.min.css">
</head>
<body>
<div id="swagger-ui"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.17.14/swagger-ui-bundle.min.js"></script>
<script>
  window.onload = function() {
    SwaggerUIBundle({
      url: "/docs/openapi.json",
      dom_id: '#swagger-ui',
      presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
      layout: "BaseLayout",
      deepLinking: true,
      defaultModelsExpandDepth: 1,
      defaultModelExpandDepth: 2,
      tryItOutEnabled: true,
      requestInterceptor: function(req) {
        // Persist the TOKEN header across "Try it out" calls
        var stored = localStorage.getItem('cera_token');
        if (stored && !req.headers['TOKEN']) req.headers['TOKEN'] = stored;
        return req;
      }
    });
  }
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_swagger(app: Flask) -> None:
    """Attach the /docs blueprint to *app*.

    This function is called once from ``create_app()`` and is the only
    coupling point between the docs module and the rest of the application.
    The spec is rebuilt lazily on the first request so that it always
    reflects the current ``app.config`` (e.g. ``SERVER_PATH``).
    """
    docs_bp = Blueprint("docs", __name__, url_prefix="/docs")
    _spec_cache: list[dict] = []  # mutable cell so the closure can write to it

    @docs_bp.get("")
    @docs_bp.get("/")
    def swagger_ui():
        return _SWAGGER_UI_HTML, 200, {"Content-Type": "text/html"}

    @docs_bp.get("/openapi.json")
    def openapi_spec():
        if not _spec_cache:
            _spec_cache.append(_build_spec(app))
        return jsonify(_spec_cache[0])

    app.register_blueprint(docs_bp)
