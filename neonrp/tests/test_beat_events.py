"""R6 (10-06): contract 1.0 beat events from turn traces."""
from __future__ import annotations

from neonrp.core import beat_events


def _tr(seq, kind, **ap):
    return {"turn_seq": seq, "apply": {"beat": {"kind": kind, **ap.pop("beat", {})}, **ap}}


def test_plan_then_resolve_with_dice_state_and_settle():
    trs = [_tr(1, "plan", beat={"checks": [{"who": "player", "attr": "DEX"}]}, narration_plain="赫伦点头。"),
           _tr(2, "resolve", beat={"advanced_by": "player"}, narration_plain="你翻过墙。",
               tool_returns=[{"request": "dice 1d20", "text": "14"}, {"request": "look gate", "text": "…"}],
               applied=[{"op": "add", "var": "player.hp", "from": 10, "to": 9}], settled={"exit": "ending:good"})]
    evs, node = beat_events.from_traces(trs)
    names = [e for e, _ in evs]
    assert names == ["node.enter", "plan.beat", "node.leave", "node.enter", "resolve.beat", "dice", "tool", "state.changed", "run.settled"]
    assert node == "resolve" and evs[1][1]["checks"][0]["attr"] == "DEX" and evs[4][1]["advanced_by"] == "player"
    assert evs[-1][1]["exit"] == "ending:good" and set(names) <= set(beat_events.EVENTS)


def test_node_carries_over_between_lines_and_modes_enter():
    evs, node = beat_events.from_traces([_tr(3, "resolve", mode={"name": "combat"})], prev_node="resolve")
    assert [e for e, _ in evs] == ["resolve.beat", "node.leave", "node.enter"] and node == "combat"


def test_generators_carry_beat_events():
    from _paths import PRODUCT_TEMPLATES

    _MARKET = PRODUCT_TEMPLATES / "stoneford-market.template"   # dev repo only (conftest skips it where it is absent)

    from neonrp import template as TP
    from neonrp.template import v3

    t = TP.load(_MARKET)
    with v3._scratch(t, None) as root:
        c = v3.contract(t, root)
    assert "plan.beat" in c["beat_events"]
    assert "export type BeatEvent = " in v3.gen_ts(c) and "'run.settled'" in v3.gen_ts(c)
    assert "signal beat(event: String, data: Dictionary)" in v3.gen_gd(c)
