"""The rule panel and the check rulebook: a check reads the roller's
numbers down one chain — own sheet → this run's fills → the world's role panel → the rulebook's baseline — never a
silent +0, and a value completed once is kept (the character state), so the same character reads the same number."""
from __future__ import annotations

import json
from pathlib import Path

from neonrp import template as TP
from neonrp.core.registry import load_registry
from neonrp.packs.pct import rules as PR
from neonrp.packs.rpg import character_state as cs
from neonrp.packs.rpg import panel, referee
from _paths import PRODUCT_TEMPLATES


def _run(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    TP.build(PRODUCT_TEMPLATES / f"{name}.template", root)
    return root


def _world_rules(root: Path, **kv) -> None:
    p = root / "game" / "rules" / "rules.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    have = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    p.write_text(json.dumps({**have, **kv}, ensure_ascii=False), encoding="utf-8")


def test_an_npc_without_a_sheet_reads_the_baseline_and_keeps_it(tmp_path):
    """stoneford: no NPC has attributes — a contest against one used to be 1d20+0 with nothing said."""
    root = _run(tmp_path, "stoneford-elena")
    _world_rules(root, role_panels={})  # a world with no role panels: straight to the baseline
    reg = load_registry(root)
    assert not reg.entries["NPC002"].props.get("attributes")
    v, src = panel.attr(root, reg, "NPC002", "cha")
    assert (v, src) == (5, "baseline")
    st = cs.read(root, "NPC002")["panel"]
    assert st["attributes"]["cha"] == 5 and st["source"]["attributes.cha"] == "baseline", "written to the run's state"
    assert not (root / "game" / "towns" / "T001" / "npcs.json").read_text(encoding="utf-8").count('"attributes"'), "the author's record stays as written"
    assert panel.attr(root, load_registry(root), "NPC002", "cha") == (5, "baseline"), "read back: same number, same source"


def test_the_worlds_role_panel_comes_before_the_baseline(tmp_path):
    root = _run(tmp_path, "stoneford-elena")
    _world_rules(root, role_panels={"shopkeeper": {"attributes": {"cha": 8, "int": 7}}})
    reg = load_registry(root)
    assert panel.attr(root, reg, "NPC002", "cha") == (8, "role:shopkeeper")
    assert panel.attr(root, reg, "NPC002", "str") == (5, "baseline"), "what the role panel does not give, the baseline does"
    assert panel.attr(root, reg, "player", "dex")[1] == "sheet"


def test_a_check_names_its_attribute_by_what_it_does_not_by_its_reason(tmp_path):
    root = _run(tmp_path, "stoneford-elena")
    assert panel.action_attr(root, "玩家 砍价")[0] == "cha"
    assert panel.action_attr(root, panel.head({"text": "玩家 砍价 为了搜查他的钱袋", "why": "搜查他的钱袋"}))[0] == "cha"
    assert panel.action_attr(root, "玩家 冥想片刻") == ("int", "fallback_attr"), "nothing matched: the rulebook's fallback, still a roll"


def test_a_d20_contest_with_a_sheetless_npc_says_where_its_number_came_from(tmp_path):
    root = _run(tmp_path, "stoneford-elena")
    reg = load_registry(root)
    r = referee.roll_check(root, reg, {"text": "玩家 vs 老苇 砍价", "who": "player", "vs": "NPC002", "why": "压价"}, seed="s")
    assert r["attr"] == "CHA" and r["attr_how"] == "action:persuade"
    assert r["a"]["source"] == "sheet" and r["b"]["source"] == "role:shopkeeper" and r["b"]["value"] == 7, "stoneford's own role panel"


def test_a_dc_number_reads_as_the_nearest_tier_unless_the_world_keeps_numbers(tmp_path):
    root = _run(tmp_path, "stoneford-elena")
    reg = load_registry(root)
    r = referee.roll_check(root, reg, {"text": "玩家 DEX 13 翻墙", "who": "player", "attr": "DEX", "dc": "13", "why": "翻墙"}, seed="s")
    assert r["dc"] == 12 and r["tier"] == "normal<-13"
    _world_rules(root, dc_numbers="keep")
    r = referee.roll_check(root, load_registry(root), {"text": "玩家 DEX 13 翻墙", "who": "player", "attr": "DEX", "dc": "13", "why": "翻墙"}, seed="s")
    assert r["dc"] == 13 and r["tier"] == "number"


def test_a_souls_sheet_is_her_own_file(tmp_path):
    root = _run(tmp_path, "pct-house")
    reg = load_registry(root)
    soul = reg.of_class("soul")[0]
    sheet = json.loads((root / soul.props["sheet"]).read_text(encoding="utf-8"))
    key = next(iter(sheet["attributes"]))
    assert panel.attr(root, reg, soul.id, key) == (int(sheet["attributes"][key]), "sheet")


def test_pct_skills_come_off_the_sheet_the_table_or_the_fallback(tmp_path):
    root = _run(tmp_path, "pct-house")
    reg = load_registry(root)
    own = panel.skill(root, reg, "player", "玩家 说服")
    assert own["label"] == "说服" and own["source"] == "sheet"
    npc = next(e.id for e in reg.of_class("soul") if e.name == "奥斯温")  # the butler is a soul (10-14)
    base = panel.skill(root, reg, npc, "伪装")  # a table skill not on his sheet
    assert base["key"] == "disguise" and base["label"] == "伪装" and base["source"] in ("baseline", "base(sheet)") and base["value"] >= 1
    assert cs.read(root, npc)["panel"]["skills"]["disguise"] == base["value"], "the table's base, kept for this run"
    odd = panel.skill(root, reg, "player", "玩家 观星术")
    assert odd["via"] == "fallback_attr:int" and odd["value"] == panel.attr(root, reg, "player", "int")[0] * 5


def test_a_pct_contest_rolls_the_other_side_on_the_skill_that_opposes_it(tmp_path):
    root = _run(tmp_path, "pct-house")
    reg = load_registry(root)
    npc = next(e.id for e in reg.of_class("soul") if e.name == "奥斯温")  # the butler is a soul (10-14)
    r = PR.roll_check(root, reg, {"text": "玩家 vs 管家 说服", "who": "player", "vs": npc, "why": "问出锁法"}, seed="s")
    assert r["a"]["label"] == "说服" and r["b"]["label"] == "洞察", "BRP: Persuade is resisted by Insight (洞察)"
