"""Two-beat fixes from the 10-19 real-model replays (docs/playrecords/two-beat-1019; root causes in the lead report):

- B: the settled plan's brief names the rule pack's own ops for a pack that has them, instead of the generic 「patch it
  onto the person」 reminder that turned agreed votes into seat properties nobody registered
- C: a check set only at the switch — one the player never heard — does not resolve the turn: he is told and asked
  (an @GM still resolves at once); a line that is the player asking is not judged settled for him
- D (10-25 narration-model runs): a percentile contest's dice line put the other side's roll in his label and read as
  「59 ≤ 60 → 失败」; its dice event said his own 「success」 beside ``passed: false``; a check with no 为了 showed whole
  as its reason (「INT(夜见 INT normal 辨认…)」)
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


def test_a_talk_line_is_cut_on_whole_sentences_never_inside_a_quote():
    """10-25 N[19]: 3 sentences counted inside the quotes left 「有人用过。 open on the player's screen."""
    if plan_loop is None:
        pytest.skip("private layer absent")
    b = plan_loop.brief
    two = "「书签是读者写给我的一行字。写下了，我就得照做——不管我心里愿不愿意。」「有人用过。很久以前。」"
    assert b(two) == two  # two quoted lines are two units, not five sentences
    assert b("「书签是一行字。写下了就得照做。」「有人用过。") == "「书签是一行字。写下了就得照做。」"  # the open one goes
    assert b("「有人用过。") == "「有人用过。」"  # all she said: kept, closed
    assert b("一。二。三。四。") == "一。二。三。"
    assert b("Fine. I'll go. But \"only if you pay. Later.\" Then more.") == "Fine. I'll go. But \"only if you pay. Later.\""


# ── D: contests say who won and why; a check's own parts are not its reason (10-25) ──

def _contest_reg():
    from types import SimpleNamespace as N

    return N(root=None, entries={"player": N(name="归乡后生"), "si-lian": N(name="莲妹")})


def _side(who, roll, target, level):
    return {"who": who, "roll": roll, "mod": 0, "total": roll, "target": target, "label": "敏捷", "level": level}


# A1-deepseek-style / P1-minimax-r2: same tier, her margin 11 against his 1 · her 2/55 critical against his 82/60
SAME_TIER = {"system": "pct", "attr": "敏捷", "why": "抢在熄屏前拍下井水", "result": "fail",
             "a": _side("player", 59, 60, "success"), "b": _side("si-lian", 44, 55, "success")}
HER_CRIT = {"system": "pct", "attr": "敏捷", "why": "把手机举到井水上方拍照", "result": "fail",
            "a": _side("player", 82, 60, "fail"), "b": _side("si-lian", 2, 55, "crit")}


