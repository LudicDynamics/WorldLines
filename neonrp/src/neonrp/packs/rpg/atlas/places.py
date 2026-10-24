"""Places on the map (rpg map tool): new_location with its spot in the tree (near / between / in / over), link,
unlink — validators and handlers. Growth is never refused for its anchor; what it is refused for: another name for a
place the town has, a place the judge finds out of place, a road that would cut a place off or cross layers."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from neonrp.core.handlers import Verdict
from neonrp.core.place_nav import join_location, split_location
from neonrp.core.registry import Envelope, Registry

_INSIDE = ("大厅", "大堂", "里面", "内部", "里", "内", "前台", "柜台", "hall", "inside", "interior")


def same_place(reg: Registry, name: str) -> str | None:
    """A new name that is only another way of saying a place this town already has (公会 / 公会大厅 for 冒险者公会):
    that place's id. Plain text, deterministic; a different spot near it (主街尽头的小巷, 北门外) is a new place."""
    n = name.strip().casefold()
    if len(n) < 2:
        return None
    town = reg.current_town or ""
    for e in reg.of_class("place"):
        if town and not (e.id.startswith(town + "/") or e.parent == town):
            continue
        for x in {e.name, *[a for a in e.aliases if isinstance(a, str)]}:
            x = str(x).strip().casefold()
            if len(x) < 2:
                continue
            core = next((n[: -len(suf)].rstrip(" 的") for suf in _INSIDE if n.endswith(suf) and len(n) > len(suf) + 1), n)
            if core == x or (len(core) >= 2 and core in x):
                return e.id
    return None


def _fits(reg: Registry, name: str, summary: str, at: str | None) -> tuple[bool, str]:
    """The judge's one question (Jev → LLM judge): does a place by this name make sense here? No answer → it grows."""
    from neonrp.core import system_one as s1

    town = reg.entries.get(reg.current_town or "")
    here = reg.entries.get(at or "")
    q = s1.noul(f"Does a place called '{name}' make sense around '{here.name if here else 'here'}' in '{town.name if town else 'this town'}'? "
                "(it does when the world's era, style and geography allow it; it does not, e.g., for a subway station in a "
                "medieval town or a seaport beside an inland town)")
    state = {"town": town.props.get("summary", "") if town else "", "here": here.props.get("summary", "") if here else "",
             "places": [e.name for e in reg.of_class("place")][:30], "new": name, "summary": summary}
    try:
        a = (s1.ask(state, {"fits": q}) or {}).get("fits")
    except Exception:  # noqa: BLE001 — the judge never blocks growth
        return True, ""
    if a is None or a.yes >= 0.35:
        return True, ""
    return False, f"'{name}' does not make sense here (judge {a.yes:.2f}); pick a place that fits this world and this spot, or go to a place that exists"


def _relation(reg: Registry, o: dict[str, Any]) -> tuple[str | None, list[str], str]:
    """The place's spot in the tree, as written: near=A[,B] · between=A,B · in=A · over=A,B → (rel, place ids, problem)."""
    from neonrp.packs.rpg.atlas.graph import RELATIONS

    rel = next((r for r in RELATIONS if o.get(r)), None)
    if rel is None:
        return None, [], ""
    ends = []  # 10-21 ID2: `near=T001/townhall` is one place (the prompt asks for full paths), not T001 and townhall
    for x in (x.strip() for x in re.split(r"[,，、]", str(o[rel])) if x.strip()):
        ends += [x] if "/" not in x or reg.resolve(x, cls="place") else [y.strip() for y in x.split("/") if y.strip()]
    ids = [reg.resolve(x, cls="place") for x in ends]
    if not ends or None in ids:
        bad = [e for e, i in zip(ends, ids) if i is None]
        return rel, [], f"{rel}= names places that do not exist: {bad or ends}"
    if len({split_location(x)[0] for x in ids}) != 1:
        return rel, [], f"the places in {rel}= must be in one town"
    return rel, [x for x in ids if x], ""


def _target_town(reg: Registry, o: dict[str, Any]) -> str | None:
    """The town a new place is meant for: the one its relation names, else the one the player is in."""
    rel, ids, _why = _relation(reg, o)
    return split_location(ids[0])[0] if ids else (reg.current_town or None)


