"""pct's combat layer: rpg's one-shot node (roster, binding the world's own people, rounds) with percentile numbers —
each foe carries an attack skill % and a dodge %; the state block shows those, the player's fighting skills and damage
bonus. The rules themselves (attack d100 ≤ skill, dodge / parry as a contest, damage = weapon dice + bonus, a blow of
half the max hp → major wound) are the layer prompt's (packs/pct/prompts/combat.<lang>.md) and pct's tick."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def spawn(root: Path, reg: Any, *, note: str = "", turn: int = 0, room: Any = None, roster: str = "") -> dict[str, Any]:
    from neonrp.packs.pct import rules as _r
    from neonrp.packs.rpg import combat as _c, data

    st = _c.spawn(root, reg, note=note, turn=turn, room=room, roster=roster)
    table = data.table(root, "foes")
    R = _r.rules(root)
    for fid, f in (st.get("foes") or {}).items():
        ref = reg.entries.get(str(f.get("ref") or "")) if f.get("ref") else None
        if ref is not None:  # one of the world's own people: her own fighting skill and dodge
            vals = [_r.skill_value(R, ref, str((R.get("skills") or {}).get(k, {}).get("zh") or k)) for k in ("melee", "brawl")]
            f["skill"] = max((v for v in vals if v is not None), default=40)  # the better of her melee / brawl
            f["dodge"] = _r.skill_value(R, ref, "dodge") or 25
            continue
        base = table.get(str(f.get("kind") or "")) or table.get("foe") or {}
        f["skill"] = int(base.get("skill", 40))
        f["dodge"] = int(base.get("dodge", 25))
    return st


def state_block(root: Path, reg: Any) -> str:
    from neonrp import prompts
    from neonrp.core.output_lang import prompt_lang
    from neonrp.packs.pct import rules as _r
    from neonrp.packs.rpg import combat as _c

    st = _c.read(root)
    if not st:
        return ""
    lang = prompt_lang(root)
    S = prompts.strings("pct", lang)
    R = _r.rules(root)
    lines = [S["combat_head"].format(r=st.get("round", 1), note=st.get("note") or "—")]
    for fid, f in (st.get("foes") or {}).items():
        lines.append(S["combat_foe"].format(fid=fid, name=f.get("name"), hp=f.get("hp"), max=f.get("max_hp"), skill=f.get("skill", 40),
                                            dodge=f.get("dodge", 25), dmg=f.get("dmg"), down="" if int(f.get("hp", 0)) > 0 else S["combat_down"]))
    p = reg.entries.get("player")
    if p is not None:
        fight = []
        for key in ("brawl", "melee", "firearms", "dodge"):
            row = (R.get("skills") or {}).get(key) or {}
            n = str(row.get(lang) or row.get("en") or key)
            v = _r.skill_value(R, p, n)
            if v is not None:
                fight.append(f"{n} {v}%")
        lines.append(S["combat_player"].format(hp=p.props.get("hp"), max=p.props.get("max_hp"), skills=" · ".join(fight), db=_r.damage_bonus(R, p)))
    return "\n".join(lines)
