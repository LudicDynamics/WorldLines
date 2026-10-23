"""Two-beat fixes from the 10-19 real-model replays (docs/playrecords/two-beat-1019; root causes in the lead report):

- B: the settled plan's brief names the rule pack's own ops for a pack that has them, instead of the generic 「patch it
  onto the person」 reminder that turned agreed votes into seat properties nobody registered
- C: a check set only at the switch — one the player never heard — does not resolve the turn: he is told and asked
  (an @GM still resolves at once); a line that is the player asking is not judged settled for him
"""
from __future__ import annotations

import pytest
from _paths import PRODUCT_TEMPLATES

from neonrp import template as TP

try:  # the planning beat is a private-layer plugin; without it every case here is skipped (requires_private.txt)
    from neonrp.core import plan_loop
except ImportError:
    plan_loop = None


def _judges(monkeypatch, *, settled=None, gap=None):
    monkeypatch.setattr(plan_loop, "settled", lambda *a, **k: settled)
    monkeypatch.setattr(plan_loop, "overrode", lambda *a, **k: None)
    monkeypatch.setattr(plan_loop, "check_gap", lambda *a, **k: gap)
    monkeypatch.setattr(plan_loop, "host_again", lambda *a, **k: None)


def _world(tmp_path, monkeypatch, replies, tpl="stoneford-elena"):
    root = tmp_path / "w"
    TP.build(PRODUCT_TEMPLATES / f"{tpl}.template", root)
    it = iter(replies)
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: next(it))
    out0 = plan_loop.step(root, user_text="开始游戏", last_narration="")
    return root, out0


ADVANCE = "<lines>\n进镇就是主街,旅店在河边。\n</lines>\n<board>\n玩家: 进镇去旅店打听北路\n</board>\nnext: advance"
SET_CHECK = "<lines>\n先问清楚。\n</lines>\n<board>\n检定: 玩家 CHA easy 向旅店老板打听北路\n</board>\nnext: advance"


def test_a_check_he_never_heard_is_offered_not_rolled(tmp_path, monkeypatch):
    _judges(monkeypatch, settled=0.2, gap=0.9)
    root, out0 = _world(tmp_path, monkeypatch, [ADVANCE, SET_CHECK])
    out = plan_loop.step(root, user_text="那我们先进镇,去旅店打听打听", last_narration=out0["narration"])
    assert out["kind"] == "plan", "the turn does not resolve on a check set only at the switch"
    beat = out["beat"]
    assert beat["checks"] and beat["ended_by"] is None
    host = [x["text"] for x in beat["script"] if x["role"] == "host"][-1]
    assert host.endswith("要试吗?"), host
    # he says go: the agreed board (with its check) resolves
    out2 = plan_loop.step(root, user_text="定", last_narration=out["narration"])
    assert out2["kind"] == "resolve" and out2["checks"]


def test_an_at_gm_line_still_resolves_with_the_check(tmp_path, monkeypatch):
    _judges(monkeypatch, settled=0.2, gap=0.9)
    root, out0 = _world(tmp_path, monkeypatch, [ADVANCE, SET_CHECK])
    out = plan_loop.step(root, user_text="@dm 进镇去旅店打听打听", last_narration=out0["narration"])
    assert out["kind"] == "resolve" and out["checks"]


def test_a_question_he_asks_is_not_judged_settled(tmp_path, monkeypatch):
    _judges(monkeypatch, settled=0.95)
    root, out0 = _world(tmp_path, monkeypatch, ["<lines>\n她点点头。\n</lines>\nnext: wait"])
    out = plan_loop.step(root, user_text="艾琳娜,刚才那人说的你听到了吗?", last_narration=out0["narration"])
    assert out["kind"] == "plan" and out["beat"].get("ended_by") is None


def test_a_statement_is_still_judged_settled(tmp_path, monkeypatch):
    _judges(monkeypatch, settled=0.95)
    root, out0 = _world(tmp_path, monkeypatch, ["<lines>\n墙根背风。\n</lines>\nnext: wait"])
    out = plan_loop.step(root, user_text="我先在这儿墙根靠着歇一阵。", last_narration=out0["narration"])
    assert out["kind"] == "resolve" and out["advanced_by"] == "judge:settled"


def test_the_brief_names_the_packs_own_ops_where_it_has_them(tmp_path):
    for tpl in ("werewolf-night-village", "stoneford-elena"):
        if not (PRODUCT_TEMPLATES / f"{tpl}.template").is_dir():
            pytest.skip(f"{tpl}: not in this checkout")
    L = plan_loop._L(None)
    ww = tmp_path / "ww"
    TP.build(PRODUCT_TEMPLATES / "werewolf-night-village.template", ww)
    brief = plan_loop.resolve_facts({"board": {"玩家": "投 S03"}, "checks": []}, ww)
    assert L["rf_write_ops"] in brief and L["rf_write"] not in brief
    el = tmp_path / "el"
    TP.build(PRODUCT_TEMPLATES / "stoneford-elena.template", el)
    brief = plan_loop.resolve_facts({"board": {"玩家": "买药"}, "checks": []}, el)
    assert L["rf_write"] in brief and L["rf_write_ops"] not in brief, "a pack without ops of its own keeps the old line"
