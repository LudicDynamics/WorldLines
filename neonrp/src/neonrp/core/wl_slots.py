"""How many requests this engine has open at ai.worldlines.gg at once (10-25 funnel check: 20 × 429 ``concurrency_limit``
in one run — the story plan allows 3 open requests per account, chat and System One together, and the engine had 3 chat
lanes open while it fired 8 System One questions in one second).

- every Worldlines call takes a slot first; at most :data:`limit` are open (``NEONRP_WL_CONCURRENCY``, default 3);
- System One holds at most one of them (``NEONRP_S1_CONCURRENCY``, default 1) and waits in line for it no longer than
  its own timeout — then the question takes the no-Jev path instead of a 429;
- a chat call waits for a slot as long as its beat allows, then goes anyway (a slot is a courtesy, never a deadlock).
A stream keeps its slot until it is closed (core/llm_openai._closing). One process only: other processes on the machine
share the account's limit, which is why a 429 still backs off by ``Retry-After``."""
from __future__ import annotations

import os
import threading
import time
import weakref
from typing import Any, Callable

_cond = threading.Condition()
_open = {"all": 0, "s1": 0}
CHAT_WAIT_S = 120.0


def _num(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


def limit() -> int:
    return _num("NEONRP_WL_CONCURRENCY", 3)


def s1_limit() -> int:
    return min(limit(), _num("NEONRP_S1_CONCURRENCY", 1))


def _noop() -> None:
    return None


def acquire(kind: str, timeout: float | None = None) -> Callable[[], None] | None:
    """Wait for a slot. → a release function (idempotent), or None when System One did not get one in ``timeout``.
    A chat call that waits too long gets a no-op release and goes ahead."""
    s1 = kind == "s1"
    wait = timeout if timeout is not None else CHAT_WAIT_S
    deadline = time.monotonic() + max(0.0, wait)
    with _cond:
        while _open["all"] >= limit() or (s1 and _open["s1"] >= s1_limit()):
            left = deadline - time.monotonic()
            if left <= 0:
                return None if s1 else _noop
            _cond.wait(left)
        _open["all"] += 1
        if s1:
            _open["s1"] += 1
    done = threading.Event()

    def release() -> None:
        with _cond:
            if done.is_set():
                return
            done.set()
            _open["all"] -= 1
            if s1:
                _open["s1"] -= 1
            _cond.notify_all()

    return release


def hold_until_closed(stream: Any, release: Callable[[], None]) -> Any:
    """A stream keeps its slot until ``_closing`` ends it — or, never iterated, until it is collected."""
    try:
        stream._wl_slot_release = release
        weakref.finalize(stream, release)
    except (AttributeError, TypeError):  # an object that takes no attributes (a test's stand-in): give the slot back now
        release()
    return stream


def in_use() -> dict[str, int]:
    with _cond:
        return dict(_open)
