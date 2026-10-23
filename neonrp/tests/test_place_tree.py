"""Places as a folder tree (「按文件夹定层级」): the folder a place
sits in is the place it belongs to; old world_map / town_map / flat locations worlds read exactly as before; the
migration script turns the old three sources into the tree."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

from neonrp.core import place_tree
from neonrp.core.place_nav import load_world_map, qualify_location, resolve_move_target, town_node_view
from neonrp.tui.map_panel import WORLD_LEVEL, MapPanel, load_child_graph, load_world_graph

ROOT = Path(__file__).resolve().parents[1]


def _w(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _tree_world(tmp_path: Path, player_at: str = "T001/gate") -> Path:
    """石津镇 (T001) with a gate, an inn and a guild; a hall inside the guild; 风栈堡 (T002) one road away."""
    root = tmp_path / "w"
    g = root / "game"
    _w(g / "world" / "world_map.json", {"name": "灰雾北境", "routes": [{"id": "R1", "from": "T001", "to": "T002", "distance": 40}]})
    loc = g / "locations"
    _w(loc / "T001" / "location.json", {"name": "石津镇", "type": "town", "pos": [12, 7], "connections": ["T002"]})
    _w(loc / "T002" / "location.json", {"name": "风栈堡", "type": "town", "pos": [5, 10], "connections": ["T001"]})
    _w(loc / "T001" / "gate" / "location.json", {"name": "北门", "type": "gate", "pos": {"x": 100, "y": 100},
                                                "connections": ["inn", "guild"], "aliases": ["old-gate"]})
    _w(loc / "T001" / "inn" / "location.json", {"name": "河灯旅店", "pos": {"x": 300, "y": 120}, "connections": ["gate"]})
    _w(loc / "T001" / "guild" / "location.json", {"name": "冒险者公会", "pos": {"x": 200, "y": 260}, "connections": ["gate"]})
    _w(loc / "T001" / "guild" / "hall" / "location.json", {"name": "公会大厅", "pos": {"x": 50, "y": 50}, "connections": []})
    _w(g / "meta" / "run_state.json", {"turn_count": 1, "location": {"node": player_at, "node_id": player_at.split("/")[0]}})
    return root


# ── reading the tree ──────────────────────────────────────────────────


def test_the_folder_a_place_sits_in_is_where_it_belongs(tmp_path):
    root = _tree_world(tmp_path)
    assert place_tree.is_tree(root)
    wm = load_world_map(root)
    assert sorted(n["id"] for n in wm["nodes"]) == ["T001", "T002"] and wm["name"] == "灰雾北境" and wm["routes"]
    assert place_tree.town_ids(root) == ["T001"]
    doc = place_tree.level_doc(root, "T001")
    by = {n["id"]: n for n in doc["nodes"]}
    assert set(by) == {"gate", "inn", "guild", "hall"}
    assert by["hall"]["parent"] == "guild" and "parent" not in by["gate"], "one folder deeper = one layer down"
    assert by["gate"]["links"] == ["inn", "guild"], "connections read as the town map's links"
    view = town_node_view(root, "gate", prefer_town="T001")
    assert view["name"] == "北门" and [e["id"] for e in view["exits"]] == ["inn", "guild"]


def test_an_alias_in_a_place_folder_resolves_to_the_folder_id(tmp_path):
    root = _tree_world(tmp_path)
    assert qualify_location(root, "old-gate", current_town="T001") == "T001/gate"
    assert resolve_move_target(root, "old-gate", current_location="T001/inn") == "T001/gate"


def test_a_record_cannot_say_where_it_sits_against_its_folder(tmp_path):
    root = _tree_world(tmp_path)
    rec = root / "game/locations/T001/inn/location.json"
    d = json.loads(rec.read_text(encoding="utf-8"))
    d["parent"] = "guild"
    rec.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    by = {n["id"]: n for n in place_tree.level_doc(root, "T001")["nodes"]}
    assert "parent" not in by["inn"], "the folder says where it is, not a stray key"


def test_save_moves_a_folder_when_its_layer_changes_and_keeps_the_rest(tmp_path):
    root = _tree_world(tmp_path)
    (root / "game/locations/T001/inn/notes.md").write_text("热汤", encoding="utf-8")
    doc = place_tree.level_doc(root, "T001")
    for n in doc["nodes"]:
        if n["id"] == "inn":
            n["parent"] = "guild"
    doc["state"] = {"discovered_nodes": ["gate"]}
    place_tree.save_level_doc(root, "T001", doc)
    moved = root / "game/locations/T001/guild/inn"
    assert (moved / "location.json").is_file() and (moved / "notes.md").read_text(encoding="utf-8") == "热汤"
    assert not (root / "game/locations/T001/inn").exists()
    rec = json.loads((moved / "location.json").read_text(encoding="utf-8"))
    assert "parent" not in rec and rec["connections"] == ["gate"]
    meta = json.loads((root / "game/towns/T001/town_map.json").read_text(encoding="utf-8"))
    assert "nodes" not in meta and meta["state"] == {"discovered_nodes": ["gate"]}, "the town's own keys, no node list"
    assert place_tree.is_tree(root)


# ── old-form worlds are untouched ─────────────────────────────────────


def test_an_old_form_world_reads_exactly_as_on_disk(tmp_path):
    root = tmp_path / "old"
    wm = {"name": "w", "nodes": [{"id": "T001", "name": "镇", "pos": [1, 2], "links": ["R1"]}], "routes": []}
    tm = {"town_id": "T001", "nodes": [{"id": "gate_north", "name": "北门", "links": []}]}
    _w(root / "game/world/world_map.json", wm)
    _w(root / "game/towns/T001/town_map.json", tm)
    _w(root / "game/locations/market/location.json", {"id": "market", "name": "集市"})  # an old one-level folder record
    assert not place_tree.is_tree(root)
    assert place_tree.level_doc(root, "world") == wm and place_tree.level_doc(root, "T001") == tm
    assert place_tree.town_ids(root) == ["T001"]
    place_tree.save_level_doc(root, "T001", {**tm, "nodes": [*tm["nodes"], {"id": "inn", "name": "旅店", "links": []}]})
    assert [n["id"] for n in json.loads((root / "game/towns/T001/town_map.json").read_text(encoding="utf-8"))["nodes"]] == ["gate_north", "inn"]
    assert not (root / "game/locations/T001").exists(), "an old-form town is written back to its town_map.json"


# ── the migration script ──────────────────────────────────────────────


def _migrate_mod():
    spec = importlib.util.spec_from_file_location("migrate_map_to_folders", ROOT / "scripts" / "migrate_map_to_folders.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["migrate_map_to_folders"] = mod  # its dataclass looks itself up there
    spec.loader.exec_module(mod)
    return mod


def _old_world(tmp_path: Path) -> Path:
    """The stoneford shape that drew 「石津镇·北门」 as a stray dot: a town map, plus flat records under other ids."""
    root = tmp_path / "old"
    g = root / "game"
    _w(g / "world/world_map.json", {"name": "灰雾北境", "nodes": [
        {"id": "T001", "type": "town", "name": "石津镇", "pos": [12, 7], "links": ["R1"]},
        {"id": "T002", "type": "town", "name": "风栈堡", "pos": [5, 10], "links": ["R1"]}],
        "routes": [{"id": "R1", "from": "T001", "to": "T002"}], "layout": {"market-square": [1, 2], "T001": [3, 4]}})
    _w(g / "towns/T001/town_map.json", {"town_id": "T001", "state": {"discovered_nodes": ["gate_north"]}, "nodes": [
        {"id": "gate_north", "name": "北门", "type": "gate", "pos": {"x": 236, "y": 153}, "links": ["main_street"]},
        {"id": "main_street", "name": "主街", "pos": {"x": 504, "y": 316}, "links": ["gate_north", "inn"]},
        {"id": "inn", "name": "河灯旅店", "pos": {"x": 621, "y": 268}, "links": ["main_street"]},
        {"id": "cellar", "name": "地窖", "parent": "inn", "pos": {"x": 10, "y": 10}, "links": []}]})
    _w(g / "towns/T001/town.json", {"id": "T001", "name": "石津镇"})
    _w(g / "locations/north-gate.json", {"id": "north-gate", "name": "石津镇·北门", "summary": "歪斜的木栅门",
                                          "connections": ["market-square"]})
    _w(g / "locations/riverlamp-inn.json", {"id": "riverlamp-inn", "name": "河灯旅店", "connections": ["market-square"]})
    _w(g / "locations/market-square/location.json", {"id": "market-square", "name": "石津镇·集市广场",
                                                       "connections": ["north-gate", "riverlamp-inn"]})
    (g / "locations/market-square/notes.md").write_text("晨市", encoding="utf-8")
    _w(g / "meta/run_state.json", {"location": {"node": "north-gate", "node_id": "T001"}})
    return root


def test_migration_dry_run_writes_nothing(tmp_path):
    root = _old_world(tmp_path)
    before = sorted(str(p.relative_to(root)) for p in root.rglob("*"))
    plan = _migrate_mod().plan_world(root)
    assert "T001/market-square" in plan.records and "T001/gate_north" in plan.records
    assert sorted(str(p.relative_to(root)) for p in root.rglob("*")) == before


def test_migration_merges_the_same_spot_and_keeps_the_other_id_as_alias(tmp_path):
    root = _old_world(tmp_path)
    m = _migrate_mod()
    m.apply(m.plan_world(root))
    loc = root / "game/locations"
    gate = json.loads((loc / "T001/gate_north/location.json").read_text(encoding="utf-8"))
    assert gate["name"] == "北门" and gate["aliases"] == ["north-gate"] and gate["summary"] == "歪斜的木栅门"
    assert "market-square" in gate["connections"], "joined back from the new spot"
    inn = json.loads((loc / "T001/inn/location.json").read_text(encoding="utf-8"))
    assert inn["aliases"] == ["riverlamp-inn"]
    ms = json.loads((loc / "T001/market-square/location.json").read_text(encoding="utf-8"))
    assert ms["name"] == "集市广场" and ms["connections"] == ["gate_north", "inn"], "re-pointed at the town map's ids"
    assert isinstance(ms.get("pos"), dict), "placed beside the place it joins"
    assert (loc / "T001/market-square/notes.md").read_text(encoding="utf-8") == "晨市", "the folder's other files move with it"
    assert (loc / "T001/inn/cellar/location.json").is_file(), "a town-map parent becomes one folder deeper"
    assert not (loc / "north-gate.json").exists() and not (loc / "riverlamp-inn.json").exists() and not (loc / "market-square").exists()
    wm = json.loads((root / "game/world/world_map.json").read_text(encoding="utf-8"))
    assert "nodes" not in wm and wm["routes"] and wm["layout"] == {"T001": [3, 4]}, "a world-unit drag does not fit a town map"
    tm = json.loads((root / "game/towns/T001/town_map.json").read_text(encoding="utf-8"))
    assert "nodes" not in tm and tm["state"] == {"discovered_nodes": ["gate_north"]}
    t1 = json.loads((loc / "T001/location.json").read_text(encoding="utf-8"))
    assert t1["connections"] == ["T002"], "a route id in links becomes the place at its other end"
    # and the engine reads the result
    assert place_tree.is_tree(root)
    assert qualify_location(root, "north-gate") == "T001/gate_north" and qualify_location(root, "riverlamp-inn") == "T001/inn"
    assert sorted(n.id for n in load_world_graph(root).nodes.values()) == ["T001", "T002"], "no stray town spots on the world map"
    town = load_child_graph(root, "T001", "石津镇")
    assert sorted(town.nodes) == ["gate_north", "inn", "main_street", "market-square"]
    assert town.nodes["inn"].has_children and ("gate_north", "market-square") in town.edges


def test_migration_a_grown_place_hangs_off_its_parent_it_is_not_inside_it(tmp_path):
    """sf-plan 10-05: places grown in play carry ``parent: T001/gate_north`` (the spot they hang off — the engine made it
    a road) and the town map already registered them under the same id; they must merge, not nest a second copy."""
    root = _old_world(tmp_path)
    tm_p = root / "game/towns/T001/town_map.json"
    tm = json.loads(tm_p.read_text(encoding="utf-8"))
    tm["nodes"].append({"id": "reeds", "name": "苇丛浅滩", "pos": {"x": 300, "y": 90}, "links": ["gate_north"]})
    tm_p.write_text(json.dumps(tm, ensure_ascii=False), encoding="utf-8")
    _w(root / "game/locations/reeds/location.json", {"id": "reeds", "name": "苇丛浅滩", "parent": "T001/gate_north",
                                                       "town": "T001", "summary": "芦苇", "connections": ["gate_north"]})
    _w(root / "game/locations/well/location.json", {"id": "well", "name": "古井", "parent": "gate_north", "town": "T001"})
    m = _migrate_mod()
    m.apply(m.plan_world(root))
    loc = root / "game/locations/T001"
    assert (loc / "reeds/location.json").is_file() and not (loc / "gate_north/reeds").exists()
    assert json.loads((loc / "reeds/location.json").read_text(encoding="utf-8"))["summary"] == "芦苇"
    well = json.loads((loc / "well/location.json").read_text(encoding="utf-8"))
    assert well["connections"] == ["gate_north"], "the spot it hung off becomes its road, on the same layer"
    assert not (loc / "gate_north/well").exists()


def test_migrating_twice_is_a_no_op(tmp_path):
    root = _old_world(tmp_path)
    m = _migrate_mod()
    m.apply(m.plan_world(root))
    again = m.plan_world(root)
    assert again.records == {} and any("already a folder tree" in n for n in again.notes)


# ── the map tab on a tree ─────────────────────────────────────────────


def _run(coro):
    return asyncio.run(coro)


def test_map_drills_a_layer_down_inside_a_town_and_follows_the_player_there(tmp_path):
    root = _tree_world(tmp_path)

    async def go():
        from neonrp.tui.app import NeonRPApp

        app = NeonRPApp(root=root, mode="play")
        async with app.run_test(size=(120, 44)) as pilot:
            await pilot.pause()
            await pilot.click("#tab-map")
            await pilot.pause()
            panel = app.query_one("#map-panel", MapPanel)
            assert panel.level == WORLD_LEVEL and sorted(panel.graph.nodes) == ["T001", "T002"]
            assert panel.graph.nodes["T001"].has_children
            assert panel.drill("T001") and sorted(panel.graph.nodes) == ["gate", "guild", "inn"]
            assert panel.graph.nodes["guild"].has_children and not panel.graph.nodes["inn"].has_children
            assert panel.drill("guild") and panel.level == "T001/guild" and list(panel.graph.nodes) == ["hall"]
            assert "冒险者公会" in panel.breadcrumb and "石津镇" in panel.breadcrumb
            assert "公会大厅" in panel.render().plain
            assert panel.go_up() and panel.level == "T001" and panel.go_up() and panel.level == WORLD_LEVEL
            # the player walks into the hall → the map follows to the layer the hall is drawn on
            _w(root / "game/meta/run_state.json", {"turn_count": 2, "location": {"node": "T001/hall", "node_id": "T001"}})
            panel.reload()
            assert panel.level == "T001/guild" and panel._is_current("hall")
            assert panel.go_up() and panel.level == "T001"

    _run(go())
