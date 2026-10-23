"""Places as a folder tree (「按文件夹定层级」).

A place is a folder with a ``location.json``; the folder it sits in is the place it belongs to:

    game/locations/T001/location.json                    石津镇 (a world-level place)
    game/locations/T001/gate_north/location.json         北门, inside 石津镇 → address ``T001/gate_north``
    game/locations/T001/guild/hall/location.json         a room inside the guild → address ``T001/hall``,
                                                         drawn one layer down inside ``guild`` (town-map ``parent``)

``location.json`` carries only the place's own facts: ``name`` (or ``name_i18n``), ``pos`` (in its parent's
coordinates), ``connections`` (sibling ids), ``type``, ``description``/``summary``, ``aliases`` …

A world is in **tree form** when ``game/world/world_map.json`` has no ``nodes`` list (it keeps the world's own keys:
``name``, ``world_id``, ``routes``, ``time``, ``travel``, ``layout`` …). Then the folders are the map. Worlds still
written the old way (``world_map.json`` nodes + ``towns/<T>/town_map.json`` nodes + flat ``locations/*.json``) read
exactly as before; folders found inside them only add what the old files do not have.

Everything that used to read or write ``world_map.json`` / ``town_map.json`` nodes goes through two calls here, which
keep the old document shape so the callers did not change:

    level_doc(root, level)            "world" → a world_map-shaped dict; "T001" → a town_map-shaped dict; None if empty
    save_level_doc(root, level, doc)  tree form → each node into its folder's location.json; old form → the old file
"""
from __future__ import annotations

import copy
import json
import logging
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

WORLD = "world"
RECORD = "location.json"
_NODE_ONLY = ("parent",)  # encoded by the folder, never stored in location.json


# ── files ────────────────────────────────────────────────────────────────

_GAME_DIRS: dict[str, Path] = {}


def game_dir(root: Path) -> Path:
    """paths.get_game_dir, remembered per world root (it costs ~1.5 ms and a pack asks dozens of times); re-asked when
    the remembered folder is gone."""
    key = str(root)
    hit = _GAME_DIRS.get(key)
    if hit is not None and hit.is_dir():
        return hit
    try:
        from neonrp.core.paths import get_game_dir

        out = get_game_dir(root)
    except Exception:  # noqa: BLE001
        out = Path(root) / "game"
    if out.is_dir():
        _GAME_DIRS[key] = out
    return out


def _rj(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _wj(path: Path, data: dict[str, Any]) -> None:
    from neonrp.core.storage import atomic_write_json

    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, data)


def world_map_file(root: Path) -> Path:
    return game_dir(root) / "world" / "world_map.json"


def town_map_file(root: Path, town: str) -> Path:
    """``towns/<town>/town_map.json`` — or the town dir whose map names itself ``town_id: <town>``."""
    towns = game_dir(root) / "towns"
    direct = towns / town / "town_map.json"
    if not direct.is_file() and towns.is_dir():
        for d in sorted(towns.iterdir()):
            tm = _rj(d / "town_map.json") if d.is_dir() else None
            if tm is not None and str(tm.get("town_id") or "") == town:
                return d / "town_map.json"
    return direct


def locations_dir(root: Path) -> Path:
    return game_dir(root) / "locations"


# ── form ─────────────────────────────────────────────────────────────────

def is_tree(root: Path) -> bool:
    """Tree form: world_map.json exists and carries no ``nodes`` list (the folders are the map)."""
    wm = _rj(world_map_file(root))
    return wm is not None and not isinstance(wm.get("nodes"), list)


def _place_dirs(d: Path) -> list[Path]:
    """Child folders of ``d`` that are places (carry a location.json), sorted."""
    if not d.is_dir():
        return []
    return sorted(c for c in d.iterdir() if c.is_dir() and (c / RECORD).is_file())


def _node_of(folder: Path, parent: str | None = None) -> dict[str, Any]:
    """A folder's record as a map node: the folder name is the id, ``connections`` read as ``links``."""
    data = _rj(folder / RECORD) or {}
    # where it sits is the folder's say alone: a ``parent`` / ``within`` some writer left in the record is not read
    node = {k: v for k, v in data.items() if k not in ("connections", "id", "parent", "within")}
    node["id"] = folder.name
    if data.get("id") and str(data["id"]) != folder.name:
        node["aliases"] = sorted({*map(str, node.get("aliases") or []), str(data["id"])})
    node["links"] = [str(c) for c in data.get("connections") or data.get("links") or [] if c]
    if parent:
        node["parent"] = parent
    return node


