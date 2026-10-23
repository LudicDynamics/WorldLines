"""Class growth policy + the creator's approval queue (open schema governance; the 3.0 mock's pending / approve).

Each class carries a ``policy`` for instances the NARRATION tries to create with ``new`` (the model's op):

    auto     lands (default — nothing changes for worlds that never set a policy)
    approve  queued in ``game/meta/pending.json``; the creator approves (lands) or rejects
    creator  only the creator adds them (schema register / workbench); the model is refused
    forbid   nobody adds more

World rules (pack ticks, mixin handlers) are the world's own and are not gated. The policy is set like any
class field — ``registry.register(root, "classes", cls, {"policy": …})`` layers over the pack's class.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from neonrp.core.paths import get_data_dir_name

POLICIES = ("auto", "approve", "creator", "forbid")


def _path(root: Path) -> Path:
    return root / get_data_dir_name(root) / "meta" / "pending.json"


def _read(root: Path) -> list[dict[str, Any]]:
    try:
        d = json.loads(_path(root).read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _write(root: Path, rows: list[dict[str, Any]]) -> None:
    p = _path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def queue(root: Path, op: dict[str, Any], *, turn: int | None = None, by: str = "narration") -> dict[str, Any]:
    """Queue a `new` for approval (idempotent per class + name while it is open)."""
    rows = _read(root)
    clean = {k: v for k, v in op.items() if not str(k).startswith("_")}
    for r in rows:
        if r.get("status") == "open" and r["op"].get("class") == clean.get("class") and r["op"].get("name") == clean.get("name"):
            return r
    row = {"id": uuid.uuid4().hex[:10], "op": clean, "turn": turn, "by": by, "ts": time.time(), "status": "open"}
    rows.append(row)
    _write(root, rows)
    return row


def pending(root: Path, *, all_rows: bool = False) -> list[dict[str, Any]]:
    rows = _read(root)
    return rows if all_rows else [r for r in rows if r.get("status") == "open"]


def decide(root: Path, pid: str, approve: bool) -> dict[str, Any]:
    """Approve (the op lands now, through apply — as the creator's act) or reject. Returns the row."""
    rows = _read(root)
    row = next((r for r in rows if r.get("id") == pid), None)
    if row is None or row.get("status") != "open":
        raise KeyError(pid)
    if approve:
        from neonrp.core import sdk
        from neonrp.core.registry import load_registry

        reg = load_registry(root)
        vr = sdk.verify(root, [{**row["op"], "_approved": True}], reg)
        if not vr.accepted:
            row.update(status="failed", why=vr.refused[0].why if vr.refused else "refused")
        else:
            turn = int(reg.variables["turn"].value) if "turn" in reg.variables and reg.variables["turn"].value is not None else 0
            ar = sdk.apply(root, vr.accepted, reg, turn=turn)
            row.update(status="approved", created=[c.get("id") for c in ar.created])
    else:
        row["status"] = "rejected"
    row["decided_ts"] = time.time()
    _write(root, rows)
    return row