def test_a_contest_line_says_who_won_first_then_each_side_in_plain_words():
    if plan_loop is None:
        pytest.skip("private layer absent")
    from neonrp.tui.app import ConversationView

    reg = _contest_reg()
    lines = plan_loop.dice_lines(reg, [SAME_TIER, HER_CRIT])
    # was 「[归乡后生 敏捷 对 莲妹 敏捷 44/55 成功(抢在熄屏前拍下井水): 59 ≤ 60] → 失败」, then (10-25 fix/dice-contest)
    # 「… → 成功,对抗输给莲妹(44/55 成功;同档,余量 11 > 1) → 失败」 — read as it streams, 成功 came before 失败
    assert lines[0] == ("[归乡后生 敏捷(抢在熄屏前拍下井水): 59 ≤ 60] → 失败:你掷 59(目标 60)成功,莲妹掷 44(目标 55)也成功;"
                        "同样成功时比谁赢得多,莲妹多 11,你多 1 → 莲妹赢")
    assert lines[1] == "[归乡后生 敏捷(把手机举到井水上方拍照): 82 > 60] → 失败:你掷 82(目标 60)失败,莲妹掷 2(目标 55)大成功;档位高的赢,大成功压过失败 → 莲妹赢"
    won = {**SAME_TIER, "result": "success", "a": _side("player", 48, 60, "success"), "b": _side("si-lian", 65, 55, "fail")}
    tie = {**SAME_TIER, "a": _side("player", 50, 60, "success"), "b": _side("si-lian", 45, 55, "success")}
    lost_both = {**SAME_TIER, "a": _side("player", 70, 60, "fail"), "b": _side("si-lian", 80, 55, "fail")}
    assert plan_loop.dice_lines(reg, [won])[0].endswith("→ 成功:你掷 48(目标 60)成功,莲妹掷 65(目标 55)失败;档位高的赢,成功压过失败 → 你赢")
    assert plan_loop.dice_lines(reg, [tie])[0].endswith("莲妹掷 45(目标 55)也成功;同样成功、多出也一样时守方赢 → 莲妹赢")
    assert plan_loop.dice_lines(reg, [lost_both])[0].endswith("莲妹掷 80(目标 55)也失败;两边都没成功时守方赢 → 莲妹赢")
    # still the skeleton the TUI boxes, coloured by who won (the first word), not by his own 59 ≤ 60
    for ln, tier in ((lines[0], "fail"), (plan_loop.dice_lines(reg, [won])[0], "success")):
        m = ConversationView._DICE_LINE_RE.match(ln)
        assert m and ConversationView._dice_tier(None, m.group("outcome"), m.group("expr"), m.group("target"), False) == tier
    # what the host / the characters / the narrator read is not the player's line: unchanged
    text = plan_loop.check_line(reg, SAME_TIER)
    assert "→ 对抗输给莲妹(同档,余量 11 > 1) → 失败(抢在熄屏前拍下井水)" in text and "44 ≤ 55 成功" in text
    # a d20 contest targets her total; the plain words say whose total that is and the rule
    d20 = {"a": {"who": "player", "roll": 5, "mod": 3, "total": 8}, "b": {"who": "si-lian", "roll": 11, "mod": 2, "total": 13},
           "attr": "DEX", "why": "翻页时谁先动", "result": "fail"}
    assert plan_loop.dice_lines(reg, [d20]) == ["[归乡后生 DEX 对 莲妹(翻页时谁先动): 5+3=8 < 13] → 失败:你掷出 8,莲妹掷出 13;发起方不低于对方就赢 → 莲妹赢"]
    # a plain check: as it was
    plain = {"system": "pct", "attr": "敏捷", "why": "抄名字", "result": "success", "a": _side("player", 51, 60, "success")}
    assert plan_loop.dice_lines(reg, [plain]) == ["[归乡后生 敏捷(抄名字): 51 ≤ 60] → 成功"]


def test_a_contest_dice_event_never_says_his_own_success_beside_a_loss():
    if plan_loop is None:
        pytest.skip("private layer absent")
    from neonrp.core import beat_display as bd

    (ev,) = plan_loop.dice_events([{**SAME_TIER, "line": "x"}], _contest_reg())
    assert ev["passed"] is False and ev["level"] == "fail" and ev["own_level"] == "success" and ev["name"] == "归乡后生"
    assert ev["contest"] == {"who": "si-lian", "name": "莲妹", "label": "敏捷", "total": 44, "vs": 55, "level": "success",
                             "why": "同档,余量 11 > 1", "by": "margin"}
    assert bd.outcome_level(ev) == "fail"
    assert bd._dice_line(ev, "zh") == ("[抢在熄屏前拍下井水: 59 ≤ 60] → 失败:你掷 59(目标 60)成功,莲妹掷 44(目标 55)也成功;"
                                       "同样成功时比谁赢得多,莲妹多 11,你多 1 → 莲妹赢")
    (crit,) = plan_loop.dice_events([HER_CRIT], _contest_reg())
    assert crit["level"] == "fail" and "own_level" not in crit and crit["contest"]["level"] == "crit" and crit["contest"]["by"] == "tier"
    assert bd._dice_line(crit, "zh").endswith("→ 失败:你掷 82(目标 60)失败,莲妹掷 2(目标 55)大成功;档位高的赢,大成功压过失败 → 莲妹赢")
    # each rule the pack decided by rides the event (packs/pct/rules.py better: tier / margin / tie / both_fail; d20 total)
    by = lambda a, b, res: plan_loop.dice_events([{**SAME_TIER, "result": res, "a": a, "b": b}], _contest_reg())[0]["contest"]["by"]  # noqa: E731
    assert by(_side("player", 50, 60, "success"), _side("si-lian", 45, 55, "success"), "fail") == "tie"
    assert by(_side("player", 70, 60, "fail"), _side("si-lian", 80, 55, "fail"), "fail") == "both_fail"
    d20 = {"a": {"who": "player", "roll": 5, "mod": 3, "total": 8}, "b": {"who": "si-lian", "roll": 11, "mod": 2, "total": 13}, "attr": "DEX", "result": "fail"}
    assert plan_loop.dice_events([d20], _contest_reg())[0]["contest"]["by"] == "total"


