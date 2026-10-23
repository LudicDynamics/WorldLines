"""A character away from the player walks the party's cross-town rule on her own days (10-23 niko). 21 of 69 regression
runs had Rowan step from 碧石镇 (T004) to 石津镇's gate (T001) in one beat: the rule (set out, the road takes days) was the
party's only, and a bare 「北门」 from T004 resolved to T001's gate."""
from __future__ import annotations

from pathlib import Path

from test_engine_v3 import _install

from neonrp.core import beat_display
from neonrp.core.registry import load_registry
from neonrp.packs.rpg import travel
from neonrp.packs.rpg.atlas.move import judge, move

ROWAN, ELENA = "si-rowan0001", "si-elena0001"


def _world(tmp_path: Path):
    root = _install(tmp_path / "w")
    return root, load_registry(root)


def _away(reg, iid, text="x"):
    return beat_display.away_lines(reg, [{"iid": iid, "name": reg.entries[iid].name, "text": text}], "zh")[0]


def test_her_names_resolve_in_her_own_town_never_the_players(tmp_path):
    root, reg = _world(tmp_path)
    cur = reg.entries[ROWAN].parent  # T004, away from the player (T001)
    assert judge(root, reg, ROWAN, cur, "gate_west").to == "T004/gate_west"
    assert judge(root, reg, ROWAN, cur, "guild").to == "T004/guild"
    assert judge(root, reg, ROWAN, cur, "冒险者公会（碧石分部）").to == "T004/guild"  # by name, in her town
    for ask in ("gate_north", "北门", "冒险者公会"):  # T004 has no north gate and its guild has another name — never T001's
        v = judge(root, reg, ROWAN, cur, ask)
        assert not v.ok and v.fixable and "T004/gate_west" in " ".join(v.allowed) and "T001" not in " ".join(v.allowed), ask


def test_another_town_is_a_road_she_walks_on_her_own_days(tmp_path):
    root, reg = _world(tmp_path)
    cur = reg.entries[ROWAN].parent
    v = judge(root, reg, ROWAN, cur, "T001")
    assert v.ok and v.to == "road_T004_T001" and v.clamped and "3" in v.reason
    assert judge(root, reg, ROWAN, cur, "T001/guild").to == "road_T004_T001"
    assert move(root, reg, ROWAN, "road_T004_T001")
    reg = load_registry(root)
    assert reg.entries[ROWAN].parent == "road_T004_T001"
    assert reg.entries["road_T004_T001"].name == "驿路(碧石镇→石津镇)"  # the road is a place on reload too
    j = travel.soul_journey(root, ROWAN)
    assert j["from"] == "T004" and j["to"] == "T001" and j["days"] == 3
    # on the road: not there yet — no arrival, and a move to the far end is refused without a re-ask
    assert travel.tick_souls(root, reg) == []
    v = judge(root, reg, ROWAN, "road_T004_T001", "T001")
    assert not v.ok and not v.fixable and "3" in v.reason
    # the world's days pass (the player sleeps, travels): she arrives at the gate, by an op like any other
    travel.advance_calendar(root, reg, 3, note="")
    reg = load_registry(root)
    assert travel.tick_souls(root, reg) == [{"op": "move_to", "who": ROWAN, "to": "T001/gate_north"}]
    v = judge(root, reg, ROWAN, "road_T004_T001", "T001/gate_north")
    assert v.ok and v.to == "T001/gate_north"
    assert move(root, reg, ROWAN, "T001/gate_north")
    reg = load_registry(root)
    assert reg.entries[ROWAN].parent == "T001/gate_north" and travel.soul_journey(root, ROWAN) is None


def test_the_away_line_names_her_town_and_her_road(tmp_path):
    root, reg = _world(tmp_path)
    assert move(root, reg, ROWAN, "T004/tavern")
    reg = load_registry(root)
    assert "翠晶酒馆(碧石镇)" in _away(reg, ROWAN)
    assert "(" not in _away(reg, ELENA).split("@")[1].split(":")[0]  # a place in the player's own town stays bare
    assert move(root, reg, ROWAN, "T004/guild")
    assert "@ 冒险者公会（碧石分部）:" in _away(load_registry(root), ROWAN)  # a name that already says the town gets no suffix
    assert move(root, reg, ROWAN, "road_T004_T001")
    assert "驿路(碧石镇→石津镇)" in _away(load_registry(root), ROWAN)


def test_the_party_and_companion_rules_are_unchanged(tmp_path):
    root, reg = _world(tmp_path)
    v = judge(root, reg, "player", reg.player_location, "T004")
    assert not (v.ok and str(v.to).startswith("T004/"))  # the player still sets out / meets the referee, never lands at once
    v = judge(root, reg, ELENA, reg.entries[ELENA].parent, "T004")  # beside the player: the party's rule, not a road of her own
    assert not (v.ok and str(v.to).startswith("T004/")) and travel.soul_journey(root, ELENA) is None
