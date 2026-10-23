"""The deterministic post-process location judge (place_nav.judge_move).

Root cause it fixes: world-agent moves landed with allow_cross_town=True and
the town_map/world_map ``links`` graphs were never consulted — a soul could
legally cross the world in one turn (the Rowan teleport). Policy under test:
intra-town movement is free; a town TRANSITION is the one budgeted travel
action per turn and goes through gates; no world-map route → refused; anything
unmapped stays permissive (zero false rejections on name-only worlds).
"""

import json
from pathlib import Path

from neonrp.core.conversation import (
    _drain_location_judgments,
    _judge_world_agent_move,
    _location_judgments_path,
)
from neonrp.core.place_nav import judge_move


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _node(nid, links, *, ntype="street", name=None):
    return {"id": nid, "type": ntype, "name": name or nid, "links": links}


def _build_mapped_world(root: Path) -> Path:
    """Two towns joined by a road; a third town isolated ON PURPOSE (wired to
    another town so its separation is positive evidence, not sloppiness)."""
    # T001: gate + square + inn, plus an orphan node (no links at all).
    _write_json(
        root / "game" / "towns" / "T001" / "town_map.json",
        {
            "town_id": "T001",
            "nodes": [
                _node("gate_east", ["square"], ntype="gate", name="东门"),
                _node("square", ["gate_east", "inn"], name="广场"),
                _node("inn", ["square"], ntype="facility", name="旅店"),
                _node("shrine", [], name="荒祠"),  # orphan island
            ],
        },
    )
    # T002: gate + market.
    _write_json(
        root / "game" / "towns" / "T002" / "town_map.json",
        {
            "town_id": "T002",
            "nodes": [
                _node("gate_west", ["market"], ntype="gate", name="西门"),
                _node("market", ["gate_west"], name="市场"),
            ],
        },
    )
    # T003: gateless town, linked to T004 on the world map.
    _write_json(
        root / "game" / "towns" / "T003" / "town_map.json",
        {"town_id": "T003", "nodes": [_node("plaza", [], name="孤城广场")]},
    )
    _write_json(
        root / "game" / "towns" / "T004" / "town_map.json",
        {
            "town_id": "T004",
            "nodes": [_node("gate_south", ["yard"], ntype="gate"), _node("yard", ["gate_south"])],
        },
    )
    # World map: T001—R001—T002 (adjacent); T003—R009—T004 (their own island).
    _write_json(
        root / "game" / "world" / "world_map.json",
        {
            "nodes": [
                {"id": "T001", "type": "town", "links": ["R001"]},
                {"id": "T002", "type": "town", "links": ["R001"]},
                {"id": "T003", "type": "town", "links": ["R009"]},
                {"id": "T004", "type": "town", "links": ["R009"]},
            ]
        },
    )
    return root


# ── judge_move policy ────────────────────────────────────────────


def test_intra_town_multi_hop_is_free(tmp_path):
    root = _build_mapped_world(tmp_path)
    v = judge_move(root, current_location="T001/gate_east", target="T001/inn")
    assert v.allowed and v.tier == "intra" and v.final == "T001/inn"


def test_intra_town_nonexistent_node_rejected_with_suggestions(tmp_path):
    root = _build_mapped_world(tmp_path)
    v = judge_move(root, current_location="T001/square", target="T001/castle")
    assert not v.allowed and v.final is None and v.tier == "intra"
    assert "castle" in v.reason and "gate_east" in v.reason  # names valid nodes


def test_cross_town_away_from_gate_walks_out_and_arrives_in_one_beat(tmp_path):
    """10-19 niko: one beat is the whole walk — out by the gate and into the next town (no beat stopped at the gate)."""
    root = _build_mapped_world(tmp_path)
    v = judge_move(root, current_location="T001/inn", target="T002/market")
    assert v.allowed and v.tier == "cross" and v.final == "T002/market"


def test_cross_town_from_gate_lands_at_target_node(tmp_path):
    root = _build_mapped_world(tmp_path)
    v = judge_move(root, current_location="T001/gate_east", target="T002/market")
    assert v.allowed and v.tier == "cross" and v.final == "T002/market"


def test_cross_town_without_route_is_refused(tmp_path):
    root = _build_mapped_world(tmp_path)
    # T001 and T003 both have world-graph wiring but no path between them.
    v = judge_move(root, current_location="T001/gate_east", target="T003/plaza")
    assert not v.allowed and v.clamped_to is None and v.tier == "cross"
    assert "没有路线" in v.reason


