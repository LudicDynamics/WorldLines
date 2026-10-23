"""Wire format: JSON-RPC 2.0 (the envelope MCP and A2A also use — 10-10: no protocol of our own invention), plus a thin
session layer for a turn-based world.

Client → host (POST /rpc):   {"jsonrpc": "2.0", "id": 1, "method": "turn.send", "params": {...}}
Host → client (SSE /rpc/events), each event one JSON-RPC message:
    notification   {"jsonrpc": "2.0", "method": "bus.message", "params": {"topic", "seq", "payload"}}
    request        {"jsonrpc": "2.0", "id": "h3", "method": "ask_user", "params": {...}}   ← answered with POST
                   {"jsonrpc": "2.0", "id": 9, "method": "reply", "params": {"id": "h3", "result": ...}}

Session layer: ``session.hello`` exchanges the protocol version first; every bus notification carries the bus ``seq``
so a client that reconnects can ask for what it missed (``since``).
"""
from __future__ import annotations

import itertools
import json
from typing import Any

PROTOCOL = "worldlines.net/1"
JSONRPC = "2.0"

# JSON-RPC 2.0 error codes (spec) + ours in the implementation-defined range
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR = -32700, -32600, -32601, -32602, -32603
UNAUTHORIZED, BUSY, VERSION_MISMATCH, NO_SESSION, FORBIDDEN = -32001, -32002, -32003, -32004, -32005

_ids = itertools.count(1)


def request(method: str, params: dict[str, Any] | None = None, *, id: Any = None) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC, "id": next(_ids) if id is None else id, "method": method, "params": dict(params or {})}


def notification(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC, "method": method, "params": dict(params or {})}


def result(id: Any, value: Any) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC, "id": id, "result": value}


def error(id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": JSONRPC, "id": id, "error": err}


def parse(raw: bytes | str) -> dict[str, Any]:
    """One JSON-RPC message, or a ValueError naming what is wrong."""
    try:
        d = json.loads(raw)
    except (ValueError, TypeError) as e:
        raise ValueError(f"parse error: {e}") from e
    if not isinstance(d, dict) or d.get("jsonrpc") != JSONRPC:
        raise ValueError("not a JSON-RPC 2.0 message")
    return d


def dumps(msg: dict[str, Any]) -> str:
    return json.dumps(msg, ensure_ascii=False, default=str)


class RpcError(RuntimeError):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"[{code}] {message}")
        self.code, self.message, self.data = code, message, data
