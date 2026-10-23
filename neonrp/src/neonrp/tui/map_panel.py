"""The map tab of the play stage (任务 A2).

A place is a dot with its name under it; roads are dotted lines between
dots; the place the player is standing at blinks. Every dot can be dragged
(the coordinate is remembered in ``world_map.json`` under ``layout`` and
nothing else in that file is touched, so the topology — ``links`` /
``routes`` / ``connections`` — never changes). Double-clicking a place with
a level below it (a town's ``town_map.json``, a folder location's
``map.json``, or nodes that name it as ``parent``) descends; ``Esc`` or the
↑ button climbs back. The wheel zooms; there are + / − buttons for people
who do not have a wheel.

Reading is deliberately tolerant: locations may be ``game/locations/<id>.json``
or, after the location-folder work, ``game/locations/<id>/location.json``.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Static

WORLD_LEVEL = "world"
ZOOM_MIN = 0.5
ZOOM_MAX = 3.0
ZOOM_STEP = 1.15
DOUBLE_CLICK_SECONDS = 0.4

DOT = "●"
DOT_CURRENT = "◉"
EDGE = "·"

_STYLE_DOT = "bold #18FF82"
_STYLE_DOT_DIM = "#3FB36A"
_STYLE_CURRENT_ON = "bold #ffffff on #18FF82"
_STYLE_CURRENT_OFF = "bold #18FF82"
_STYLE_LABEL = "#d8d2c0"
_STYLE_LABEL_CURRENT = "bold #eafdf1"
_STYLE_EDGE = "#2f4a3a"
_STYLE_HINT = "italic #F59E0B"
_STYLE_TAG = "#6b6480"
TAG_MAX_CELLS = 18


def _soul_tag(names: list[str]) -> str:
    """`· 艾琳娜 罗文` clipped to the tag budget (`+n` for the rest)."""
    shown: list[str] = []
    used = 2
    for n in names:
        w = sum(2 if ord(c) > 0x2E80 else 1 for c in n) + 1
        if used + w > TAG_MAX_CELLS and shown:
            break
        shown.append(n)
        used += w
    rest = len(names) - len(shown)
    return "· " + " ".join(shown) + (f" +{rest}" if rest > 0 else "")


@dataclass
class MapNode:
    id: str
    name: str
    x: float
    y: float
    kind: str = ""
    has_children: bool = False
    # Filled by the renderer: the cell where the dot was drawn.
    cx: int = 0
    cy: int = 0


@dataclass
class MapGraph:
    level: str
    title: str
    nodes: dict[str, MapNode] = field(default_factory=dict)
    edges: set[tuple[str, str]] = field(default_factory=set)
    # Where this level's coordinates came from, so drags persist in the
    # same coordinate system (world_map ``pos`` units, town pixels, ...).
    parent: str | None = None

    def add_edge(self, a: str, b: str) -> None:
        if a and b and a != b and a in self.nodes and b in self.nodes:
            self.edges.add((a, b) if a < b else (b, a))


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _game_dir(root: Path) -> Path:
    try:
        from neonrp.core.paths import get_game_dir

        return get_game_dir(root)
    except Exception:
        return root / "game"


def _pos_of(entry: dict[str, Any]) -> tuple[float, float] | None:
    pos = entry.get("pos")
    if isinstance(pos, (list, tuple)) and len(pos) >= 2:
        try:
            return float(pos[0]), float(pos[1])
        except (TypeError, ValueError):
            return None
    if isinstance(pos, dict):
        try:
            return float(pos.get("x", 0)), float(pos.get("y", 0))
        except (TypeError, ValueError):
            return None
    return None


def _name_of(entry: dict[str, Any], fallback: str) -> str:
    for key in ("name", "name_local", "title", "label"):
        v = entry.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    if isinstance(entry.get("name_i18n"), dict):
        for v in entry["name_i18n"].values():
            if isinstance(v, str) and v.strip():
                return v.strip()
    return fallback


def location_entries(root: Path) -> list[tuple[str, dict[str, Any], Path]]:
    """Every ``game/locations`` place: file form or folder form.

    Returns ``(id, data, path)``; the folder form is ``<id>/location.json``
    (a folder may also carry ``map.json`` for its own sub-map).
    """
    out: list[tuple[str, dict[str, Any], Path]] = []
    loc_dir = _game_dir(root) / "locations"
    if not loc_dir.is_dir():
        return out
    for child in sorted(loc_dir.iterdir()):
        if child.is_dir():
            data = _read_json(child / "location.json")
            if data:
                out.append((str(data.get("id") or child.name), data, child))
            continue
        if child.suffix == ".json":
            data = _read_json(child)
            if data and data.get("id"):
                out.append((str(data["id"]), data, child))
    return out


def _auto_positions(ids: list[str]) -> dict[str, tuple[float, float]]:
    """A circle for places that carry no coordinates."""
    n = max(1, len(ids))
    out: dict[str, tuple[float, float]] = {}
    for i, nid in enumerate(ids):
        ang = 2 * math.pi * i / n
        out[nid] = (50 + 40 * math.cos(ang), 50 + 40 * math.sin(ang))
    return out


def _apply_layout(graph: MapGraph, layout: dict[str, Any], prefix: str) -> None:
    """Overlay saved drag positions (``layout``) onto a graph."""
    for nid, node in graph.nodes.items():
        key = nid if prefix == WORLD_LEVEL else f"{prefix}/{nid}"
        saved = layout.get(key)
        if isinstance(saved, (list, tuple)) and len(saved) >= 2:
            try:
                node.x, node.y = float(saved[0]), float(saved[1])
            except (TypeError, ValueError):
                pass


_SEPS = ("·", "・", "/", " - ", "：", ":")


def _town_nodes(root: Path) -> dict[str, dict[str, str]]:
    """{town id: {node id: name}} for every town level (town_map.json or place folders)."""
    from neonrp.core.place_tree import town_docs

    out: dict[str, dict[str, str]] = {}
    for tid, data in town_docs(root).items():
        nodes = {str(n["id"]): _name_of(n, str(n["id"])) for n in data.get("nodes") or [] if isinstance(n, dict) and n.get("id")}
        if nodes:
            out[tid] = nodes
    return out


def _layer(root: Path, level: str) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
    """One layer of a town's map: ``T001`` → its nodes with no ``parent``; ``T001/guild`` → the nodes inside ``guild``.
    Read through place_tree, so town_map.json and place folders (``locations/T001/guild/hall/``) read the same."""
    from neonrp.core.place_tree import level_doc

    town, _, inner = level.partition("/")
    doc = level_doc(root, town)
    if not doc or not doc.get("nodes"):
        return None
    nodes = [n for n in doc["nodes"] if isinstance(n, dict) and n.get("id") and (str(n.get("parent") or "") == inner)]
    return (nodes, doc) if nodes else None


def _level_of(root: Path, addr: str) -> str:
    """The map level an address is drawn on: ``T001/hall`` (hall inside guild) → ``T001/guild``; ``T001/gate`` →
    ``T001``; ``T002`` → the world."""
    from neonrp.core.place_tree import level_doc

    town, _, bare = (addr or "").partition("/")
    if not bare:
        return WORLD_LEVEL
    parents = {str(n["id"]): str(n.get("parent") or "") for n in (level_doc(root, town) or {}).get("nodes") or []
               if isinstance(n, dict) and n.get("id")}
    up = parents.get(bare, "")
    return f"{town}/{up}" if up else town


def _owner_of(nid: str, data: dict[str, Any], world: dict[str, str], towns: dict[str, dict[str, str]]) -> tuple[str, str | None] | None:
    """A ``game/locations`` place that carries neither coordinates nor a ``parent`` but plainly sits inside a place one
    level up: (that place's id, the id of the same spot on its own map, if it has one). Read from the data only — its id
    or name is a node of a town map, or its name is "<world place name>·<spot>". None when nothing says so (it then stays
    on the world map as before)."""
    name = _name_of(data, nid)
    tail = name
    for sep in _SEPS:
        if sep in name:
            tail = name.split(sep)[-1].strip()
            break
    for town, nodes in towns.items():
        for tid, tname in nodes.items():
            if nid == tid or name == tname or (tail and tail == tname):
                return town, tid
    for wid, wname in world.items():
        if wname and name != wname and any(name.startswith(wname + sep) for sep in _SEPS):
            return wid, None
    return None


def _place_missing(graph: MapGraph) -> None:
    """Dots with no coordinates go on a ring around the ones that have them (same units), or on a 100-unit circle when
    nothing has coordinates."""
    missing = [nid for nid, nd in graph.nodes.items() if math.isnan(nd.x) or math.isnan(nd.y)]
    if not missing:
        return
    have = [nd for nid, nd in graph.nodes.items() if nid not in missing]
    if not have:
        for nid, (x, y) in _auto_positions(missing).items():
            graph.nodes[nid].x, graph.nodes[nid].y = x, y
        return
    cx = sum(nd.x for nd in have) / len(have)
    cy = sum(nd.y for nd in have) / len(have)
    span = max(1.0, max(abs(nd.x - cx) for nd in have) + max(abs(nd.y - cy) for nd in have))
    for i, nid in enumerate(missing):
        ang = 2 * math.pi * i / len(missing)
        graph.nodes[nid].x = cx + span * math.cos(ang)
        graph.nodes[nid].y = cy + span * math.sin(ang)


def _children_source(root: Path, node_id: str) -> Path | None:
    """A folder place's own ``map.json`` (the old sub-map form), if any."""
    folder = _game_dir(root) / "locations" / node_id / "map.json"
    return folder if folder.is_file() else None


def _has_below(root: Path, level: str) -> bool:
    """Whether a dot opens a level: a town map / place folders under it, or a folder ``map.json``."""
    return _layer(root, level) is not None or ("/" not in level and _children_source(root, level) is not None)


def load_world_graph(root: Path) -> MapGraph:
    """Top level: the world's places (``world_map.json`` nodes, or the top place folders) + ``game/locations`` places."""
    from neonrp.core.place_tree import WORLD, is_tree, level_doc

    tree = is_tree(root)
    wm = level_doc(root, WORLD) or {}
    graph = MapGraph(level=WORLD_LEVEL, title=str(wm.get("name") or root.name))

    nodes = [n for n in (wm.get("nodes") or []) if isinstance(n, dict) and n.get("id")]
    parents: dict[str, str] = {}
    for n in nodes:
        nid = str(n["id"])
        if n.get("parent"):
            parents[nid] = str(n["parent"])
            continue  # a child of another node: shown one level down
        pos = _pos_of(n)
        graph.nodes[nid] = MapNode(id=nid, name=_name_of(n, nid), x=pos[0] if pos else math.nan, y=pos[1] if pos else math.nan, kind=str(n.get("type") or ""))
    world_names = {nid: nd.name for nid, nd in graph.nodes.items()}
    towns = _town_nodes(root)
    for nid, data, _path in location_entries(root):
        if nid in graph.nodes:
            continue
        if data.get("parent"):
            parents[nid] = str(data["parent"])
            continue
        pos = _pos_of(data)
        # guessing a town from the name is for worlds still written the old way; in a folder tree the folder says it
        owner = None if (pos or tree) else _owner_of(nid, data, world_names, towns)
        if owner is not None:
            parents[nid] = owner[0]  # inside a town / place: shown one level down, not as a stray world dot
            continue
        graph.nodes[nid] = MapNode(id=nid, name=_name_of(data, nid), x=pos[0] if pos else math.nan, y=pos[1] if pos else math.nan, kind=str(data.get("kind") or "location"))

    # Which nodes have a level below them.
    for nid, node in graph.nodes.items():
        node.has_children = _has_below(root, nid) or nid in set(parents.values())

    # Edges: routes (from/to), links (node→node or node→route id), connections.
    routes: dict[str, tuple[str, str]] = {}
    for r in wm.get("routes") or []:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("id") or "")
        a = r.get("from") or r.get("a") or r.get("src")
        b = r.get("to") or r.get("b") or r.get("dst")
        if not (a and b):
            ends = r.get("endpoints") or r.get("nodes")
            if isinstance(ends, (list, tuple)) and len(ends) >= 2:
                a, b = ends[0], ends[1]
        if a and b:
            if rid:
                routes[rid] = (str(a), str(b))
            graph.add_edge(str(a), str(b))
    for n in nodes:
        nid = str(n["id"])
        for link in n.get("links") or []:
            link = str(link)
            if link in routes:
                a, b = routes[link]
                graph.add_edge(a, b)
            else:
                graph.add_edge(nid, link)
    for nid, data, _path in location_entries(root):
        for other in data.get("connections") or []:
            graph.add_edge(nid, str(other))

    # Coordinates: saved layout wins, then the file's own, then a ring.
    _place_missing(graph)
    _apply_layout(graph, wm.get("layout") if isinstance(wm.get("layout"), dict) else {}, WORLD_LEVEL)
    return graph


