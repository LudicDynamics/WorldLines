"""The map tab (任务 A2): dots with names under them, roads
between them, the player's place blinking; drag remembers a coordinate in
``world_map.json`` (only ``layout``), double-click goes one level down, the
wheel or + / − zooms."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from neonrp.tui import map_panel as M
from neonrp.tui.map_panel import (
    WORLD_LEVEL,
    ZOOM_MAX,
    ZOOM_MIN,
    MapPanel,
    load_child_graph,
    load_world_graph,
    save_layout,
)

TOWN_MAP = {
    "town_id": "T001",
    "nodes": [
        {"id": "gate_north", "name": "北门", "pos": {"x": 236, "y": 153}, "links": ["main_street"]},
        {"id": "main_street", "name": "主街", "pos": {"x": 504, "y": 316}, "links": ["gate_north", "inn"]},
        {"id": "inn", "name": "河灯旅店", "pos": {"x": 621, "y": 268}, "links": ["main_street"]},
    ],
}

WORLD_MAP = {
    "world_id": "w",
    "name": "灰雾北境",
    "nodes": [
        {"id": "T001", "type": "town", "name": "石津镇", "pos": [12, 7], "links": ["R001"]},
        {"id": "T002", "type": "town", "name": "风栈堡", "pos": [5, 10], "links": ["R001"]},
        {"id": "D001", "type": "dungeon", "name": "苔墓地穴", "pos": [14, 8], "links": []},
    ],
    "routes": [{"id": "R001", "from": "T001", "to": "T002"}],
    "time": {"day": 1},
}


def _world(tmp_path: Path, *, player_at: str = "T001/gate_north") -> Path:
    root = tmp_path / "w"
    game = root / "game"
    (game / "meta").mkdir(parents=True)
    (game / "meta" / "run_state.json").write_text(
        json.dumps({"turn_count": 3, "location": {"node": player_at, "node_id": player_at.split("/")[0]}}),
        encoding="utf-8",
    )
    (game / "world").mkdir()
    (game / "world" / "world_map.json").write_text(json.dumps(WORLD_MAP, ensure_ascii=False), encoding="utf-8")
    (game / "towns" / "T001").mkdir(parents=True)
    (game / "towns" / "T001" / "town_map.json").write_text(json.dumps(TOWN_MAP, ensure_ascii=False), encoding="utf-8")
    loc = game / "locations"
    loc.mkdir()
    # File form ...
    (loc / "north-gate.json").write_text(
        json.dumps({"id": "north-gate", "kind": "location", "name": "石津镇·北门", "connections": ["market-square"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    # ... and folder form (what the location-folder work will write).
    (loc / "market-square").mkdir()
    (loc / "market-square" / "location.json").write_text(
        json.dumps({"id": "market-square", "kind": "location", "name": "集市广场", "connections": ["north-gate"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    return root


# ── reading ───────────────────────────────────────────────────────────


def test_world_graph_merges_map_nodes_and_both_location_forms(tmp_path):
    root = _world(tmp_path)
    loc = root / "game" / "locations"
    (loc / "old-road.json").write_text(json.dumps({"id": "old-road", "name": "旧道", "connections": ["far-shrine"]}, ensure_ascii=False), encoding="utf-8")
    (loc / "far-shrine").mkdir()
    (loc / "far-shrine" / "location.json").write_text(json.dumps({"id": "far-shrine", "name": "远祠", "connections": ["old-road"]}, ensure_ascii=False), encoding="utf-8")
    g = load_world_graph(root)
    assert set(g.nodes) == {"T001", "T002", "D001", "market-square", "old-road", "far-shrine"}, "「石津镇·北门」归镇里;「集市广场」数据上看不出归属,留在世界图"
    assert ("T001", "T002") in g.edges, "route R001 becomes an edge"
    assert ("far-shrine", "old-road") in g.edges, "connections become edges (both file and folder form)"
    assert g.nodes["T001"].has_children, "a town with a town_map has a level below"
    assert not g.nodes["D001"].has_children
    assert g.title == "灰雾北境"


def test_places_without_coordinates_still_get_a_spot(tmp_path):
    root = _world(tmp_path)
    (root / "game" / "locations" / "old-road.json").write_text(json.dumps({"id": "old-road", "name": "旧道"}, ensure_ascii=False), encoding="utf-8")
    g = load_world_graph(root)
    assert g.nodes["old-road"].x == g.nodes["old-road"].x, "not NaN"


def test_town_spots_without_coordinates_stay_inside_the_town(tmp_path):
    """「石津镇·北门」「集市广场」「河灯旅店」被画成世界地图上远离石津镇的散点。一个没坐标、没 parent 的地点,
    数据上明明属于某镇(id/名字是镇地图的节点,或名字是「镇名·某处」)就只在那个镇里出现,不上世界图。"""
    root = _world(tmp_path)
    loc = root / "game" / "locations"
    (loc / "riverlamp-inn.json").write_text(json.dumps({"id": "riverlamp-inn", "name": "河灯旅店", "connections": ["market-square"]}, ensure_ascii=False), encoding="utf-8")
    (loc / "market-square" / "location.json").write_text(json.dumps(
        {"id": "market-square", "name": "石津镇·集市广场", "connections": ["north-gate", "riverlamp-inn"]}, ensure_ascii=False), encoding="utf-8")
    g = load_world_graph(root)
    assert set(g.nodes) == {"T001", "T002", "D001"}, "镇内地点不上世界图"
    assert g.nodes["T001"].has_children
    town = load_child_graph(root, "T001", "石津镇")
    assert town is not None
    assert "north-gate" not in town.nodes and "riverlamp-inn" not in town.nodes, "镇图上已有同一处(北门/河灯旅店),不重复画"
    assert town.nodes["market-square"].name == "集市广场", "镇里不再带「石津镇·」前缀"
    assert ("gate_north", "market-square") in town.edges and ("inn", "market-square") in town.edges, "别名 id 的连线接到镇图节点"
    xs = [nd.x for nd in town.nodes.values() if nd.id != "market-square"]
    assert min(xs) - 1000 < town.nodes["market-square"].x < max(xs) + 1000, "放在镇图同一套坐标里"


def test_child_graph_is_the_town_map(tmp_path):
    g = load_child_graph(_world(tmp_path), "T001", "石津镇")
    assert g is not None and g.level == "T001"
    assert set(g.nodes) == {"gate_north", "main_street", "inn"}
    assert ("gate_north", "main_street") in g.edges


def test_child_graph_from_folder_map_json(tmp_path):
    root = _world(tmp_path)
    folder = root / "game" / "locations" / "market-square"
    (folder / "map.json").write_text(
        json.dumps({"nodes": [{"id": "stall", "name": "鱼摊", "links": ["well"]}, {"id": "well", "name": "井"}]}), encoding="utf-8"
    )
    g = load_child_graph(root, "market-square", "集市广场")
    assert g is not None and set(g.nodes) == {"stall", "well"}
    assert load_world_graph(root).nodes["market-square"].has_children


def test_no_children_means_none(tmp_path):
    assert load_child_graph(_world(tmp_path), "D001") is None


# ── layout persistence ────────────────────────────────────────────────


def test_save_layout_touches_only_the_layout_key(tmp_path):
    root = _world(tmp_path)
    path = root / "game" / "world" / "world_map.json"
    before = json.loads(path.read_text(encoding="utf-8"))
    save_layout(root, WORLD_LEVEL, "T001", 3.5, 4.25)
    save_layout(root, "T001", "inn", 600, 270)
    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["layout"] == {"T001": [3.5, 4.25], "T001/inn": [600, 270]}
    after.pop("layout")
    assert after == before, "nodes / routes / everything else untouched"


def test_saved_layout_wins_over_pos(tmp_path):
    root = _world(tmp_path)
    save_layout(root, WORLD_LEVEL, "T001", 99, 98)
    g = load_world_graph(root)
    assert (g.nodes["T001"].x, g.nodes["T001"].y) == (99, 98)
    assert (g.nodes["T002"].x, g.nodes["T002"].y) == (5, 10)


# ── the widget, headless ──────────────────────────────────────────────


def _run(coro):
    return asyncio.run(coro)


async def _open_map(root: Path):
    from neonrp.tui.app import NeonRPApp

    app = NeonRPApp(root=root, mode="play")
    pilot_cm = app.run_test(size=(120, 44))
    pilot = await pilot_cm.__aenter__()
    await pilot.pause()
    await pilot.click("#tab-map")
    await pilot.pause()
    await pilot.pause()
    panel = app.query_one("#map-panel", MapPanel)
    return app, pilot, pilot_cm, panel


def test_map_renders_dots_and_roads_and_blinks(tmp_path):
    root = _world(tmp_path)

    async def go():
        app, pilot, cm, panel = await _open_map(root)
        try:
            text = panel.render().plain
            assert text.count(M.DOT) + text.count(M.DOT_CURRENT) >= len(panel.graph.nodes) >= 4
            assert M.EDGE in text, "roads are drawn"
            assert "石津镇" in text and "风栈堡" in text
            # The player's town blinks: the glyph alternates between ticks.
            assert panel._is_current("T001")
            a = panel._blink_on
            panel._tick_blink()
            assert panel._blink_on != a
            # Every dot is hit-testable where it was drawn.
            for nid, nd in panel.graph.nodes.items():
                assert panel.node_at(nd.cx, nd.cy) == nid
        finally:
            await cm.__aexit__(None, None, None)

    _run(go())


def test_drag_moves_a_dot_and_persists_only_layout(tmp_path):
    root = _world(tmp_path)
    path = root / "game" / "world" / "world_map.json"
    before = json.loads(path.read_text(encoding="utf-8"))

    async def go():
        app, pilot, cm, panel = await _open_map(root)
        try:
            nd = panel.graph.nodes["D001"]
            x0, y0 = nd.cx, nd.cy
            panel.move_node_to_cell("D001", x0 + 10, y0 + 3)
            panel.render()
            assert (nd.cx, nd.cy) != (x0, y0)
            assert abs(nd.cx - (x0 + 10)) <= 1 and abs(nd.cy - (y0 + 3)) <= 1
            panel.persist_node("D001")
        finally:
            await cm.__aexit__(None, None, None)

    _run(go())
    after = json.loads(path.read_text(encoding="utf-8"))
    assert "D001" in after["layout"]
    after.pop("layout")
    assert after == before
    # Topology untouched: the edge set is what it was.
    assert set(load_world_graph(root).edges) == set(load_world_graph(_world(tmp_path / "again")).edges)


def test_double_click_drills_down_and_esc_comes_back(tmp_path):
    root = _world(tmp_path)

    async def go():
        app, pilot, cm, panel = await _open_map(root)
        try:
            nd = panel.graph.nodes["T001"]
            ev = SimpleNamespace(x=nd.cx, y=nd.cy, chain=1, stop=lambda: None)
            panel.on_click(ev)
            assert panel.level == WORLD_LEVEL, "one click does nothing"
            panel.on_click(ev)  # second click inside the double-click window
            assert panel.level == "T001"
            assert "石津镇" in panel.breadcrumb and "灰雾北境" in panel.breadcrumb
            assert panel._is_current("gate_north"), "inside the town the player's spot blinks"
            await pilot.pause()
            crumb = app.query_one("#map-crumb").render()
            assert "石津镇" in str(crumb)
            panel.on_key(SimpleNamespace(key="escape", stop=lambda: None))
            assert panel.level == WORLD_LEVEL
            # `chain=2` (a real double click) works directly.
            panel._last_click = None
            panel.on_click(SimpleNamespace(x=nd.cx, y=nd.cy, chain=2, stop=lambda: None))
            assert panel.level == "T001"
            assert panel.go_up() and panel.level == WORLD_LEVEL
        finally:
            await cm.__aexit__(None, None, None)

    _run(go())


def test_double_click_on_a_leaf_flashes_a_hint(tmp_path):
    root = _world(tmp_path)

    async def go():
        app, pilot, cm, panel = await _open_map(root)
        try:
            assert not panel.drill("D001")
            assert panel.level == WORLD_LEVEL
            assert panel._hint and time.monotonic() < panel._hint_until
        finally:
            await cm.__aexit__(None, None, None)

    _run(go())


def test_zoom_clamps_and_buttons_work(tmp_path):
    root = _world(tmp_path)

    async def go():
        app, pilot, cm, panel = await _open_map(root)
        try:
            for _ in range(40):
                panel.zoom_in()
            assert panel.zoom == pytest.approx(ZOOM_MAX)
            for _ in range(80):
                panel.zoom_out()
            assert panel.zoom == pytest.approx(ZOOM_MIN)
            await pilot.click("#btn-map-reset")
            await pilot.pause()
            assert panel.zoom == 1.0
            await pilot.click("#btn-map-zoom-in")
            await pilot.pause()
            assert panel.zoom > 1.0
            await pilot.click("#btn-map-zoom-out")
            await pilot.pause()
            assert panel.zoom == pytest.approx(1.0)
            # Dots spread out when zoomed in.
            panel.reset_view()
            panel.render()
            a = panel.graph.nodes["T001"].cx - panel.graph.nodes["T002"].cx
            panel.zoom_in()
            panel.zoom_in()
            panel.render()
            b = panel.graph.nodes["T001"].cx - panel.graph.nodes["T002"].cx
            assert abs(b) > abs(a)
        finally:
            await cm.__aexit__(None, None, None)

    _run(go())


def test_world_without_places_says_so(tmp_path):
    root = tmp_path / "empty"
    (root / "game" / "meta").mkdir(parents=True)
    (root / "game" / "meta" / "run_state.json").write_text("{}", encoding="utf-8")

    async def go():
        app, pilot, cm, panel = await _open_map(root)
        try:
            assert panel.graph is not None and not panel.graph.nodes
            text = panel.render().plain.lower()
            assert any(w in text for w in ("地图", "map", "地図", "지도")), text   # whatever the shell's LANG
        finally:
            await cm.__aexit__(None, None, None)

    _run(go())


# ── TODO #11 · 地图小项:地点下的角色小标签、拖空白处平移 ──────────────


def _with_souls(root: Path) -> Path:
    from neonrp.core.playthrough import Playthrough, SoulRef, WorldAgentTeam, WorldRef, write_playthrough

    souls = [("elena", "si-elena0001", "艾琳娜", "T001/gate_north"), ("rowan", "si-rowan0001", "罗文", "T001/inn")]
    for sid, iid, name, node in souls:
        sd = root / "souls" / f"{sid}-{iid}"
        sd.mkdir(parents=True, exist_ok=True)
        (sd / "soul.json").write_text(json.dumps({"sid": sid, "name": sid, "name_local": name}, ensure_ascii=False), encoding="utf-8")
        (sd / "run_state.json").write_text(json.dumps({"location": node}), encoding="utf-8")
    write_playthrough(root, Playthrough(
        schema_version=2, playthrough_id="pt", world=WorldRef(wid="w", instance_id="wi-0000000000ff", version_hash="sha256:x", head_commit=""),
        world_agent_team=WorldAgentTeam(seeded_from="t", agents=[]),
        souls=[SoulRef(sid=s, instance_id=i, version_hash="", head_commit="", role="npc") for s, i, _n, _l in souls],
        created_at="2026-09-13T00:00:00Z", active_souls=tuple(i for _s, i, _n, _l in souls),
    ))
    return root


def test_souls_by_node_keys_follow_the_level(tmp_path):
    root = _with_souls(_world(tmp_path))
    assert M.souls_by_node(root, WORLD_LEVEL) == {"T001": ["艾琳娜", "罗文"]}
    assert M.souls_by_node(root, "T001") == {"gate_north": ["艾琳娜"], "inn": ["罗文"]}
    assert M._soul_tag(["艾琳娜", "罗文", "甲", "乙", "丙", "丁"]).startswith("· 艾琳娜 罗文") and "+" in M._soul_tag(["艾琳娜", "罗文", "甲", "乙", "丙", "丁"])


def test_soul_tags_render_under_the_place_and_follow_drill(tmp_path):
    root = _with_souls(_world(tmp_path))

    async def go():
        app, pilot, cm, panel = await _open_map(root)
        try:
            assert panel.souls == {"T001": ["艾琳娜", "罗文"]}
            text = panel.render().plain
            assert "· 艾琳娜 罗文" in text
            nd = panel.graph.nodes["T001"]
            row = text.splitlines()[nd.cy + 2]
            assert "艾琳娜" in row, "标签就在名字下一行"
            assert panel.drill("T001")
            text2 = panel.render().plain
            assert "· 艾琳娜" in text2 and "· 罗文" in text2 and panel.souls["inn"] == ["罗文"]
        finally:
            await cm.__aexit__(None, None, None)

    _run(go())


def test_dragging_empty_space_pans_and_arrows_pan(tmp_path):
    root = _world(tmp_path)

    async def go():
        app, pilot, cm, panel = await _open_map(root)
        try:
            panel.render()
            before = {nid: (nd.cx, nd.cy) for nid, nd in panel.graph.nodes.items()}
            # find an empty cell
            x, y = 1, 1
            while panel.node_at(x, y) is not None:
                x += 1
            panel.on_mouse_down(SimpleNamespace(x=x, y=y, button=1, stop=lambda: None))
            panel.on_mouse_move(SimpleNamespace(x=x + 6, y=y + 2, button=1, stop=lambda: None))
            panel.on_mouse_up(SimpleNamespace(x=x + 6, y=y + 2, button=1, stop=lambda: None))
            assert panel.pan == (6, 2)
            panel.render()
            after = {nid: (nd.cx, nd.cy) for nid, nd in panel.graph.nodes.items()}
            assert all(after[n] == (before[n][0] + 6, before[n][1] + 2) for n in before), "整张图平移,拓扑不动"
            # a pan-drag is not a click on anything
            panel.on_click(SimpleNamespace(x=x + 6, y=y + 2, chain=1, stop=lambda: None))
            assert not panel._crumbs
            panel.on_key(SimpleNamespace(key="left", stop=lambda: None))
            assert panel.pan == (10, 2)
            panel.reset_view()
            assert panel.pan == (0.0, 0.0)
        finally:
            await cm.__aexit__(None, None, None)

    _run(go())


def test_soul_tag_is_whole_or_absent_never_cut_by_a_neighbour_label(tmp_path):
    """石津镇下「· 艾琳娜」被紧挨着的「苔墓地穴」标签盖掉一半,读成「艾 苔墓地穴」——像她在地穴。"""
    root = _with_souls(_world(tmp_path))

    async def go():
        app, pilot, cm, panel = await _open_map(root)
        try:
            text = panel.render().plain
            for line in text.splitlines():
                if "· 艾" in line:
                    assert "· 艾琳娜" in line, f"标签被截断: {line!r}"
                    after = line.split("· 艾琳娜", 1)[1]
                    assert not after or after[0] == " ", f"标签和别的地名粘在一起: {line!r}"
        finally:
            await cm.__aexit__(None, None, None)

    _run(go())


def test_map_follows_the_player_when_they_move(tmp_path):
    root = _world(tmp_path, player_at="T002")

    async def go():
        app, pilot, cm, panel = await _open_map(root)
        try:
            assert panel.level == WORLD_LEVEL, "第一次打开是世界总览"
            rs = root / "game" / "meta" / "run_state.json"
            rs.write_text(json.dumps({"turn_count": 4, "location": {"node": "T001/inn", "node_id": "T001"}}), encoding="utf-8")
            panel.reload()
            assert panel.level == "T001" and panel._is_current("inn"), "玩家进镇 → 地图跟到镇里"
            assert panel.go_up() and panel.level == WORLD_LEVEL
            panel.reload()
            assert panel.level == WORLD_LEVEL, "手动切回总览后,玩家没动就不再跳"
            rs.write_text(json.dumps({"turn_count": 5, "location": {"node": "T002", "node_id": "T002"}}), encoding="utf-8")
            panel.drill("T001")
            panel.reload()
            assert panel.level == WORLD_LEVEL, "玩家出镇 → 回世界图"
        finally:
            await cm.__aexit__(None, None, None)

    _run(go())