def judge_new_location(root: Path, reg: Registry, o: dict[str, Any]) -> Verdict:
    """A place the world names is grown, never refused for its anchor; it says where it sits in the tree
    (near / between / in / over, ``core/locations.town_rehang``) — and when it says nothing, it hangs beside where the
    player stands, marked ``default`` so the after-turn pass can place it from the prose (the move is async anyway)."""
    name = str(o.get("name") or "").strip()
    have = reg.resolve(name, cls="place")
    if have and split_location(have)[0] in (_target_town(reg, o), None):  # 10-21 PL4: one town's north gate is not another's
        return Verdict(False, reason=f"place {name!r} already exists", scope="world", field="name", fixable=False)
    same = same_place(reg, name)
    if same:  # 10-02「得看是否合理」: another name for a place we have is not a new place
        return Verdict(False, reason=f"'{name}' is the existing {same} ({reg.entries[same].name}): use it", allowed=[same], scope="entity", field="name")
    rel, ids, why = _relation(reg, o)
    if why:  # a relation we cannot read: grow it anyway, beside the player, and let the after-turn pass place it
        rel, ids = None, []
    here = reg.player_location
    on = reg.entries.get(here or "")
    if on is not None and on.cls == "road":  # off the road (a camp in the reeds): it hangs by the gate the party left from (M9 r3)
        from neonrp.packs.rpg import travel

        j = travel.journey(root) or {}
        gate = next((e.id for e in reg.of_class("place") if e.parent == j.get("from") and "gate" in e.id), None)
        here = gate or str(j.get("origin") or "") or here
    anchor = ids[0] if ids else here
    ok, why2 = _fits(reg, name, str(o.get("summary") or ""), anchor if reg.entries.get(anchor or "") else here)
    if not ok:
        return Verdict(False, reason=why2, scope="world", field="name")
    if rel:
        return Verdict(True, data={"rel": rel, "targets": ids, "parent": ids[0], "links": ids if rel in ("near", "between") else []})
    parent = str(o.get("parent") or "")
    pid = (reg.resolve(parent, cls="place") or next((x for x in (reg.resolve(parent, cls=c) for c in ("town", "region", "dungeon")) if x), None)) if parent else None
    links = [x for x in (reg.resolve(str(lk), cls="place") for lk in o.get("links") or []) if x] or ([pid] if pid and reg.entries.get(pid) and reg.entries[pid].cls == "place" else [])
    if not links and here:
        links = [here]
    in_town = [x for x in links if reg.entries.get(x) is not None and reg.entries[x].cls == "place"]
    return Verdict(True, data={"rel": "near" if in_town else None, "targets": in_town, "parent": pid or here, "links": links,
                               "default": not o.get("links") and not parent, **({"unread": why} if why else {})})


def _refresh_town_links(root: Path, reg: Registry, town: str) -> None:
    """After a tree edit: the registry's places of this town take their links / layer from the map file again."""
    from neonrp.packs.rpg.atlas.graph import _town_map

    _p, data = _town_map(root, town)
    by_node = {str(n.get("id")): n for n in data.get("nodes") or [] if isinstance(n, dict) and n.get("id")}
    kids: dict[str, list[str]] = {}
    for nid, n in by_node.items():
        if n.get("parent"):
            kids.setdefault(str(n["parent"]), []).append(nid)
    for nid, n in by_node.items():
        env = reg.entries.get(join_location(town, nid)) or next((e for e in reg.of_class("place") if e.name == n.get("name") and split_location(e.id)[0] in (town, None)), None)
        if env is None:
            continue
        links = [join_location(town, str(x)) for x in n.get("links") or []]
        if n.get("parent"):
            env.props["within"] = join_location(town, str(n["parent"]))
            links.append(env.props["within"])
        else:
            env.props.pop("within", None)
        links += [join_location(town, k) for k in kids.get(nid, [])]
        env.links = links


def _record_source(root: Path, loc_id: str) -> str:
    """The file a grown place lives in — its record, not its folder (10-03 llm6 PL4: a patch on 雾中石南洼地 opened the
    folder for writing and the whole Resolve patch was lost)."""
    from neonrp.core.locations import location_record_path

    p = location_record_path(root, loc_id)
    if p is not None:
        try:
            return p.relative_to(root).as_posix()
        except ValueError:
            pass
    return f"game/locations/{loc_id}/location.json"