def load_child_graph(root: Path, node_id: str, title: str = "") -> MapGraph | None:
    """The level under ``node_id``: one layer of a town map (``T001``, or ``T001/guild`` for what sits inside the guild —
    town_map.json and place folders read the same), a folder ``map.json``, or the nodes that name it as ``parent``.
    None when there is nothing below."""
    from neonrp.core.place_tree import WORLD, is_tree, level_doc

    game = _game_dir(root)
    town = node_id.partition("/")[0]
    graph = MapGraph(level=node_id, title=title or node_id, parent=town if "/" in node_id else WORLD_LEVEL)
    layer = _layer(root, node_id)
    src = None if layer is not None or "/" in node_id else _children_source(root, node_id)
    if layer is not None or src is not None:
        nodes, data = layer if layer is not None else (
            [n for n in _read_json(src).get("nodes") or [] if isinstance(n, dict) and n.get("id")], _read_json(src))
        for n in nodes:
            nid = str(n["id"])
            pos = _pos_of(n)
            graph.nodes[nid] = MapNode(id=nid, name=_name_of(n, nid), x=pos[0] if pos else math.nan, y=pos[1] if pos else math.nan, kind=str(n.get("type") or ""))
        for n in nodes:
            for link in n.get("links") or n.get("connections") or []:
                graph.add_edge(str(n["id"]), str(link))
        for r in data.get("routes") or []:
            if isinstance(r, dict) and r.get("from") and r.get("to"):
                graph.add_edge(str(r["from"]), str(r["to"]))
        if "/" not in node_id and not is_tree(root):
            # Old-form worlds only: a flat game/locations record that plainly belongs to this town (by name) — see _owner_of.
            wm0 = level_doc(root, WORLD) or {}
            world_names = {str(n["id"]): _name_of(n, str(n["id"])) for n in wm0.get("nodes") or [] if isinstance(n, dict) and n.get("id")}
            towns = _town_nodes(root)
            extra, alias = [], {}
            for nid, ldata, _path in location_entries(root):
                if _pos_of(ldata) or ldata.get("parent"):
                    continue
                owner = _owner_of(nid, ldata, world_names, towns)
                if not owner or owner[0] != node_id:
                    continue
                if owner[1]:
                    alias[nid] = owner[1]  # the same spot under another id (a location file for a town-map node)
                elif nid not in graph.nodes:
                    name = _name_of(ldata, nid)
                    prefix = world_names.get(node_id, "")
                    for sep in _SEPS:
                        if prefix and name.startswith(prefix + sep):
                            name = name[len(prefix + sep):].strip() or name  # inside the town, "<town>·market" is "market"
                            break
                    graph.nodes[nid] = MapNode(id=nid, name=name, x=math.nan, y=math.nan, kind=str(ldata.get("kind") or "location"))
                    extra.append((nid, ldata))
            for nid, ldata in extra:
                for other in ldata.get("connections") or []:
                    graph.add_edge(nid, alias.get(str(other), str(other)))
    elif "/" not in node_id:
        wm = level_doc(root, WORLD) or {}
        kids = [n for n in (wm.get("nodes") or []) if isinstance(n, dict) and str(n.get("parent") or "") == node_id]
        for nid, data, _path in location_entries(root):
            if str(data.get("parent") or "") == node_id:
                kids.append({**data, "id": nid})
        for n in kids:
            nid = str(n["id"])
            pos = _pos_of(n)
            graph.nodes[nid] = MapNode(id=nid, name=_name_of(n, nid), x=pos[0] if pos else math.nan, y=pos[1] if pos else math.nan, kind=str(n.get("type") or n.get("kind") or ""))
        for n in kids:
            for link in n.get("links") or n.get("connections") or []:
                graph.add_edge(str(n["id"]), str(link))
    if not graph.nodes:
        return None
    for nid, nd in graph.nodes.items():
        # one layer down inside a town (``T001/guild``), or — for a town-level dot named like a town — that town's map
        nd.has_children = _layer(root, f"{town}/{nid}") is not None if layer is not None else _has_below(root, nid)
    _place_missing(graph)
    wm = _read_json(game / "world" / "world_map.json")
    _apply_layout(graph, wm.get("layout") if isinstance(wm.get("layout"), dict) else {}, node_id)
    return graph