def test_a_check_without_a_reason_marker_drops_its_own_parts_from_the_reason():
    if plan_loop is None:
        pytest.skip("private layer absent")
    who = {"夜见": "si-yomi01"}
    # 霓虹 10-25: was 「INT(夜见 INT normal 辨认最后一页的笔迹与墨迹)」
    c = plan_loop.parse_check("夜见 INT normal 辨认最后一页的笔迹与墨迹", who)
    assert c["who"] == "si-yomi01" and c["attr"] == "INT" and c["dc"] == "normal" and c["why"] == "辨认最后一页的笔迹与墨迹"
    assert plan_loop.parse_check("检定: 夜见 INT normal 12", who)["why"] == ""  # nothing left: no reason
    assert plan_loop.parse_check("夜见 INT normal 为了看清墨迹", who)["why"] == "看清墨迹"
    from types import SimpleNamespace as N

    reg = N(root=None, entries={"si-yomi01": N(name="夜见")})
    r = {"a": {"who": "si-yomi01", "roll": 9, "mod": 1, "total": 10}, "dc": 12, "attr": "INT", "why": "", "result": "fail"}
    assert plan_loop.dice_lines(reg, [r]) == ["[夜见 INT: 9+1=10 < 12] → 失败"]
    assert not plan_loop.check_line(reg, r).endswith(")")


def test_a_level_against_passed_gives_way_to_passed():
    """Public: whatever a pack wrote, the tier shown never contradicts who won."""
    from neonrp.core import beat_display as bd

    assert bd.outcome_level({"level": "success", "passed": False, "vs": 60, "total": 59, "under": True}) == "fail"
    assert bd.outcome_level({"level": "crit", "passed": False, "vs": 60}) == "fail"
    assert bd.outcome_level({"level": "fumble", "passed": True, "vs": 60}) == "success"
    assert bd.outcome_level({"level": "crit", "passed": True, "vs": 60}) == "critical"
    assert bd.outcome_level({"level": "crit"}) == "critical"  # no passed: the level as it is


# ── E: the contest's own line and card (niko 10-25): who won first, in plain words, both sides on the web card ──

# the dice event a lost percentile contest lands with (the private plan layer's dice_events: his side on top, hers in contest)
LOST_EV = {"request": "dice 1d100", "who": "player", "name": "归乡后生", "label": "敏捷", "reason": "抢在熄屏前拍下井水", "total": 59, "vs": 60,
           "under": True, "passed": False, "level": "fail", "own_level": "success",
           "contest": {"who": "si-lian", "name": "莲妹", "label": "敏捷", "total": 44, "vs": 55, "level": "success", "by": "margin"}}
WON_EV = {**LOST_EV, "total": 32, "passed": True, "level": "success", "own_level": None,
          "contest": {**LOST_EV["contest"], "total": 30}}


