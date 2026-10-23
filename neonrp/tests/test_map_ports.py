"""Cross-level ports (MAP-SCALES-1005 G1) and the map lint (G3), on a copy of the stoneford-elena world."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from neonrp.core import place_tree as pt
from neonrp.core.map_lint import lint_map
from neonrp.core.place_nav import judge_move
from neonrp.core.registry import load_registry
from _paths import PRODUCT, PRODUCT_TEMPLATES

_TPL = Path("src/neonrp/templates/stoneford-elena")


def _world(tmp_path: Path) -> Path:
    root = tmp_path / "w"
    shutil.copytree(_TPL, root)
    return root


def _rec(root: Path, *parts: str) -> Path:
    return root / "game" / "locations" / Path(*parts) / "location.json"


def _edit(path: Path, **kv) -> None:
    d = json.loads(path.read_text(encoding="utf-8"))
    for k, v in kv.items():
        if v is None:
            d.pop(k, None)
        else:
            d[k] = v
    path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def test_a_route_in_lands_on_its_port_else_on_the_entry(tmp_path):
    """G1 acceptance: from the world level R002 (the crypt trail) comes into 石津镇 at the node that takes it; R001
    (the road from the west town) is taken by no node → the level's entry."""
    root = _world(tmp_path)
    _edit(_rec(root, "T001", "gate_north"), ports={"up": ["R002"]})
    _edit(_rec(root, "T001"), entry="dock")
    v = judge_move(root, current_location="D001/D001_R001", target="T001")
    assert v.clamped_to == "T001/gate_north", v
    v = judge_move(root, current_location="T002", target="T001")
    assert v.clamped_to == "T001/dock", v


def test_leaving_a_town_goes_by_the_node_bound_to_the_road(tmp_path):
    root = _world(tmp_path)
    _edit(_rec(root, "T001", "dock"), ports={"up": ["R004"]})
    v = judge_move(root, current_location="T001/main_street", target="T004")
    assert v.clamped_to and v.clamped_to.startswith("T004/"), "one beat: out by the dock and into T004 (10-19)"
    v2 = judge_move(root, current_location="T001/dock", target="T004")
    assert v2.clamped_to == v.clamped_to, v2


def test_a_world_without_ports_or_entry_travels_as_before(tmp_path):
    root = _world(tmp_path)
    for parts in (("T001", "gate_north"), ("T004", "gate_west")):
        _edit(_rec(root, *parts), ports=None)
    _edit(_rec(root, "T001"), entry=None)
    _edit(_rec(root, "T004"), entry=None)
    v = judge_move(root, current_location="T001/main_street", target="T004")
    assert v.clamped_to == "T004/gate_west", "no ports: in by the gate, in one beat (10-19)"


def test_the_fixed_stoneford_map_lints_clean():
    for w in ("src/neonrp/templates/stoneford-elena", "src/neonrp/templates/stoneford-elena-en",
              "src/neonrp/templates/stoneford-elena-ja", str(PRODUCT / "examples" / "worlds" / "stoneford-elena")):
        assert lint_map(Path(w)) == [], w


def test_the_lint_reports_each_kind_of_defect(tmp_path):
    """G3 acceptance: the five §5 defects, put back, are each reported."""
    root = _world(tmp_path)
    gn = _rec(root, "T001", "gate_north")
    d = json.loads(gn.read_text(encoding="utf-8"))
    _edit(gn, connections=[*d["connections"], "old-road"], ports=None)
    ms = _rec(root, "T001", "market-square")
    d = json.loads(ms.read_text(encoding="utf-8"))
    _edit(ms, connections=[*d["connections"], "guildhall"])
    _edit(_rec(root, "T001"), entry=None)
    _edit(_rec(root, "T003"), isolated=None)
    lay = root / "game" / "dungeons" / "D001" / "layout.json"
    rooms = [{"id": c.name, "links": json.loads((c / "location.json").read_text(encoding="utf-8")).get("connections")}
             for c in sorted((root / "game" / "locations" / "D001").iterdir()) if c.is_dir()]
    shutil.rmtree(root / "game" / "locations" / "D001" / rooms[0]["id"])
    for r in rooms[1:]:
        shutil.rmtree(root / "game" / "locations" / "D001" / r["id"])
    lay.write_text(json.dumps({"dungeon_id": "D001", "rooms": rooms}), encoding="utf-8")
    _edit(_rec(root, "T004", "gate_west"), ports={"up": ["R999"]})
    got = {(i["code"], i["where"].rsplit("/", 1)[-1].split("#")[-1]) for i in lint_map(root)}
    assert ("map.dangling", "gate_north") in got and ("map.dangling", "market-square") in got
    assert any(c == "map.port_unbound" for c, _w in got)
    assert ("map.isolated", "T003") in got and ("map.isolated", "T005") not in got, "marked isolated: not reported"
    assert any(c == "map.legacy_level" and "D001" in w for c, w in {(i["code"], i["where"]) for i in lint_map(root)})
    assert ("map.port_dangling", "gate_west") in got


def test_dungeon_rooms_read_from_their_folders_and_the_dungeon_is_not_a_town(tmp_path):
    root = _world(tmp_path)
    assert "D001" not in pt.town_ids(root)
    rooms = pt.dungeon_rooms(root, "D001")
    assert [r["id"] for r in rooms][:1] == ["D001_R001"] and all(r["links"] for r in rooms)
    assert pt.level_entry(root, "D001") == "D001_R001"
    reg = load_registry(root)
    r1 = reg.entries["D001/D001_R001"]
    assert r1.cls == "room" and "D001/D001_R002" in r1.links
    assert not any(e.cls == "place" and str(e.id).startswith("D001/") for e in reg.entries.values())


def test_map_lint_on_a_world_without_dungeons(tmp_path):
    """10-06: pct-house has no game/dungeons — the lint crashed (a comprehension listed the folder before checking it)."""
    import shutil

    from neonrp.core.map_lint import lint_map as lint

    w = tmp_path / "w"
    shutil.copytree(PRODUCT_TEMPLATES / "pct-house.template" / "world", w)
    assert not (w / "game" / "dungeons").exists()
    assert isinstance(lint(w), list)
