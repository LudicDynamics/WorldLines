"""Effects — open-schema instances that run by themselves (状态效果不该自己写代码,开放 schema 加上就能用).

A class registered with ``effect: true`` makes its instances effects. Props, all optional:

    on      who it sits on (an entry id or name; default the player)
    turns   turns left; the engine counts it down each turn and removes the instance at 0 (absent = until removed)
    check   a modifier added to that one's checks (the referee and dice read it)
    each    per-turn variable changes, ``var:delta`` comma-separated (``player.hp:-1,player.gold:-1``)

Nothing here knows any particular effect: a world names them (the narrator creates them with ``new <class> …``);
this module only counts, applies and removes. Specific names belong in worlds and tests, never in engine code.
"""
from __future__ import annotations

import re
from typing import Any

from neonrp.core.registry import Envelope, Registry

_EACH_RE = re.compile(r"^\s*([A-Za-z_][\w.\-]*)\s*:\s*([+-]?\d+)\s*$")


def effect_classes(reg: Registry) -> list[str]:
    return [c.name for c in reg.classes.values() if getattr(c, "effect", False)]


def instances(reg: Registry, who: str | None = "player") -> list[Envelope]:
    """Effects sitting on ``who`` (``None`` = all effects)."""
    out = []
    target = reg.resolve(who) if who else None
    for cls in effect_classes(reg):
        for e in reg.of_class(cls):
            if who is None:
                out.append(e)
                continue
            on = str(e.props.get("on") or "player")
            if on == who or (target and reg.resolve(on) == target):
                out.append(e)
    return out


def check_mod(reg: Registry, who: str = "player") -> int:
    total = 0
    for e in instances(reg, who):
        try:
            total += int(e.props.get("check") or 0)
        except (TypeError, ValueError):
            continue
    return total


def describe(reg: Registry, who: str = "player") -> str:
    """One line per effect on ``who`` — for the referee's and the narrator's view."""
    rows = []
    for e in instances(reg, who):
        bits = [str(e.name)]
        if e.props.get("turns") not in (None, ""):
            bits.append(f"剩 {e.props.get('turns')} 回合")
        if e.props.get("check") not in (None, "", 0, "0"):
            bits.append(f"检定 {int(e.props['check']):+d}")
        if e.props.get("each"):
            bits.append(f"每回合 {e.props['each']}")
        if e.props.get("note"):
            bits.append(str(e.props["note"]))
        rows.append(" · ".join(bits))
    return "\n".join(rows)


def parse_each(each: Any) -> list[tuple[str, int]]:
    """``var:delta`` pairs; older saves and models also wrote ``player.hp -1`` / ``player.hp+2`` (normalised first)."""
    from neonrp.core.effect_rules import normalize_each

    out = []
    for part in normalize_each(each).split(","):
        m = _EACH_RE.match(part)
        if m:
            out.append((m.group(1), int(m.group(2))))
    return out


def tick_ops(reg: Registry, *, skip: set[str] | None = None) -> list[dict[str, Any]]:
    """This turn's effect ops: each instance's per-turn changes, then its countdown (patch turns-1, or remove at 0).
    Instances created this turn (``skip``) start next turn."""
    ops: list[dict[str, Any]] = []
    for e in instances(reg, None):
        if skip and e.id in skip:
            continue
        on = str(e.props.get("on") or "player")
        for var, delta in parse_each(e.props.get("each")):
            if on != "player" and var.startswith("player."):
                # the rule line is written for the player; on someone else it hits their own counter, never the player's
                var = f"char.{on}.{var[len('player.'):]}"
            if var in reg.variables:
                ops.append({"op": "add", "var": var, "delta": delta, "_effect": e.id})
        t = e.props.get("turns")
        if t in (None, ""):
            continue
        try:
            left = int(t) - 1
        except (TypeError, ValueError):
            continue
        ops.append({"op": "remove", "who": e.id} if left <= 0 else {"op": "patch", "who": e.id, "props": {"turns": left}})
    return ops
