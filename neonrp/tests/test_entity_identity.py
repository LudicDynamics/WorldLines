"""Entity identity: every object has an entry; every spelling
of one finds it; a name two entries share is reported, not silently picked; someone's things are named `owner/name`
(`{{user}}` the player, `{{char}}` the character with the player, an id) and are unique per owner."""
from __future__ import annotations

from pathlib import Path

import pytest

from neonrp import template as TP
from neonrp.core import sdk
from neonrp.core.registry import load_registry
from _paths import PRODUCT_TEMPLATES


def _run(tmp_path: Path, name: str = "stoneford-elena") -> Path:
    root = tmp_path / name
    TP.build(PRODUCT_TEMPLATES / f"{name}.template", root)
    return root


def _elena(reg):
    return next(e for e in reg.of_class("soul") if e.props.get("sid") == "elena")


# ── one entry, every spelling ─────────────────────────────────────────────────


@pytest.mark.parametrize("spelling", ["艾琳娜", "Elena", "elena", "ＥＬＥＮＡ", "elena-0001", " 艾琳娜 ", "{{char}}"])
def test_every_spelling_of_a_character_finds_the_one_entry(tmp_path, spelling):
    root = _run(tmp_path)
    reg = load_registry(root)
    el = _elena(reg)
    if spelling == "{{char}}":
        reg.focus_char = el.id
    assert reg.lookup(spelling).ids == [el.id]
    assert reg.lookup(el.id).ids == [el.id]


def test_user_macro_and_the_players_names_in_every_language_are_the_player(tmp_path):
    reg = load_registry(_run(tmp_path))
    for t in ("{{user}}", "player", "玩家", "你", "you", "プレイヤー", reg.entries["player"].name):
        assert reg.lookup(t).ids == ["player"], t


def test_a_table_of_seats_still_has_a_player_entry(tmp_path):
    """werewolf has no player file: the engine supplies the entry, so the player's things have an owner."""
    reg = load_registry(_run(tmp_path, "werewolf-night-village"))
    assert reg.entries["player"].cls == "player" and reg.lookup("{{user}}").ids == ["player"]
    assert all(reg.is_person(e.cls) for e in reg.of_class("seat"))


def test_a_name_in_two_towns_means_the_one_in_this_town_and_lookup_reports_the_rest(tmp_path):
    reg = load_registry(_run(tmp_path))
    both = [e.id for e in reg.of_class("place") if e.id.endswith("/guild")]
    assert len(both) >= 2
    reg.current_town = reg.player_location = None
    assert sorted(reg.lookup("guild").ids) == sorted(both) and reg.lookup("guild").ambiguous
    reg.player_location = next(e.id for e in reg.of_class("place") if e.id.startswith(both[1].split("/")[0] + "/") and e.id != both[1])
    assert reg.lookup("guild").ids == [both[1]] and reg.resolve("guild") == both[1]


# ── someone's things: owner/name, unique per owner ─────────────────────────────


def _status(reg, name):
    return [(e.name, reg.owner_of(e)) for e in reg.of_class("status") if e.name == name]


def test_two_people_can_each_have_the_same_status(tmp_path):
    """Before: the second 「bleeding」 was refused as already existing (class-global names)."""
    root = _run(tmp_path)
    reg = load_registry(root)
    el = _elena(reg)
    vr = sdk.verify(root, [{"op": "new", "class": "status", "name": "{{user}}/流血"},
                           {"op": "new", "class": "status", "name": "流血", "props": {"on": "艾琳娜"}}], reg)
    assert not vr.refused, [r.why for r in vr.refused]
    sdk.apply(root, vr.accepted, reg, turn=1)
    reg = load_registry(root)
    assert sorted(_status(reg, "流血"), key=str) == sorted([("流血", "player"), ("流血", el.id)], key=str)
    vr = sdk.verify(root, [{"op": "new", "class": "status", "name": "elena/流血"}], reg)
    assert vr.refused and "already exists" in vr.refused[0].why


