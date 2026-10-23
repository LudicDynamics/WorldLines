"""Map lint (MAP-SCALES-1005 G3): what a world's map says that it cannot mean. Warnings, never blocks — a world with
them still plays (the judge routes around them); the map workbench shows them so the author can fix the data.

    map.dangling       a connection names nothing on its level (not a sibling, not an alias)
    map.port_unbound   a parent-level edge (world route) reaches this level but no node takes it (ports.up) and the
                       level has no ``entry`` — where the traveller lands is a guess (the first gate)
    map.port_dangling  a ``ports.up`` names an edge the parent level does not have / that does not reach this level
    map.isolated       a world place with no route or link at all (mark it ``"isolated": true`` when it is meant to be
                       out of reach until a plot opens a road — then it is not reported)
    map.legacy_level   a level still in the old form (world_map / town_map ``nodes``, a dungeon's rooms in layout.json)

Nothing here knows a particular world; ids and names come from the data.
"""
from __future__ import annotations

from pathlib import Path


def _issue(code: str, where: str, msg: str) -> dict[str, str]:
    return {"level": "warn", "code": code, "where": where, "msg": msg}


def lint_map(root: Path) -> list[dict[str, str]]:
    from neonrp.core import place_tree as pt

    out: list[dict[str, str]] = []
    world = pt.level_doc(root, pt.WORLD) or {}
    routes = [r for r in world.get("routes") or [] if isinstance(r, dict) and r.get("id")]
    route_ids = {str(r["id"]) for r in routes}
    wnodes = {str(n["id"]): n for n in world.get("nodes") or [] if isinstance(n, dict) and n.get("id")}

    # ── old forms
    if world and not pt.is_tree(root) and wnodes:
        out.append(_issue("map.legacy_level", pt.level_label(root, pt.WORLD),
                          "the world map is still a nodes list — scripts/migrate_map_to_folders.py turns it into folders"))
    towns_dir = pt.game_dir(root) / "towns"
    for d in sorted(towns_dir.iterdir()) if towns_dir.is_dir() else []:
        tm = pt._rj(d / "town_map.json") if d.is_dir() else None
        if tm and isinstance(tm.get("nodes"), list) and tm["nodes"]:
            out.append(_issue("map.legacy_level", f"game/towns/{d.name}/town_map.json",
                              f"level {d.name} is still a nodes list — migrate it to folders"))
    dungeons = pt.game_dir(root) / "dungeons"
    for d in sorted(dungeons.iterdir()) if dungeons.is_dir() else []:
        if not (d / "dungeon.json").is_file():
            continue
        lay = pt._rj(d / "layout.json") or {}
        if lay.get("rooms") and not pt._place_dirs(pt.locations_dir(root) / d.name):
            out.append(_issue("map.legacy_level", f"game/dungeons/{d.name}/layout.json",
                              f"dungeon {d.name}'s rooms are still a list in layout.json — give each room a folder "
                              f"under locations/{d.name}/"))

    # ── world level: isolated places
    linked: set[str] = set()
    for r in routes:
        linked |= {str(r.get("from")), str(r.get("to"))}
    for nid, n in wnodes.items():
        if n.get("links"):
            linked.add(nid)
            linked |= {str(x) for x in n["links"]}
    for nid, n in wnodes.items():
        if nid not in linked and not n.get("isolated"):
            out.append(_issue("map.isolated", f"{pt.level_label(root, pt.WORLD)}#{nid}",
                              f"{n.get('name') or nid} has no route or link — nobody can walk there "
                              "(add a route, or mark it \"isolated\": true if a plot opens the way later)"))

    # ── each level below the world: dangling connections, ports
    levels = list(pt.town_ids(root)) + [d.name for d in (sorted(dungeons.iterdir()) if dungeons.is_dir() else [])
                                         if d.is_dir() and pt._place_dirs(pt.locations_dir(root) / d.name)]
    for lvl in levels:
        if pt.is_dungeon_level(root, lvl):
            nodes = {r["id"]: {**r, "links": r.get("links") or []} for r in pt.dungeon_rooms(root, lvl)}
        else:
            doc = pt.level_doc(root, lvl) or {}
            nodes = {str(n["id"]): n for n in doc.get("nodes") or [] if isinstance(n, dict) and n.get("id")}
        if not nodes:
            continue
        where = pt.level_label(root, lvl)
        known = set(nodes) | {str(a) for n in nodes.values() for a in n.get("aliases") or []}
        for nid, n in nodes.items():
            for c in n.get("links") or n.get("connections") or []:
                c = str(c)
                if c in known:
                    continue
                hint = (f"it is a route of the level above — bind it with ports.up: [\"{c}\"]" if c in route_ids
                        else "if it is the way out of this level, bind the route with ports.up; else add the place or drop the link")
                out.append(_issue("map.dangling", f"{where}/{nid}", f"{n.get('name') or nid} connects to '{c}', which is not on this level — {hint}"))
            for up in pt.ports_up(n):
                r = next((x for x in routes if str(x["id"]) == up), None)
                if r is None or lvl not in (str(r.get("from")), str(r.get("to"))):
                    out.append(_issue("map.port_dangling", f"{where}/{nid}",
                                      f"{n.get('name') or nid}.ports.up names '{up}', which is not a route reaching {lvl}"))
        bound = {up for n in nodes.values() for up in pt.ports_up(n)}
        entry = pt.level_entry(root, lvl)
        if entry and entry not in nodes:
            out.append(_issue("map.port_dangling", where, f"entry '{entry}' is not a place of {lvl}"))
            entry = None
        for r in routes:
            if lvl in (str(r.get("from")), str(r.get("to"))) and str(r["id"]) not in bound and not entry:
                other = str(r.get("to")) if str(r.get("from")) == lvl else str(r.get("from"))
                out.append(_issue("map.port_unbound", where,
                                  f"route {r['id']} ({lvl} ↔ {other}) reaches {lvl} but no place takes it (ports.up) and the level "
                                  "has no entry — travellers land at the first gate"))
    # ── G5: scale is a known word (display and image prompts only)
    for f in sorted(pt.locations_dir(root).rglob(pt.RECORD)) if pt.locations_dir(root).is_dir() else []:
        rec = pt._rj(f) or {}
        sc = rec.get("scale")
        if sc and str(sc) not in pt.SCALES:
            out.append(_issue("map.scale_unknown", str(f.relative_to(root)), f"scale {sc!r} is not one of {', '.join(pt.SCALES)}"))
    return out
