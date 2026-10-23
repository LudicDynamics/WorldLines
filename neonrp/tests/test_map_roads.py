"""地图建路 / 删路(1.0 带创作写回):一层上两地点之间的路 = 双方的 links(地点文件夹的 connections);
世界层带路程的路还在 world_map.json 的 routes。"""

from __future__ import annotations

import pytest

from _paths import PRODUCT_TEMPLATES


@pytest.fixture
def run(tmp_path):
    from neonrp import template as TP

    TP.build(PRODUCT_TEMPLATES / "stoneford-elena.template", tmp_path / "run")
    return tmp_path / "run"


def _pairs(root, level):
    from neonrp.core import worldmap as M

    return {frozenset((e["from"], e["to"])) for e in M.build_map_tree(root)["nodes"][level]["edges"]}


def test_town_road_add_and_remove(run):
    from neonrp.core import worldmap as M

    pair = frozenset(("T001/dock", "T001/inn"))
    assert pair not in _pairs(run, "T001")
    M.set_road(run, "T001", "T001/dock", "T001/inn")
    assert pair in _pairs(run, "T001")
    M.set_road(run, "T001", "T001/inn", "T001/dock")          # 已经有了:不重复
    assert len([p for p in _pairs(run, "T001") if p == pair]) == 1
    M.set_road(run, "T001", "T001/dock", "T001/inn", remove=True)
    assert pair not in _pairs(run, "T001")


def test_world_road_with_distance_and_bad_input(run):
    from neonrp.core import worldmap as M

    towns = [c for c in M.build_map_tree(run)["nodes"]["world"]["children"]]
    a, b = next((x, y) for x in towns for y in towns if x < y and frozenset((x, y)) not in _pairs(run, "world"))
    M.set_road(run, "world", a, b, distance=3)
    edge = next(e for e in M.build_map_tree(run)["nodes"]["world"]["edges"] if {e["from"], e["to"]} == {a, b})
    assert edge["distance"] == 3
    M.set_road(run, "world", a, b, remove=True)
    assert frozenset((a, b)) not in _pairs(run, "world")
    with pytest.raises(ValueError):
        M.set_road(run, "T001", "T001/dock", "T001/dock")
    with pytest.raises(ValueError):
        M.set_road(run, "T001", "T001/dock", "T001/nowhere")
