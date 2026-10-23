"""pct's own tick (inside every apply, after the turn's ops):

- statuses the sanity tool left pending in the player's Character State (temporary / permanent insanity) become
  statuses (``new status <name>``, its line from the pack's status table);
- sanity at 0 → the ``insane`` event once (``{"op": "event", "event": "insane", "who": "player"}``) — the contract's
  ``deaths`` decides what that exit means;
- one blow of half the max hp or more (``major_wound_ratio``) → a 「重伤」 status on whoever took it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _name(root: Path, key: str) -> str:
    from neonrp.core.output_lang import pick_lang, prompt_lang
    from neonrp.packs.pct import rules as _r

    return pick_lang((_r.rules(root).get("effect_names") or {}).get(key) or {}, prompt_lang(root), key)


def _who_of_var(var: str) -> str | None:
    if var == "player.hp":
        return "player"
    parts = var.split(".")
    if len(parts) >= 3 and parts[0] in ("char", "foe") and parts[-1] == "hp":
        return ".".join(parts[1:-1])
    return None


def tick(root: Path, reg: Any, *, turn: int = 0, res: Any = None) -> list[dict[str, Any]]:
    from neonrp.core import effects
    from neonrp.packs.pct import rules as _r
    from neonrp.packs.rpg import character_state as cs

    R = _r.rules(root)
    ops: list[dict[str, Any]] = []
    have = {(e.props.get("on") or "player", e.name) for e in effects.instances(reg, None)}

    def add_status(who: str, key: str) -> None:
        n = _name(root, key)
        if (who, n) not in have:
            ops.append({"op": "new", "class": "status", "name": n, "props": {"on": who}})
            have.add((who, n))

    st = cs.read(root, "player")
    pend = list(st.get("pending_status") or [])
    if pend:
        for key in pend:
            add_status("player", str(key))
        cs.write(root, "player", pending_status=[])
    san = reg.variables.get("player.san")
    if san is not None and int(san.value or 0) <= 0 and not int(st.get("insane") or 0):
        cs.write(root, "player", insane=1)
        add_status("player", "insane_perm")
        if res is not None:
            res.applied.append({"op": "event", "who": "player", "event": "insane", "by": "tick:pct"})
    ratio = float(R.get("major_wound_ratio", 0.5))
    for a in list(getattr(res, "applied", None) or []):
        if a.get("op") not in ("set", "add") or str(a.get("by") or "").startswith("tick:"):
            continue
        who = _who_of_var(str(a.get("var") or ""))
        if who is None:
            continue
        e = reg.entries.get(who)
        before = a.get("from")
        if before is None and e is not None:  # her first blow: the state file had no hp yet — her hp before this apply
            before = e.props.get("hp")
        try:
            drop = int(before) - int(a.get("to"))
        except (TypeError, ValueError):
            continue
        mx = int((e.props.get("max_hp") if e is not None else 0) or 0)
        if e is not None and mx and drop >= mx * ratio:
            add_status(who, "major")
    return ops


# O7 (10-06): what this background unit may write (temporary / permanent madness, major wounds — statuses only)
tick.unit = {"on": "apply", "llm": False, "writes": ["op:new"]}  # type: ignore[attr-defined]
