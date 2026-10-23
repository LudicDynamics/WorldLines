"""In-process ring buffer of recent LLM call records, for the debug panel.

The engine (``llm_anthropic``, ``agent_runner``, …) calls
``record_llm_call`` after each completed LLM turn. The TUI's debug panel
polls ``get_recent_calls`` on a refresh tick. Both ends are guarded by
``DEBUG_ENABLED``: when off, ``record_llm_call`` is a no-op and the panel
never imports.

Synchronous, thread-safe append. The buffer is capped (``_MAX_RECORDS``)
so a long session can't grow it unbounded.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from neonrp.core.debug_flag import is_enabled

_MAX_RECORDS = 200

_lock = threading.Lock()
_records: deque[dict[str, Any]] = deque(maxlen=_MAX_RECORDS)
_seq = 0


def record_llm_call(record: dict[str, Any]) -> None:
    """Append one LLM-call record. No-op when debug is disabled.

    Caller supplies a JSON-able dict; ``seq`` and ``ts`` are stamped here
    so every record has monotonic ordering and a wall clock.
    """
    if not is_enabled():
        return
    global _seq
    with _lock:
        _seq += 1
        record = dict(record)
        record.setdefault("seq", _seq)
        record.setdefault("ts", time.time())
        _records.append(record)


def get_recent_calls(limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent ``limit`` records, newest last. Empty list
    when debug is disabled."""
    if not is_enabled():
        return []
    with _lock:
        if limit >= len(_records):
            return list(_records)
        return list(_records)[-limit:]


def clear() -> None:
    """Drop all buffered records (tests / panel "clear" action)."""
    if not is_enabled():
        return
    with _lock:
        _records.clear()


def latest_seq() -> int:
    """Monotonic counter — the panel uses this to decide whether to
    repaint without copying the buffer."""
    if not is_enabled():
        return 0
    with _lock:
        return _seq