def new_location(root: Path, reg: Registry, o: dict[str, Any], res: Any) -> None:
    if getattr(res, "writers", "on") == "off":
        res.refused.append({"op": o, "scope": "world", "field": "op", "why": "writers disabled"})
        return None
    from neonrp.core.locations import create_location
    from neonrp.packs.rpg.atlas.graph import town_rehang

    parent = o.get("parent")
    t, _n = split_location(parent or "")
    rel, targets = o.get("rel"), list(o.get("targets") or [])
    rec = create_location(root, name=str(o["name"]), summary=str(o.get("summary") or ""),
                          connections=[] if rel else [split_location(x)[1] or x for x in o.get("links") or []],
                          parent=parent, town=t or reg.current_town, world_map=False)
    town = str(rec.get("town") or "")
    eid = join_location(town, str(rec["id"])) if town else str(rec.get("id"))
    env = Envelope(eid, "place", town or parent, [], {"name": o["name"], "summary": rec.get("summary", ""), "node": str(rec["id"])},
                   {"turn": res.turn, "by": "writer"}, aliases={str(rec["id"])}, source=_record_source(root, str(rec["id"])))
    reg.add(env)
    placed, why = "", ""
    if rel and town and targets:
        ok, why = town_rehang(root, town, str(rec["id"]), str(rel), [split_location(x)[1] or x for x in targets])
        if not ok and o.get("rel") and not o.get("default"):  # the written relation does not draw: beside the player, fixed after the turn
            here = reg.player_location or ""
            if split_location(here)[0] == town:
                town_rehang(root, town, str(rec["id"]), "near", [split_location(here)[1] or here])
            o = {**o, "default": True}
        placed = rel if ok else "near"
        _refresh_town_links(root, reg, town)
    else:
        env.links = list(o.get("links") or [])
    res.created.append({"id": env.id, "class": "place", "by": "writer", "handler": "locations.create_location",
                        "relation": placed or None, "targets": targets, "default": bool(o.get("default")),
                        **({"why": why} if why else {})})
    return None


def _edge_ends(reg: Registry, o: dict[str, Any]) -> tuple[list[str], str | None]:
    ids = [reg.resolve(str(o.get(k) or ""), cls="place") for k in ("a", "b")]
    if None in ids:
        bad = o.get("a") if ids[0] is None else o.get("b")
        return [], f"unknown place {bad!r}"
    if ids[0] == ids[1]:
        return [], "both ends are the same place"
    if split_location(ids[0])[0] != split_location(ids[1])[0]:
        return [], "a road in town joins places of one town; to reach another town use new_town / move"
    return list(ids), None


def judge_link(root: Path, reg: Registry, o: dict[str, Any]) -> Verdict:
    from neonrp.packs.rpg.atlas.graph import town_linked

    ids, why = _edge_ends(reg, o)
    if why:
        return Verdict(False, reason=why, scope="entity", field="a")
    t, a = split_location(ids[0])
    if town_linked(root, t or "", a or ids[0], split_location(ids[1])[1] or ids[1]):
        return Verdict(False, reason="these two places are already connected", scope="world", field="b", fixable=False)
    if reg.entries[ids[0]].props.get("within") != reg.entries[ids[1]].props.get("within"):  # roads join one layer; in / out is through the parent
        return Verdict(False, reason="these two places are not on one layer: a place inside another is entered only from it", scope="world", field="b")
    return Verdict(True, data={"a": ids[0], "b": ids[1]})


def judge_unlink(root: Path, reg: Registry, o: dict[str, Any]) -> Verdict:
    from neonrp.packs.rpg.atlas.graph import town_linked, town_stays_whole

    ids, why = _edge_ends(reg, o)
    if why:
        return Verdict(False, reason=why, scope="entity", field="a")
    (t, a), (_t2, b) = split_location(ids[0]), split_location(ids[1])
    if not town_linked(root, t or "", a or ids[0], b or ids[1]):
        return Verdict(False, reason="there is no road between these two places", scope="world", field="b", fixable=False)
    if not town_stays_whole(root, t or "", a or ids[0], b or ids[1]):
        return Verdict(False, reason="cutting this road leaves part of the town unreachable; to close it, first build another one (link)", scope="world", field="b")
    return Verdict(True, data={"a": ids[0], "b": ids[1]})


def _edge(root: Path, reg: Registry, o: dict[str, Any], res: Any, *, add: bool) -> None:
    from neonrp.packs.rpg.atlas.graph import town_edge

    (t, a), (_t2, b) = split_location(o["a"]), split_location(o["b"])
    written = town_edge(root, t or reg.current_town or "", a or o["a"], b or o["b"], add=add)
    for x, y in ((o["a"], o["b"]), (o["b"], o["a"])):
        env = reg.entries.get(x)
        if env is not None:
            if add and y not in env.links:
                env.links.append(y)
            elif not add and y in env.links:
                env.links.remove(y)
    res.applied.append({"op": "link" if add else "unlink", "a": o["a"], "b": o["b"], "handler": "locations.town_edge", "written": written})


def link(root: Path, reg: Registry, o: dict[str, Any], res: Any) -> None:
    _edge(root, reg, o, res, add=True)


def unlink(root: Path, reg: Registry, o: dict[str, Any], res: Any) -> None:
    _edge(root, reg, o, res, add=False)
