"""Layered world map: the world's folders → one map tree → image-rendered maps.

The map data already lives on disk, spread over three layers:

    world   game/world/world_map.json          nodes (town/city/dungeon/region) + routes
    town    game/towns/<T>/town_map.json       spots (gate/street/facility/dock) + links
    dungeon game/dungeons/<D>/layout.json      rooms + links (no coordinates → auto layout)

``build_map_tree`` folds them into one tree keyed by the engine's own scoped
addresses (``T001``, ``T001/gate_north`` — see place_nav.qualify_location), with
every character placed on it and inconsistencies between files reported.

Images are generated FROM the coordinates, so image and data stay aligned by
construction:

    coordinates → layout guide (drawn here) → image model follows the guide
    → pins (hotspots) = the same coordinates through the same transform

The transform is frozen into ``assets/maps/<level>.json`` when an image is
generated. Moving or adding a node later maps through that frozen transform, so
pins stay on the existing picture; the image is merely flagged ``stale`` until
it is regenerated.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import random
import re
import time
from pathlib import Path
from typing import Any

from neonrp.core import fallback_art

logger = logging.getLogger(__name__)

ROOT = "world"
W, H = 1536, 1024
PADS = {"world": (170, 150), "town": (260, 190), "dungeon": (260, 220)}
DEFAULT_STYLE = (
    "Painterly dark-fantasy illustration, muted foggy palette (slate blue, moss green, "
    "warm lantern amber), cinematic, highly detailed, no text, no labels, no letters, no UI."
)
KIND_EN = {
    "town": "small town", "city": "walled city", "dungeon": "sunken dungeon entrance",
    "region": "wild region", "gate": "gatehouse", "street": "street / square",
    "facility": "building", "dock": "wooden dock", "entry": "entrance chamber",
    "hall": "corridor", "chamber": "chamber", "boss": "inner sanctum",
}


# ── files ────────────────────────────────────────────────────────────────

def _gdir(root: Path) -> Path:
    from neonrp.core.paths import get_data_dir_name

    return root / get_data_dir_name(root)


def _rj(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _wj(path: Path, data: Any) -> None:
    from neonrp.core.storage import atomic_write_json

    atomic_write_json(path, data)


def level_kind(tree: dict[str, Any], level: str) -> str:
    if level == ROOT:
        return "world"
    return "dungeon" if tree["nodes"][level]["kind"] == "dungeon" else "town"


def _slug(addr: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "__", addr) or ROOT


def map_image_path(root: Path, level: str) -> Path:
    return root / "assets" / "maps" / f"{_slug(level)}.webp"


def map_meta_path(root: Path, level: str) -> Path:
    return root / "assets" / "maps" / f"{_slug(level)}.json"


def map_guide_path(root: Path, level: str) -> Path:
    return root / "assets" / "maps" / f"{_slug(level)}.guide.png"


_IMG_EXTS = (".webp", ".png", ".jpg", ".jpeg")


def scene_image_path(root: Path, addr: str) -> Path | None:
    base = root / "assets" / "places"
    for ext in _IMG_EXTS:
        p = base / f"{_slug(addr)}{ext}"
        if p.is_file():
            return p
    return None


def cast_ids(root: Path) -> set[str] | None:
    """The instance ids this run cast (its playthrough.json ``souls``); None = no playthrough (every soul folder counts).
    A soul the world carries but the template did not list stays on disk and is not active (template spec §3.6)."""
    for p in (root / "playthrough.json", root / ".neonrp" / "playthrough.json"):
        d = _rj(p)
        if isinstance(d, dict) and isinstance(d.get("souls"), list):
            return {str(s.get("instance_id")) for s in d["souls"] if isinstance(s, dict) and s.get("instance_id")}
    return None


def soul_dir_iid(sd: Path, run_state: dict[str, Any] | None = None) -> str:
    """A soul folder's instance id: the folder name after ``<sid>-`` (``elena-si-elena0001`` → ``si-elena0001``) — the
    name the run gave it; a copied run_state.json may still carry another soul's id. No ``-si-`` → its run_state's."""
    if "-si-" in sd.name:
        return "si-" + sd.name.split("-si-", 1)[1]
    rs = run_state if run_state is not None else (_rj(sd / "run_state.json") or {})
    return str((rs or {}).get("instance_id") or sd.name)


def soul_dir(root: Path, sid: str) -> Path | None:
    sdir = root / "souls"
    if not sdir.is_dir():
        return None
    for d in sorted(sdir.iterdir()):
        if d.is_dir() and (d.name == sid or d.name.split("-si-")[0] == sid or d.name.endswith(sid)):
            return d
    return None


_ALIAS_STEMS = ("portrait", "sprite")


def asset_alias(sd: Path, stem: str) -> str | None:
    """``soul.json`` ``assets: {"sprite": "portrait"}`` = this soul's sprite *is* its portrait (the author's portrait is
    already a full-body picture, niko 10-24): the slot points at the other picture — no copy. Only between the soul's
    own picture slots."""
    sj = _rj(Path(sd) / "soul.json") or {}
    a = sj.get("assets") if isinstance(sj, dict) and isinstance(sj.get("assets"), dict) else {}
    v = str(a.get(stem) or "")
    return v if v in _ALIAS_STEMS and v != stem else None


def soul_asset(root: Path, sid: str, stem: str) -> Path | None:
    d = soul_dir(root, sid)
    if d is None:
        return None
    for s in (stem, asset_alias(d, stem)):
        for ext in _IMG_EXTS if s else ():
            p = d / "assets" / f"{s}{ext}"
            if p.is_file():
                return p
    return None


# ── tree ─────────────────────────────────────────────────────────────────

def build_map_tree(root: Path) -> dict[str, Any]:
    """Fold world_map / town_map / dungeon layout into one addressable tree."""
    from neonrp.core.place_nav import qualify_location

    from neonrp.core.place_tree import WORLD, is_tree, level_doc

    g = _gdir(root)
    wm = level_doc(root, WORLD) or {}  # tree form: the top place folders are the nodes
    tree_form = is_tree(root)
    issues: list[dict[str, Any]] = []
    nodes: dict[str, dict[str, Any]] = {}
    rel = lambda p: str(p.relative_to(root))  # noqa: E731

    nodes[ROOT] = {
        "addr": ROOT, "id": wm.get("world_id") or ROOT, "name": wm.get("name") or root.name,
        "kind": "territory", "parent": None, "source": "game/world/world_map.json",
        "children": [], "edges": [], "frontier": wm.get("foreign_lands") or [],
        "summary": wm.get("parent_territory") or "",
    }
    for n in wm.get("nodes") or []:
        if not isinstance(n, dict) or not n.get("id"):
            continue
        pos = n.get("pos") or [0, 0]
        if isinstance(pos, dict):
            pos = [pos.get("x", 0), pos.get("y", 0)]
        a = str(n["id"])
        nodes[a] = {
            "addr": a, "id": a, "name": n.get("name") or a, "kind": n.get("type") or "place",
            "parent": ROOT, "pos": {"x": float(pos[0]), "y": float(pos[1])},
            "summary": n.get("summary") or "", "state": n.get("state") or {},
            "extra": {k: n[k] for k in ("lore", "travel_info", "region") if k in n},
            "source": f"game/locations/{a}/location.json" if tree_form else f"game/world/world_map.json#nodes/{a}",
            "children": [], "edges": [],
        }
        nodes[ROOT]["children"].append(a)
    for r in wm.get("routes") or []:
        if not isinstance(r, dict) or r.get("from") not in nodes or r.get("to") not in nodes:
            continue
        nodes[ROOT]["edges"].append({
            "id": r.get("id"), "from": r["from"], "to": r["to"], "kind": r.get("kind") or "road",
            "distance": r.get("distance"), "tags": r.get("tags") or [],
            "blocked": bool((r.get("state") or {}).get("blocked")),
        })
    if tree_form:  # a place folder's connections are roads too, unless a route already draws them
        for n in wm.get("nodes") or []:
            a = str(n.get("id") or "") if isinstance(n, dict) else ""
            for b in (n.get("links") or []) if a in nodes else []:
                b = str(b)
                if b in nodes and b != a and not any({e["from"], e["to"]} == {a, b} for e in nodes[ROOT]["edges"]):
                    nodes[ROOT]["edges"].append({"id": None, "from": min(a, b), "to": max(a, b), "kind": "road",
                                                 "distance": None, "tags": [], "blocked": False})

    # towns
    from neonrp.core.place_tree import level_doc, level_in_folders, level_label, town_ids

    towns = g / "towns"
    tdirs = [d for d in sorted(towns.iterdir()) if d.is_dir()] if towns.is_dir() else []
    tdirs += [towns / t for t in town_ids(root) if not (towns / t).is_dir()]  # tree form: places with places inside
    for tdir in tdirs:
        folders = level_in_folders(root, tdir.name)
        tm = (level_doc(root, tdir.name) or {}) if folders else (_rj(tdir / "town_map.json") or {})
        map_src = level_label(root, tdir.name) if folders else rel(tdir / "town_map.json")
        tid = str(tm.get("town_id") or tdir.name)
        if tid not in nodes:
            issues.append({"kind": "orphan", "addr": tid,
                           "msg": f"towns/{tdir.name} 不在 world_map.nodes 里"})
            continue
        town = nodes[tid]
        tj = _rj(tdir / "town.json") or {}
        town["overview"] = tj.get("overview") or ""
        town["town"] = {k: tj.get(k) for k in ("tags", "economy", "laws", "state") if tj.get(k)}
        town["dir"] = rel(tdir)
        disc = set((tm.get("state") or {}).get("discovered_nodes") or [])
        for sn in tm.get("nodes") or []:
            if not isinstance(sn, dict) or not sn.get("id"):
                continue
            a = f"{tid}/{sn['id']}"
            pos = sn.get("pos") or {}
            if isinstance(pos, list):
                pos = {"x": pos[0], "y": pos[1]}
            detail = None
            if sn.get("facility_file"):
                detail = _rj(tdir / sn["facility_file"])
                if detail is None:
                    issues.append({"kind": "missing", "addr": a,
                                   "msg": f"{a} 指向的 {sn['facility_file']} 不存在"})
            nodes[a] = {
                "addr": a, "id": sn["id"], "name": sn.get("name") or sn["id"],
                "kind": sn.get("type") or "spot", "parent": tid,
                "pos": {"x": float(pos.get("x", 0)), "y": float(pos.get("y", 0))},
                "summary": sn.get("description") or "",
                "state": {"discovered": (sn["id"] in disc) if disc else True},
                "detail": detail, "source": f"{map_src}#nodes/{sn['id']}",
                "children": [], "edges": [],
            }
        for sn in tm.get("nodes") or []:  # layers (10-02): a node's "parent" puts it inside that node, one level down
            if not isinstance(sn, dict) or not sn.get("id"):
                continue
            a = f"{tid}/{sn['id']}"
            up = f"{tid}/{sn['parent']}" if sn.get("parent") and f"{tid}/{sn['parent']}" in nodes else tid
            nodes[a]["parent"] = up
            nodes[up]["children"].append(a)
        for sn in tm.get("nodes") or []:
            if not isinstance(sn, dict) or not sn.get("id"):
                continue
            a = f"{tid}/{sn['id']}"
            for link in sn.get("links") or []:
                b = f"{tid}/{link}"
                if b not in nodes or nodes[b].get("parent") != nodes[a].get("parent"):
                    continue
                lvl = nodes[nodes[a]["parent"]]
                x, y = sorted([a, b])
                if not any(e["from"] == x and e["to"] == y for e in lvl["edges"]):
                    lvl["edges"].append({"from": x, "to": y})
        town["npcs"] = [n for n in ((_rj(tdir / "npcs.json") or {}).get("npcs") or []) if isinstance(n, dict)]
        town["quests"] = [q for q in ((_rj(tdir / "quests.json") or {}).get("quests") or []) if isinstance(q, dict)]

    # dungeons (rooms have no coordinates → BFS layout, deterministic)
    dungeons = g / "dungeons"
    for ddir in sorted(dungeons.iterdir()) if dungeons.is_dir() else []:
        if not ddir.is_dir():
            continue
        did = ddir.name
        if did not in nodes:
            issues.append({"kind": "orphan", "addr": did, "msg": f"dungeons/{did} 不在 world_map.nodes 里"})
            continue
        dun = nodes[did]
        dj = _rj(ddir / "dungeon.json") or {}
        dun["dungeon"] = {k: dj.get(k) for k in ("theme", "danger", "recommended_level", "boss") if dj.get(k)}
        dun["dir"] = rel(ddir)
        for key in ("discovered",):
            a_, b_ = dun["state"].get(key), (dj.get("state") or {}).get(key)
            if a_ is not None and b_ is not None and a_ != b_:
                issues.append({"kind": "conflict", "addr": did,
                               "msg": f"{key}: world_map={a_} vs dungeons/{did}/dungeon.json={b_}"})
        a_, b_ = dun["state"].get("danger"), dj.get("danger")
        if a_ is not None and b_ is not None and a_ != b_:
            issues.append({"kind": "conflict", "addr": did,
                           "msg": f"danger: world_map={a_} vs dungeons/{did}/dungeon.json={b_}"})
        lay = _rj(ddir / "layout.json") or {}
        from neonrp.core.place_tree import dungeon_rooms, level_entry, locations_dir

        rooms = dungeon_rooms(root, did)  # its room folders (10-05 MAP-SCALES G3) when it has them, else layout.json
        in_folders = (locations_dir(root) / did).is_dir() and any((locations_dir(root) / did / r["id"]).is_dir() for r in rooms)
        depth: dict[str, int] = {}
        if rooms:
            links = {r["id"]: r.get("links") or [] for r in rooms}
            first = level_entry(root, did)
            q = [first if first in links else rooms[0]["id"]]
            depth[q[0]] = 0
            while q:
                c = q.pop(0)
                for link in links.get(c, []):
                    if link not in depth:
                        depth[link] = depth[c] + 1
                        q.append(link)
        count: dict[int, int] = {}
        order: dict[str, int] = {}
        for r in rooms:
            d = depth.get(r["id"], 0)
            order[r["id"]] = count.get(d, 0)
            count[d] = count.get(d, 0) + 1
        for r in rooms:
            a = f"{did}/{r['id']}"
            d = depth.get(r["id"], 0)
            rf = ddir / "rooms" / f"{r['id']}.json"
            detail = _rj(rf)
            nodes[a] = {
                "addr": a, "id": r["id"], "name": r.get("name") or r["id"], "kind": r.get("type") or "room",
                "parent": did, "pos": {"x": float(d * 10), "y": float(order[r["id"]] * 10 - (count[d] - 1) * 5)},
                "summary": (detail or {}).get("description") or "",
                "state": {"discovered": True, **(r.get("state") or {})},
                "detail": detail, "source": (rel(locations_dir(root) / did / r["id"] / "location.json") if in_folders
                                             else f"{rel(ddir / 'layout.json')}#rooms/{r['id']}"),
                "children": [], "edges": [],
            }
            dun["children"].append(a)
        for r in rooms:
            a = f"{did}/{r['id']}"
            for link in r.get("links") or []:
                b = f"{did}/{link}"
                if b in nodes:
                    x, y = sorted([a, b])
                    if not any(e["from"] == x and e["to"] == y for e in dun["edges"]):
                        dun["edges"].append({"from": x, "to": y})
        cur = (lay.get("state") or {}).get("current_room")
        dun["current_room"] = f"{did}/{cur}" if cur else None

    # flat multi-agent locations (game/locations/*.json) → which tree node they are
    flat: list[dict[str, Any]] = []
    locdir = g / "locations"
    for lf in sorted(locdir.glob("*.json")) if locdir.is_dir() else []:
        lj = _rj(lf) or {}
        name = str(lj.get("name") or lf.stem)
        hit = None
        q = qualify_location(root, lf.stem)
        if q in nodes:
            hit = q
        elif "·" in name:
            tname, spot = name.split("·", 1)
            for a, n in nodes.items():
                if n.get("parent") and nodes.get(n["parent"], {}).get("name") == tname and (
                    n["name"] == spot or spot.startswith(n["name"]) or n["name"].startswith(spot)
                ):
                    hit = a
        else:
            same = [a for a, n in nodes.items() if n["name"] == name]
            if len(same) == 1:
                hit = same[0]
        flat.append({"id": lf.stem, "name": name, "resolved": hit, "source": rel(lf),
                     "summary": lj.get("summary") or ""})
        if not hit:
            issues.append({"kind": "unresolved", "addr": None,
                           "msg": f"locations/{lf.name}「{name}」在层级地图里找不到对应节点"})

    # characters
    entities: list[dict[str, Any]] = []
    rs = _rj(g / "meta" / "run_state.json") or {}
    loc = rs.get("location") or {}
    raw_player = "/".join(x for x in (loc.get("node_id"), loc.get("subnode_id")) if x) if isinstance(loc, dict) else str(loc)
    player_addr = qualify_location(root, raw_player) or None
    player_town = player_addr.split("/")[0] if player_addr else None
    party = (rs.get("party") or {}).get("player") or {}
    alt = qualify_location(root, party.get("location"), current_town=player_town) if party.get("location") else ""
    if alt and player_addr and alt != player_addr:
        issues.append({"kind": "conflict", "addr": player_addr,
                       "msg": f"玩家位置两处不一致:run_state.location→{player_addr} vs party.player.location→{alt}"})
    prof = _rj(g / "player" / "profile.json") or {}
    entities.append({
        "id": "player", "kind": "player", "name": prof.get("name_local") or prof.get("name") or "玩家",
        "addr": player_addr if player_addr in nodes else None, "raw": raw_player,
        "has_portrait": any((g / "player" / "assets" / f"portrait{e}").is_file() for e in _IMG_EXTS),
        "portrait_fallback": fallback_art.player(root),  # no picture: the stand-in silhouette (core/fallback_art, 10-17)
    })
    sroot = root / "souls"
    cast = cast_ids(root)
    for sd in sorted(sroot.iterdir()) if sroot.is_dir() else []:
        if not sd.is_dir() or not (sd / "soul.json").is_file():
            continue
        sj = _rj(sd / "soul.json") or {}
        srs = _rj(sd / "run_state.json") or {}
        if cast is not None and soul_dir_iid(sd, srs) not in cast:
            continue  # a soul the world carries but this run did not cast stays on disk, not on the map (10-15)
        sid = str(sj.get("sid") or sd.name.split("-si-")[0])
        raw = str(srs.get("location") or "")
        addr = qualify_location(root, raw, current_town=player_town) if raw else ""
        for tid in [a for a, n in nodes.items() if n.get("npcs")]:
            for npc in nodes[tid]["npcs"]:
                if (npc.get("state") or {}).get("soul_ref") == sd.name and npc.get("location"):
                    finer = f"{tid}/{npc['location']}"
                    if finer in nodes and addr == tid:
                        issues.append({"kind": "coarse", "addr": finer,
                                       "msg": f"{sj.get('name_local') or sid} 的 run_state 只写到 {raw},"
                                              f"{tid}/npcs.json 有更细的 {finer}(已采用)"})
                        addr = finer
                    elif finer in nodes and addr and addr != finer and not addr.startswith(tid):
                        issues.append({"kind": "conflict", "addr": finer,
                                       "msg": f"{sj.get('name_local') or sid} 位置:run_state={addr} vs npcs.json={finer}"})
        entities.append({
            "id": sid, "kind": "soul", "dir": sd.name, "name": sj.get("name_local") or sj.get("name") or sid,
            "addr": addr if addr in nodes else None, "raw": raw, "status": srs.get("status") or {},
            "has_portrait": soul_asset(root, sid, "portrait") is not None,
            "has_sprite": soul_asset(root, sid, "sprite") is not None,
            "portrait_fallback": fallback_art.soul_dir(sd),
        })
    for tid, t in list(nodes.items()):
        for npc in t.get("npcs") or []:
            if (npc.get("state") or {}).get("soul_ref"):
                continue
            a = f"{tid}/{npc['location']}" if npc.get("location") and f"{tid}/{npc['location']}" in nodes else tid
            entities.append({"id": str(npc.get("id")), "kind": "npc", "name": npc.get("name") or "?",
                             "addr": a, "role": npc.get("role"), "traits": npc.get("traits") or [],
                             "met": bool((npc.get("state") or {}).get("met")), "portrait_fallback": fallback_art.portrait(npc)})

    tree = {"root": ROOT, "nodes": nodes, "entities": entities, "flat_locations": flat, "issues": issues}
    for lv in map_levels(tree):
        nodes[lv]["level"] = level_kind(tree, lv)
    return tree


def map_levels(tree: dict[str, Any]) -> list[str]:
    """Nodes whose children have coordinates → each is one drawable map."""
    return [a for a, n in tree["nodes"].items() if n["children"] and all("pos" in tree["nodes"][c] for c in n["children"])]


# ── coordinates ↔ image ─────────────────────────────────────────────────

def layout_fit(tree: dict[str, Any], level: str) -> dict[str, float]:
    kids = tree["nodes"][level]["children"]
    xs = [tree["nodes"][c]["pos"]["x"] for c in kids] or [0.0]
    ys = [tree["nodes"][c]["pos"]["y"] for c in kids] or [0.0]
    px, py = PADS[level_kind(tree, level)]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    return {"px": px, "py": py, "x0": x0, "y0": y0,
            "sx": (W - 2 * px) / max(1e-9, x1 - x0) if x1 > x0 else 1.0,
            "sy": (H - 2 * py) / max(1e-9, y1 - y0) if y1 > y0 else 1.0}


def to_image(fit: dict[str, float], x: float, y: float) -> tuple[float, float]:
    """Level coordinates → percent of the image."""
    return ((fit["px"] + (x - fit["x0"]) * fit["sx"]) / W * 100,
            (fit["py"] + (y - fit["y0"]) * fit["sy"]) / H * 100)


def to_level(fit: dict[str, float], xp: float, yp: float) -> tuple[float, float]:
    """Percent of the image → level coordinates (inverse of to_image)."""
    return (fit["x0"] + (xp / 100 * W - fit["px"]) / fit["sx"],
            fit["y0"] + (yp / 100 * H - fit["py"]) / fit["sy"])


def level_fit(root: Path, tree: dict[str, Any], level: str) -> dict[str, float]:
    """The frozen transform of the current image if there is one, else a fresh fit."""
    meta = _rj(map_meta_path(root, level)) or {}
    fit = meta.get("fit")
    if isinstance(fit, dict) and all(k in fit for k in ("px", "py", "x0", "y0", "sx", "sy")):
        return fit
    return layout_fit(tree, level)


def hotspots(root: Path, tree: dict[str, Any], level: str) -> dict[str, list[float]]:
    fit = level_fit(root, tree, level)
    out = {}
    for c in tree["nodes"][level]["children"]:
        p = tree["nodes"][c]["pos"]
        x, y = to_image(fit, p["x"], p["y"])
        out[c] = [round(x, 2), round(y, 2)]
    return out


def layout_hash(tree: dict[str, Any], level: str) -> str:
    n = tree["nodes"]
    sig = [(c, n[c]["kind"], n[c]["name"], round(n[c]["pos"]["x"], 1), round(n[c]["pos"]["y"], 1))
           for c in sorted(n[level]["children"])]
    sig.append(("edges", sorted((e["from"], e["to"]) for e in n[level]["edges"])))
    return hashlib.sha1(json.dumps(sig, ensure_ascii=False).encode()).hexdigest()[:12]


def map_status(root: Path, tree: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out = {}
    for lv in map_levels(tree):
        meta = _rj(map_meta_path(root, lv)) or {}
        has = map_image_path(root, lv).is_file()
        out[lv] = {
            "has_image": has,
            "stale": bool(has and meta.get("layout_hash") and meta["layout_hash"] != layout_hash(tree, lv)),
            "backend": meta.get("backend"), "generated_at": meta.get("generated_at"),
            "kind": level_kind(tree, lv),
        }
    return out


# ── layout guide (what the image model must follow) ─────────────────────

def draw_guide(tree: dict[str, Any], level: str, out: Path, fit: dict[str, float] | None = None) -> Path:
    from PIL import Image, ImageDraw, ImageFilter

    fit = fit or layout_fit(tree, level)
    nodes = tree["nodes"]
    kids = nodes[level]["children"]
    P = {c: (to_image(fit, nodes[c]["pos"]["x"], nodes[c]["pos"]["y"])) for c in kids}
    P = {c: (x / 100 * W, y / 100 * H) for c, (x, y) in P.items()}
    kind = level_kind(tree, level)
    rng = random.Random(level)

    if kind == "world":
        im = Image.new("RGB", (W, H), (196, 182, 150))
        d = ImageDraw.Draw(im)
        dirs = {f.get("direction") for f in nodes[level].get("frontier") or [] if isinstance(f, dict)}
        names = " ".join(str(f.get("name", "")) for f in nodes[level].get("frontier") or [] if isinstance(f, dict))
        if "north" in dirs:
            for i in range(19):
                x = 40 + i * 82
                y = 60 + (i % 3) * 18
                d.polygon([(x, y + 90), (x + 55, y), (x + 110, y + 90)], fill=(120, 112, 100))
        if "south" in dirs:
            fill = (88, 104, 116) if ("海" in names or "sea" in names.lower()) else (150, 150, 120)
            d.rectangle([0, H - 120, W, H], fill=fill)
        if dirs & {"east", "far_east"}:
            for i in range(40):
                x = 1180 + (i * 53) % 330
                y = 240 + (i * 97) % 460
                d.ellipse([x, y, x + 46, y + 46], fill=(88, 110, 78))
        # a river runs through any settlement that has a dock
        for c in kids:
            if any(nodes[s]["kind"] == "dock" for s in nodes[c]["children"]):
                x, y = P[c]
                d.line([(x - 260, 150), (x - 120, y - 160), (x + 10, y + 30), (x - 60, y + 260), (x + 40, H - 110)],
                       fill=(92, 118, 132), width=34, joint="curve")
        for e in nodes[level]["edges"]:
            if e["from"] in P and e["to"] in P:
                road = e.get("kind") != "trail"
                d.line([P[e["from"]], P[e["to"]]], fill=(150, 120, 80) if road else (120, 100, 70), width=12 if road else 7)
        for c in kids:
            x, y = P[c]
            k = nodes[c]["kind"]
            if k in ("town", "city"):
                r = 46 if k == "city" else 36
                for j in range(9):
                    a = j * 0.7
                    bx, by = x + math.cos(a) * r * 0.6, y + math.sin(a) * r * 0.5
                    d.rectangle([bx - 12, by - 10, bx + 12, by + 10], fill=(70, 60, 55))
                if k == "city":
                    d.ellipse([x - r, y - r, x + r, y + r], outline=(70, 60, 55), width=6)
            elif k == "dungeon":
                d.ellipse([x - 30, y - 22, x + 30, y + 22], fill=(40, 50, 40))
                d.ellipse([x - 12, y - 10, x + 12, y + 10], fill=(10, 10, 10))
            else:
                for j in range(5):
                    d.rectangle([x - 40 + j * 18, y - 20 + (j % 2) * 14, x - 28 + j * 18, y + 6 + (j % 2) * 14],
                                fill=(150, 150, 140))
    elif kind == "town":
        im = Image.new("RGB", (W, H), (128, 138, 120))
        d = ImageDraw.Draw(im)
        docks = [P[c] for c in kids if nodes[c]["kind"] == "dock"]
        if docks:
            dy = max(y for _, y in docks)
            d.polygon([(0, dy + 40), (W, dy - 60), (W, H), (0, H)], fill=(70, 96, 110))
        gates = [P[c] for c in kids if nodes[c]["kind"] == "gate"]
        for gx, gy in gates:
            if gy < H * 0.35:
                d.line([(40, gy - 10), (W - 40, gy - 60)], fill=(100, 95, 90), width=26)
            elif gx < W * 0.3:
                d.line([(gx + 10, 40), (gx - 10, H - 40)], fill=(100, 95, 90), width=26)
        for e in nodes[level]["edges"]:
            if e["from"] in P and e["to"] in P:
                d.line([P[e["from"]], P[e["to"]]], fill=(170, 160, 140), width=34)
        for c in kids:
            x, y = P[c]
            k = nodes[c]["kind"]
            if k == "gate":
                d.rectangle([x - 50, y - 60, x + 50, y + 30], fill=(80, 76, 70))
                d.rectangle([x - 20, y - 20, x + 20, y + 30], fill=(30, 28, 26))
            elif k == "dock":
                d.rectangle([x - 90, y - 10, x + 90, y + 26], fill=(110, 84, 60))
                d.polygon([(x + 20, y + 40), (x + 110, y + 40), (x + 90, y + 70), (x + 40, y + 70)], fill=(90, 64, 44))
            elif k == "street":
                d.ellipse([x - 70, y - 45, x + 70, y + 45], fill=(165, 155, 135))
            else:
                d.rectangle([x - 70, y - 55, x + 70, y + 45], fill=(92, 70, 58))
                d.polygon([(x - 80, y - 55), (x, y - 110), (x + 80, y - 55)], fill=(60, 48, 44))
        top = min((y for _, y in gates), default=60) + 40
        bottom = min((y for _, y in docks), default=H - 40) - 30
        for _ in range(80):
            x, y = rng.randint(60, W - 60), rng.randint(int(top), int(max(top + 1, bottom)))
            if min(math.hypot(x - px_, y - py_) for px_, py_ in P.values()) < 130:
                continue
            d.rectangle([x - 24, y - 18, x + 24, y + 16], fill=(105, 84, 70))
    else:  # dungeon
        im = Image.new("RGB", (W, H), (38, 40, 42))
        d = ImageDraw.Draw(im)
        for e in nodes[level]["edges"]:
            if e["from"] in P and e["to"] in P:
                d.line([P[e["from"]], P[e["to"]]], fill=(88, 86, 80), width=40)
        for c in kids:
            x, y = P[c]
            big = nodes[c]["kind"] == "boss"
            w, h = (130, 100) if big else (100, 76)
            d.rectangle([x - w, y - h, x + w, y + h], fill=(120, 116, 104))
            d.rectangle([x - w + 14, y - h + 14, x + w - 14, y + h - 14], fill=(72, 70, 64))
    out.parent.mkdir(parents=True, exist_ok=True)
    im.filter(ImageFilter.GaussianBlur(1.3)).save(out)
    return out


# ── prompts (content from the files, layout from the guide) ─────────────

def art_style(root: Path) -> str:
    p = root / "assets" / "art-style.md"
    try:
        s = p.read_text(encoding="utf-8").strip()
        return s or DEFAULT_STYLE
    except OSError:
        return DEFAULT_STYLE


def map_prompt(root: Path, tree: dict[str, Any], level: str) -> str:
    n = tree["nodes"]
    lv = n[level]
    kind = level_kind(tree, level)
    items = []
    for c in lv["children"]:
        k = n[c]
        items.append(f"- {KIND_EN.get(k['kind'], k['kind'])} 「{k['name']}」: {k.get('summary') or ''}".strip())
    if kind == "world":
        head = (f"Turn this layout sketch into a hand-painted top-down fantasy regional map of 「{lv['name']}」. "
                "STRICTLY keep the sketch's composition: every settlement exactly where a dark cluster is drawn, "
                "roads and trails exactly along the drawn lines, terrain bands (mountains, sea, forest, river) where drawn.")
    elif kind == "town":
        head = (f"Turn this layout sketch into a painted top-down (slightly isometric) map of 「{lv['name']}」 — "
                f"{lv.get('overview') or lv.get('summary') or ''} STRICTLY keep the sketch's layout: each marked "
                "building, gate, square and dock exactly where drawn, streets along the drawn lines, walls and water where drawn; "
                "small ordinary houses fill the rest.")
    else:
        head = (f"Turn this layout sketch into a painted top-down dungeon map of 「{lv['name']}」 "
                f"({(lv.get('dungeon') or {}).get('theme') or lv.get('summary') or ''}). STRICTLY keep each room exactly where "
                "a chamber is drawn and corridors along the drawn lines.")
    return f"{head}\nPlaces (content only — positions come from the sketch):\n" + "\n".join(items) + f"\nStyle: {art_style(root)}"


def scene_prompt(root: Path, tree: dict[str, Any], addr: str) -> str:
    n = tree["nodes"][addr]
    par = tree["nodes"].get(n.get("parent") or "", {})
    detail = n.get("detail") or {}
    bits = [f"「{n['name']}」, a {KIND_EN.get(n['kind'], n['kind'])} in 「{par.get('name', '')}」.",
            par.get("overview") or par.get("summary") or "", n.get("summary") or "",
            detail.get("description") or ""]
    feats = detail.get("features")
    if isinstance(feats, list) and feats:
        bits.append("Details: " + "; ".join(map(str, feats)))
    return (" ".join(b for b in bits if b) +
            " Wide establishing shot for a visual-novel background, eye level, empty foreground floor for characters to stand. "
            f"Style: {art_style(root)}")


def portrait_prompt(root: Path, sid: str) -> str:
    d = soul_dir(root, sid)
    if d is None:
        raise ValueError(f"no soul {sid}")
    sj = _rj(d / "soul.json") or {}
    prof = _rj(d / "character" / "profile.json") or {}
    eq = _rj(d / "character" / "equipment.json") or {}
    charter = ""
    try:
        charter = (d / "soul.md").read_text(encoding="utf-8")[:900]
    except OSError:
        pass
    gear = ", ".join(str(v) for v in ((eq.get("equipped") or {}).values())) if isinstance(eq.get("equipped"), dict) else ""
    return ("Create a NEW character portrait in EXACTLY the same art style, rendering, lighting and framing as the "
            "reference portraits (same painter, same game). "
            f"Character: {sj.get('name') or sid} ({sj.get('name_local') or ''}). {prof.get('summary') or ''} "
            f"Gear: {gear}. Character notes:\n{charter}\n"
            "Half-body portrait facing slightly toward the viewer, soft-focus background of where they live. "
            "No text, no letters, no logo, no card frame.")


# ── generation ───────────────────────────────────────────────────────────

def _to_webp(src: Path, dst: Path, *, max_side: int = 1600, quality: int = 84) -> Path:
    from PIL import Image

    im = Image.open(src)
    im.thumbnail((max_side, max_side))
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, "WEBP", quality=quality)
    return dst


def generate_map(root: Path, level: str, *, cfg: Any = None) -> dict[str, Any]:
    """Guide → image model → ``assets/maps/<level>.webp`` + meta with frozen transform."""
    from neonrp.core.imagegen import edit_image, load_image_config

    cfg = cfg or load_image_config()
    tree = build_map_tree(root)
    if level not in map_levels(tree):
        raise ValueError(f"{level} has no drawable map (no child coordinates)")
    fit = layout_fit(tree, level)
    guide = draw_guide(tree, level, map_guide_path(root, level), fit)
    prompt = map_prompt(root, tree, level)
    raw = map_image_path(root, level).with_suffix(".raw.png")
    edit_image(prompt, [guide], raw, cfg=cfg, width=W, height=H)
    _to_webp(raw, map_image_path(root, level))
    raw.unlink(missing_ok=True)
    meta = {
        "level": level, "fit": fit, "size": [W, H], "layout_hash": layout_hash(tree, level),
        "backend": cfg.backend, "model": getattr(cfg, "openai_model", "") if cfg.backend == "openai" else cfg.backend,
        "prompt": prompt, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "guide": map_guide_path(root, level).name,
    }
    _wj(map_meta_path(root, level), meta)
    return meta


def generate_scene(root: Path, addr: str, *, cfg: Any = None) -> Path:
    from neonrp.core.imagegen import generate_image, load_image_config

    cfg = cfg or load_image_config()
    tree = build_map_tree(root)
    if addr not in tree["nodes"]:
        raise ValueError(f"unknown place {addr}")
    tmp = generate_image(scene_prompt(root, tree, addr), root / ".neonrp" / "imagegen", cfg=cfg, width=W, height=H)
    for ext in _IMG_EXTS:
        (root / "assets" / "places" / f"{_slug(addr)}{ext}").unlink(missing_ok=True)
    return _to_webp(tmp, root / "assets" / "places" / f"{_slug(addr)}.webp", max_side=1600)


def generate_portrait(root: Path, sid: str, *, cfg: Any = None, sprite: bool = True) -> Path:
    """Style-matched portrait (other portraits in this world are the style references)."""
    from neonrp.core.imagegen import edit_image, load_image_config

    cfg = cfg or load_image_config()
    d = soul_dir(root, sid)
    if d is None:
        raise ValueError(f"no soul {sid}")
    refs = [p for p in (root / "souls").glob("*/assets/portrait.png") if p.parent.parent != d][:2]
    player = _gdir(root) / "player" / "assets" / "portrait.png"
    if player.is_file() and len(refs) < 2:
        refs.append(player)
    out = d / "assets" / "portrait.png"
    raw = d / "assets" / "portrait.raw.png"
    edit_image(portrait_prompt(root, sid), refs, raw, cfg=cfg, width=1024, height=1536)
    raw.replace(out)
    if sprite:
        make_sprite(root, sid, cfg=cfg)
    return out


def make_sprite(root: Path, sid: str, *, cfg: Any = None) -> Path | None:
    """Transparent standing sprite for the 'space' view, cut from the portrait."""
    from neonrp.core.imagegen import edit_image, load_image_config

    cfg = cfg or load_image_config()
    src = soul_asset(root, sid, "portrait")
    d = soul_dir(root, sid)
    if src is None or d is None:
        return None
    raw = d / "assets" / "sprite.raw.png"
    try:
        edit_image("Remove the background completely; output the same character as a clean cut-out on a fully "
                   "transparent background. Keep the character EXACTLY identical. No shadow, no text.",
                   [src], raw, cfg=cfg, width=1024, height=1536, background="transparent")
    except Exception as exc:  # sprite is a nicety; the portrait already landed
        logger.warning("sprite cut failed for %s: %s", sid, exc)
        return None
    from PIL import Image

    im = Image.open(raw)
    if im.mode == "RGBA" and im.getbbox():
        im = im.crop(im.getbbox())
    im.thumbnail((1000, 1000))
    out = d / "assets" / "sprite.webp"
    im.save(out, "WEBP", quality=84)
    raw.unlink(missing_ok=True)
    return out


# ── editing (workbench) ──────────────────────────────────────────────────

def _level_key(tree: dict[str, Any], level: str) -> str:
    """The place_tree level a map level is stored as ("world" or the town id)."""
    if level == ROOT:
        return "world"
    if level_kind(tree, level) == "town":
        return level
    raise ValueError("dungeon rooms are laid out automatically; edit layout.json links instead")


def _rel(root: Path, p: Path) -> str:
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


def move_node(root: Path, level: str, addr: str, xp: float, yp: float) -> dict[str, Any]:
    """Drop a node at image-percent (xp, yp); writes its coordinates back to the level file."""
    tree = build_map_tree(root)
    if tree["nodes"].get(addr, {}).get("parent") != level:
        raise ValueError(f"{addr} is not on map {level}")
    fit = level_fit(root, tree, level)
    x, y = to_level(fit, xp, yp)
    from neonrp.core.place_tree import level_doc, save_level_doc

    key = _level_key(tree, level)
    data = level_doc(root, key) or {}
    nid = tree["nodes"][addr]["id"]
    for n in data.get("nodes") or []:
        if isinstance(n, dict) and n.get("id") == nid:
            n["pos"] = [round(x, 2), round(y, 2)] if level == ROOT else {"x": round(x), "y": round(y)}
            break
    else:
        raise ValueError(f"{nid} not on map {level}")
    written = save_level_doc(root, key, data)
    return {"file": _rel(root, _written_for(written, nid)), "id": nid, "pos": [round(x, 2), round(y, 2)]}


def _written_for(written: list[Path], nid: str) -> Path:
    """The file that holds ``nid`` among what a level save wrote (its folder record, or the one map file)."""
    return next((p for p in written if p.name == "location.json" and p.parent.name == nid), written[0])


def add_node(root: Path, level: str, *, name: str, kind: str, xp: float, yp: float,
             summary: str = "", link_to: str | None = None) -> dict[str, Any]:
    tree = build_map_tree(root)
    fit = level_fit(root, tree, level)
    x, y = to_level(fit, xp, yp)
    from neonrp.core.place_tree import level_doc, save_level_doc

    key = _level_key(tree, level)
    data = level_doc(root, key) or {"nodes": []}
    existing = {str(n.get("id")) for n in data.get("nodes") or [] if isinstance(n, dict)}
    base = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")
    if not base or not base[0].isalpha():
        base = ("N" if level == ROOT else "spot") + f"{len(existing) + 1:03d}"
    nid, i = base, 2
    while nid in existing:
        nid, i = f"{base}_{i}", i + 1
    if level == ROOT:
        node: dict[str, Any] = {"id": nid, "type": kind or "town", "name": name, "region": "",
                                "pos": [round(x, 2), round(y, 2)], "summary": summary, "links": [],
                                "state": {"discovered": True}}
    else:
        node = {"id": nid, "name": name, "type": kind or "facility", "description": summary,
                "pos": {"x": round(x), "y": round(y)}, "links": []}
        link = (link_to or "").split("/")[-1] or None
        if link and link in existing:
            node["links"].append(link)
            for n in data["nodes"]:
                if n.get("id") == link:
                    n.setdefault("links", []).append(nid)
        disc = (data.get("state") or {}).get("discovered_nodes")
        if isinstance(disc, list):
            disc.append(nid)
    data.setdefault("nodes", []).append(node)
    written = save_level_doc(root, key, data)
    addr = nid if level == ROOT else f"{level}/{nid}"
    return {"file": _rel(root, _written_for(written, nid)), "addr": addr, "node": node}


def set_road(root: Path, level: str, a: str, b: str, *, remove: bool = False, distance: Any = None) -> dict[str, Any]:
    """Add / remove the road between two places on one level (1.0 创作写回). A road is the pair's
    ``links`` (both ways — a place folder's ``connections``); on the world level a route with a distance lives in
    ``world_map.json`` ``routes`` and is added / removed with it. Returns {file(s), edges on that level}."""
    from neonrp.core.place_tree import level_doc, save_level_doc

    tree = build_map_tree(root)
    if level not in tree["nodes"]:
        raise ValueError(f"no level {level!r}")
    key = _level_key(tree, level)
    la, lb = a.split("/")[-1], b.split("/")[-1]
    if la == lb:
        raise ValueError("a road needs two different places")
    data = level_doc(root, key) or {"nodes": []}
    by = {str(n.get("id")): n for n in data.get("nodes") or [] if isinstance(n, dict) and n.get("id")}
    if la not in by or lb not in by:
        raise ValueError(f"{a} / {b}: not both on level {level}")
    if level != ROOT and (by[la].get("parent") or None) != (by[lb].get("parent") or None):
        raise ValueError("roads join places of the same level; across levels use a port")
    for x, y in ((la, lb), (lb, la)):
        links = [str(v) for v in by[x].get("links") or []]
        if remove:
            links = [v for v in links if v != y]
        elif y not in links:
            links.append(y)
        by[x]["links"] = links
    if level == ROOT:
        routes = [r for r in data.get("routes") or [] if isinstance(r, dict)]
        same = lambda r: {str(r.get("from")), str(r.get("to"))} == {la, lb}  # noqa: E731
        routes = [r for r in routes if not same(r)]
        if not remove and distance not in (None, ""):
            routes.append({"id": f"R_{min(la, lb)}_{max(la, lb)}", "from": la, "to": lb, "kind": "road", "distance": distance})
        data["routes"] = routes
    written = save_level_doc(root, key, data)
    t2 = build_map_tree(root)
    return {"files": [_rel(root, w) for w in written], "edges": len(t2["nodes"][level]["edges"])}


def bind_scene(root: Path, addr: str, data: bytes) -> Path:
    """Store an uploaded picture as the scene image of a place."""
    import io

    from PIL import Image

    im = Image.open(io.BytesIO(data))
    im.load()
    for ext in _IMG_EXTS:
        (root / "assets" / "places" / f"{_slug(addr)}{ext}").unlink(missing_ok=True)
    out = root / "assets" / "places" / f"{_slug(addr)}.webp"
    out.parent.mkdir(parents=True, exist_ok=True)
    im.thumbnail((1600, 1600))
    im.convert("RGB").save(out, "WEBP", quality=84)
    return out


# ── views ────────────────────────────────────────────────────────────────

def _known(n: dict[str, Any]) -> bool:
    return (n.get("state") or {}).get("discovered") is not False


_GOLDEN = 2.399963229728653  # radians: spreads guessed places around without two landing on one spot


def place_unplaced(tree: dict[str, Any]) -> set[str]:
    """A level's places that have no position of their own — none, or the very spot a sibling already has (rooms that
    all say {0, 0}, a place the engine grew) — get one in the level's free space: beside the sibling they link to, else
    on a ring around the level. Marked ``pos_guess``; returns their addresses (10-15, §5.20)."""
    nodes = tree["nodes"]
    guessed: set[str] = set()
    for addr, n in nodes.items():
        kids = [c for c in n.get("children") or [] if c in nodes]
        if not kids:
            continue
        placed: dict[str, tuple[float, float]] = {}
        todo: list[str] = []
        for c in kids:
            p = nodes[c].get("pos")
            xy = (float(p["x"]), float(p["y"])) if isinstance(p, dict) and "x" in p and "y" in p else None
            if xy is None or xy in placed.values():
                todo.append(c)
            else:
                placed[c] = xy
        if not todo:
            continue
        pts = list(placed.values()) or [(0.0, 0.0)]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        span = max(max(xs) - min(xs), max(ys) - min(ys)) or 100.0
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        links: dict[str, list[str]] = {}
        for e in n.get("edges") or []:
            if isinstance(e, dict) and e.get("from") and e.get("to"):
                links.setdefault(str(e["from"]), []).append(str(e["to"]))
                links.setdefault(str(e["to"]), []).append(str(e["from"]))
        for k, c in enumerate(todo):
            anchor = next((placed[x] for x in links.get(c, []) if x in placed), None)
            r, (ax, ay) = (0.18 * span, anchor) if anchor else ((0.5 if placed else 0.4) * span, (cx, cy))
            for step in range(24):  # the first angle that is not on top of someone
                a = (k + step) * _GOLDEN
                x, y = ax + r * math.cos(a), ay + r * math.sin(a)
                if all(math.hypot(x - px, y - py) > 0.08 * span for px, py in placed.values()):
                    break
            placed[c] = (round(x, 2), round(y, 2))
            nodes[c]["pos"] = {"x": placed[c][0], "y": placed[c][1]}
            nodes[c]["pos_guess"] = True
            guessed.add(c)
    return guessed


def pos100(tree: dict[str, Any]) -> None:
    """Every node's ``pos100``: its position on its own level as 0–100 (each level's own units — world grid, town
    pixels, room slots — fitted to 6–94), so levels can be drawn and stacked the same way (10-15, §5.20)."""
    nodes = tree["nodes"]
    for n in nodes.values():
        kids = [c for c in n.get("children") or [] if c in nodes and isinstance(nodes[c].get("pos"), dict)]
        if not kids:
            continue
        xs = [float(nodes[c]["pos"]["x"]) for c in kids]
        ys = [float(nodes[c]["pos"]["y"]) for c in kids]
        x0, y0 = min(xs), min(ys)
        sx, sy = (max(xs) - x0) or 0.0, (max(ys) - y0) or 0.0
        s = max(sx, sy)
        for c, x, y in zip(kids, xs, ys):
            nodes[c]["pos100"] = {"x": round(50 + (x - x0 - sx / 2) / s * 88, 2) if s else 50.0,
                                  "y": round(50 + (y - y0 - sy / 2) / s * 88, 2) if s else 50.0}


def map_view(root: Path, *, lens: str = "studio") -> dict[str, Any]:
    """What the UI renders. ``lens="play"`` hides what the player hasn't found."""
    tree = build_map_tree(root)
    guessed = place_unplaced(tree)
    pos100(tree)
    status = map_status(root, tree)
    levels = {}
    for lv in map_levels(tree):
        hs = hotspots(root, tree, lv)
        # a place the image was not drawn with (grown later, or placed by guess) still gets a pin: near where its
        # position falls on the image, kept inside the frame, flagged so the screen can draw it as approximate
        guess = sorted(c for c, (x, y) in hs.items() if c in guessed or not (0 <= x <= 100 and 0 <= y <= 100))
        hs = {c: [min(98.0, max(2.0, x)), min(98.0, max(2.0, y))] for c, (x, y) in hs.items()}
        levels[lv] = {**status[lv], "hotspots": hs, "hotspot_guess": guess}
    for a, n in tree["nodes"].items():
        n["has_scene"] = scene_image_path(root, a) is not None
    view = {**tree, "levels": levels}
    if lens != "play":
        return view
    nodes = {}
    for a, n in tree["nodes"].items():
        if _known(n) and (n["parent"] is None or _known(tree["nodes"][n["parent"]])):
            m = {k: v for k, v in n.items() if k not in ("dungeon", "npcs")}
            ex = dict(m.get("extra") or {})
            if "lore" in ex:
                ex["lore"] = {"player_knowledge": (ex["lore"] or {}).get("player_knowledge") or []}
            m["extra"] = ex
            nodes[a] = m
        else:
            nodes[a] = {"addr": a, "id": a, "name": "", "kind": "unknown", "parent": n["parent"],
                        "pos": n.get("pos"), "pos100": n.get("pos100"), "children": [], "edges": [], "state": {"discovered": False},
                        "summary": "", "has_scene": False}
    player_addr = next((e["addr"] for e in tree["entities"] if e["kind"] == "player"), None)
    ents = []
    for e in tree["entities"]:
        if e["kind"] == "npc" and not e.get("met"):
            ents.append({**e, "name": "", "traits": []})
        elif e["kind"] == "soul" and e["addr"] != player_addr and not (e.get("status") or {}).get("met_player"):
            continue  # a soul you haven't met, somewhere else — not on your map
        else:
            ents.append(e)
    return {"root": ROOT, "nodes": nodes, "entities": ents, "levels": levels,
            "flat_locations": [], "issues": []}