def test_a_status_on_someone_else_ticks_their_counter_not_the_players(tmp_path):
    """The rule line says `player.hp -1`; on her it must cost her hp (found by the 10-13 replay, once her copy was allowed)."""
    root = _run(tmp_path)
    reg = load_registry(root)
    el = _elena(reg)
    vr = sdk.verify(root, [{"op": "new", "class": "status", "name": "流血", "props": {"on": el.id, "each": "player.hp:-1"}}], reg)
    sdk.apply(root, vr.accepted, reg, turn=1)
    reg = load_registry(root)
    hp, her = reg.variables["player.hp"].value, reg.variables[f"char.{el.id}.hp"].value
    sdk.apply(root, [], reg, turn=2)
    reg = load_registry(root)
    assert reg.variables["player.hp"].value == hp
    assert reg.variables[f"char.{el.id}.hp"].value == her - 1


def test_a_bare_name_means_the_actors_own_and_an_unclear_one_is_refused_with_owner_slash_name(tmp_path):
    root = _run(tmp_path)
    reg = load_registry(root)
    el = _elena(reg)
    sdk.apply(root, sdk.verify(root, [{"op": "new", "class": "status", "name": "{{user}}/疲惫"},
                                      {"op": "new", "class": "status", "name": f"{el.id}/疲惫"}], reg).accepted, reg, turn=1)
    reg = load_registry(root)
    vr = sdk.verify(root, [{"op": "remove", "who": "疲惫"}], reg)  # no owner written: the player's (and the trace says so)
    mine = next(e.id for e in reg.of_class("status") if e.name == "疲惫" and reg.owner_of(e) == "player")
    assert vr.accepted[0]["who"] == mine and vr.accepted[0]["_identity"]["how"] == "actor"
    vr = sdk.verify(root, [{"op": "remove", "who": "艾琳娜/疲惫"}], reg)
    hers = next(e.id for e in reg.of_class("status") if e.name == "疲惫" and reg.owner_of(e) == el.id)
    assert vr.accepted[0]["who"] == hers
    sdk.apply(root, sdk.verify(root, [{"op": "remove", "who": "{{user}}/疲惫"}], reg).accepted, reg, turn=2)
    reg = load_registry(root)
    npc = reg.of_class("npc")[0]
    sdk.apply(root, sdk.verify(root, [{"op": "new", "class": "status", "name": f"{npc.name}/疲惫"}], reg).accepted, reg, turn=3)
    reg = load_registry(root)
    assert sorted(reg.owner_of(e) for e in reg.of_class("status") if e.name == "疲惫") == sorted([el.id, npc.id])
    vr = sdk.verify(root, [{"op": "remove", "who": "疲惫"}], reg)  # two others have it, the player does not: ask, never pick
    assert not vr.accepted and "owner/name" in vr.refused[0].why
    assert sorted(vr.refused[0].allowed) == sorted([f"{el.id}({el.name})/疲惫", f"{npc.id}({npc.name})/疲惫"])


def test_an_unknown_owner_is_refused_with_the_people_to_choose_from(tmp_path):
    root = _run(tmp_path)
    reg = load_registry(root)
    vr = sdk.verify(root, [{"op": "new", "class": "status", "name": "流血", "props": {"on": "nobody-here"}}], reg)
    assert vr.refused and "owner" in vr.refused[0].why and any("player" in a for a in vr.refused[0].allowed)


def test_a_status_without_an_owner_is_the_players_as_before(tmp_path):
    root = _run(tmp_path)
    reg = load_registry(root)
    vr = sdk.verify(root, [{"op": "new", "class": "status", "name": "轻伤", "props": {"note": "x"}}], reg)
    assert vr.accepted[0]["props"]["on"] == "player" and vr.accepted[0]["_identity"]["how"] == "actor"


# ── V3: the ledger stays whole ─────────────────────────────────────────────────