def test_unmapped_world_judge_is_inert(tmp_path):
    # Name-only world: no town maps at all → everything allowed.
    v = judge_move(tmp_path, current_location="河灯旅店", target="north-cliff")
    assert v.allowed and v.tier == "unmapped"


def test_wilderness_target_is_permissive(tmp_path):
    root = _build_mapped_world(tmp_path)
    v = judge_move(root, current_location="T001/square", target="misty-woods")
    assert v.allowed and v.tier == "unmapped" and v.final == "misty-woods"


def test_dangling_world_links_stay_permissive_but_gated(tmp_path):
    """Sloppy real maps (links name undeclared roads) must not trap souls:
    adjacency is 'unknown' → travel allowed, still staged through the gate."""
    root = _build_mapped_world(tmp_path)
    # Rewire the world map so T002's only road is dangling (isolated).
    _write_json(
        root / "game" / "world" / "world_map.json",
        {
            "nodes": [
                {"id": "T001", "type": "town", "links": ["R001"]},
                {"id": "T002", "type": "town", "links": ["R404"]},  # dangling
                {"id": "T003", "type": "town", "links": ["R001"]},
            ]
        },
    )
    v = judge_move(root, current_location="T001/inn", target="T002/market")
    assert v.allowed and v.final == "T002/market"  # out by the gate and in, one beat
    v2 = judge_move(root, current_location="T001/gate_east", target="T002/market")
    assert v2.allowed and v2.final == "T002/market"


def test_town_level_target_lands_at_its_gate(tmp_path):
    root = _build_mapped_world(tmp_path)
    v = judge_move(root, current_location="T001/gate_east", target="T002")
    assert not v.allowed and v.final == "T002/gate_west"
    assert "gate_west" in v.reason


# ── the Pass B hook (landing + correction queue) ─────────────────


def _make_soul(root: Path, iid: str, location: str) -> Path:
    soul_dir = root / "souls" / f"ada-{iid}"
    _write_json(soul_dir / "run_state.json", {"location": location})
    return soul_dir


def test_hook_clamps_cross_town_move_and_queues_judgment(tmp_path):
    root = _build_mapped_world(tmp_path)
    soul_dir = _make_soul(root, "siada0001", "T001/inn")

    landed = _judge_world_agent_move(
        root, soul_dir, instance_id="siada0001", display_name="Ada", move="T002"
    )
    assert landed == "T002/gate_west"  # a town-level move lands at its gate (clamped)

    lines = _drain_location_judgments(root)
    assert len(lines) == 1
    assert lines[0].startswith("[soul:siada0001] Ada:")
    assert "gate_west" in lines[0]
    # Drain is destructive — delivered exactly once.
    assert _drain_location_judgments(root) == []
    assert not _location_judgments_path(root).exists()


def test_hook_refuses_routeless_move_soul_stays(tmp_path):
    root = _build_mapped_world(tmp_path)
    soul_dir = _make_soul(root, "siada0001", "T001/gate_east")

    landed = _judge_world_agent_move(
        root, soul_dir, instance_id="siada0001", display_name="Ada", move="T003/plaza"
    )
    assert landed == ""  # refused → caller skips the move; soul stays put
    lines = _drain_location_judgments(root)
    assert len(lines) == 1 and "没有路线" in lines[0]


def test_hook_allows_intra_town_move_untouched(tmp_path):
    root = _build_mapped_world(tmp_path)
    soul_dir = _make_soul(root, "siada0001", "T001/gate_east")

    landed = _judge_world_agent_move(
        root, soul_dir, instance_id="siada0001", display_name="Ada", move="inn"
    )
    assert landed == "T001/inn"
    assert _drain_location_judgments(root) == []  # nothing queued


# ── validate: travel-graph warnings ──────────────────────────────


def test_validate_warns_orphan_node_and_gateless_town(tmp_path):
    from neonrp.core.validation import _travel_graph_issues

    root = _build_mapped_world(tmp_path)
    issues = _travel_graph_issues(root)
    codes = {(i.code, i.file) for i in issues}
    # T001's shrine is unreachable from the gate.
    assert ("node-unreachable", "game/towns/T001/town_map.json") in codes
    assert any("shrine" in i.message for i in issues)
    # T003 is on the world map but has no gate.
    assert ("town-gateless", "game/towns/T003/town_map.json") in codes
    # T002/T004 are healthy — no issues for them.
    assert not any("T002" in i.file or "T004" in i.file for i in issues)
