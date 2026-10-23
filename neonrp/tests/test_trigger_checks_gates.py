"""Rules a world writes as data and the engine keeps (10-15, 神乐岛 / 七夜 rules pass): a named check rolled this turn
wakes `check` triggers (any of the skill's names), a place's own way in (`enter_if` in location.json) stops the
player's move in verify, triggers compare a variable with another one, move a soul and put a status on or off."""
from __future__ import annotations

from pathlib import Path

import pytest

from neonrp import template
from neonrp.core import sdk, triggers
from neonrp.core.registry import load_registry

KAGURA = Path(__file__).resolve().parents[1] / "worldlines" / "templates" / "kagura-island.template"


@pytest.fixture
def world(tmp_path: Path) -> Path:
    dest = tmp_path / "run"
    template.build(template.load(KAGURA), dest)
    return dest


def _apply(root: Path, turn: int, ops: list | None = None, says: str = ""):
    reg = load_registry(root)
    vr = sdk.verify(root, list(ops or []), reg)
    return vr, sdk.apply(root, vr.accepted, reg, turn=turn, refused=vr.refused, player_says=says, narration=says)


def test_a_skill_command_roll_is_heard_by_the_worlds_check_rules(world):
    from neonrp.core import player_action

    _apply(world, 1, [{"op": "move_to", "who": "player", "to": "T001/cafe"}])
    out = player_action.skill_turn(world, "侦查", "储物间", turn=2)
    assert out["action"]["rolled"]
    heard = triggers.checks_of(world, 2)
    assert heard and heard[-1]["label"] == "察觉" and "侦查" in heard[-1]["names"] and "Search" in heard[-1]["names"]
    _, r = _apply(world, 2, says=out["say"])
    assert any(t["trigger"] == "P01.cafe_search" for t in r.triggered) == bool(out["action"]["passed"])
    assert not triggers.checks_of(world, 2), "heard once"


def test_rpg_dice_names_the_check_from_its_reason():
    from neonrp.packs.rpg.tools import check_label

    class E:
        props = {"attributes": {"体": 4, "识": 4}, "skills": [{"name": "骇入"}]}

    class R:
        entries = {"player": E()}

    assert check_label(None, R(), {"reason": "识·读朔的来历"}) == "识"
    assert check_label(None, R(), {"reason": "骇入 门禁"}) == "骇入"
    assert check_label(None, R(), {"reason": "身体撑住"}) == "", "a name inside a word is not a label"
    assert check_label(None, R(), {"attr": "DEX", "reason": "识"}) == "DEX"


def test_a_place_gate_stops_only_the_player(world):
    reg = load_registry(world)
    assert triggers.enter_refused(world, reg, "player", "T001/south_shore", "T001/islet_surface")
    assert triggers.enter_refused(world, reg, "si-hane0001", "T001/south_shore", "T001/islet_surface") is None
    assert triggers.enter_refused(world, reg, "player", "T001/islet_dock", "T001/islet_surface") is None, "from below"
    vr, _ = _apply(world, 1, [{"op": "move_to", "who": "player", "to": "T001/islet_surface"}])
    assert vr.refused and not vr.refused[0].fixable


def test_a_condition_may_compare_two_variables(world):
    reg = load_registry(world)
    st = triggers.snapshot(reg)
    st["vars"].update({"talk.kagami": 2, "talk.makoto": 1})
    ok = triggers._cond(reg, {"var": "talk.kagami", ">": {"var": "talk.makoto"}}, st, st, {}, {})[0]
    assert ok and not triggers._cond(reg, {"var": "talk.makoto", ">=": {"var": "talk.kagami"}}, st, st, {}, {})[0]
    assert triggers.validate(reg, {"when": {"turn": True}, "if": [{"var": "talk.kagami", ">": {"var": "nope"}}],
                                   "then": [{"to": "log"}]})


def test_new_emits_and_kinds_validate(world):
    reg = load_registry(world)
    good = {"when": {"check": "急救"}, "if": [{"check": "急救", "passed": True}, {"who": "羽", "at": "player", "is": False}],
            "then": [{"to": "move", "who": "镜子", "place": "T001"}, {"to": "status", "name": "噪蚀"}]}
    assert triggers.validate(reg, good) == []
    bad = {"when": {"check": ""}, "then": [{"to": "move", "who": "镜子"}, {"to": "status"}]}
    assert len(triggers.validate(reg, bad)) == 3


def test_show_and_form_emits_validate_and_degrade(world):
    """10-16 (归乡): a trigger may show a template picture (`show`) and switch a soul to another form (`form`); both
    need their fields, a soul that declares no such form / a slot the template lacks only logs an error."""
    reg = load_registry(world)
    soul = reg.of_class("soul")[0].id
    good = {"when": {"flag": "x"}, "then": [{"to": "show", "slot": "card:cover"}, {"to": "form", "who": soul, "form": "elder"}]}
    assert triggers.validate(reg, good) == []
    bad = {"when": {"flag": "x"}, "then": [{"to": "show"}, {"to": "form", "who": soul}, {"to": "form", "who": "nobody", "form": "a"}]}
    assert len(triggers.validate(reg, bad)) == 3
    spec = reg.triggers.get(next(iter(reg.triggers))) if reg.triggers else None

    out = triggers._emit(world, reg, spec, [{"to": "show", "slot": "no-such"}, {"to": "form", "who": soul, "form": "elder"}], {}, None, turn=1)
    assert "error" in out[0] and "no form" in out[1]["error"]
    from neonrp.core import show

    assert show.arrivals(world, reg, reg.player_location) == [], "nothing queued"