def save_layout(root: Path, level: str, node_id: str, x: float, y: float) -> None:
    """Persist one dragged coordinate. Only the ``layout`` key of
    ``world_map.json`` is written; everything else is left byte-for-byte."""
    from neonrp.core.storage import atomic_write_json

    path = _game_dir(root) / "world" / "world_map.json"
    data = _read_json(path)
    layout = data.get("layout")
    if not isinstance(layout, dict):
        layout = {}
    key = node_id if level == WORLD_LEVEL else f"{level}/{node_id}"
    layout[key] = [round(float(x), 2), round(float(y), 2)]
    data["layout"] = layout
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, data)


def souls_by_node(root: Path, level: str) -> dict[str, list[str]]:
    """Who stands where, keyed the way this map level names its dots
    (TODO #11 地图小项:地点下的角色小标签).

    World level: a soul in ``T004/guild`` tags the town ``T004`` (an
    unscoped node tags itself). Inside town ``T004``: it tags ``guild``.
    """
    try:
        from neonrp.core.ontology import get_roster
        from neonrp.core.place_nav import split_location

        roster = get_roster(root)
    except Exception:
        return {}
    out: dict[str, list[str]] = {}
    lvl_town, _, inner = level.partition("/")
    parents: dict[str, str] = {}
    if level != WORLD_LEVEL:
        from neonrp.core.place_tree import level_doc

        parents = {str(n["id"]): str(n.get("parent") or "") for n in (level_doc(root, lvl_town) or {}).get("nodes") or []
                   if isinstance(n, dict) and n.get("id")}
    for row in list(roster.get("present") or []) + list(roster.get("away") or []):
        if not isinstance(row, dict):
            continue
        loc = row.get("location") if isinstance(row.get("location"), dict) else {}
        node = loc.get("node")
        if not node:
            continue
        town, bare = split_location(str(node))
        if level == WORLD_LEVEL:
            key = town or bare or ""
        else:
            key = ""
            if town == lvl_town and bare:
                # a soul deeper inside tags the place on this layer that holds it (hall inside guild → guild)
                cur, seen = bare, set()
                while cur and cur not in seen:
                    seen.add(cur)
                    if parents.get(cur, "") == inner:
                        key = cur
                        break
                    cur = parents.get(cur, "")
        if not key:
            continue
        name = str(row.get("name") or row.get("sid") or "")
        if name and name not in out.setdefault(key, []):
            out[key].append(name)
    return out


