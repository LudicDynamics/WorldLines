"""Character State — what is changing about a character in this run.

Souls and NPCs are one system here. The author's record is the base (a soul's ``character/stats.json``, an NPC's row in
``npcs.json``) and is never rewritten in play; what changes in this run lives in ``game/states/<id>.json``:

    hp / max_hp     only when the class's schema declares ``hp`` (「NPC 是否有血条是 Schema 决定的」)
    down            0 / 1 — able / down; every character has it (a world without hp judges only this)
    dead            0 / 1
    stable          0 / 1 — down but no longer rolling (the down rule's own outcome)
    down_pass / down_fail   the down rule's counters (packs/rpg/downed.py)

The registry entry of a character is its base with this state laid over it; the variables ``char.<id>.hp`` /
``char.<id>.down`` … point at the state file, so an op that hurts her lands here. A soul's folder stays clean and can
travel to another world.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

KEYS = ("hp", "max_hp", "down", "dead", "stable", "down_pass", "down_fail")
COUNTERS = ("down", "dead", "stable", "down_pass", "down_fail")


def _safe(eid: str) -> str:
    return re.sub(r"[^\w.\-]", "_", str(eid))


def rel_path(root: Path, eid: str) -> str:
    from neonrp.core.paths import get_data_dir_name

    return f"{get_data_dir_name(root)}/states/{_safe(eid)}.json"


def read(root: Path, eid: str) -> dict[str, Any]:
    try:
        d = json.loads((Path(root) / rel_path(root, eid)).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def has_hp(reg: Any, cls: str) -> bool:
    """Whether this class has an hp bar: its schema declares ``hp``."""
    spec = getattr(reg, "classes", {}).get(cls)
    return bool(spec is not None and "hp" in (getattr(spec, "props", None) or {}))


def characters(reg: Any) -> list[Any]:
    return [*reg.of_class("soul"), *reg.of_class("npc")]


def overlay(reg: Any, default_hp: int) -> None:
    """Lay each character's run state over its base (in the registry entry). A class with hp in its schema whose record
    has none starts from the pack's default (rules.json ``npc_hp_default``)."""
    root = reg.root
    for e in characters(reg):
        st = read(root, e.id)
        if has_hp(reg, e.cls):
            base = e.props.get("hp")
            base = int(base) if isinstance(base, (int, float)) or str(base or "").isdigit() else default_hp
            mx = e.props.get("max_hp")
            mx = int(mx) if isinstance(mx, (int, float)) or str(mx or "").isdigit() else base
            e.props["max_hp"] = int(st.get("max_hp") or mx)
            e.props["hp"] = int(st["hp"]) if isinstance(st.get("hp"), (int, float)) else base
        else:
            e.props.pop("hp", None)
            e.props.pop("max_hp", None)
        for k in COUNTERS:
            e.props[k] = int(st.get(k) or 0)


def register_vars(reg: Any, var: Any) -> None:
    """``char.<id>.hp`` (classes with hp) and ``char.<id>.down`` … (everyone), stored in ``states/<id>.json``."""
    root = reg.root
    for e in characters(reg):
        p = rel_path(root, e.id)
        if has_hp(reg, e.cls) and e.props.get("hp") is not None:
            var(f"char.{e.id}.hp", "int", p, "hp", e.props.get("hp"), min=0, max=e.props.get("max_hp"),
                doc=f"{e.name} hp → 0 = down", about=e.id, rest=e.props.get("max_hp"))
        # only `down` is the model's to write (a world without hp judges able / down); dead / stable / the counters are
        # the down rule's own (packs/rpg/downed.py writes them) — not listed, so the variable list stays short
        var(f"char.{e.id}.down", "int", p, "down", e.props.get("down", 0), min=0, max=1, about=e.id, rest=0)
    # the player too has a down / dead state (her hp stays in player/stats.json)
    if "player" in reg.entries:
        st = read(root, "player")
        var("char.player.down", "int", rel_path(root, "player"), "down", int(st.get("down") or 0), min=0, max=1)
        for k in COUNTERS:
            reg.entries["player"].props[k] = int(st.get(k) or 0)


def write(root: Path, eid: str, **kv: Any) -> dict[str, Any]:
    """The rule's own write into a character's state (dead / stable / counters) — not an op. Returns the new state."""
    p = Path(root) / rel_path(root, eid)
    st = read(root, eid)
    st.update(kv)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return st


def hp_var(reg: Any, eid: str) -> str | None:
    """The variable holding this character's hp, if it has one."""
    if eid == "player":
        return "player.hp" if "player.hp" in reg.variables else None
    v = f"char.{eid}.hp"
    return v if v in reg.variables else None
