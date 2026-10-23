"""Effects as one free rule line:
the engine reads only the countdown (resolves; game time = the rpg layer) and the per-resolve change from the line,
the rest stays text; check modifiers are written by the host into the checks it agrees."""
from __future__ import annotations

import json

import pytest
from test_engine_v3 import _install

from neonrp.core import effect_rules as er
from neonrp.core import effects, sdk, turn_v3
from neonrp.core.registry import load_registry


@pytest.mark.parametrize("line, want", [
    ("持续 3 次结算 · 检定 -2,只作用于 DEX/STR · 走路吃痛", {"turns": 3, "check": -2}),  # 10-14: the number is a mechanism
    ("持续 3 次结算 · 每次结算 player.hp -1 · 解毒草立解", {"turns": 3, "each": "player.hp:-1"}),
    ("持续 12 小时 · 每次结算 player.hp -1", {"hours": 12.0, "each": "player.hp:-1"}),
    ("持续 2 天", {"hours": 48.0}),
    ("lasts 2 turns · each resolve player.hp -1", {"turns": 2, "each": "player.hp:-1"}),
    ("3ターン続く · 毎回 player.hp -1", {"turns": 3, "each": "player.hp:-1"}),
    ("6시간 지속 · 매번 player.hp -1", {"hours": 6.0, "each": "player.hp:-1"}),
    ("每逢阴天发作,隐隐作痛", {}),  # vague: no mechanism, stays text (「一带而过也行」)
])
def test_a_rule_line_yields_only_the_mechanisms_it_states(line, want):
    assert er.parse_rule(line) == want


def test_each_is_normalised_whatever_was_written():
    assert [er.normalize_each(x) for x in ("无", "0", "none", "なし", "player.hp+2", "player.hp -1", "player.hp: -1", "note=x")] == \
        ["", "", "", "", "player.hp:+2", "player.hp:-1", "player.hp:-1", ""]
    assert effects.parse_each("player.hp -1") == [("player.hp", -1)]


def _world(tmp_path):
    root = _install(tmp_path)
    reg = load_registry(root)
    if "status" not in effects.effect_classes(reg) or "player.hp" not in reg.variables:
        pytest.skip("world without the rpg status class")
    return root, reg


def test_a_status_named_from_the_table_is_completed_by_its_line(tmp_path):
    root, reg = _world(tmp_path)
    tab = er.table(root)
    assert tab, "the rpg pack ships a default table"
    name = next(n for n, r in tab.items() if er.parse_rule(r).get("each") and er.parse_rule(r).get("turns"))
    (op,) = turn_v3.parse_transition(f"<files>\nnew status {name}\n</files>")
    sdk.apply(root, [op], reg, turn=1)
    reg = load_registry(root)
    (st,) = [e for e in effects.instances(reg) if e.name == name]
    mech = er.parse_rule(tab[name])
    assert int(st.props["turns"]) == mech["turns"] and st.props["each"] == mech["each"] and st.props["rule"] == tab[name]


def test_a_new_status_line_is_read_cleaned_and_remembered(tmp_path):
    """The model writes a status the table lacks, with its own line (open rule): the mechanisms are read from it, a
    stray modifier in the name and a broken each are cleaned, and the line joins the world's table for next time."""
    root, reg = _world(tmp_path)
    (op,) = turn_v3.parse_transition("<files>\nnew status 腐鱼反胃 -1 turns=48 each=无 note=持续 2 次结算 · 每次结算 player.hp -1 · 吐干净可解\n</files>")
    sdk.apply(root, [op], reg, turn=1)
    reg = load_registry(root)
    (st,) = [e for e in effects.instances(reg) if e.name.startswith("腐鱼反胃")]
    assert st.name == "腐鱼反胃" and st.props["each"] == "player.hp:-1"
    assert int(st.props["turns"]) == 48, "a usable number the model gave is kept"
    assert "腐鱼反胃" in er.table(root), "remembered in the world's rules/status.md"


def test_a_clock_status_runs_out_on_the_world_clock(tmp_path):
    """rpg layer (「clock 是 rpg 里的内容」): 「持续 N 小时」 → until on the clock; one long resolve wears it off."""
    root, reg = _world(tmp_path)
    if "time.clock" not in reg.variables or "time.day" not in reg.variables:
        pytest.skip("world without a clock")
    sdk.apply(root, [{"op": "set", "var": "time.clock", "value": "09:00"}], reg, turn=1)  # forward only (10-14: the clock never goes back)
    reg = load_registry(root)
    (op,) = turn_v3.parse_transition("<files>\nnew status 宿醉 note=持续 6 小时 · 头疼\n</files>")
    sdk.apply(root, [op], reg, turn=2)
    reg = load_registry(root)
    (st,) = [e for e in effects.instances(reg) if e.name == "宿醉"]
    assert int(st.props["until"]) == 15 * 60 and st.props["until_text"] == "D1 15:00"
    sdk.apply(root, [{"op": "set", "var": "time.clock", "value": "10:00"}], reg, turn=3)
    assert [e for e in effects.instances(load_registry(root)) if e.name == "宿醉"], "not yet"
    reg = load_registry(root)
    sdk.apply(root, [{"op": "set", "var": "time.clock", "value": "15:30"}], reg, turn=4)
    assert not [e for e in effects.instances(load_registry(root)) if e.name == "宿醉"], "slept past it: gone"


