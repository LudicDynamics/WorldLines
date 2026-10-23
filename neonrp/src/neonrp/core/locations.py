"""Places as folders (任务 B2).

A location used to be one file, ``game/locations/<id>.json``. Agents now
create places *while playing* and keep refining them, and a place that
grows (notes, sub-places, scene state, pictures) wants a folder:

    game/locations/<id>/location.json   ← the record (same keys as the file form)
    game/locations/<id>/notes.md        ← free-form refinement
    game/locations/<id>/scene_state.json (already lived here)
    game/locations/<id>/assets/          ← pictures, later

Both forms are read everywhere (vault, map, location header); new places
are always written in the folder form. The world map (``world_map.json``)
gets a node for every new place so the map tab and the canvas see it.

Town-structured worlds (``game/towns/<TID>/town_map.json``, TODO #5 2026-09-11)
get the place registered as a node of the right town too — that map is what
movement (`place_nav`) and the souls' perception actually walk, so a place
that only lived in ``game/locations/`` was somewhere nobody could go. The
town is the explicit ``town=``, else the parent's / a connection's town, else
the town the player is standing in; a place in no town stays wilderness.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

LOCATION_FILE = "location.json"
NOTES_FILE = "notes.md"
_META_FILES = {"scene_state.json", "map.json"}


class LocationError(ValueError):
    pass


def locations_dir(root: Path) -> Path:
    try:
        from neonrp.core.paths import get_game_dir

        return get_game_dir(root) / "locations"
    except Exception:
        return root / "game" / "locations"


def world_map_path(root: Path) -> Path:
    try:
        from neonrp.core.paths import get_game_dir

        return get_game_dir(root) / "world" / "world_map.json"
    except Exception:
        return root / "game" / "world" / "world_map.json"


def towns_dir(root: Path) -> Path:
    try:
        from neonrp.core.paths import get_game_dir

        return get_game_dir(root) / "towns"
    except Exception:
        return root / "game" / "towns"


def town_map_file(root: Path, town: str) -> Path:
    return towns_dir(root) / town / "town_map.json"


def town_ids(root: Path) -> list[str]:
    """Towns with a map: ``towns/<T>/town_map.json``, or (folder tree) a place with places inside it."""
    from neonrp.core import place_tree

    return place_tree.town_ids(root)


def _town_dir_for(root: Path, town: str) -> Path | None:
    """Where ``town``'s map lives (its towns/ dir, or its place folder in tree form); None if it has no map."""
    from neonrp.core import place_tree

    if town not in place_tree.town_ids(root):
        return None
    if place_tree.level_in_folders(root, town):
        return place_tree.locations_dir(root) / town
    return place_tree.town_map_file(root, town).parent


def _player_town(root: Path) -> str | None:
    try:
        from neonrp.core.light_chat import _player_node
        from neonrp.core.place_nav import split_location

        town, _node = split_location(_player_node(root))
        return town
    except Exception:
        return None


def resolve_town(
    root: Path,
    *,
    town: str | None = None,
    parent: str | None = None,
    connections: list[str] | tuple[str, ...] = (),
) -> str | None:
    """Which town a new place belongs to, or None (no towns / wilderness)."""
    if not town_ids(root):
        return None
    from neonrp.core.place_nav import split_location, town_of_node

    if town:
        t = str(town).strip()
        if _town_dir_for(root, t) is not None:
            return t
        t2, _ = split_location(t)
        if t2 and _town_dir_for(root, t2) is not None:
            return t2
    if parent:
        t, node = split_location(parent)
        if t and _town_dir_for(root, t) is not None:
            return t
        t = town_of_node(root, node or parent)
        if t:
            return t
    for c in connections:
        t, node = split_location(str(c))
        t = t if (t and _town_dir_for(root, t) is not None) else town_of_node(root, node or str(c))
        if t:
            return t
    return _player_town(root)


