"""P0 understanding: read the player's words against the world before anyone reacts. The player is one
actor among the souls, so what they say is an *attempt*, and every thing they mention is checked against the world:
here / elsewhere / only known to a town / absent. The same block goes to the souls (so nobody vouches for a phantom)
and to the narrator. Rule-only (alias tables), a few ms; P1 (Jev) and P2 (a small model) build on the same output."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from neonrp.packs.rpg import data
from neonrp.packs.rpg.i18n import lang_of, t as _t


def _foe_grounds(root: Path, reg: Any) -> dict[str, str]:
    """Foe id → why it is here: a pending road stop, this room's encounter table, or the fight under way."""
    from neonrp.packs.rpg import combat, travel

    out: dict[str, str] = {}
    j = travel.journey(root)
    if j and j.get("pending"):
        tag = str(j["pending"].get("tag"))
        hz = data.table(root, "hazards").get(tag) or {}  # the stop's foes from the hazards table (no tag named in code, 10-01)
        for fid in [*(hz.get("foes") or {}), *(hz.get("also") or [])]:
            out[str(fid)] = _t(root, "und_why_stop")
    here = reg.entries.get(reg.player_location or "")
    if here is not None and here.cls == "road":  # on a road the map tags with a danger (beasts, bandits …): its foes (10-19 M9)
        rf = travel.route_facts(root, str(here.props.get("from") or ""), str(here.props.get("to") or ""))
        for tag in rf.get("tags") or []:
            hz = data.table(root, "hazards").get(str(tag)) or {}
            for fid in [*(hz.get("foes") or {}), *(hz.get("also") or [])]:
                out.setdefault(str(fid), _t(root, "und_why_road"))
    if here is not None and here.cls == "room":
        for row in here.props.get("encounters") or []:
            fid = data.foe_key(root, str(row.get("enemy")))
            if fid:
                out.setdefault(fid, _t(root, "und_why_room"))
    for f in combat.standing(combat.read(root)).values():
        out.setdefault(str(f.get("kind")), _t(root, "und_why_fight"))
    return out


def _said(text: str, names: list[str]) -> str | None:
    for n in sorted({x for x in names if x and len(x) >= 2}, key=len, reverse=True):
        if re.search(re.escape(n), text, re.IGNORECASE):
            return n
    return None


def understand(root: Path, reg: Any, user_text: str) -> dict[str, Any]:
    """{"refs": [{said, kind, id, status, where?, why?}], "attempt": user_text, "block": text for souls and narrator}."""
    text = str(user_text or "")
    if not text.strip():
        return {}
    here = reg.player_location
    refs: list[dict[str, Any]] = []
    for e in [*reg.of_class("soul"), *reg.of_class("npc")]:
        said = _said(text, [e.name, *[a for a in e.aliases if isinstance(a, str)]])
        if not said:
            continue
        if here and e.parent == here:
            refs.append({"said": said, "kind": e.cls, "id": e.id, "status": "here"})
            continue
        w = reg.entries.get(e.parent or "")
        status = "town_only" if (w is not None and w.cls in ("town", "region")) else "elsewhere"
        refs.append({"said": said, "kind": e.cls, "id": e.id, "status": status, "where": f"{w.name}({e.parent})" if w is not None else str(e.parent)})
    grounds = _foe_grounds(root, reg)
    lang = lang_of(root)
    taken = {r["said"].lower() for r in refs}
    for fid, f in data.table(root, "foes").items():
        if fid == "foe":
            continue
        said = _said(text, [*((f.get("names") or {}).values()), *(f.get("aliases") or [])])
        if not said or said.lower() in taken:
            continue
        name = data.pick(f.get("names"), lang) or said
        if fid in grounds:
            refs.append({"said": said, "kind": "foe", "id": fid, "status": "here", "name": name, "why": grounds[fid]})
        else:
            refs.append({"said": said, "kind": "foe", "id": fid, "status": "absent", "name": name, "why": _t(root, "und_absent_why")})
    lines = [_t(root, "und_head"), _t(root, "und_attempt", said=text.strip()[:300])]
    for r in refs:
        nm = r.get("name") or (reg.entries[r["id"]].name if r["id"] in reg.entries else r["said"])
        if r["status"] == "here":
            lines.append(_t(root, "und_foe_here", name=nm, why=r["why"]) if r["kind"] == "foe" else _t(root, "und_here", name=nm))
        elif r["status"] == "absent":
            lines.append(_t(root, "und_absent", name=nm, why=r["why"]))
        elif r["status"] == "town_only":
            lines.append(_t(root, "und_town_only", name=nm, where=r["where"]))
        else:
            lines.append(_t(root, "und_elsewhere", name=nm, where=r["where"]))
    from neonrp.packs.rpg.gates import SHEET_RE

    if SHEET_RE.search(text):  # the panel is shown by the engine (gates); the prose stays in the world
        lines.append(_t(root, "und_sheet"))
    return {"refs": refs, "attempt": text.strip(), "block": "\n".join(lines)}


def combat_grounds(root: Path, reg: Any, op: dict[str, Any]) -> Any:
    """Validator for the <combat> switch. The world writing [combat …] is the encounter itself (niko 10-20: 「combat 这里
    其实就是遭遇了敌人,应该新建这个敌人,然后继续推进」): whoever its roster or hand-off names is spawned by the combat
    layer — a road stop's / a room's / the table's foe, someone here, or a new one by its own name. Only a tag that
    names nobody at all, with no stop, room encounter or fight under way to fall back on, is refused."""
    from neonrp.core.handlers import Verdict

    roster = " ".join(str(x) for x in (op.get("args") or [])) + " " + str(op.get("roster") or "")
    if roster.strip() or str(op.get("note") or "").strip() or _foe_grounds(root, reg):
        return Verdict(True, None)
    return Verdict(False, None, reason=_t(root, "no_grounds", who="?"), field="combat")
