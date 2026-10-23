"""Per-turn collector of upstream request ids: every model / Jev response from ai.worldlines.gg carries
``x-request-id``; the turn records them so a local run binds to the api's usage rows (chronicle ``runs.request_ids``).

Thread-safe, process-global, reset by the turn loop. Providers that send no id add nothing."""
from __future__ import annotations

import threading
from typing import Any

_LOCK = threading.Lock()
_IDS: list[dict[str, Any]] = []


def reset() -> None:
    with _LOCK:
        _IDS.clear()


def add(request_id: str | None, *, kind: str, **meta: Any) -> None:
    if not request_id:
        return
    with _LOCK:
        _IDS.append({"id": str(request_id), "kind": kind, **{k: v for k, v in meta.items() if v is not None}})


def take() -> list[dict[str, Any]]:
    with _LOCK:
        out = list(_IDS)
        _IDS.clear()
        return out


def peek() -> list[dict[str, Any]]:
    with _LOCK:
        return list(_IDS)
