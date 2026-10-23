"""What a test bench needs to show a world without hand-written components (TESTBENCH-AUTOVIEW-1005 V1–V3, 10-06).

    view_schema(root)          V1  classes (props types · render line · title · folder) + variables + views / panels + units
    round_bundle(root, i)      V2  one round in one piece: node path · spans · tool calls · background units · diff
    var_history(root, var)     V3  a variable's values over the run (from the ledger's var.changed)

All read-only, computed from the registry, the pack, the orchestration graph, the traces and the ledger.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def view_schema(root: Path) -> dict[str, Any]:
    from neonrp.core import orchestration
    from neonrp.core.registry import load_registry

    reg = load_registry(root)
    classes = {}
    for name, c in sorted(reg.classes.items()):
        classes[name] = {"props": dict(getattr(c, "props", None) or {}), "render": getattr(c, "render", "") or "",
                         "title": getattr(c, "title", "") or "", "folder": str(getattr(c, "folder", "") or ""),
                         "mutable": list(getattr(c, "mutable", None) or []), "effect": bool(getattr(c, "effect", False)),
                         "count": len(reg.of_class(name))}
    variables = {k: {kk: vv for kk, vv in v.to_dict().items() if kk not in ("path", "key")} for k, v in sorted(reg.variables.items())}
    ui: dict[str, Any] = {}
    try:
        from neonrp.packs import resolve as _resolve_pack

        pk = _resolve_pack(root)
        ui = dict(getattr(pk, "ui", {}) or {})
        pack_name = str(getattr(pk, "name", ""))
    except Exception:  # noqa: BLE001
        pack_name = ""
    g = orchestration.graph(root)
    return {"schema": "worldlines.view-schema/1", "pack": pack_name, "classes": classes, "variables": variables,
            "views": ui.get("views") or [], "panels": ui.get("panels") or [], "slots": ui.get("slots") or [],
            "units": g.get("units") or [], "lint": g.get("lint") or []}


def round_bundle(root: Path, i: int, branch: str = "main") -> dict[str, Any] | None:
    """Round ``i`` (0-based, the traces' order): everything a bench tab reads, in one piece."""
    from neonrp.core.orchestration_trace import read_turn_traces

    trs = read_turn_traces(root, branch)
    if not (0 <= i < len(trs)):
        return None
    tr = trs[i]
    ap = tr.get("apply") or {}
    beat = ap.get("beat") if isinstance(ap.get("beat"), dict) else {}
    applied = list(ap.get("applied") or [])
    units: dict[str, list[dict[str, Any]]] = {}
    for a in applied:
        by = str(a.get("by") or "")
        if by.startswith("tick:"):
            units.setdefault(by[5:], []).append(a)
    return {"i": i, "turn_seq": tr.get("turn_seq"), "input": tr.get("player_input") or "",
            "nodes": [n for n in (beat.get("kind"), (ap.get("mode") or {}).get("name") if isinstance(ap.get("mode"), dict) else None) if n],
            "advanced_by": beat.get("advanced_by"), "spans": tr.get("spans") or [],
            "tools": [{k: x.get(k) for k in ("request", "text", "async") if k in x} for x in ap.get("tool_returns") or []],
            "units": units, "diff": {"applied": [a for a in applied if not str(a.get("by") or "").startswith("tick:")],
                                     "created": ap.get("created") or [], "refused": ap.get("refused") or []},
            "narration": ap.get("narration_plain") or "", "options": ap.get("options") or []}


def var_history(root: Path, var: str, limit: int = 2000) -> list[dict[str, Any]]:
    """[{turn, seq, from, to, by}] for ``var``, oldest first."""
    from neonrp.core import ledger

    out = []
    for e in ledger.events(root, type="var.changed", limit=limit):
        p = e.get("payload") or {}
        if p.get("var") == var:
            out.append({"turn": e.get("turn"), "seq": e.get("seq"), "from": p.get("from"), "to": p.get("to"), "by": p.get("by")})
    return out