def town_of_place(root: Path, loc_id: str) -> str | None:
    rec = location_record_path(root, loc_id)
    if rec is not None:
        t = _read_json(rec).get("town")
        if isinstance(t, str) and t and _town_dir_for(root, t) is not None:
            return t
    try:
        from neonrp.core.place_nav import town_of_node

        return town_of_node(root, loc_id)
    except Exception:
        return None


def _town_pos(nodes: list[Any], anchor: dict[str, Any] | None) -> dict[str, int]:
    """Where a grown place sits on the town map (「连接图是否能画出来」): beside the place it hangs off,
    pointing away from the town's middle, clear of the other nodes. Deterministic."""
    import math

    pts = [(float(n["pos"]["x"]), float(n["pos"]["y"])) for n in nodes
           if isinstance(n, dict) and isinstance(n.get("pos"), dict) and {"x", "y"} <= set(n["pos"])]
    if anchor is None or not isinstance(anchor.get("pos"), dict) or not pts:
        i = len(nodes)
        return {"x": 100 + (i * 90) % 700, "y": 100 + (i * 70) % 400}
    ax, ay = float(anchor["pos"]["x"]), float(anchor["pos"]["y"])
    cx, cy = sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts)
    base = math.atan2(ay - cy, ax - cx) if (ax, ay) != (cx, cy) else 0.0
    for k in range(24):  # 0, +30°, −30°, +60°, … then a longer arm
        ang = base + math.radians(30 * ((k % 12 + 1) // 2) * (1 if k % 2 else -1))
        r = 90 if k < 12 else 150
        x, y = ax + r * math.cos(ang), ay + r * math.sin(ang)
        if all((x - px) ** 2 + (y - py) ** 2 >= 60 ** 2 for px, py in pts):
            return {"x": round(x), "y": round(y)}
    return {"x": round(ax + 90), "y": round(ay + 60)}


def _sync_town_node(
    root: Path,
    town: str,
    loc_id: str,
    *,
    name: str,
    summary: str,
    links: list[str],
    create: bool,
) -> Path | None:
    """Register/refresh ``loc_id`` in ``town``'s town_map (links kept symmetric
    with nodes that exist there). Returns the map path when it changed."""
    from neonrp.core import place_tree

    if _town_dir_for(root, town) is None:
        return None
    data = place_tree.level_doc(root, town) or {}
    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        nodes = []
        data["nodes"] = nodes
    by_id = {str(n.get("id")): n for n in nodes if isinstance(n, dict)}
    from neonrp.core.place_nav import split_location

    wanted: list[str] = []
    for raw in links:
        t, node = split_location(str(raw))
        node = node or str(raw)
        if (t is None or t == town) and node in by_id and node != loc_id and node not in wanted:
            wanted.append(node)
    changed = False
    node = by_id.get(loc_id)
    if node is None:
        if not create:
            return None
        node = {
            "id": loc_id,
            "name": name,
            "type": "place",
            "description": summary,
            "pos": _town_pos(nodes, by_id.get(wanted[0]) if wanted else None),
            "links": [],
        }
        nodes.append(node)
        by_id[loc_id] = node
        changed = True
    if name and node.get("name") != name:
        node["name"] = name
        changed = True
    if summary and node.get("description") != summary:
        node["description"] = summary
        changed = True
    cur = [str(lk) for lk in (node.get("links") or []) if lk]
    for lk in wanted:
        if lk not in cur:
            cur.append(lk)
            changed = True
    node["links"] = cur
    for lk in wanted:
        other = by_id[lk]
        back = [str(x) for x in (other.get("links") or []) if x]
        if loc_id not in back:
            back.append(loc_id)
            other["links"] = back
            changed = True
    if not changed:
        return None
    data.setdefault("town_id", town)
    written = place_tree.save_level_doc(root, town, data)
    return next((p for p in written if p.name == LOCATION_FILE and p.parent.name == loc_id), written[0])


def slugify_id(name: str) -> str:
    """A filesystem/id-safe token that keeps CJK (「北门」stays 北门)."""
    text = str(name or "").strip().lower()
    text = re.sub(r"[\s/\\:*?\"<>|]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-.")
    return text or "place"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    from neonrp.core.storage import atomic_write_json

    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, data)


def location_record_path(root: Path, loc_id: str) -> Path | None:
    """Where ``loc_id`` is recorded: folder form first, then the file form, then a place folder deeper in the tree
    (``T001/gate_north`` as an address, or a bare id / alias — the first town that has it)."""
    from neonrp.core import place_tree

    base = locations_dir(root)
    if "/" in str(loc_id):
        town, _, node = str(loc_id).partition("/")
        rec = place_tree.place_dir(root, town, node) / LOCATION_FILE
        return rec if rec.is_file() else None
    folder = base / loc_id / LOCATION_FILE
    if folder.is_file():
        return folder
    flat = base / f"{loc_id}.json"
    if flat.is_file():
        return flat
    for town in place_tree.town_ids(root):
        for node, f in place_tree.folder_nodes(root, town):
            if node["id"] == loc_id or loc_id in (node.get("aliases") or []):
                return f / LOCATION_FILE
    return None


def read_location(root: Path, loc_id: str) -> dict[str, Any] | None:
    path = location_record_path(root, loc_id)
    return _read_json(path) if path else None


def iter_locations(root: Path) -> list[tuple[str, dict[str, Any], Path]]:
    """Every place record, both forms, sorted by id; places deeper in a folder tree come after, as ``town/id``."""
    from neonrp.core import place_tree

    base = locations_dir(root)
    out: list[tuple[str, dict[str, Any], Path]] = []
    if not base.is_dir():
        return out
    for child in sorted(base.iterdir()):
        if child.is_dir():
            rec = child / LOCATION_FILE
            if rec.is_file():
                data = _read_json(rec)
                out.append((str(data.get("id") or child.name), data, rec))
        elif child.suffix == ".json" and child.name not in _META_FILES:
            data = _read_json(child)
            if data:
                out.append((str(data.get("id") or child.stem), data, child))
    for town in place_tree.town_ids(root):
        for node, f in place_tree.folder_nodes(root, town):
            out.append((f"{town}/{node['id']}", _read_json(f / LOCATION_FILE), f / LOCATION_FILE))
    return out


def _find_by_name(root: Path, token: str) -> str | None:
    t = str(token or "").strip().lower()
    if not t:
        return None
    for loc_id, data, _ in iter_locations(root):
        if loc_id.lower() == t or str(data.get("name") or "").strip().lower() == t:
            return loc_id
    return None


def resolve_location_id(root: Path, token: str) -> str | None:
    """Accept an id or a display name."""
    if location_record_path(root, token) is not None:
        return token
    return _find_by_name(root, token)


def _auto_pos(nodes: list[dict[str, Any]], parent: str | None) -> list[int]:
    if parent:
        for n in nodes:
            if isinstance(n, dict) and n.get("id") == parent and isinstance(n.get("pos"), list) and len(n["pos"]) == 2:
                return [int(n["pos"][0]) + 4, int(n["pos"][1]) + 3]
    i = len(nodes)
    return [4 + (i * 7) % 42, 3 + (i * 5) % 18]


def _sync_map_node(root: Path, loc_id: str, *, name: str, summary: str, parent: str | None, create: bool) -> bool:
    """Make sure the world map knows the place (world_map.json nodes, or its folder in tree form). True when it changed."""
    from neonrp.core import place_tree

    data = place_tree.level_doc(root, place_tree.WORLD) or {}
    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        nodes = []
        data["nodes"] = nodes
    for n in nodes:
        if isinstance(n, dict) and n.get("id") == loc_id:
            changed = False
            if name and n.get("name") != name:
                n["name"] = name
                changed = True
            if summary and n.get("summary") != summary:
                n["summary"] = summary
                changed = True
            if parent is not None and n.get("parent") != parent:
                n["parent"] = parent
                changed = True
            if changed:
                place_tree.save_level_doc(root, place_tree.WORLD, data)
            return changed
    if not create:
        return False
    node: dict[str, Any] = {"id": loc_id, "type": "place", "name": name, "summary": summary, "pos": _auto_pos(nodes, parent), "links": []}
    if parent:
        node["parent"] = parent
    nodes.append(node)
    place_tree.save_level_doc(root, place_tree.WORLD, data)
    return True


def _link(root: Path, a_id: str, b_id: str, *, add: bool) -> Path | None:
    """Symmetric connection edit on ``b_id``'s record. Returns the path written."""
    path = location_record_path(root, b_id)
    if path is None:
        return None
    data = _read_json(path)
    conns = [str(c) for c in (data.get("connections") or []) if c]
    if add and a_id not in conns:
        conns.append(a_id)
    elif not add and a_id in conns:
        conns.remove(a_id)
    else:
        return None
    data["connections"] = conns
    _write_json(path, data)
    return path


def create_location(
    root: Path,
    *,
    name: str,
    loc_id: str | None = None,
    summary: str = "",
    connections: list[str] | tuple[str, ...] = (),
    parent: str | None = None,
    tags: list[str] | tuple[str, ...] = (),
    notes: str = "",
    town: str | None = None,
    world_map: bool = True,
) -> dict[str, Any]:
    name = str(name or "").strip()
    if not name:
        raise LocationError("a place needs a name")
    from neonrp.core import place_tree

    loc_id = slugify_id(loc_id or name)
    if not place_tree.is_tree(root) and location_record_path(root, loc_id) is not None:
        raise LocationError(f"place already exists: {loc_id}")
    if parent:
        parent = resolve_location_id(root, parent) or parent
    resolved_conns: list[str] = []
    unknown: list[str] = []
    for c in connections:
        rid = resolve_location_id(root, str(c))
        if rid:
            if rid not in resolved_conns:
                resolved_conns.append(rid)
        else:
            unknown.append(str(c))

    folder = locations_dir(root) / loc_id
    town_id = resolve_town(root, town=town, parent=parent, connections=[*resolved_conns, *unknown])
    in_tree = bool(town_id) and place_tree.level_in_folders(root, town_id)
    if in_tree:
        # tree form: the place's folder goes inside its town's. In a town, ``parent`` is the spot it hangs off (it becomes
        # a road, as on the old town map) — going one layer down inside a spot is the map tool's ``in=`` (town_rehang)
        folder = place_tree.place_dir(root, town_id, loc_id)
    if place_tree.is_tree(root) and (folder / LOCATION_FILE).is_file():
        raise LocationError(f"place already exists: {loc_id}")
    record = folder / LOCATION_FILE
    if town_id:  # town-map nodes (gate_north, main_street…) are connections too, even with no game/locations record
        resolved_conns = [*resolved_conns, *[u for u in unknown if u not in resolved_conns]]
    payload: dict[str, Any] = {
        "id": loc_id,
        "kind": "location",
        "name": name,
        "tags": [str(t) for t in tags if str(t).strip()],
        "summary": str(summary or "").strip(),
        "connections": resolved_conns,
        "notes": "",
    }
    if parent:
        payload["parent"] = parent
    if town_id:
        payload["town"] = town_id
    _write_json(record, payload)
    written = [record]
    notes_path = folder / NOTES_FILE
    notes_path.write_text((f"# {name}\n\n" + (str(notes).strip() + "\n" if notes else "")), encoding="utf-8")
    written.append(notes_path)
    for c in resolved_conns:
        p = _link(root, loc_id, c, add=True)
        if p:
            written.append(p)
    # world_map=False (the rpg pack, 10-02): world_map.json is the map between towns, a place inside a town goes on that town's map only
    # tree form: a place inside a town is on the town's map only — its folder already says where it is
    map_changed = _sync_map_node(root, loc_id, name=name, summary=payload["summary"], parent=parent, create=True) if (
        (world_map or not town_id) and not in_tree) else False
    town_map: Path | None = None
    if town_id:
        # Town-map links may name nodes that are not game/locations records
        # (gate_west, main_street…): pass the raw tokens through as well.
        raw_links = [*resolved_conns, *[str(c) for c in unknown]]
        if parent:
            raw_links.append(parent)
        town_map = _sync_town_node(root, town_id, loc_id, name=name, summary=payload["summary"], links=raw_links, create=True)
        if town_map:
            written.append(town_map)
    return {
        "id": loc_id,
        "name": name,
        "path": str(record.relative_to(root)) if record.is_relative_to(root) else str(record),
        "folder": str(folder),
        "connections": resolved_conns,
        "unknown_connections": unknown,
        "map_node_added": map_changed,
        "town": town_id,
        "town_node_added": bool(town_map),
        "written": [str(p.relative_to(root)) if p.is_relative_to(root) else str(p) for p in written],
    }


def update_location(
    root: Path,
    loc_id: str,
    *,
    name: str | None = None,
    summary: str | None = None,
    tags: list[str] | tuple[str, ...] | None = None,
    add_connections: list[str] | tuple[str, ...] = (),
    remove_connections: list[str] | tuple[str, ...] = (),
    notes_append: str | None = None,
    parent: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rid = resolve_location_id(root, loc_id)
    if rid is None:
        raise LocationError(f"no such place: {loc_id}")
    path = location_record_path(root, rid)
    assert path is not None
    data = _read_json(path)
    written: list[Path] = []
    if name is not None and str(name).strip():
        data["name"] = str(name).strip()
    if summary is not None:
        data["summary"] = str(summary).strip()
    if tags is not None:
        data["tags"] = [str(t) for t in tags if str(t).strip()]
    if parent is not None:
        data["parent"] = resolve_location_id(root, parent) or parent
    if extra:
        for k, v in extra.items():
            if k not in {"id", "kind", "connections"}:
                data[k] = v
    conns = [str(c) for c in (data.get("connections") or []) if c]
    unknown: list[str] = []
    for c in add_connections:
        cid = resolve_location_id(root, str(c))
        if not cid:
            unknown.append(str(c))
            continue
        if cid not in conns:
            conns.append(cid)
        p = _link(root, rid, cid, add=True)
        if p:
            written.append(p)
    for c in remove_connections:
        cid = resolve_location_id(root, str(c)) or str(c)
        if cid in conns:
            conns.remove(cid)
        p = _link(root, rid, cid, add=False)
        if p:
            written.append(p)
    data["connections"] = conns
    _write_json(path, data)
    written.insert(0, path)
    if notes_append and str(notes_append).strip():
        notes_path = path.parent / NOTES_FILE if path.name == LOCATION_FILE else path.with_suffix("") / NOTES_FILE
        notes_path.parent.mkdir(parents=True, exist_ok=True)
        with notes_path.open("a", encoding="utf-8") as fh:
            if notes_path.stat().st_size == 0 if notes_path.exists() else True:
                fh.write(f"# {data.get('name') or rid}\n\n")
            fh.write(str(notes_append).strip() + "\n")
        written.append(notes_path)
    _sync_map_node(root, rid, name=str(data.get("name") or ""), summary=str(data.get("summary") or ""), parent=data.get("parent"), create=True)
    town_id = data.get("town") if isinstance(data.get("town"), str) else None
    town_id = town_id or town_of_place(root, rid)
    if town_id:
        tm = _sync_town_node(
            root, town_id, rid,
            name=str(data.get("name") or ""), summary=str(data.get("summary") or ""),
            links=[*conns, *unknown, *([data["parent"]] if data.get("parent") else [])],
            create=bool(data.get("town")),
        )
        if tm:
            written.append(tm)
    return {
        "id": rid,
        "name": data.get("name"),
        "connections": conns,
        "unknown_connections": unknown,
        "town": town_id,
        "written": [str(p.relative_to(root)) if p.is_relative_to(root) else str(p) for p in written],
    }