def test_the_host_names_the_effect_and_the_engine_adds_its_number(tmp_path):
    """「这个是引擎加」: the host still judges which effects apply to this roll by naming them; the number is
    the effect's rule line's, never the one the host wrote; a check that names none takes every effect with a modifier."""
    from neonrp.core import plan_loop
    from neonrp.packs.rpg import referee

    root, reg = _world(tmp_path)
    c = plan_loop.parse_check("玩家 DEX normal -9(扭伤) 为了翻过矮墙", {})
    assert c["adj"] == -9 and c["adj_why"] == "扭伤" and c["why"] == "翻过矮墙" and c["dc"] == "normal"
    sdk.apply(root, [{"op": "new", "class": "status", "name": "旧伤", "props": {"check": "-5"}},
                     {"op": "new", "class": "status", "name": "扭伤", "props": {"rule": "持续 3 次结算 · 检定 -2,只作用于 DEX/STR"}}], reg, turn=1)
    reg = load_registry(root)
    named = referee.roll_check(root, reg, c, seed="s")
    plain = referee.roll_check(root, reg, {k: v for k, v in c.items() if k not in ("adj", "adj_why")}, seed="s")
    assert named["a"]["effects"] == ["扭伤-2"] and named["host_adj"] == -9, "named: only 扭伤, at its own -2"
    assert sorted(plain["a"]["effects"]) == ["扭伤-2", "旧伤-5"] and named["a"]["mod"] - plain["a"]["mod"] == 5
    # the grammar the host is given now: 「状态:名字」, no number
    c2 = plan_loop.parse_check("玩家 DEX normal 状态:扭伤 为了翻过矮墙", {})
    assert c2["adj_why"] == "扭伤" and "adj" not in c2 and c2["why"] == "翻过矮墙"
    assert referee.roll_check(root, reg, c2, seed="s")["a"]["effects"] == ["扭伤-2"]


def test_the_world_context_carries_the_status_table(tmp_path):
    root, reg = _world(tmp_path)
    txt = sdk.render_pack(sdk.pack(root, registry=reg))
    first = next(iter(er.table(root)))
    assert f"- {first}:" in txt
    assert "检定 ?" not in txt and "剩 ? " not in txt


def test_status_lines_in_the_pack_tables_all_parse():
    from pathlib import Path

    for f in Path("src/neonrp/packs/rpg/data").glob("status.*.md"):
        lines = er._read_lines(f)
        assert len(lines) >= 10, f
        # hunger (until a meal) and the down rule's own three (down / stabilized / dead, packs/rpg/downed.py) carry no countdown
        assert sum(1 for r in lines.values() if er.parse_rule(r)) >= len(lines) - 4, f"{f}: lines without a mechanism"
    assert json.loads(Path("src/neonrp/prompts/effect_rules.ko.json").read_text(encoding="utf-8"))["turns"]


def test_a_text_value_with_spaces_stays_in_its_field():
    """10-05: `note=持续 2 次结算 · …` broke at the first space and leaked into the status name."""
    (a,) = turn_v3.parse_transition("<files>\nnew status Sprain note=sprained ankle, walks with a limp\n</files>")
    assert a["name"] == "Sprain" and a["props"]["note"] == "sprained ankle, walks with a limp"
    (b,) = turn_v3.parse_transition("<files>\nnew status 恶心 turns=3 each=player.hp -1 note=吐了 一地\n</files>")
    assert b["name"] == "恶心" and b["props"] == {"turns": "3", "each": "player.hp:-1", "note": "吐了 一地"}


def test_a_reason_written_before_its_marker_is_read(tmp_path):
    """10-14: Japanese and Korean put the reason before ため / 위해 — the check keeps it, not the whole line."""
    from neonrp.core import plan_loop

    assert plan_loop.parse_check("判定: プレイヤー DEX normal 状態:捻挫 塀を越えるため", {})["why"] == "塀を越える"
    assert plan_loop.parse_check("プレイヤー 発見 隠し扉を見つけるために", {})["why"] == "隠し扉を見つける"
    assert plan_loop.parse_check("판정: 플레이어 DEX normal 상태: 염좌 담을 넘기 위해", {})["why"] == "담을 넘기"
    assert plan_loop.parse_check("玩家 察觉 为了找暗门", {})["why"] == "找暗门"