def test_a_contest_line_reads_who_won_first_in_each_language():
    from neonrp.core import beat_display as bd

    won = {k: v for k, v in WON_EV.items() if v is not None}
    want = {
        "zh": ("[抢在熄屏前拍下井水: 59 ≤ 60] → 失败:你掷 59(目标 60)成功,莲妹掷 44(目标 55)也成功;同样成功时比谁赢得多,莲妹多 11,你多 1 → 莲妹赢",
               "[抢在熄屏前拍下井水: 32 ≤ 60] → 成功:你掷 32(目标 60)成功,莲妹掷 30(目标 55)也成功;同样成功时比谁赢得多,你多 28,莲妹多 25 → 你赢"),
        "en": ("[抢在熄屏前拍下井水: 59 ≤ 60] → failure: you rolled 59 (target 60), success; 莲妹 rolled 44 (target 55), success too; "
               "both succeeded, so whoever rolled further under their target wins: 莲妹 by 11, you by 1 → 莲妹 wins",
               "[抢在熄屏前拍下井水: 32 ≤ 60] → success: you rolled 32 (target 60), success; 莲妹 rolled 30 (target 55), success too; "
               "both succeeded, so whoever rolled further under their target wins: you by 28, 莲妹 by 25 → you win"),
        "ja": ("[抢在熄屏前拍下井水: 59 ≤ 60] → 失敗:あなたは 59(目標 60)で成功、莲妹は 44(目標 55)で同じく成功。"
               "どちらも成功なら目標との差が大きいほうが勝ち、莲妹は 11、あなたは 1 → 莲妹の勝ち",
               "[抢在熄屏前拍下井水: 32 ≤ 60] → 成功:あなたは 32(目標 60)で成功、莲妹は 30(目標 55)で同じく成功。"
               "どちらも成功なら目標との差が大きいほうが勝ち、あなたは 28、莲妹は 25 → あなたの勝ち"),
        "ko": ("[抢在熄屏前拍下井水: 59 ≤ 60] → 실패: 나 59(목표 60) 성공, 莲妹 44(목표 55) 역시 성공; 둘 다 성공하면 목표와의 차이가 큰 쪽이 이김, 莲妹 11, 나 1 → 莲妹 승리",
               "[抢在熄屏前拍下井水: 32 ≤ 60] → 성공: 나 32(목표 60) 성공, 莲妹 30(목표 55) 역시 성공; 둘 다 성공하면 목표와의 차이가 큰 쪽이 이김, 나 28, 莲妹 25 → 내 승리"),
    }
    for lang, (lost, win) in want.items():
        assert bd._dice_line(LOST_EV, lang) == lost, lang
        assert bd._dice_line(won, lang) == win, lang
    # the other rules, and an event from before ``by`` (the rule read off the two tiers and margins)
    crit = {**LOST_EV, "total": 82, "own_level": None, "contest": {**LOST_EV["contest"], "total": 2, "level": "crit", "by": "tier"}}
    assert bd._dice_line(crit, "en").endswith("the better result wins, critical beats failure → 莲妹 wins")
    old = {**LOST_EV, "contest": {k: v for k, v in LOST_EV["contest"].items() if k != "by"}}
    assert bd._dice_line(old, "zh") == bd._dice_line(LOST_EV, "zh")
    # an NPC rolling against an NPC: names, no 「你」
    npc = {**LOST_EV, "who": "si-yomi", "name": "夜见"}
    assert bd._dice_line(npc, "zh").endswith("夜见掷 59(目标 60)成功,莲妹掷 44(目标 55)也成功;同样成功时比谁赢得多,莲妹多 11,夜见多 1 → 莲妹赢")


def test_a_plain_check_line_is_as_it_was():
    from neonrp.core import beat_display as bd

    ev = {"request": "dice 1d100", "who": "player", "reason": "找暗门", "total": 37, "vs": 60, "under": True, "passed": True, "level": "success"}
    assert bd._dice_line(ev, "zh") == "[找暗门: 37 ≤ 60] → 成功"
    assert bd._dice_line({**ev, "total": 2, "level": "crit"}, "en") == "[找暗门: 2 ≤ 60] → critical"
    assert bd._dice_line({**ev, "total": 72, "passed": False, "level": "fail"}, "ja") == "[找暗门: 72 > 60] → 失敗"
    d20 = {"request": "dice 1d20+2", "rolls": [11], "total": 13, "vs": 12, "passed": True, "reason": "撬锁"}
    assert bd._dice_line(d20, "ko") == "[撬锁: 11+2=13 >= 12] → 성공"