def _walk(d: Path, parent: str | None, out: list[tuple[dict[str, Any], Path]]) -> None:
    for c in _place_dirs(d):
        out.append((_node_of(c, parent), c))
        _walk(c, c.name, out)


def folder_nodes(root: Path, level: str) -> list[tuple[dict[str, Any], Path]]:
    """(node, folder) for every place on ``level``: the world's top folders, or every folder under a town (nested
    folders carry ``parent`` = the folder they sit in, the town map's own layer field)."""
    base = locations_dir(root)
    if level == WORLD:
        return [(_node_of(c), c) for c in _place_dirs(base)] if is_tree(root) else []
    out: list[tuple[dict[str, Any], Path]] = []
    _walk(base / level, None, out)
    return out


# ── documents in the old shape ───────────────────────────────────────────

def _merge(doc: dict[str, Any], nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Folder nodes win over same-id nodes of the old file; old nodes the folders lack stay."""
    old = [n for n in doc.get("nodes") or [] if isinstance(n, dict) and n.get("id")]
    have = {n["id"] for n in nodes}
    doc["nodes"] = [*nodes, *[n for n in old if str(n["id"]) not in have]]
    return doc


def level_doc(root: Path, level: str) -> dict[str, Any] | None:
    """The map document of one level, in the shape callers already know (world_map.json / town_map.json)."""
    if level == WORLD:
        raw = _rj(world_map_file(root))
        if raw is None:
            return None
        if not is_tree(root):
            return raw
        doc = copy.deepcopy(raw)
        return _merge(doc, [n for n, _ in folder_nodes(root, WORLD)])
    raw = _rj(town_map_file(root, level))
    nodes = [n for n, _ in folder_nodes(root, level)]
    if raw is None and not nodes:
        return None
    if raw is not None and not nodes and isinstance(raw.get("nodes"), list):
        return raw  # an old-form town, exactly as on disk
    doc = copy.deepcopy(raw) if raw is not None else {"town_id": level}
    return _merge(doc, nodes)


def town_ids(root: Path) -> list[str]:
    """Every level below the world that has a map: towns with a town_map.json, and (tree form) world places with
    places inside them."""
    out: list[str] = []
    towns = game_dir(root) / "towns"
    if towns.is_dir():
        for d in sorted(towns.iterdir()):
            tm = _rj(d / "town_map.json") if d.is_dir() else None
            if tm is not None:
                tid = str(tm.get("town_id") or d.name)
                if tid not in out:
                    out.append(tid)
    for c in _place_dirs(locations_dir(root)):
        if _place_dirs(c) and c.name not in out and not is_dungeon_level(root, c.name):
            out.append(c.name)
    return out


# ── dungeons, ports and entries (10-05 MAP-SCALES-1005 G1 / G3) ─────────────────

def is_dungeon_level(root: Path, level: str) -> bool:
    """A level that is a dungeon (``game/dungeons/<id>/dungeon.json``): its rooms may sit in folders under
    ``locations/<id>/`` for the map, but it is not a town — the dungeon layer owns movement inside it."""
    return (game_dir(root) / "dungeons" / level / "dungeon.json").is_file()


def dungeon_rooms(root: Path, did: str) -> list[dict[str, Any]]:
    """A dungeon's rooms in ``layout.json`` shape (``{id, name, type, links, state}``): from its folders
    (``locations/<did>/<room>/location.json``, connections → links) when it has them, else ``layout.json``."""
    folders = _place_dirs(locations_dir(root) / did)
    if folders:
        out = []
        for c in folders:
            d = _rj(c / RECORD) or {}
            out.append({"id": c.name, "name": d.get("name") or c.name, "type": d.get("type") or "room",
                        "links": [str(x) for x in d.get("connections") or [] if x], "state": d.get("state") or {},
                        **({"ports": d["ports"]} if isinstance(d.get("ports"), dict) else {})})
        return out
    lay = _rj(game_dir(root) / "dungeons" / did / "layout.json") or {}
    return [r for r in (lay.get("rooms") or []) if isinstance(r, dict) and r.get("id")]


def level_entry(root: Path, level: str) -> str | None:
    """A level's default landing node (``entry``): on the level's own record (``locations/<level>/location.json``,
    tree form) or its old map file (town_map.json / a dungeon's layout.json)."""
    for path in (locations_dir(root) / level / RECORD, town_map_file(root, level),
                 game_dir(root) / "dungeons" / level / "layout.json"):
        d = _rj(path)
        if d and d.get("entry"):
            return str(d["entry"])
    return None


def ports_up(node: dict[str, Any]) -> list[str]:
    """The parent-level edges (world route ids) this node is the landing of (``ports.up``)."""
    p = node.get("ports") if isinstance(node.get("ports"), dict) else {}
    return [str(x) for x in (p.get("up") or []) if x]


def port_node(doc: dict[str, Any] | None, edge: str | None) -> str | None:
    """The node of a level document bound to parent edge ``edge`` (its ``ports.up`` names it)."""
    if not doc or not edge:
        return None
    for n in doc.get("nodes") or []:
        if isinstance(n, dict) and n.get("id") and edge in ports_up(n):
            return str(n["id"])
    return None


def town_docs(root: Path) -> dict[str, dict[str, Any]]:
    """{town id: town_map-shaped doc} for every town level (old files and folders together)."""
    out: dict[str, dict[str, Any]] = {}
    for tid in town_ids(root):
        doc = level_doc(root, tid)
        if doc is not None:
            out[tid] = doc
    return out


def level_label(root: Path, level: str) -> str:
    """Where a level lives, relative to the world root — for messages and ``source`` fields."""
    p = locations_dir(root) if level_in_folders(root, level) else (
        world_map_file(root) if level == WORLD else town_map_file(root, level))
    if level != WORLD and p == locations_dir(root):
        p = p / level
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


def level_in_folders(root: Path, level: str) -> bool:
    if level == WORLD:
        return is_tree(root)
    raw = _rj(town_map_file(root, level))
    if raw is not None and isinstance(raw.get("nodes"), list):
        return False
    return is_tree(root) or bool(_place_dirs(locations_dir(root) / level))


def place_dir(root: Path, level: str, node_id: str, parent: str | None = None) -> Path:
    """Where a place of ``level`` lives (existing folder, else where a new one goes)."""
    for n, folder in folder_nodes(root, level) if level != WORLD or is_tree(root) else []:
        if n["id"] == node_id:
            return folder
    base = locations_dir(root) if level == WORLD else locations_dir(root) / level
    if parent:
        for n, folder in folder_nodes(root, level):
            if n["id"] == parent:
                return folder / node_id
    return base / node_id


def save_level_doc(root: Path, level: str, doc: dict[str, Any]) -> list[Path]:
    """Write a level document back. Tree form: every node into its folder's location.json (a changed ``parent`` moves
    the folder); the doc's other keys into the old file without ``nodes``. Old form: the old file, as before.
    A node missing from ``doc`` is left alone (removing a place = removing its folder). Returns the paths written."""
    if not level_in_folders(root, level):
        path = world_map_file(root) if level == WORLD else town_map_file(root, level)
        _wj(path, doc)
        return [path]
    written: list[Path] = []
    nodes = [n for n in doc.get("nodes") or [] if isinstance(n, dict) and n.get("id")]
    have = {n["id"]: f for n, f in folder_nodes(root, level)}
    pending = list(nodes)
    for _ in range(len(pending) + 1):  # parents first: a child of a new place needs that folder to exist
        later = []
        for n in pending:
            nid = str(n["id"])
            parent = str(n.get("parent") or "") or None
            if parent and parent not in have:
                later.append(n)
                continue
            want = (have[parent] / nid) if parent else ((locations_dir(root) / level / nid) if level != WORLD else locations_dir(root) / nid)
            cur = have.get(nid)
            if cur is not None and cur != want:
                want.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(cur), str(want))
                for k, f in list(have.items()):  # folders under the moved one moved with it
                    if f == cur or cur in f.parents:
                        have[k] = want / f.relative_to(cur)
            have[nid] = want
            rec = want / RECORD
            data = _rj(rec) or {}
            for k, v in n.items():
                if k in ("id", "links", *_NODE_ONLY):
                    continue
                data[k] = v
            data.pop("within", None)
            data.pop("parent", None)
            data["id"] = data.get("id") or nid
            data["connections"] = [str(x) for x in n.get("links") or [] if x]
            _wj(rec, data)
            written.append(rec)
        if not later or len(later) == len(pending):
            for n in later:  # nothing placed this round: these name a parent the level does not have
                logger.warning("place %s: parent %s not on level %s", n.get("id"), n.get("parent"), level)
            break
        pending = later
    meta = {k: v for k, v in doc.items() if k != "nodes"}
    path = world_map_file(root) if level == WORLD else town_map_file(root, level)
    if level == WORLD or path.is_file() or set(meta) - {"town_id"}:
        _wj(path, meta)
        written.append(path)
    return written


# ── aliases ──────────────────────────────────────────────────────────────

def canonical(root: Path, node: str | None, town: str | None = None) -> str | None:
    """A place id another file used for the same spot (``aliases`` in its location.json) → the folder's id."""
    if not node:
        return node
    docs = town_docs(root)
    order = ([town] if town in docs else []) + [t for t in docs if t != town]
    for t in order:
        for n in docs[t].get("nodes") or []:
            if isinstance(n, dict) and (n.get("id") == node):
                return node
    for t in order:
        for n in docs[t].get("nodes") or []:
            if isinstance(n, dict) and node in (n.get("aliases") or []):
                return str(n["id"])
    return node


# G5 (10-06): a place's scale — for display and image prompts only, never logic
SCALES = ("world", "region", "town", "district", "building", "indoor", "dungeon", "island", "wilds")


def level_graph(root: Path, level: str = WORLD) -> dict[str, Any] | None:
    """One level's connectivity, the one shape the map editor and the test bench read (G2, the handover 10-06):
    ``nodes`` (id · name · pos or null · has_children · ports_up · isolated) · ``edges`` ({id?, a, b, cost?}: world routes
    and every node's links / connections, each pair once) · ``ports`` {node: [parent edge ids]} · ``entry`` · ``frozen``
    (every node has a pos — the image is laid out). Computed from the level documents; nothing is stored. None when the
    level does not exist."""
    if level != WORLD and is_dungeon_level(root, level):
        nodes_raw = dungeon_rooms(root, level)
        doc: dict[str, Any] = {"nodes": nodes_raw}
    else:
        got = level_doc(root, level)
        if got is None:
            return None
        doc = got
    nodes_in = [n for n in doc.get("nodes") or [] if isinstance(n, dict) and n.get("id")]
    ids = {str(n["id"]) for n in nodes_in}
    below = set(town_ids(root)) if level == WORLD else set()
    nodes, ports = [], {}
    for n in nodes_in:
        nid = str(n["id"])
        pos = n.get("pos")
        pos = pos if isinstance(pos, (list, dict)) and pos else None
        up = ports_up(n)
        if up:
            ports[nid] = up
        nodes.append({"id": nid, "name": n.get("name") or nid, "pos": pos, "type": n.get("type") or n.get("kind"),
                      **({"scale": str(n["scale"])} if n.get("scale") else {}),
                      "has_children": nid in below or is_dungeon_level(root, nid), "ports_up": up,
                      **({"isolated": True} if n.get("isolated") else {})})
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(a: str, b: str, **kw: Any) -> None:
        if a in ids and b in ids and a != b and (min(a, b), max(a, b)) not in seen:
            seen.add((min(a, b), max(a, b)))
            edges.append({"a": a, "b": b, **{k: v for k, v in kw.items() if v is not None}})

    for r in doc.get("routes") or []:
        if isinstance(r, dict):
            a, b = r.get("from") or r.get("a"), r.get("to") or r.get("b")
            if a and b:
                add(str(a), str(b), id=r.get("id"), cost=r.get("days") or r.get("cost"))
    for n in nodes_in:
        for other in [*(n.get("links") or []), *(n.get("connections") or [])]:
            add(str(n["id"]), str(other))
    return {"level": level, "label": level_label(root, level) if level != WORLD or is_tree(root) else "world",
            "nodes": nodes, "edges": edges, "ports": ports, "entry": level_entry(root, level),
            "frozen": bool(nodes) and all(n["pos"] is not None for n in nodes)}
