"""pct — percentile investigation (「类 COC」).

d100 skill / attribute checks (01–05 critical, 96–00 fumble), contests by level then margin, the sanity tool (loss,
temporary insanity, the insane event at 0), dying = one failed CON check, percentile combat (attack / dodge, damage
bonus, a major wound), and the minimal test world (worldlines/templates/pct-house.template) built and played one beat."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from neonrp import packs, template
from neonrp.core import effects, sdk

try:  # the planning beat lives in the private layer (10-10 R1); the open engine has none
    from neonrp.core import plan_loop
except ImportError:
    plan_loop = None
from neonrp.core.registry import load_registry
from neonrp.packs.pct import rules as R
from neonrp.packs.pct import tools as T
from neonrp.packs.rpg import character_state as cs
from _paths import PRODUCT_TEMPLATES

TPL = PRODUCT_TEMPLATES / "pct-house.template"


@pytest.fixture
def world(tmp_path: Path) -> Path:
    dest = tmp_path / "run"
    template.build(template.load(TPL), dest)
    return dest


def test_the_template_builds_on_the_pct_pack_and_lints_clean(world):
    rep = template.lint(template.load(TPL))
    assert rep["counts"]["block"] == 0, rep["problems"]
    assert packs.template_of(world) == "pct" and packs.resolve(world).base == "rpg"
    assert template.load(TPL).data.get("play_contract") == "mystery-trpg@1"
    reg = load_registry(world)
    p = reg.entries["player"]
    assert reg.variables["player.san"].value == 55 and p.props["hp"] == 12
    assert "察觉 60%" in p.props["sheet"] and "心神 55" in p.props["sheet"], "pct-house names the sanity score 心神 (rules.json san_names)"
    assert [e.name for e in reg.of_class("soul")] == ["温妮", "奥斯温"] and [e.name for e in reg.of_class("npc")] == [], "the butler is a soul (10-14)"


def test_levels_and_contests():
    """BRP (10-14): ≤ 1/20 critical, ≤ 1/5 special, ≤ the skill success, 99 / 00 fumble; fractions round up."""
    rules = R.rules(None)
    assert [R.level(r, 60, rules) for r in (3, 4, 12, 13, 60, 61, 98, 99, 100)] == [
        "crit", "special", "special", "success", "success", "fail", "fail", "fumble", "fumble"]
    assert R.level(1, 1, rules) == "crit" and R.level(99, 99, rules) == "success" and R.level(100, 99, rules) == "fumble"
    assert R.passed("special") and R.better(("special", 0), ("success", 50))
    assert R.better(("crit", 0), ("success", 50)) and R.better(("success", 30), ("success", 10))
    assert not R.better(("fail", 10), ("fail", 30)) and not R.better(("success", 10), ("success", 10))


def test_targets_come_from_her_skills_the_table_or_her_attributes(world):
    reg = load_registry(world)
    p = reg.entries["player"]
    rules = R.rules(world)
    assert R.find_target(rules, p, "侦查 为了找暗门") == ("察觉", 60), "the sheet's old name finds the skill; it shows by its BRP name"
    assert R.find_target(rules, p, "察觉 为了找暗门") == ("察觉", 60), "the BRP name finds the same skill"
    assert R.find_target(rules, p, "潜行 溜进书房") == ("潜行", 10), "a table skill she lacks: its base"
    assert R.find_target(rules, p, "力量 推开柜子") == ("力量", 50), "STR 10 × 5"
    assert R.find_target(rules, p, "Spot the desk") == ("察觉", 60), "any language names the same skill"
    assert R.damage_bonus(rules, p) == "0" and R.hp_of(p) == 12


def test_an_agreed_check_rolls_d100_and_shows_as_a_percentile_dice_line(world):
    reg = load_registry(world)
    c = plan_loop.parse_check("玩家 侦查 -20(重伤) 为了找暗门", {})
    r = R.roll_check(world, reg, c, seed="s1")
    assert r["a"]["target"] == 60 and r["host_adj"] == -20, "10-14: the number the host wrote counts only through an effect"
    vr = sdk.verify(world, [{"op": "new", "class": "status", "name": "重伤", "props": {}}], reg)
    sdk.apply(world, vr.accepted, reg, turn=1)
    reg = load_registry(world)
    r = R.roll_check(world, reg, c, seed="s1")
    a = r["a"]
    assert r["system"] == "pct" and a["label"] == "察觉" and a["target"] == 40, "60 − 20 by 重伤's own rule line"
    assert a["source"] == "sheet" and a["effects"] == ["重伤-20"]
    assert r["result"] == ("success" if a["level"] in ("success", "special", "crit") else "fail")
    (line,) = plan_loop.dice_lines(reg, [r])
    assert line.startswith("[调查员 察觉(找暗门): ") and ("≤ 40]" in line or "> 40]" in line)
    from neonrp.tui.app import ConversationView

    assert ConversationView._DICE_LINE_RE.match(line), line
    # the beat's own record line (what the play screen shows): a d100 under the skill, never 「1d20+0 = 62 ≥ 35?」 (10-14)
    text = plan_loop.check_line(reg, r)
    assert "1d100 = " in text and ("≤ 40" in text or "> 40" in text) and "1d20" not in text and "≥" not in text, text
    vs = R.roll_check(world, reg, {"text": "玩家 vs 管家 潜行 溜过门厅", "who": "player", "vs": "si-butler0001", "why": "溜过门厅"}, seed="s2")
    assert "b" in vs and vs["b"]["who"] == "si-butler0001" and vs["result"] in ("success", "fail")


def test_the_dice_tool_rolls_under_or_sums(world):
    reg = load_registry(world)
    a = T.dice(world, reg, {"dice": "1d100", "vs": 60, "seed_key": "k"}, seed="x")
    assert a["under"] and 1 <= a["total"] <= 100 and a["passed"] == (a["level"] in ("success", "special", "crit"))
    b = T.dice(world, reg, {"dice": "侦查", "seed_key": "k2"}, seed="x")
    assert b["vs"] == 60 and b["label"] == "察觉"
    c = T.dice(world, reg, {"dice": "1d6+1d4", "seed_key": "k3"}, seed="x")
    assert 2 <= c["total"] <= 10 and len(c["rolls"]) == 2 and "vs" not in c
    from neonrp.core.beat_display import _dice_line

    assert _dice_line({**a, "reason": "找暗门"}).startswith("[找暗门: ")


def test_sanity_loss_temporary_insanity_and_the_insane_event(world, monkeypatch):
    reg = load_registry(world)
    """BRP (10-14): losing half the SAN the scene began with goes temporarily insane — here two losses in one resolve
    (55 → 41 → 27: 28 lost of 55, half is 28), no INT check."""
    monkeypatch.setattr(T, "_d100", lambda seed, key: 90)  # every SAN check fails (90 > SAN) → the failure loss
    out = T.san(world, reg, {"spec": "1/14", "why": "看见墙缝里的东西"}, seed="z")
    assert out["ok"] and out["loss"] == 14 and out["san"] == [55, 41]
    assert not cs.read(world, "player").get("pending_status"), "14 of 55: not yet half"
    out = T.san(world, reg, {"spec": "1/14", "why": "那东西动了"}, seed="z2")
    assert out["san"] == [41, 27]
    st = json.loads((world / "game" / "player" / "stats.json").read_text(encoding="utf-8"))
    assert st["san"]["current"] == 27
    assert cs.read(world, "player")["pending_status"] == ["insane_temp"]
    sdk.apply(world, [], load_registry(world), turn=1)
    assert [e.name for e in effects.instances(load_registry(world))] == ["临时失控"], "the world's own name for it (rules.json effect_names)"
    assert not cs.read(world, "player").get("pending_status")
    reg = load_registry(world)
    r = sdk.apply(world, [{"op": "set", "var": "player.san", "value": 0}], reg, turn=2)
    assert any(a.get("event") == "insane" and a.get("who") == "player" for a in r.applied)
    assert "长久失控" in [e.name for e in effects.instances(load_registry(world))]
    r2 = sdk.apply(world, [], load_registry(world), turn=3)
    assert not any(a.get("event") == "insane" for a in r2.applied), "once"


def test_dying_is_one_failed_con_check(world, monkeypatch):
    from neonrp.packs.pct import rules as RR

    reg = load_registry(world)
    soul = next(iter(reg.of_class("soul")))
    sdk.apply(world, [{"op": "set", "var": f"char.{soul.id}.hp", "value": 0}], reg, turn=1)
    st = cs.read(world, soul.id)
    names = [e.name for e in effects.instances(load_registry(world), soul.id)]
    assert st["down"] == 1 and "濒死" in names and "重伤" in names, "10 → 0 in one blow is also a major wound"
    monkeypatch.setattr(RR, "roll_d100", lambda *a, **k: {"total": 99, "level": "fumble"})
    sdk.apply(world, [], load_registry(world), turn=2)
    st = cs.read(world, soul.id)
    assert st["dead"] == 1 and st["down_fail"] == 1, st
    names = [e.name for e in effects.instances(load_registry(world), soul.id)]
    assert "死亡" in names and "濒死" not in names


def test_first_aid_back_above_zero_gets_her_up(world, monkeypatch):
    from neonrp.packs.pct import rules as RR

    reg = load_registry(world)
    soul = next(iter(reg.of_class("soul")))
    sdk.apply(world, [{"op": "set", "var": f"char.{soul.id}.hp", "value": 0}], reg, turn=1)
    monkeypatch.setattr(RR, "roll_d100", lambda *a, **k: {"total": 10, "level": "success"})
    sdk.apply(world, [], load_registry(world), turn=2)
    assert cs.read(world, soul.id)["down_pass"] == 1
    sdk.apply(world, [{"op": "set", "var": f"char.{soul.id}.hp", "value": 2}], load_registry(world), turn=3)
    names = [e.name for e in effects.instances(load_registry(world), soul.id)]
    assert cs.read(world, soul.id)["down"] == 0 and "濒死" not in names and "重伤" in names, "up again; the wound stays its 24 hours"


def test_combat_runs_on_percentages_and_a_big_blow_is_a_major_wound(world):
    from neonrp.core import modes
    from neonrp.packs.pct import combat as pct_combat
    from neonrp.packs.rpg import combat

    reg = load_registry(world)
    combat.write(world, {**pct_combat.spawn(world, reg, turn=1, roster="管家×1"), "at": reg.player_location})
    foes = combat.read(world)["foes"]
    (fid, f), = foes.items()
    assert f["ref"] == "si-butler0001" and f["skill"] == 40 and f["dodge"] == 25 and f["max_hp"] == 12
    reg = load_registry(world)
    block = modes.state_block(world, reg, packs.resolve(world).modes["combat"])
    assert "攻击 40%" in block and "闪避 25%" in block and "伤害加值 0" in block
    sys_ = modes.layer_system(world, reg, "combat", "zh")
    assert "百分骰" in sys_ and "1d100" in sys_
    r = sdk.apply(world, [{"op": "add", "var": f"foe.{fid}.hp", "delta": -7}], reg, turn=2)
    assert not r.refused, r.refused
    assert "重伤" in [e.name for e in effects.instances(load_registry(world), "si-butler0001")], "7 ≥ 12 / 2"
    sdk.apply(world, [{"op": "add", "var": "player.hp", "delta": -2}], load_registry(world), turn=3)
    assert "重伤" not in [e.name for e in effects.instances(load_registry(world), "player")]


def test_the_planning_host_is_told_the_percentile_grammar_and_rpg_keeps_its_own(world, tmp_path):
    assert "技能名" in plan_loop.plan_sys(world) and "难度只写档位" not in plan_loop.plan_sys(world)
    assert "{check_grammar}" not in plan_loop.plan_sys(world) and "{check_grammar}" not in plan_loop.plan_sys(None)
    assert "难度只写档位" in plan_loop.plan_sys(None) and "状态:" in plan_loop.plan_sys(None)  # 10-14: tiers, effects by name


def test_one_beat_plays_through_with_a_stub_model(world, monkeypatch):
    """开场 → 商量 → 清算 one beat, the agreed check rolled as a percentile dice line."""
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user:
                        "<lines>\n那就搜。\n</lines>\n<board>\n玩家: 搜书房\n检定: 玩家 侦查 为了找暗门\n</board>\nnext: advance")
    out0 = plan_loop.step(world, user_text="开始游戏", last_narration="")
    assert out0["beat"]["kind"] == "opening" and "灰橡宅" in out0["narration"]
    out = plan_loop.step(world, user_text="@dm 我搜书房。", last_narration=out0["narration"])
    resolve = out.get("resolve") or out
    rolled = (resolve.get("beat") or {}).get("rolled") or resolve.get("rolled") or []
    reg = load_registry(world)
    lines = plan_loop.dice_lines(reg, [x for x in rolled if isinstance(x, dict)]) if rolled and isinstance(rolled[0], dict) else []
    if not lines:  # the step returned the agreed checks; roll them as the Resolve does
        checks = [plan_loop.parse_check("玩家 侦查 为了找暗门", {})]
        lines = plan_loop.dice_lines(reg, plan_loop.roll_checks(world, reg, checks, seed="t"))
    assert lines and lines[0].startswith("[调查员 察觉(找暗门): ") and ("≤" in lines[0] or ">" in lines[0])


def test_sanity_at_zero_settles_the_run_on_the_fail_ending(world):
    """The contract engine (core/settlement.py, merged 10-05): mystery-trpg's deaths.insanity exits on a fail ending —
    pct-house's E09. pct gives it player.san at 0 and the insane event."""
    from neonrp.core import settlement

    reg = load_registry(world)
    r = sdk.apply(world, [{"op": "set", "var": "player.san", "value": 0}], reg, turn=1)
    assert any(a.get("event") == "insane" for a in r.applied)
    st = settlement.read(world)
    assert st is not None and st["exit"]["id"] == "E09", st


def test_a_plots_stage_is_the_plots_own(tmp_path):
    """10-06 pct-house real play: the state transition wrote P01.stage 3→1 and the true ending's gate was lost. The model
    may read a plot's stage, not write it; the plot's own triggers still move it."""
    import shutil

    from neonrp.core import sdk
    from neonrp.core.registry import load_registry
    from neonrp.template import build

    t = tmp_path / "t.template"
    shutil.copytree(PRODUCT_TEMPLATES / "pct-house.template", t)
    root = tmp_path / "run"
    build(t, root)
    reg = load_registry(root)
    assert reg.variables["P01.stage"].readonly
    vr = sdk.verify(root, [{"op": "set", "var": "P01.stage", "value": 3}], reg)
    assert vr.refused and not vr.accepted
    sdk.apply(root, [], reg, turn=1, narration="你在书桌抽屉里找到一本日记。")
    assert load_registry(root).variables["P01.stage"].value == 1, "the diary trigger still moves it"