def test_the_tui_colours_a_contest_row_by_who_won_new_line_or_old():
    from neonrp.core import beat_display as bd
    from neonrp.tui.app import ConversationView as CV

    def tier(line: str) -> str | None:
        m = CV._DICE_LINE_RE.match(line)
        assert m, line
        return CV._dice_tier(None, m.group("outcome"), m.group("expr"), m.group("target"), False)
    for lang in ("zh", "en", "ja", "ko"):
        assert tier(bd._dice_line(LOST_EV, lang)) == "fail", lang  # 59 ≤ 60 and his own success: the row is the loss
    # a line saved before (who won last) still reads the same
    assert tier("[抢在熄屏前拍下井水: 59 ≤ 60] → 成功,对抗输给莲妹(44/55 成功;同档,余量 11 > 1) → 失败") == "fail"
    assert tier("[x: 59 ≤ 60] → success, lost the contest to Lian (44/55 success; same tier and margin: the defender wins) → failure") == "fail"
    assert tier("[找暗门: 37 ≤ 60] → 成功") == "success"


def test_the_web_dice_card_draws_both_sides_of_a_contest():
    """worldlines/ui/player director.js ``dieOf``: a contest event → both sides (name, roll, target, own tier), who won,
    which rule; the roll's own tier / result = who won, so the die lands on the final verdict."""
    import json
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if not node:
        pytest.skip("no node")
    src = Path(__file__).resolve().parents[1] / "worldlines" / "ui" / "player" / "src"
    if not (src / "director.js").is_file():
        pytest.skip("the standard front end is not in this repo")
    js = """
const fs = require('fs'), vm = require('vm'), [src, lang, evs] = process.argv.slice(1);
const ctx = { location: { search: '?lang=' + lang }, localStorage: { getItem: () => null }, navigator: { language: lang }, document: { documentElement: {} }, URLSearchParams };
vm.createContext(ctx);
for (const f of ['i18n.js', 'director.js']) vm.runInContext(fs.readFileSync(src + '/' + f, 'utf-8') + '\\n;this.D = typeof DIRECTOR !== "undefined" ? DIRECTOR : this.D;', ctx);
console.log(JSON.stringify(JSON.parse(evs).map(e => ctx.D.dieOf(e))));
"""
    won = {k: v for k, v in WON_EV.items() if v is not None}
    plain = {"request": "dice 1d100", "who": "player", "label": "查资料", "total": 51, "vs": 60, "under": True, "passed": True, "level": "success"}

    def run(lang: str) -> list[dict]:
        out = subprocess.run([node, "-e", js, str(src), lang, json.dumps([LOST_EV, won, plain], ensure_ascii=False)],
                             capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        return json.loads(out.stdout)
    lost, win, one = run("zh")
    assert (lost["tier"], lost["res"], lost["ok"]) == ("fail", "失败", False)
    assert lost["vs"]["me"] == {"name": "你", "you": True, "total": 59, "dc": 60, "tier": "success", "res": "成功"}
    assert lost["vs"]["them"] == {"name": "莲妹", "you": False, "total": 44, "dc": 55, "tier": "success", "res": "成功"}
    assert lost["vs"]["winner"] == "莲妹赢" and lost["vs"]["why"] == "同样成功时比谁赢得多,莲妹多 11,你多 1"
    assert (win["tier"], win["vs"]["winner"]) == ("success", "你赢")
    assert one["vs"] is None and one["tier"] == "success"  # a plain check: no second die
    assert run("en")[0]["vs"]["why"] == "Both succeeded, so whoever rolled further under their target wins: 莲妹 by 11, you by 1"
    assert [d["vs"]["winner"] for d in run("ja")[:2]] == ["莲妹の勝ち", "あなたの勝ち"]
    assert [d["vs"]["winner"] for d in run("ko")[:2]] == ["莲妹 승리", "내 승리"]