def player_location(root: Path) -> str | None:
    """Scoped address of the player (``T001/north-gate``), or None."""
    try:
        from neonrp.core.ontology import get_location

        info = get_location(root, "player")
        loc = info.get("location") if isinstance(info, dict) else None
        node = loc.get("node") if isinstance(loc, dict) else None
        return str(node) if node else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# The widget
# ---------------------------------------------------------------------------


class MapPanel(Widget, can_focus=True):
    """Dots, names, roads; drag / double-click / wheel."""

    DEFAULT_CSS = """
    MapPanel {
        width: 100%;
        height: 1fr;
        background: #070b08;
        color: #d8d2c0;
    }
    MapPanel:focus { border: none; }
    """

    BLINK_INTERVAL = 0.6

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._root: Path | None = None
        self._graph: MapGraph | None = None
        self._crumbs: list[tuple[str, str]] = []  # (level, title) above the current one
        self._zoom: float = 1.0
        self._pan: tuple[float, float] = (0.0, 0.0)
        self._blink_on: bool = True
        self._blink_timer: Any | None = None
        self._drag: str | None = None
        self._drag_moved: bool = False
        # Dragging empty space pans the view (TODO #11).
        self._pan_from: tuple[int, int, tuple[float, float]] | None = None
        self._pan_moved: bool = False
        self._souls: dict[str, list[str]] = {}
        self._last_click: tuple[str, float] | None = None
        self._hint: str = ""
        self._hint_until: float = 0.0
        self._current: str | None = None
        self._followed: str | None = None  # the player location the view last followed
        # Callbacks the host may hook (breadcrumb label, level changes).
        self.on_level_change: Any | None = None

    # -- public API ---------------------------------------------------------

    def set_root(self, root: Path | None) -> None:
        self._root = Path(root) if root else None
        self._followed = None
        self._crumbs = []
        self._zoom = 1.0
        self._pan = (0.0, 0.0)
        self.reload()

    def reload(self) -> None:
        if self._root is None:
            self._graph = None
            self.refresh()
            return
        if self._graph is None or self._graph.level == WORLD_LEVEL:
            self._graph = load_world_graph(self._root)
        else:
            self._graph = load_child_graph(self._root, self._graph.level, self._graph.title) or load_world_graph(self._root)
        self._current = player_location(self._root)
        if self._current != self._followed:
            if self._followed is not None:  # the first look opens on the world; a move afterwards is followed
                self._follow_player()
            self._followed = self._current
        self._reload_souls()
        self._notify_level()
        self.refresh()

    def _follow_player(self) -> None:
        """The player moved: show the level they stand on (inside a town → that town's map, else the world). Moving the
        view by hand sticks until the player moves again."""
        if self._root is None or not self._current:
            return
        want = _level_of(self._root, self._current)  # T001/hall inside the guild → T001/guild
        if self.level == want:
            return
        world = load_world_graph(self._root)
        town, _, inner = want.partition("/")
        town_title = world.nodes[town].name if town in world.nodes else town
        child = None
        if want != WORLD_LEVEL:
            town_graph = load_child_graph(self._root, town, town_title)
            child = town_graph if not inner else load_child_graph(
                self._root, want, town_graph.nodes[inner].name if town_graph and inner in town_graph.nodes else inner)
        if child is None:
            if self.level == WORLD_LEVEL:
                return
            self._crumbs, self._graph = [], world
        else:
            self._crumbs = [(WORLD_LEVEL, world.title)] + ([(town, town_title)] if inner else [])
            self._graph = child
        self._zoom, self._pan = 1.0, (0.0, 0.0)

    def _reload_souls(self) -> None:
        if self._root is None or self._graph is None:
            self._souls = {}
            return
        self._souls = souls_by_node(self._root, self._graph.level)

    @property
    def souls(self) -> dict[str, list[str]]:
        return self._souls

    @property
    def graph(self) -> MapGraph | None:
        return self._graph

    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def level(self) -> str:
        return self._graph.level if self._graph else WORLD_LEVEL

    @property
    def breadcrumb(self) -> str:
        parts = [t for _, t in self._crumbs]
        if self._graph:
            parts.append(self._graph.title)
        return " › ".join(parts)

    def zoom_in(self) -> None:
        self._set_zoom(self._zoom * ZOOM_STEP)

    def zoom_out(self) -> None:
        self._set_zoom(self._zoom / ZOOM_STEP)

    def reset_view(self) -> None:
        self._zoom = 1.0
        self._pan = (0.0, 0.0)
        self.refresh()

    def pan_by(self, dx: int, dy: int) -> None:
        """Shift the view by whole cells (drag on empty space / arrow keys)."""
        self._pan = (self._pan[0] + dx, self._pan[1] + dy)
        self.refresh()

    @property
    def pan(self) -> tuple[float, float]:
        return self._pan

    def drill(self, node_id: str) -> bool:
        """Descend into ``node_id``. False (with a hint) when it has no level below."""
        if self._root is None or self._graph is None or node_id not in self._graph.nodes:
            return False
        node = self._graph.nodes[node_id]
        here = self._graph.level
        # inside a town map, the layer under a dot is ``<town>/<dot>`` (what sits inside it); elsewhere the dot's own id
        level = node_id if here == WORLD_LEVEL or _layer(self._root, here) is None else f"{here.partition('/')[0]}/{node_id}"
        child = load_child_graph(self._root, level, node.name)
        if child is None:
            self.flash_hint(self._t("play.map.no_children"))
            return False
        self._crumbs.append((self._graph.level, self._graph.title))
        self._graph = child
        self._zoom = 1.0
        self._pan = (0.0, 0.0)
        self._reload_souls()
        self._notify_level()
        self.refresh()
        return True

    def go_up(self) -> bool:
        if not self._crumbs or self._root is None:
            return False
        level, title = self._crumbs.pop()
        if level == WORLD_LEVEL:
            self._graph = load_world_graph(self._root)
        else:
            self._graph = load_child_graph(self._root, level, title) or load_world_graph(self._root)
        self._zoom = 1.0
        self._pan = (0.0, 0.0)
        self._reload_souls()
        self._notify_level()
        self.refresh()
        return True

    def flash_hint(self, text: str, seconds: float = 2.0) -> None:
        self._hint = text
        self._hint_until = time.monotonic() + seconds
        self.refresh()

    def _place_nodes(self) -> None:
        """Compute every dot's cell. Called by render() and whenever the graph
        was (re)loaded, so hit-testing works before the next paint too."""
        if self._graph is None or not self._graph.nodes:
            return
        for nd in self._graph.nodes.values():
            nd.cx, nd.cy = self._units_to_cell(nd.x, nd.y)

    def node_at(self, x: int, y: int) -> str | None:
        """The node whose dot (or the row of its name) is at cell (x, y)."""
        if self._graph is None:
            return None
        if self._graph.nodes and all(nd.cx == 0 and nd.cy == 0 for nd in self._graph.nodes.values()):
            self._place_nodes()
        best: tuple[int, str] | None = None
        for nid, nd in self._graph.nodes.items():
            if abs(nd.cy - y) <= 1 and abs(nd.cx - x) <= max(1, len(nd.name) // 2 + 1):
                d = abs(nd.cx - x) + abs(nd.cy - y)
                if best is None or d < best[0]:
                    best = (d, nid)
        return best[1] if best else None

    def move_node_to_cell(self, node_id: str, x: int, y: int) -> None:
        """Put ``node_id``'s dot at cell (x, y) — the drag primitive."""
        if self._graph is None or node_id not in self._graph.nodes:
            return
        ux, uy = self._cell_to_units(x, y)
        nd = self._graph.nodes[node_id]
        nd.x, nd.y = ux, uy
        self.refresh()

    def persist_node(self, node_id: str) -> None:
        if self._root is None or self._graph is None or node_id not in self._graph.nodes:
            return
        nd = self._graph.nodes[node_id]
        try:
            save_layout(self._root, self._graph.level, node_id, nd.x, nd.y)
        except Exception:
            pass

    # -- lifecycle ----------------------------------------------------------

    def on_mount(self) -> None:
        self._blink_timer = self.set_interval(self.BLINK_INTERVAL, self._tick_blink)

    def _tick_blink(self) -> None:
        if not self.display:
            return
        self._blink_on = not self._blink_on
        if self._hint and time.monotonic() > self._hint_until:
            self._hint = ""
        self.refresh()

    def on_resize(self) -> None:
        self.refresh()

    # -- mouse --------------------------------------------------------------

    def on_mouse_down(self, event: events.MouseDown) -> None:
        nid = self.node_at(int(event.x), int(event.y))
        self._drag = nid
        self._drag_moved = False
        self._pan_moved = False
        # Empty space: start a pan instead of a node drag.
        self._pan_from = None if nid is not None else (int(event.x), int(event.y), self._pan)
        try:
            self.capture_mouse()
        except Exception:
            pass
        event.stop()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if not getattr(event, "button", 0):
            return
        if self._drag is not None:
            self._drag_moved = True
            self.move_node_to_cell(self._drag, int(event.x), int(event.y))
            event.stop()
            return
        if self._pan_from is not None:
            x0, y0, pan0 = self._pan_from
            dx, dy = int(event.x) - x0, int(event.y) - y0
            if dx or dy:
                self._pan_moved = True
            self._pan = (pan0[0] + dx, pan0[1] + dy)
            self.refresh()
            event.stop()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        nid, moved = self._drag, self._drag_moved
        self._drag = None
        self._drag_moved = False
        self._pan_from = None
        try:
            self.release_mouse()
        except Exception:
            pass
        if nid is not None and moved:
            self.persist_node(nid)
            event.stop()

    def on_click(self, event: events.Click) -> None:
        if self._drag_moved or self._pan_moved:
            self._pan_moved = False
            return
        nid = self.node_at(int(event.x), int(event.y))
        if nid is None:
            self._last_click = None
            return
        now = time.monotonic()
        double = int(getattr(event, "chain", 1) or 1) >= 2
        if not double and self._last_click and self._last_click[0] == nid and now - self._last_click[1] <= DOUBLE_CLICK_SECONDS:
            double = True
        self._last_click = (nid, now)
        if double:
            self._last_click = None
            self.drill(nid)
            event.stop()

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        self.zoom_in()
        event.stop()

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        self.zoom_out()
        event.stop()

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape" and self._crumbs:
            self.go_up()
            event.stop()
        elif event.key in ("plus", "equals_sign", "equals"):
            self.zoom_in()
            event.stop()
        elif event.key == "minus":
            self.zoom_out()
            event.stop()
        elif event.key in ("left", "right", "up", "down"):
            dx = {"left": 4, "right": -4}.get(event.key, 0)
            dy = {"up": 2, "down": -2}.get(event.key, 0)
            self.pan_by(dx, dy)
            event.stop()

    # -- geometry -----------------------------------------------------------

    def _bounds(self) -> tuple[float, float, float, float]:
        assert self._graph is not None
        xs = [nd.x for nd in self._graph.nodes.values()]
        ys = [nd.y for nd in self._graph.nodes.values()]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        if maxx - minx < 1e-6:
            maxx = minx + 1.0
        if maxy - miny < 1e-6:
            maxy = miny + 1.0
        return minx, miny, maxx, maxy

    def _frame(self) -> tuple[int, int, int, int]:
        """(width, height, left margin, top margin) of the drawing area."""
        w = max(10, int(self.size.width or 0) or 60)
        h = max(6, int(self.size.height or 0) or 20)
        return w, h, 2, 1

    def _scale(self) -> tuple[float, float, float, float, float, float]:
        """Returns (minx, miny, sx, sy, ox, oy): cell = o + (u - min) * s."""
        minx, miny, maxx, maxy = self._bounds()
        w, h, ml, mt = self._frame()
        usable_w = max(1, w - 2 * ml - 12)  # room for the widest label
        usable_h = max(1, h - 2 * mt - 2)  # room for the label row + hint
        sx = usable_w / (maxx - minx) * self._zoom
        sy = usable_h / (maxy - miny) * self._zoom
        # Keep the world centred when zooming.
        cx = ml + (w - 2 * ml) / 2
        cy = mt + (h - 2 * mt) / 2
        ox = cx - (maxx - minx) * sx / 2 + self._pan[0]
        oy = cy - (maxy - miny) * sy / 2 + self._pan[1]
        return minx, miny, sx, sy, ox, oy

    def _units_to_cell(self, ux: float, uy: float) -> tuple[int, int]:
        minx, miny, sx, sy, ox, oy = self._scale()
        return int(round(ox + (ux - minx) * sx)), int(round(oy + (uy - miny) * sy))

    def _cell_to_units(self, x: int, y: int) -> tuple[float, float]:
        minx, miny, sx, sy, ox, oy = self._scale()
        return minx + (x - ox) / sx, miny + (y - oy) / sy

    def _set_zoom(self, z: float) -> None:
        self._zoom = max(ZOOM_MIN, min(ZOOM_MAX, z))
        self.refresh()

    # -- rendering ----------------------------------------------------------

    def _t(self, key: str) -> str:
        try:
            from neonrp.tui.i18n import get_message

            loc = getattr(self.app, "ui_locale", None) or "en"
            return get_message(loc, key)
        except Exception:
            return key

    def _is_current(self, nid: str) -> bool:
        cur = self._current
        if not cur or self._graph is None:
            return False
        town, _, bare = cur.partition("/")
        if self._graph.level == WORLD_LEVEL:
            return nid == town or nid == cur or (not bare and nid == town)
        return nid == bare or nid == cur

    def render(self) -> Text:
        if self._graph is None or not self._graph.nodes:
            return Text(f"  {self._t('play.map.empty')}", style="#4a4458")
        w, h, _ml, _mt = self._frame()
        grid: list[list[tuple[str, str]]] = [[(" ", "") for _ in range(w)] for _ in range(h)]

        def put(x: int, y: int, ch: str, style: str, *, force: bool = False) -> None:
            if 0 <= x < w and 0 <= y < h and (force or grid[y][x][0] == " "):
                grid[y][x] = (ch, style)

        # Positions first, so edges know where dots are.
        self._place_nodes()

        # Roads: straight dotted lines between dot centres.
        for a, b in self._graph.edges:
            na, nb = self._graph.nodes[a], self._graph.nodes[b]
            for x, y in _line(na.cx, na.cy, nb.cx, nb.cy):
                put(x, y, EDGE, _STYLE_EDGE)

        # Dots + names (names below the dot, centred, never dropped).
        for nid, nd in self._graph.nodes.items():
            current = self._is_current(nid)
            if current:
                ch = DOT_CURRENT if self._blink_on else DOT
                style = _STYLE_CURRENT_ON if self._blink_on else _STYLE_CURRENT_OFF
            else:
                ch = DOT
                style = _STYLE_DOT if nd.has_children else _STYLE_DOT_DIM
            put(nd.cx, nd.cy, ch, style, force=True)
            label = nd.name + (" ▾" if nd.has_children else "")
            width = sum(2 if ord(c) > 0x2E80 else 1 for c in label)
            start = nd.cx - width // 2
            col = start
            for c in label:
                put(col, nd.cy + 1, c, _STYLE_LABEL_CURRENT if current else _STYLE_LABEL, force=True)
                col += 2 if ord(c) > 0x2E80 else 1
                if ord(c) > 0x2E80:
                    # A wide glyph occupies two cells; blank the second so the
                    # next put() cannot draw into the middle of it.
                    put(col - 1, nd.cy + 1, "", "", force=True)


        # Who is here (TODO #11): a dim tag row under each name. Drawn after
        # every dot and label (those win), over roads (a road may pass).
        def put_tag(x: int, y: int, ch: str) -> None:
            if 0 <= x < w and 0 <= y < h and grid[y][x][0] in (" ", EDGE):
                grid[y][x] = (ch, _STYLE_TAG)

        def tag_fits(x0: int, y: int, width: int) -> bool:
            # plus one clear cell each side, so it never runs into a neighbour's name
            return 0 <= y < h and 0 <= x0 and x0 + width <= w and all(
                grid[y][x][0] in (" ", EDGE) for x in range(max(0, x0 - 1), min(w, x0 + width + 1)))

        for nid, nd in self._graph.nodes.items():
            names = self._souls.get(nid) or []
            if not names:
                continue
            tag = _soul_tag(names)
            twidth = sum(2 if ord(c) > 0x2E80 else 1 for c in tag)
            # A tag is shown whole or not at all: half a name next to another place's label reads as being there.
            spot = next(((x0, y) for x0, y in ((nd.cx - twidth // 2, nd.cy + 2), (nd.cx - twidth // 2, nd.cy - 1),
                                               (nd.cx + 2, nd.cy)) if tag_fits(x0, y, twidth)), None)
            if spot is None:
                continue
            col, row = spot
            for c in tag:
                put_tag(col, row, c)
                col += 2 if ord(c) > 0x2E80 else 1
                if ord(c) > 0x2E80:
                    put_tag(col - 1, row, "")

        text = Text()
        for row in grid:
            for ch, style in row:
                if ch == "":
                    continue
                text.append(ch, style=style or None)
            text.append("\n")
        if self._hint:
            text.append(f"  {self._hint}", style=_STYLE_HINT)
        return text

    def _notify_level(self) -> None:
        cb = self.on_level_change
        if cb is not None:
            try:
                cb(self.breadcrumb, bool(self._crumbs))
            except Exception:
                pass


def _line(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    """Bresenham, endpoints excluded (the dots live there)."""
    pts: list[tuple[int, int]] = []
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    guard = 0
    while (x, y) != (x1, y1) and guard < 10000:
        guard += 1
        if (x, y) != (x0, y0):
            pts.append((x, y))
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy
    return pts


class MapView(Vertical):
    """The map tab: a thin bar (↑ 上一级 · + · − · ⟲ · breadcrumb) over the map."""

    DEFAULT_CSS = """
    MapView { width: 100%; height: 1fr; layout: vertical; }
    #map-bar { height: 1; width: 100%; background: #0d1a12; }
    #map-bar Button {
        height: 1; min-width: 5; margin: 0 1 0 0; border: none; padding: 0 1;
        background: #14301f; color: #18FF82; text-style: bold;
    }
    #map-bar Button:hover, #map-bar Button:focus { background: #1d4a30; color: #b9ffd0; }
    #map-crumb { height: 1; width: 1fr; color: #9BE89B; padding: 0 1; }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(id="map-bar"):
            yield Button("↑", id="btn-map-up")
            yield Button("+", id="btn-map-zoom-in")
            yield Button("−", id="btn-map-zoom-out")
            yield Button("⟲", id="btn-map-reset")
            yield Static("", id="map-crumb", markup=False)
        yield MapPanel(id="map-panel")

    def on_mount(self) -> None:
        panel = self.query_one("#map-panel", MapPanel)
        panel.on_level_change = self._on_level
        self._on_level(panel.breadcrumb, False)

    def _on_level(self, crumb: str, can_go_up: bool) -> None:
        try:
            self.query_one("#map-crumb", Static).update(crumb)
            self.query_one("#btn-map-up", Button).disabled = not can_go_up
        except Exception:
            pass

    def relabel(self, up: str, zoom_in: str, zoom_out: str, reset: str) -> None:
        try:
            self.query_one("#btn-map-up", Button).label = up
            self.query_one("#btn-map-zoom-in", Button).label = zoom_in
            self.query_one("#btn-map-zoom-out", Button).label = zoom_out
            self.query_one("#btn-map-reset", Button).label = reset
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        try:
            panel = self.query_one("#map-panel", MapPanel)
        except Exception:
            return
        if bid == "btn-map-up":
            panel.go_up()
        elif bid == "btn-map-zoom-in":
            panel.zoom_in()
        elif bid == "btn-map-zoom-out":
            panel.zoom_out()
        elif bid == "btn-map-reset":
            panel.reset_view()
        else:
            return
        event.stop()
        panel.focus()