def test_ledger_invariants_hold_on_every_shipped_template(tmp_path):
    from neonrp.core.identity_check import problems

    for t in ("stoneford-elena", "pct-house", "werewolf-night-village"):
        reg = load_registry(_run(tmp_path, t))
        assert problems(reg) == [], t


# ── ② the Jev identity gate ───────────────────────────────────────────────────


def _jev(pick_of):
    """A stub Jev: for each choice question, the option `pick_of(criteria)` with p 0.9."""
    from neonrp.core import system_one as s1

    def stub(state, questions):
        out = {}
        for qid, q in questions.items():
            v = pick_of(q.criteria)
            out[qid] = s1.Answer("choice", v, {v: 0.9}, 0.9)
        return out
    return stub


def test_the_gate_settles_a_name_that_matched_nothing_and_leaves_unsure_ones_refused(tmp_path, monkeypatch):
    from neonrp.core import system_one as s1

    root = _run(tmp_path)
    reg = load_registry(root)
    sdk.apply(root, sdk.verify(root, [{"op": "new", "class": "status", "name": "{{user}}/扭伤"}], reg).accepted, reg, turn=1)
    reg = load_registry(root)
    sprain = next(e.id for e in reg.of_class("status") if e.name == "扭伤")
    vr = sdk.verify(root, [{"op": "remove", "who": "脚踝的伤"}], reg)  # another wording of the same sprain
    assert vr.refused and not vr.accepted
    monkeypatch.setattr(s1, "fast_judge_available", lambda: True)
    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    s1.install_stub(_jev(lambda c: next(k for k, v in c.items() if "扭伤" in v)))
    try:
        vr2, log = sdk.identity_gate(root, reg, vr, "你给脚踝敷了药,扭伤好了。")
    finally:
        s1.install_stub(None)
    assert [o["who"] for o in vr2.accepted] == [sprain] and vr2.accepted[0]["_identity"]["by"] == "jev"
    assert log[0]["landed"] and not vr2.refused
    s1.install_stub(_jev(lambda c: "none"))
    try:
        vr3, log = sdk.identity_gate(root, reg, vr, "")
    finally:
        s1.install_stub(None)
    assert not vr3.accepted and vr3.refused and not log[0]["landed"]


def test_without_a_fast_jev_the_gate_changes_nothing(tmp_path, monkeypatch):
    from neonrp.core import system_one as s1

    root = _run(tmp_path)
    reg = load_registry(root)
    vr = sdk.verify(root, [{"op": "remove", "who": "不存在的东西"}], reg)
    monkeypatch.setattr(s1, "fast_judge_available", lambda: False)
    assert sdk.identity_gate(root, reg, vr, "") == (vr, [])


# ── 10-13: braced handles, names back, places as paths ─────────────────────────


def test_braced_ids_are_handles_and_written_text_gets_the_names_back(tmp_path):
    from neonrp.core import turn_v3

    root = _run(tmp_path)
    reg = load_registry(root)
    el = _elena(reg)
    assert reg.lookup("{{elena}}").ids == [el.id] and reg.lookup("{{NPC001}}").ids == ["NPC001"] and reg.handle(el.id) == "elena"
    ops = turn_v3.parse_transition("<files>\nnew status {{user}}/轻伤 note=右肩 · {{elena}} 帮忙包扎\nnew status {{elena}}/流血\n</files>")
    vr = sdk.verify(root, ops, reg)
    assert not vr.refused, [r.why for r in vr.refused]
    sdk.apply(root, vr.accepted, reg, turn=1)
    reg = load_registry(root)
    hurt = next(e for e in reg.of_class("status") if e.name == "轻伤")
    assert reg.owner_of(hurt) == "player" and "{{" not in hurt.props["note"] and el.name in hurt.props["note"]
    assert [reg.owner_of(e) for e in reg.of_class("status") if e.name == "流血"] == [el.id]
    assert reg.render_refs("{{user}} 和 {{elena}};{{nobody}}") == f"{reg.entries['player'].name} 和 {el.name};{{{{nobody}}}}"


