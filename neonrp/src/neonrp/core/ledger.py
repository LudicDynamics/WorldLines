"""Event ledger + hooks — the one outlet of ⑤ APPLY (ENGINE-V3-HOOKS-MVU-TOOLS-0926 §2).

Every landed change becomes one line in ``game/meta/events.jsonl``::

    {"seq": 1042, "turn": 17, "ts": "…", "type": "var.changed", "payload": {...}}

push:  ``on(pattern, fn) -> off``   in-process callbacks, called after the ledger is written,
                                    in seq order; a callback may only ``enqueue`` an op for the
                                    next turn (it never writes files).
pull:  ``events(root, since, type)`` / ``history(root, var, since_turn)``
queue: ``enqueue(root, op)`` → ``game/meta/op_queue.json``; ``turn_v3.solve_turn`` drains it into
       the next turn's verify, so outside logic stays inside the closure theorem.

Types (closed): turn.started · var.changed · flag.set · entry.entered · entity.created ·
entity.patched · entity.promoted · trigger.fired · tool.ran · tool.requested · soul.settled ·
narration.landed · turn.done
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from neonrp.core.paths import get_data_dir_name

logger = logging.getLogger(__name__)

TYPES = ("turn.started", "var.changed", "flag.set", "entry.entered", "entity.created", "entity.patched", "entity.promoted",
         "trigger.fired", "tool.ran", "tool.requested", "soul.settled", "narration.landed", "turn.ended", "turn.done")

_HOOKS: list[tuple[str, Callable[[dict[str, Any]], None]]] = []
_LOCK = threading.Lock()


def _meta(root: Path) -> Path:
    return root / get_data_dir_name(root) / "meta"


def _ledger(root: Path) -> Path:
    return _meta(root) / "events.jsonl"


def _state_path(root: Path) -> Path:
    return _meta(root) / "events_state.json"


# ── write ────────────────────────────────────────────────────────────────────

def append(root: Path, turn: int, items: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    """Append (type, payload) items as ledger lines; returns the written events (with seq)."""
    if not items:
        return []
    with _LOCK:
        try:
            seq = int(json.loads(_state_path(root).read_text(encoding="utf-8")).get("seq", 0))
        except (OSError, ValueError):
            seq = 0
        out: list[dict[str, Any]] = []
        ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        lines = []
        for typ, payload in items:
            if typ not in TYPES:
                logger.warning("ledger: unknown event type %r", typ)
            seq += 1
            ev = {"seq": seq, "turn": turn, "ts": ts, "type": typ, "payload": payload}
            out.append(ev)
            lines.append(json.dumps(ev, ensure_ascii=False))
        p = _ledger(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        _state_path(root).write_text(json.dumps({"seq": seq}), encoding="utf-8")
    _push(out)
    return out


def from_apply(res: Any) -> list[tuple[str, dict[str, Any]]]:
    """Turn an ApplyResult into ledger items (the single place that knows both shapes)."""
    items: list[tuple[str, dict[str, Any]]] = []
    for a in res.applied:
        op = a.get("op")
        if op in ("set", "add"):
            items.append(("var.changed", {"var": a.get("var"), "from": a.get("from"), "to": a.get("to"), "by": a.get("by") or "solve"}))
        elif op == "flag":
            items.append(("flag.set", {"key": a.get("key"), "from": a.get("from")}))
        elif op == "move_to":
            items.append(("entry.entered", {"who": a.get("who"), "entry": a.get("to")}))
        elif op == "patch":
            items.append(("entity.patched", {"who": a.get("who"), "props": a.get("props")}))
    for c in res.created:
        items.append(("entity.created", {k: v for k, v in c.items() if k != "op"}))
    for t in getattr(res, "triggered", None) or []:
        items.append(("trigger.fired", {"id": t.get("trigger"), "why": t.get("why"), "emitted": t.get("emitted"), "payload": t.get("payload")}))
    for r in res.requests:
        if r.get("kind") == "tool":
            items.append(("tool.requested", {"name": r.get("name"), "args": r.get("args"), "trigger": r.get("trigger")}))
    if getattr(res, "ended", None):
        items.append(("turn.ended", dict(res.ended)))
    if getattr(res, "settled", None):  # the run reached its exit: the fixed output (core/settlement.py, R5)
        items.append(("run.settled", {"exit": res.settled.get("exit"), "contract": res.settled.get("contract")}))
    items.append(("turn.done", {"applied": len(res.applied), "refused": len(res.refused), "created": len(res.created), "triggered": len(getattr(res, "triggered", None) or [])}))
    return items


# ── push ─────────────────────────────────────────────────────────────────────

def on(pattern: str, fn: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
    """Subscribe. pattern = "*" | "<type>" | "<type>:<key>" | "<type>:*" (key = var name / trigger id / entry id / who)."""
    entry = (pattern, fn)
    _HOOKS.append(entry)

    def off() -> None:
        try:
            _HOOKS.remove(entry)
        except ValueError:
            pass
    return off


def _key_of(ev: dict[str, Any]) -> str:
    p = ev.get("payload") or {}
    return str(p.get("var") or p.get("id") or p.get("key") or p.get("who") or p.get("entry") or p.get("name") or "")


def _matches(pattern: str, ev: dict[str, Any]) -> bool:
    if pattern == "*":
        return True
    typ, _, key = pattern.partition(":")
    if typ != ev.get("type") and typ != "*":
        return False
    return key in ("", "*") or key == _key_of(ev)


def _push(events: list[dict[str, Any]]) -> None:
    for ev in events:
        for pattern, fn in list(_HOOKS):
            if _matches(pattern, ev):
                try:
                    fn(ev)
                except Exception:  # noqa: BLE001 — a subscriber never breaks the turn
                    logger.warning("ledger hook %r failed", pattern, exc_info=True)


def clear_hooks() -> None:
    _HOOKS.clear()


# ── pull ─────────────────────────────────────────────────────────────────────

def events(root: Path, *, since: int = 0, type: str | None = None, limit: int = 500) -> list[dict[str, Any]]:  # noqa: A002
    p = _ledger(root)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if int(ev.get("seq", 0)) <= since:
                continue
            if type and ev.get("type") != type:
                continue
            out.append(ev)
    return out[-limit:]


def history(root: Path, var: str, *, since_turn: int = 0) -> list[dict[str, Any]]:
    """A variable's changes: [{turn, from, to, by, seq}]."""
    return [{"turn": ev["turn"], "seq": ev["seq"], **ev["payload"]} for ev in events(root, type="var.changed")
            if ev["payload"].get("var") == var and int(ev.get("turn", 0)) >= since_turn]


# ── queue (the only thing a hook may do) ─────────────────────────────────────

def _queue_path(root: Path) -> Path:
    return _meta(root) / "op_queue.json"


def enqueue(root: Path, op: dict[str, Any], *, by: str = "hook") -> int:
    """Queue an op for the next turn's verify. Returns queue length."""
    p = _queue_path(root)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    q = data.get("ops") if isinstance(data.get("ops"), list) else []
    q.append({**op, "_by": by})
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"ops": q}, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(q)


def drain(root: Path) -> list[dict[str, Any]]:
    """Take (and clear) the queued ops."""
    p = _queue_path(root)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    q = data.get("ops") if isinstance(data.get("ops"), list) else []
    if q:
        p.write_text(json.dumps({"ops": []}), encoding="utf-8")
    return [dict(o) for o in q]
