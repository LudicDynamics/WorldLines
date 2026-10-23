"""Every tool call goes through here (「所有的工具调用可以用一个和工具调用绑定的函数去做监视函数,
调用之后 trigger 一个外部调用的函数,里面有写工具的名字」).

    call(root, reg, name, handler, op, res, *, seed, source)   run the tool, then notify
    watch(fn, tools="*")  -> unwatch                           fn(event) after each call of those tools

The event: {"tool": name, "args": {...}, "result": {...}, "source": "narrator" | "referee" | "plan" | …, "turn": n}
(watchers also get "root": the world it ran in).
It is also written to the ledger as ``tool.ran`` (so a replay sees it). A watcher is outside the engine — a frontend
playing the dice animation for ``dice``, a sound for ``map``, a log — it is told, it never changes the turn; a watcher
that raises is logged and skipped. The random numbers stay in the tool (``dice`` → core/dice's backend, seeded).
"""
from __future__ import annotations

import fnmatch
import json
import logging
import threading
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_WATCHERS: list[tuple[str, Callable[[dict[str, Any]], None]]] = []
_LOCK = threading.Lock()


def watch(fn: Callable[[dict[str, Any]], None], tools: str = "*") -> Callable[[], None]:
    """Register ``fn`` for tools matching ``tools`` (a name, a glob, or "*"). Returns the function that unregisters it."""
    item = (tools, fn)
    with _LOCK:
        _WATCHERS.append(item)

    def unwatch() -> None:
        with _LOCK:
            if item in _WATCHERS:
                _WATCHERS.remove(item)
    return unwatch


def clear() -> None:
    with _LOCK:
        _WATCHERS.clear()


def _jsonable(x: Any) -> Any:
    try:
        json.dumps(x, ensure_ascii=False)
        return x
    except (TypeError, ValueError):
        return str(x)


def notify(root: Path, name: str, args: dict[str, Any], result: Any, *, source: str = "narrator", turn: int | None = None,
           record: bool = True) -> dict[str, Any]:
    ev = {"tool": name, "args": {k: _jsonable(v) for k, v in (args or {}).items() if not str(k).startswith("_")},
          "result": _jsonable(result), "source": source}
    if record:  # planning writes nothing to the world (10-03 llm2 PL1: a read in the talk touched events.jsonl)
        try:
            from neonrp.core import ledger

            if turn is None:
                try:
                    from neonrp.core.paths import get_data_dir_name

                    rs = json.loads((root / get_data_dir_name(root) / "meta" / "run_state.json").read_text(encoding="utf-8"))
                    turn = int(rs.get("turn_count", 0) or 0)
                except (OSError, ValueError):
                    turn = 0
            ev["turn"] = turn
            ledger.append(root, int(turn), [("tool.ran", ev)])
            if name == "dice":  # a named check is heard by the world's `check` triggers (core/triggers.py)
                from neonrp.core import triggers as _triggers

                _triggers.record_check(root, int(turn), ev["args"], result)
        except Exception:  # noqa: BLE001 — telling never breaks a turn
            logger.debug("tool.ran not recorded", exc_info=True)
    with _LOCK:
        watchers = list(_WATCHERS)
    for pattern, fn in watchers:
        if pattern == "*" or fnmatch.fnmatch(name, pattern):
            try:
                fn({**ev, "root": str(root)})  # which world it ran in (a watcher per session filters on it)
            except Exception:  # noqa: BLE001
                logger.warning("tool watcher for %s failed", name, exc_info=True)
    return ev


def call(root: Path, reg: Any, name: str, handler: str, op: dict[str, Any], res: Any = None, *, seed: str = "",
         source: str = "narrator", turn: int | None = None) -> Any:
    """Run a registered tool (its handler path), then notify the watchers with its name, arguments and result."""
    from neonrp.core.handlers import resolve

    args = {k: v for k, v in (op or {}).items() if not str(k).startswith("_")}
    out = resolve(handler)(root, reg, dict(args), res, seed=seed)
    notify(root, name, args, out, source=source, turn=turn)
    return out
