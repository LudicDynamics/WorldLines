"""Named handlers — the seam between the engine and a template's mechanics.

An action in ``actions.json`` names what checks it (``validator``) and what lands it
(``handler``). The engine never calls a map or a mover directly; it resolves the name:

    "builtin:map.judge"        one of the engine's reference handlers (this module)
    "mypkg.mymap:judge"        any importable ``module:function`` — an external SDK

Move validator contract:  fn(root, reg, who, cur, to) -> Verdict
Move handler contract:    fn(root, reg, who, to) -> bool

The rpg template's graph judge / mover live in ``neonrp.packs.rpg.map`` (registered under the
compat names ``builtin:map.judge`` / ``builtin:map.move`` when that pack loads); a template that
registers ``{"move_to": {"validator": "board:judge"}}`` replaces the map without touching the engine.
"""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class Verdict:
    ok: bool
    to: str | None = None  # where the move lands (may differ from the ask: alias resolved, or clamped)
    clamped: bool = False
    reason: str = ""
    allowed: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)  # template ops: normalised fields merged into the accepted op
    scope: str = "world"  # refusal scope when not ok: field | entity | world
    field: str = "op"  # refusal field when not ok
    fixable: bool = True  # False = do not re-propose (e.g. "already exists")


class HandlerError(ValueError):
    pass


def resolve(name: str) -> Callable[..., Any]:
    """``builtin:x.y`` from the table below, or ``module.path:function`` imported."""
    name = str(name or "").strip()
    if not name:
        raise HandlerError("empty handler name")
    if name.startswith("builtin:"):
        fn = BUILTIN.get(name[len("builtin:"):])
        if fn is None:
            raise HandlerError(f"unknown builtin handler {name!r}; have {sorted(BUILTIN)}")
        return fn
    mod, _, attr = name.partition(":")
    if not mod or not attr:
        raise HandlerError(f"handler must be 'builtin:name' or 'module:function', got {name!r}")
    try:
        return getattr(importlib.import_module(mod), attr)
    except (ImportError, AttributeError) as exc:
        raise HandlerError(f"cannot import handler {name!r}: {exc}") from exc


BUILTIN: dict[str, Callable[..., Any]] = {}  # filled by core/mechanics (generic) and by template packs on import
