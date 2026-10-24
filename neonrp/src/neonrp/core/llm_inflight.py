"""Model streams in flight (10-18, iOS: the app was suspended while a turn was running — back in the foreground the
connection to the model is gone, and the turn hangs on a dead socket until its read timeout).

Every streamed model call registers here while it runs and marks each chunk it receives. A host that knows when the
process was frozen (the iOS shell's wl_host, on resume) asks :func:`quiet_since`: which streams opened before that moment
have not received a byte since. Those are dead: :func:`abort` shuts their sockets down, the blocked read fails at once,
and the call ends like any failed call (the caller's existing fallback runs). Nothing here is timed by itself and nothing
changes for a stream that keeps receiving.

Wall-clock time (``time.time``) on purpose: the monotonic clock does not count a phone's sleep.
"""
from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any

_lock = threading.Lock()
_calls: dict[int, "Call"] = {}
_seq = 0


@dataclass
class Call:
    kind: str
    started: float = field(default_factory=time.time)
    last: float = 0.0
    response: Any = None  # the httpx.Response under the stream, once it is open
    aborted: bool = False


def begin(kind: str = "stream") -> int:
    global _seq
    with _lock:
        _seq += 1
        _calls[_seq] = Call(kind)
        return _seq


def attach(token: int, response: Any) -> None:
    with _lock:
        c = _calls.get(token)
        if c is not None:
            c.response = response


def touch(token: int) -> None:
    c = _calls.get(token)
    if c is not None:
        c.last = time.time()


def end(token: int) -> None:
    with _lock:
        _calls.pop(token, None)


def snapshot() -> list[dict[str, Any]]:
    now = time.time()
    with _lock:
        return [{"kind": c.kind, "age_s": round(now - c.started, 1), "quiet_s": round(now - (c.last or c.started), 1),
                 "aborted": c.aborted} for c in _calls.values()]


def quiet_since(t: float) -> list[int]:
    """Streams opened before ``t`` that have not received a byte since ``t``."""
    with _lock:
        return [k for k, c in _calls.items() if c.started < t and c.last < t and not c.aborted]


def _shut(response: Any) -> bool:
    """Shut the socket under an httpx response down: the read blocked in the stream's own thread wakes with end-of-file
    and that thread closes the stream as usual (llm_openai._closing). Not response.close() from here: closing the fd
    under a thread that is polling it can leave that thread waiting forever (macOS), and closing takes the connection
    pool's lock from the wrong thread (the 10-11 hang)."""
    try:
        ns = (getattr(response, "extensions", None) or {}).get("network_stream")
        sock = ns.get_extra_info("socket") if ns is not None else None
        if sock is None:
            return False
        sock.shutdown(socket.SHUT_RDWR)
        return True
    except Exception:  # noqa: BLE001 — already closed / not a real socket
        return False


def abort(tokens: list[int] | None = None) -> int:
    """Cut these streams (default: every one in flight). Returns how many were cut."""
    with _lock:
        picked = [c for k, c in _calls.items() if (tokens is None or k in tokens) and not c.aborted]
        for c in picked:
            c.aborted = True
    return sum(1 for c in picked if c.response is not None and _shut(c.response))