def test_the_pack_shows_a_character_by_her_stable_id(tmp_path):
    root = _run(tmp_path)
    reg = load_registry(root)
    el = _elena(reg)
    reg.entries[el.id].parent = reg.player_location
    txt = sdk.render_pack(sdk.pack(root, registry=reg))
    assert f"- elena {el.name}" in txt and f"- {el.id} " not in txt


def test_a_bare_place_name_reads_as_a_relative_path_and_an_unplaced_one_is_never_a_silent_pick(tmp_path):
    root = _run(tmp_path)
    reg = load_registry(root)
    here_town = reg.current_town
    other = next(e.id for e in reg.of_class("place") if e.id.endswith("/guild") and not e.id.startswith(f"{here_town}/"))
    assert reg.lookup("guild").ids == [f"{here_town}/guild"]  # ./guild from where the player stands
    assert reg.lookup(other).ids == [other] and reg.lookup("{{" + other + "}}").ids == [other]  # a full path is never re-read
    reg.player_location = reg.current_town = None
    vr = sdk.verify(root, [{"op": "move_to", "who": "player", "to": "guild"}], reg)
    assert vr.refused and "full path" in vr.refused[0].why and len(vr.refused[0].allowed) >= 2


def test_a_name_with_its_class_written_in_front_is_found(tmp_path):
    """`remove status 疲惫` — three refusals in the recorded runs were this spelling."""
    root = _run(tmp_path)
    reg = load_registry(root)
    vr = sdk.verify(root, [{"op": "new", "class": "status", "name": "疲惫", "props": {"turns": "8"}}], reg)
    sdk.apply(root, vr.accepted, reg, turn=1)
    reg = load_registry(root)
    vr = sdk.verify(root, [{"op": "remove", "who": "status 疲惫"}], reg)
    assert not vr.refused, [r.why for r in vr.refused]
    assert reg.lookup("carry 疲惫").ids == []  # the class must match


def test_class_prefix_and_owner_path_together_find_her_thing_not_the_players(tmp_path):
    """V4 10-13: `remove status {{si-elena0001}}/中毒` removed the player's poison (twice), hers stayed."""
    root = _run(tmp_path)
    reg = load_registry(root)
    el = _elena(reg)
    vr = sdk.verify(root, [{"op": "new", "class": "status", "name": "中毒", "props": {"turns": "9"}},
                           {"op": "new", "class": "status", "name": "中毒", "props": {"on": el.id, "turns": "9"}}], reg)
    sdk.apply(root, vr.accepted, reg, turn=1)
    reg = load_registry(root)
    hers = next(e.id for e in reg.of_class("status") if reg.owner_of(e) == el.id)
    for spelling in (f"status {{{{{el.id}}}}}/中毒", "status {{elena}}/中毒", "status elena/中毒", "{{elena}}/中毒"):
        assert reg.lookup(spelling).ids == [hers], spelling
    vr = sdk.verify(root, [{"op": "remove", "who": "status {{nobody}}/中毒"}], reg)
    assert vr.refused and not vr.accepted  # an owner written but not recognised: refused, never the player's


def test_her_variable_table_name_finds_her(tmp_path):
    """10-14 pct-house: the transition wrote `move char.si-chara0001 T001/study` (the name her counters go by in the
    variable table) and was refused twice — `char.<id>` is her, and `char.<id>/<name>` her thing."""
    root = _run(tmp_path)
    reg = load_registry(root)
    el = _elena(reg)
    assert reg.lookup(f"char.{el.id}").ids == [el.id]
    vr = sdk.verify(root, [{"op": "new", "class": "status", "name": "中毒", "props": {"on": el.id, "turns": "9"}}], reg)
    sdk.apply(root, vr.accepted, reg, turn=1)
    reg = load_registry(root)
    hers = next(e.id for e in reg.of_class("status") if reg.owner_of(e) == el.id)
    assert reg.lookup(f"char.{el.id}/中毒").ids == [hers]
    vr = sdk.verify(root, [{"op": "move_to", "who": f"char.{el.id}", "to": "inn"}], reg)
    assert not [r for r in vr.refused if r.field == "who"], vr.refused
    assert reg.lookup("char.nobody").ids == []


