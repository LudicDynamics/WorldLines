"""Character State + down / dead: souls and NPCs one system, the
run's state in game/states/<id>.json; hp only where the schema declares it; hp 0 → down (an event) → the down rule each
Resolve (DND by default, a simplified COC) → stable / dead; healed → up."""
from __future__ import annotations

import json

import pytest
from test_engine_v3 import _install

from neonrp.core import effects, sdk
from neonrp.core.registry import load_registry
from neonrp.packs.rpg import character_state as cs


def _soul(root):
    reg = load_registry(root)
    return reg, next(e for e in reg.of_class("soul"))


def _run(root, turns, start=2):
    for t in range(start, start + turns):
        sdk.apply(root, [], load_registry(root), turn=t)
        st = cs.read(root, _soul(root)[1].id)
        if st.get("dead") or st.get("stable") or not st.get("down"):
            return st, t
    return cs.read(root, _soul(root)[1].id), start + turns - 1


def test_npcs_and_souls_have_hp_because_the_schema_says_so(tmp_path):
    root = _install(tmp_path)
    reg = load_registry(root)
    npc = next(iter(reg.of_class("npc")))
    assert cs.has_hp(reg, "npc") and cs.has_hp(reg, "soul")
    assert npc.props["hp"] == npc.props["max_hp"] and f"char.{npc.id}.hp" in reg.variables
    assert f"char.{npc.id}.down" in reg.variables


def test_a_world_whose_schema_has_no_hp_judges_only_able_or_down(tmp_path, monkeypatch):
    """「如果没有 HP 的话按 0 / 1 处理」."""
    from neonrp.packs.rpg import pack as P

    root = _install(tmp_path)
    monkeypatch.setitem(P.CLASSES["npc"].props, "hp", None)
    del P.CLASSES["npc"].props["hp"]
    try:
        reg = load_registry(root)
        npc = next(iter(reg.of_class("npc")))
        assert "hp" not in npc.props and f"char.{npc.id}.hp" not in reg.variables
        assert f"char.{npc.id}.down" in reg.variables
        sdk.apply(root, [{"op": "set", "var": f"char.{npc.id}.down", "value": 1}], reg, turn=1)
        sdk.apply(root, [], load_registry(root), turn=2)
        assert cs.read(root, npc.id).get("down") == 1
        assert any(e.name for e in effects.instances(load_registry(root), npc.id)), "a 倒地 status on her"
    finally:
        P.CLASSES["npc"].props["hp"] = {"type": "int", "min": 0}


def test_hp_zero_goes_down_rolls_each_resolve_and_ends_stable_or_dead(tmp_path):
    root = _install(tmp_path)
    reg, soul = _soul(root)
    sheet = root / soul.props["sheet"]
    before = sheet.read_text(encoding="utf-8")
    r = sdk.apply(root, [{"op": "add", "var": f"char.{soul.id}.hp", "delta": -99}], reg, turn=1)
    assert any(a.get("event") == "down" for a in r.applied)
    st = cs.read(root, soul.id)
    assert st["down"] == 1 and st["down_pass"] == 0 and st["down_fail"] == 0, "no roll on the Resolve she went down"
    assert [e.name for e in effects.instances(load_registry(root), soul.id)] == ["倒地"]
    st, _t = _run(root, 8)
    assert st.get("dead") or st.get("stable") or not st.get("down"), st
    names = [e.name for e in effects.instances(load_registry(root), soul.id)]
    assert names == (["死亡"] if st.get("dead") else ["稳住了"] if st.get("stable") else []), (st, names)
    assert sheet.read_text(encoding="utf-8") == before


def test_healed_back_above_zero_she_gets_up(tmp_path):
    root = _install(tmp_path)
    reg, soul = _soul(root)
    sdk.apply(root, [{"op": "set", "var": f"char.{soul.id}.hp", "value": 0}], reg, turn=1)
    sdk.apply(root, [{"op": "set", "var": f"char.{soul.id}.hp", "value": 3}], load_registry(root), turn=2)
    st = cs.read(root, soul.id)
    assert st.get("down") == 0 and not [e for e in effects.instances(load_registry(root), soul.id)]


def test_the_simplified_coc_rule_kills_on_the_first_failure(tmp_path):
    root = _install(tmp_path)
    (root / "game" / "rules").mkdir(parents=True, exist_ok=True)
    (root / "game" / "rules" / "rules.json").write_text(json.dumps({"down_rule": "coc_simple"}), encoding="utf-8")
    reg, soul = _soul(root)
    sdk.apply(root, [{"op": "set", "var": f"char.{soul.id}.hp", "value": 0}], reg, turn=1)
    st, _t = _run(root, 10)
    assert st.get("dead") or st.get("stable"), st
    if st.get("dead"):
        assert st["down_fail"] == 1, "one failure is enough"


def test_the_dead_take_no_turn_and_everyone_knows(tmp_path):
    from neonrp.core import plan_loop, soul_view

    root = _install(tmp_path)
    reg, soul = _soul(root)
    cs.write(root, soul.id, down=1, dead=1)
    reg = load_registry(root)
    assert int(reg.entries[soul.id].props["dead"]) == 1
    txt = sdk.render_pack(sdk.pack(root, registry=reg))
    assert f"{soul.name}" in txt and "[死亡]" in txt
    assert "已经死了" in soul_view.own_context(reg, soul.id)
    if reg.entries[soul.id].parent == reg.player_location:
        seen = []
        import neonrp.core.plan_loop as PLm

        orig = PLm._host
        PLm._host = lambda root_, system, user: (seen.append(user), "<lines>\n好。\n</lines>\nnext: wait")[1]
        try:
            plan_loop.step(root, user_text="我看看四周。", last_narration="雾。")
        finally:
            PLm._host = orig
        assert seen and soul.name not in seen[0].split("在场", 1)[-1].split("\n", 2)[0] if "在场" in seen[0] else True


def test_her_own_view_carries_her_body(tmp_path):
    from neonrp.core import soul_view

    root = _install(tmp_path)
    reg, soul = _soul(root)
    sdk.apply(root, [{"op": "add", "var": f"char.{soul.id}.hp", "delta": -5},
                     {"op": "new", "class": "status", "name": "流血", "props": {"on": soul.id}}], reg, turn=1)
    reg = load_registry(root)
    own = soul_view.own_context(reg, soul.id)
    assert f"HP {int(soul.props['hp']) - 5}/{soul.props['max_hp']}" in own and "流血" in own
    if not pytest:  # pragma: no cover
        pass


def test_hp_bars_of_people_elsewhere_do_not_crowd_the_variable_list(tmp_path):
    """The schema gives every NPC an hp bar; the model's variable list carries only those with the player, or hurt / down."""
    root = _install(tmp_path)
    reg = load_registry(root)
    p = sdk.pack(root, registry=reg)
    here = reg.player_location
    far = [e for e in reg.of_class("npc") if e.parent != here]
    assert far and not any(f"char.{e.id}.hp" in p.variables for e in far)
    sdk.apply(root, [{"op": "add", "var": f"char.{far[0].id}.hp", "delta": -2}], reg, turn=1)
    assert f"char.{far[0].id}.hp" in sdk.pack(root, registry=load_registry(root)).variables, "hurt: listed"
