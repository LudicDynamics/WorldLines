"""The pack's interaction points for the contract: every tag a model may write that stops the stream or
switches the layer, and every card the screen may show — so an SDK / Godot / TS client knows the turn's shape without
reading the engine. Derived from the registry (ActionSpec kinds) and ``Pack.modes`` (layers and their panels); nothing
here is hardcoded to rpg.

Shape (``worldlines.contract`` → ``"interaction"``)::

    {"requests": [{"tag", "form", "kind": "tool|request", "args", "reply", "writers", "layer"?}],  # layer: a one-shot node it calls
     "switches": [{"tag", "form", "layer", "exit", "writers"}],
     "exits":    [{"op", "form", "layer"}],
     "panels":   [{"id", "source": "layer|tool", "layer"?, "tool"?, "format"}],
     "engine":   [{"id", "what"}]}             # engine-initiated points (gate, road stop, encounter)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _form(a: Any) -> str:
    name = a.alias or a.op
    args = " ".join(f"<{f}>" for f in a.fields)
    head = f"{name} {args}".strip()
    if a.kind == "mode":
        roster = " <roster>" if "roster" in a.fields else ""
        return f"<{name}{roster}>{'<note>' if 'note' in a.fields else ''}</{name}>"
    if "note" in a.fields:  # a one-shot layer's call carries a body: [combat <roster>]<note>[/combat]
        head = f"{name} " + " ".join(f"<{f}>" for f in a.fields if f != "note")
        return f"[{head.strip()}]<note>[/{name}]"
    body = f"…[/{name}]" if a.op == "dice" else ""
    return f"[{head}]{body}"


def interaction_points(root: Path, reg: Any) -> dict[str, Any]:
    from neonrp.packs import resolve as _resolve_pack

    modes = dict(getattr(_resolve_pack(root), "modes", {}) or {})
    layer_ops: dict[str, list[str]] = {name: list(spec.get("ops") or []) + ([spec["exit"]] if spec.get("exit") else [])
                                       for name, spec in modes.items() if isinstance(spec, dict)}

    def writers(op: str) -> list[str]:
        w = ["narrator"] + [f"layer:{n}" for n, ops in layer_ops.items() if op in ops]
        return w

    out: dict[str, Any] = {"requests": [], "switches": [], "exits": [], "panels": [], "engine": []}
    exits = {str(spec.get("exit")): name for name, spec in modes.items() if isinstance(spec, dict) and spec.get("exit")}
    for a in reg.actions.values():
        if not a.enabled or a.scope != "world":
            continue
        if a.kind in ("tool", "request"):
            reply = f"<{a.alias or a.op} …>text</{a.alias or a.op}>" if a.kind == "tool" else "<say name …>line</say>"
            out["requests"].append({"tag": a.alias or a.op, "form": _form(a), "kind": a.kind, "args": list(a.fields), "reply": reply,
                                    "writers": writers(a.op), "doc": a.doc,
                                    **({"layer": a.op} if (modes.get(a.op) or {}).get("one_shot") else {})})
        elif a.kind == "mode":
            spec = modes.get(a.op) or {}
            out["switches"].append({"tag": a.alias or a.op, "form": _form(a), "layer": a.op, "exit": spec.get("exit"),
                                    "writers": ["narrator"], "doc": a.doc})
        elif a.op in exits:
            out["exits"].append({"op": a.op, "form": f"{a.op} " + " ".join(f"{f}=…" for f in a.fields), "layer": exits[a.op]})
    for name, spec in modes.items():
        if not isinstance(spec, dict):
            continue
        for pid, pdoc in (spec.get("panels") or {}).items():
            fmt = (pdoc.get("format") if isinstance(pdoc, dict) else None) or "text"
            out["panels"].append({"id": pid, "source": "layer", "layer": name, "tag": f"<{pid}>…</{pid}>", "format": fmt})
        if spec.get("here_class"):
            out["engine"].append({"id": f"layer:{name}", "what": f"the whole prompt switches to the {name} layer while the player stands in a {spec['here_class']}"})
    for a in reg.actions.values():  # engine-drawn cards: a tool whose handler returns a panel (rpg [map])
        if a.enabled and a.kind == "tool" and a.op == "map":
            out["panels"].append({"id": "map", "source": "tool", "tool": a.op, "format": "text"})
    try:
        from neonrp.core import mechanics

        spec_m = mechanics.spec(root)
        if spec_m.get("gate") and spec_m["gate"] != "builtin:none":
            out["engine"].append({"id": "gate", "what": "before the narrator writes, the pack may rule or fire a tool itself (e.g. draw the map when the player asks the way)"})
        if spec_m.get("post_solve") and spec_m["post_solve"] != "builtin:none":
            out["engine"].append({"id": "post_solve", "what": "the pack's rules on the prose may refuse once and ask for a rewrite"})
    except Exception:  # noqa: BLE001 — a contract is still useful without the seams
        pass
    return out
