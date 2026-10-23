"""The rpg writer ops — ``new_location`` / ``new_npc`` (rpg pack). Validators normalise the target
place; handlers write the rpg layout (``game/locations``, ``game/towns/<t>/npcs.json``) and record
``res.created``. Both honour ``res.writers`` (on | stub | off)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from neonrp.core.handlers import Verdict
from neonrp.core.paths import get_data_dir_name
from neonrp.core.place_nav import join_location, split_location
from neonrp.core.registry import Envelope, Registry


def judge_new_npc(root: Path, reg: Registry, o: dict[str, Any]) -> Verdict:
    at = str(o.get("at") or "")
    aid = (reg.resolve(at, cls="place") or reg.resolve(at, cls="road")) if at else reg.player_location  # met on the road too (10-19)
    if at and aid is None:
        return Verdict(False, reason=f"unknown place {at!r}", scope="entity", field="at")
    if reg.resolve(str(o.get("name") or "")):
        return Verdict(False, reason=f"{o.get('name')!r} already exists", scope="world", field="name", fixable=False)
    return Verdict(True, data={"at": aid})


def new_npc(root: Path, reg: Registry, o: dict[str, Any], res: Any) -> None:
    if getattr(res, "writers", "on") == "off":
        res.refused.append({"op": o, "scope": "world", "field": "op", "why": "writers disabled"})
        return None
    nid = _write_npc(root, reg, str(o["name"]), o.get("at"), str(o.get("role") or ""), res.turn)
    res.created.append({"id": nid, "class": "npc", "by": "writer", "handler": "rpg.writers.new_npc"})
    return None


def _write_npc(root: Path, reg: Registry, name: str, at: str | None, role: str, turn: int) -> str:
    road = reg.entries.get(at or reg.player_location or "")
    if road is not None and road.cls == "road":  # met on the road: no town's npcs.json — game/npc/<id>.json keeps the road as written
        nid = next(f"NPC_R{k:03d}" for k in range(1, 10000) if f"NPC_R{k:03d}" not in reg.entries)
        path = root / get_data_dir_name(root) / "npc" / f"{nid}.json"
        rec = {"id": nid, "name": name, "role": role, "location": road.id, "state": {"met": True}, "provenance": {"turn": turn, "by": "writer"}}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        reg.add(Envelope(nid, "npc", road.id, [], {k: v for k, v in rec.items() if k != "id"}, {"turn": turn, "by": "writer"},
                         aliases={name}, source=f"game/npc/{nid}.json"))
        return nid
    t, node = split_location(at or reg.player_location or "")
    tid = t or reg.current_town or "T001"
    path = root / get_data_dir_name(root) / "towns" / tid / "npcs.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"town_id": tid, "npcs": []}
    except (OSError, ValueError):
        data = {"town_id": tid, "npcs": []}
    npcs = data.setdefault("npcs", [])
    n = 1 + max((int(re.sub(r"\D", "", str(x.get("id"))) or 0) for x in npcs if isinstance(x, dict) and re.sub(r"\D", "", str(x.get("id")))), default=0)
    nid = f"NPC{n:03d}"
    npcs.append({"id": nid, "name": name, "role": role, "location": node or "", "traits": [], "state": {"met": True},
                 "provenance": {"turn": turn, "by": "writer"}})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    reg.add(Envelope(nid if nid not in reg.entries else f"{tid}/{nid}", "npc", join_location(tid, node) if node else tid, [],
                     {"name": name, "role": role, "town": tid}, {"turn": turn, "by": "writer"}, aliases={name},
                     source=f"game/towns/{tid}/npcs.json"))
    return nid


# ── new_town (直接去一个新城镇,最能展示开放 schema) ─────────────────────────────────────────────
# The world grows a town in play: a world-map node + a road from a known town, and a town folder in the rpg layout
# (town.json · town_map.json with a gate and a centre · npcs.json · quests.json). The loader reads it next turn like any
# authored town; travel, the map and the pack treat it the same. Nothing here names a town or a region.

def judge_new_town(root: Path, reg: Registry, o: dict[str, Any]) -> Verdict:
    name = str(o.get("name") or "").strip()
    if not name:
        return Verdict(False, reason="new_town needs a name", scope="field", field="name")
    if reg.resolve(name, cls="town"):
        return Verdict(False, reason=f"town {name!r} already exists", scope="world", field="name", fixable=False)
    src = str(o.get("from") or "") or (reg.current_town or "")
    fid = reg.resolve(src, cls="town") if src else None
    if fid is None:
        return Verdict(False, reason=f"unknown town {src!r} to build the road from", allowed=[e.id for e in reg.of_class("town")], scope="entity", field="from")
    try:
        days = int(str(o.get("days") or 2))
    except ValueError:
        return Verdict(False, reason="days must be a whole number of days", scope="field", field="days")
    return Verdict(True, data={"from": fid, "days": max(1, min(days, 14))})


def new_town(root: Path, reg: Registry, o: dict[str, Any], res: Any) -> None:
    if getattr(res, "writers", "on") == "off":
        res.refused.append({"op": o, "scope": "world", "field": "op", "why": "writers disabled"})
        return None
    from neonrp.packs.rpg import data as _data
    from neonrp.packs.rpg.travel import PER_DAY

    from neonrp.core import place_tree

    g = root / get_data_dir_name(root)
    wm = place_tree.level_doc(root, place_tree.WORLD) or {}  # world_map.json nodes, or the top place folders
    nodes, routes = wm.setdefault("nodes", []), wm.setdefault("routes", [])
    taken = {str(n.get("id")) for n in nodes} | {p.name for p in (g / "towns").iterdir() if p.is_dir()} if (g / "towns").is_dir() else {
        str(n.get("id")) for n in nodes}
    k = 1
    while f"T{k:03d}" in taken:
        k += 1
    tid = f"T{k:03d}"
    r = 1
    rids = {str(x.get("id")) for x in routes}
    while f"R{r:03d}" in rids:
        r += 1
    rid = f"R{r:03d}"
    src = next((n for n in nodes if str(n.get("id")) == o["from"]), {})
    days = int(o.get("days") or 2)
    per_day = float(_data.rules(root).get("travel_per_day") or PER_DAY)
    name, summary = str(o["name"]), str(o.get("summary") or "")
    tags = [x for x in str(o.get("tags") or "").split(",") if x]
    pos = list(src.get("pos") or [0, 0])
    nodes.append({"id": tid, "type": "town", "name": name, "region": src.get("region"), "pos": [pos[0] + 3 * days, pos[1] + 2],
                  "summary": summary, "links": [rid], "state": {"discovered": True, "danger_nearby": 1}, "provenance": {"turn": res.turn, "by": "writer.new_town"}})
    routes.append({"id": rid, "from": o["from"], "to": tid, "kind": "road", "distance": round(days * per_day), "tags": tags, "state": {"blocked": False}})
    if src:
        src.setdefault("links", []).append(rid)
    place_tree.save_level_doc(root, place_tree.WORLD, wm)
    td = g / "towns" / tid
    td.mkdir(parents=True, exist_ok=True)
    (td / "facilities").mkdir(exist_ok=True)
    from neonrp.packs.rpg.i18n import t as _t

    gate, centre = str(o.get("gate") or _t(root, "new_town_gate")), str(o.get("centre") or _t(root, "new_town_centre"))
    (td / "town.json").write_text(json.dumps({"id": tid, "name": name, "overview": summary, "entry_points": ["gate"], "tags": tags,
                                              "state": {"alert": 0}, "provenance": {"turn": res.turn, "by": "writer.new_town"}}, ensure_ascii=False, indent=2), encoding="utf-8")
    place_tree.save_level_doc(root, tid, {"town_id": tid, "nodes": [  # town_map.json, or folders inside the town's
        {"id": "gate", "name": gate, "type": "gate", "description": "", "links": ["centre"]},
        {"id": "centre", "name": centre, "type": "street", "description": "", "links": ["gate"]}]})
    (td / "npcs.json").write_text(json.dumps({"town_id": tid, "npcs": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    (td / "quests.json").write_text(json.dumps({"town_id": tid, "quests": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    reg.add(Envelope(tid, "town", "world", [], {"name": name, "overview": summary}, {"turn": res.turn, "by": "writer"}, source=f"{get_data_dir_name(root)}/towns/{tid}/town.json"))
    res.created.append({"id": tid, "class": "town", "name": name, "by": "writer", "handler": "writers.new_town", "path": str(td.relative_to(root)),
                        "road": {"id": rid, "from": o["from"], "days": days}})
    return None


# the place ops moved to the map tool (atlas/places.py); these names keep saved worlds' actions.json paths resolving
from neonrp.packs.rpg.atlas.places import (  # noqa: E402,F401
    judge_link, judge_new_location, judge_unlink, link, new_location, same_place, unlink,
)
