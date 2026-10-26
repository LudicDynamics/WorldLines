"""A talk cut by time keeps what was said and goes on from it (10-25 niko: 主持复述可以留,只是商量时间过长的时候,已经
生成的内容不要浪费了) — the private layer's planning beat read with core/turn_rescue.resuming_talk.

No real model: the host's reply is a fake (one cut by the beat's time, then the one that goes on)."""
from __future__ import annotations

import pytest
from _paths import PRODUCT_TEMPLATES

from neonrp import template as TP
from neonrp.core import turn_rescue

try:  # the planning beat is a private-layer plugin (requires_private.txt)
    from neonrp.core import plan_loop
except ImportError:
    plan_loop = None


@pytest.fixture
def world(tmp_path, monkeypatch):
    if plan_loop is None:
        pytest.skip("private layer absent")
    monkeypatch.setattr(plan_loop, "settled", lambda *a, **k: 0.99)  # a judge that would settle anything
    monkeypatch.setattr(plan_loop, "overrode", lambda *a, **k: None)
    monkeypatch.setattr(plan_loop, "check_gap", lambda *a, **k: None)
    monkeypatch.setattr(plan_loop, "host_again", lambda *a, **k: None)
    root = tmp_path / "w"
    TP.build(PRODUCT_TEMPLATES / "stoneford-elena.template", root)
    return root


def _host(monkeypatch, replies, asked):
    it = iter(replies)

    def host(root, system, user):
        asked.append(user)
        raw, cut = next(it)
        plan_loop._HOST_STREAM["truncated"] = cut
        return raw

    monkeypatch.setattr(plan_loop, "_host", host)


def test_a_cut_talk_lands_its_whole_sentences_and_goes_on_from_them(world, monkeypatch):
    asked: list[str] = []
    _host(monkeypatch, [("<lines>\n先别急。灯就在门边,你伸手就能拿到。不过米拉说过雾里那条", True),
                        ("<lines>\n那条小路要绕开老井。先拿灯。\n</lines>\nnext: wait", False)], asked)
    out = plan_loop.step(world, user_text="我们先进镇", last_narration="雾很大。")
    assert out["kind"] == "plan", "a talk the time cut is not settled for him"
    assert out["narration"] == "先别急。灯就在门边,你伸手就能拿到。"  # the sentence the time cut off does not land
    assert out["beat"].get("truncated")
    talk0 = plan_loop.load(world)["talk"]
    L = plan_loop._L(world)
    with turn_rescue.resuming_talk("我们先进镇"):
        out2 = plan_loop.step(world, user_text="我们先进镇", last_narration="雾很大。")
    assert L["resumed"].strip() in asked[-1]  # the host is told to go on, not to start over
    assert asked[-1].count("我们先进镇") == asked[0].count("我们先进镇")  # the line is not told twice
    assert "先别急。灯就在门边" in asked[-1]  # what was said is there to go on from
    # whole now, the judge settles it: the talk's own beat, then the Resolve
    assert out2["kind"] == "resolve" and out2["plan_beat"]["narration"] == "那条小路要绕开老井。先拿灯。"
    assert sum(1 for x in out2["talk"] if x.endswith("我们先进镇")) == 1 and len(out2["talk"]) == len(talk0) + 1


def test_a_talk_settled_with_no_time_left_goes_straight_to_the_resolve(world, monkeypatch):
    asked: list[str] = []
    _host(monkeypatch, [], asked)
    sc = plan_loop.load(world)
    plan_loop.save(world, {**sc, "board": {"玩家": "进镇去旅店"}, "advance_deferred": "judge:settled", "talk": ["玩家:进镇去旅店?"]})
    with turn_rescue.resuming_talk("进镇去旅店?"):  # a question would not resolve a deferred talk — played on, it does
        out = plan_loop.step(world, user_text="进镇去旅店?", last_narration="")
    assert out["kind"] == "resolve" and out["advanced_by"] == "judge:settled" and asked == []


def test_brief_drops_the_sentence_the_time_cut():
    b = plan_loop.brief if plan_loop is not None else pytest.skip("private layer absent")
    assert b("先别急。灯在门边,你伸", cut=True) == "先别急。"
    assert b("先别急。灯在门边。", cut=True) == "先别急。灯在门边。"
    assert b("灯在门边,你伸", cut=True) == ""
    assert b("灯在门边,你伸") == "灯在门边,你伸"  # not cut: as before
