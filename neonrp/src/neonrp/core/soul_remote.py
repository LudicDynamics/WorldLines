"""Characters played from elsewhere (10-10).

A character whose seat is taken by a remote participant answers through the network: the host registers a route for
her instance id while her seat is connected; ``light_chat.ask_soul_deliver`` sends the question there and waits up to a
deadline. No answer in time (or no one connected) → the host stands in for her, from what it holds of her (her public
card), and the answer is marked ``proxy`` (「代」) — the turn never waits on someone who is not there.

Her persona and memory live with her player (design B): a remote answer is not written into the host's copy of her.

A character played by a **person** (``human=True``) is never stood in for: no answer in time = she hesitates this turn
(the player's words are only the player's, 10-10).
"""
from __future__ import annotations

import threading
from typing import Any, Callable

ASK_TIMEOUT = 10.0  # s — a question mid-beat (soft 8 s / hard 30 s are the per-turn deadlines)

Route = Callable[..., Any]  # route(question=..., beat=..., timeout=...) -> str | None

_lock = threading.Lock()
HUMAN_TIMEOUT = 30.0  # s — a person gets the hard deadline, not the mid-beat one

_routes: dict[str, Route] = {}
_human: set[str] = set()


def register(iid: str, route: Route, *, human: bool = False) -> None:
    with _lock:
        _routes[str(iid)] = route
        (_human.add if human else _human.discard)(str(iid))


def is_human(iid: str) -> bool:
    with _lock:
        return str(iid) in _human


def unregister(iid: str, route: Route | None = None) -> None:
    """Drop the route (only that one, when given — a newer connection of the same seat keeps its own)."""
    with _lock:
        if route is None or _routes.get(str(iid)) is route:
            _routes.pop(str(iid), None)
            _human.discard(str(iid))


def route(iid: str) -> Route | None:
    with _lock:
        return _routes.get(str(iid))


def remote_iids() -> list[str]:
    with _lock:
        return sorted(_routes)