def test_a_bare_name_gives_way_to_her_thing_named_in_the_same_batch_and_a_double_lands_once(tmp_path):
    """10-20 全线 ID5: the prose's `remove 流血` (bare → the player's) and the transition's `remove {{elena}}/流血` in one
    batch took both bleeds; ID1: `remove {{user}}/中毒` written twice was refused the second time as already gone."""
    root = _run(tmp_path)
    reg = load_registry(root)
    el = _elena(reg)
    vr = sdk.verify(root, [{"op": "new", "class": "status", "name": "流血", "props": {"turns": "9"}},
                           {"op": "new", "class": "status", "name": "流血", "props": {"on": el.id, "turns": "9"}}], reg)
    sdk.apply(root, vr.accepted, reg, turn=1)
    reg = load_registry(root)
    mine = next(e.id for e in reg.of_class("status") if reg.owner_of(e) == "player")
    hers = next(e.id for e in reg.of_class("status") if reg.owner_of(e) == el.id)
    vr = sdk.verify(root, [{"op": "remove", "who": "流血"}, {"op": "remove", "who": "{{elena}}/流血"}], reg)
    assert [o["who"] for o in vr.accepted] == [hers], "the player's bleed stays"
    vr = sdk.verify(root, [{"op": "remove", "who": "{{user}}/流血"}, {"op": "remove", "who": "{{user}}/流血"}], reg)
    assert [o["who"] for o in vr.accepted] == [mine]


def test_a_status_removed_and_written_anew_in_one_batch_is_replaced(tmp_path):
    """10-20 全线 ID1: `remove ST901` then `new status {{elena}}/中毒 turns=3` — the new one was refused as already there."""
    root = _run(tmp_path)
    reg = load_registry(root)
    el = _elena(reg)
    vr = sdk.verify(root, [{"op": "new", "class": "status", "name": "中毒", "props": {"on": el.id, "turns": "9"}}], reg)
    sdk.apply(root, vr.accepted, reg, turn=1)
    reg = load_registry(root)
    hers = next(e.id for e in reg.of_class("status") if reg.owner_of(e) == el.id)
    vr = sdk.verify(root, [{"op": "remove", "who": hers}, sdk._adv_line_op("new status {{elena}}/中毒 turns=3")], reg)
    assert not vr.refused, [r.why for r in vr.refused]
    sdk.apply(root, vr.accepted, reg, turn=2)
    reg = load_registry(root)
    now = [e for e in reg.of_class("status") if reg.owner_of(e) == el.id]
    assert len(now) == 1 and str(now[0].props.get("turns")) == "3"


def test_removing_what_is_already_gone_is_no_refusal(tmp_path):
    """10-21 ID1/ID5: the prose said 「毒退了」 once more and the transition wrote `remove {{user}}/中毒` again — the
    status was gone, and the refusal counted as an error; it is nothing to do, like a move to where one stands."""
    root = _run(tmp_path)
    reg = load_registry(root)
    vr = sdk.verify(root, [sdk._adv_line_op("remove {{user}}/中毒")], reg)
    assert not vr.refused, [r.why for r in vr.refused]
    res = sdk.apply(root, vr.accepted, reg, turn=1)
    assert not res.refused and any(r.get("why") == "already gone" for r in res.repaired)
    vr = sdk.verify(root, [sdk._adv_line_op("remove 不存在的谁/中毒")], reg)
    assert vr.refused and vr.refused[0].fixable, "an owner nobody knows is still a mistake to rewrite"
