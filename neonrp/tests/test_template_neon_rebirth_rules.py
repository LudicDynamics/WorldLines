"""七夜 · the rules the engine keeps (10-15 rules pass). Each deterministic rule of the template has one test here, with
a stub of what the model would do (ops) or roll (a named check): the reader's five attributes and the reborn's three
tiers carry a line on the sheet in four languages; the machine core opens only with the white bookmark (a place's own
way in); the companion falling erases the player's pair; the machine's dawns pass over the pairs you are allied with;
an empty bookmark hand costs one more resonance on every drop; fading comes and goes with resonance; a Last Line scorches
the page, and a second one in a night below resonance 9 burns resonance; meeting Shirase at the data centre and the
Nameless underground hands over the truth and the key; the common play actions are labelled; every ending is reachable."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from neonrp import template
from neonrp.core import sdk, settlement, tool_watch
from neonrp.core.registry import load_registry

builder = pytest.importorskip("neonrp.template.builder")

TPL = Path(__file__).resolve().parents[1] / "worldlines" / "templates" / "neon-rebirth.template"
DRAFT = {"fields": {"name": "早濑", "look": "黑色雨衣", "origin": "hacker", "past": "在旧地铁网的网吧里长大",
                    "regret": "那天没有接的那通电话", "attrs": {"体": 4, "技": 5, "识": 4, "魂": 4, "运": 3}},
         "companion": "kuon"}


@pytest.fixture
def world(tmp_path: Path) -> Path:
    t = template.load(TPL)
    errs, norm = builder.check(t, DRAFT)
    assert not errs, errs
    t = builder.select_cast(t, norm)
    dest = tmp_path / "run"
    template.build(t, dest)
    builder.apply(t, dest, norm)
    return dest


def _beat(root: Path, turn: int, says: str = "", ops: list | None = None):
    return sdk.apply(root, list(ops or []), load_registry(root), turn=turn, player_says=says, narration=says)


def _step(root: Path, turn: int, says: str = "", ops: list | None = None):
    reg = load_registry(root)
    vr = sdk.verify(root, list(ops or []), reg)
    return vr, sdk.apply(root, vr.accepted, reg, turn=turn, refused=vr.refused, player_says=says, narration=says)


def _roll(root: Path, turn: int, label: str, total: int, says: str = "", passed: bool | None = None):
    res = {"ok": True, "dice": "4d6", "total": total, "label": label, **({"passed": passed} if passed is not None else {})}
    tool_watch.notify(root, "dice", {"dice": "4d6", "who": "player"}, res, turn=turn)
    return _beat(root, turn, says)


def _var(root: Path, name: str):
    return load_registry(root).variables[name].value


def _flags(root: Path) -> set[str]:
    return {k[5:] for k, v in load_registry(root).variables.items() if k.startswith("flag.") and v.value}


def _status(root: Path) -> list[str]:
    return [e.name for e in load_registry(root).of_class("status")]


def _fired(r, name: str) -> bool:
    return any(t.get("trigger") == name for t in r.triggered)


def _go(place: str) -> dict:
    return {"op": "move_to", "who": "player", "to": f"T001/{place}"}


def _phase(p: str) -> dict:
    return {"op": "set", "var": "phase", "value": p}


def test_the_sheet_explains_every_number(world):
    from neonrp.core import sheet

    for lang in ("zh", "en", "ja", "ko"):
        sh = sheet.sheet(world, lang)
        assert {r["key"] for r in sh["attrs"]} == {"体", "技", "识", "魂", "运"}
        empty = [r["key"] for k in ("attrs", "skills") for r in sh[k] if not r.get("desc")]
        assert not empty, (lang, empty)
    rules = json.loads((TPL / "world" / "game" / "rules" / "rules.json").read_text(encoding="utf-8"))
    for key in ("ink", "depth", "finale"):  # the reborn's three tiers: named and explained for the panels
        row = rules["attrs"][key]
        assert all(row["desc"].get(lang) for lang in ("zh", "en", "ja", "ko")), key


def test_the_core_opens_only_with_the_white_bookmark(world):
    _step(world, 1, "去数据中心", [_go("datacenter")])
    vr, _ = _step(world, 2, "进机房", [_go("machine_core")])
    assert vr.refused and "把手" in vr.refused[0].why and load_registry(world).player_location == "T001/datacenter"
    _beat(world, 3, "拿到白色书签", [{"op": "flag", "key": "truth_core_key"}])
    vr, r = _step(world, 4, "进机房", [_go("machine_core")])
    assert not vr.refused and _fired(r, "P01.core_open")


def test_the_companion_falling_erases_your_pair(world):
    r = _beat(world, 1, "……", [{"op": "set", "var": "char.si-kuon01.hp", "value": 0}])
    assert "closed_player" in _flags(world) and r.ended and r.ended["id"] == "E03"


def test_the_machines_dawn_passes_over_your_allies(world):
    _beat(world, 1, "和 Rin 结盟", [{"op": "flag", "key": "ally_rin"}])
    _beat(world, 2, "入夜", [_phase("night")])
    _beat(world, 3, "天亮", [_phase("dawn")])
    _beat(world, 4, "第二天", [_phase("day")])
    _beat(world, 5, "入夜", [_phase("night")])
    r = _beat(world, 6, "天亮", [_phase("dawn")])
    assert _var(world, "night") == 2 and _fired(r, "P01.dawn_erase_gu")
    assert "closed_gu" in _flags(world) and "closed_rin" not in _flags(world)


def test_with_no_bookmark_left_every_drop_costs_one_more(world):
    _beat(world, 0, "", [{"op": "set", "var": "resonance", "value": 9}])
    for i in range(3):
        _beat(world, 1 + i, "我写下一行", [{"op": "add", "var": "bookmarks", "delta": -1}])
    assert _var(world, "bookmarks") == 0
    res = _var(world, "resonance")
    r = _beat(world, 5, "我丢下了他", [{"op": "add", "var": "resonance", "delta": -2}])
    assert _fired(r, "P01.bond_thin") and _var(world, "resonance") == max(0, res - 3)


def test_fading_comes_and_goes_with_resonance(world):
    _beat(world, 1, "……", [{"op": "set", "var": "resonance", "value": 2}])
    assert "褪色" in _status(world)
    _beat(world, 2, "……", [{"op": "add", "var": "resonance", "delta": 1}])
    assert "褪色" not in _status(world)


def test_a_last_line_scorches_and_a_second_one_burns_resonance(world):
    _beat(world, 1, "……", [{"op": "set", "var": "resonance", "value": 5}])
    r = _roll(world, 2, "绝笔", 14, "绝笔!")
    assert _fired(r, "P01.finale") and "灼页" in _status(world) and _var(world, "finale.tonight") == 1
    assert _var(world, "resonance") == 5
    r = _roll(world, 3, "绝笔", 12, "再来一次!")
    assert _fired(r, "P01.finale_overdrawn") and _var(world, "resonance") == 4
    _beat(world, 4, "入夜", [_phase("night")])
    _beat(world, 5, "天亮", [_phase("dawn")])
    assert "灼页" not in _status(world)
    _beat(world, 6, "新的一天", [_phase("day")])
    assert _var(world, "finale.tonight") == 0


def test_meeting_shirase_and_the_nameless_hands_over_truth_and_key(world):
    _beat(world, 1, "入夜", [_phase("night")])
    _beat(world, 2, "天亮", [_phase("dawn")])
    _beat(world, 3, "第二天", [_phase("day")])
    _beat(world, 4, "入夜", [_phase("night")])
    r = _beat(world, 5, "去数据中心见 S", [_go("datacenter")])
    assert _fired(r, "P01.meet_shirase") and "truth_eating" in _flags(world)
    _beat(world, 6, "天亮", [_phase("dawn")])
    _beat(world, 7, "第三天", [_phase("day")])
    _beat(world, 8, "入夜", [_phase("night")])
    r = _beat(world, 9, "下到地下", [_go("underground")])
    assert _fired(r, "P01.meet_nameless") and "truth_core_key" in _flags(world)


def test_meeting_them_by_day_gives_nothing(world):
    r = _beat(world, 1, "白天去数据中心", [_go("datacenter")])
    assert not _fired(r, "P01.meet_shirase") and "truth_eating" not in _flags(world)


def test_common_actions_are_labelled():
    a = json.loads((TPL / "world" / "game" / "meta" / "actions.json").read_text(encoding="utf-8"))
    rows = {r["name"]: r for r in a["actions"]}
    assert all(r.get("label") for r in rows.values())
    assert {n for n, r in rows.items() if r.get("common")} == {"go", "talk", "read", "bookmark", "finale", "ally"}


ENDINGS = {
    "E01": [[{"op": "flag", "key": "truth_eating"}, {"op": "flag", "key": "truth_core_key"}, _go("machine_core")],
            "我用最后一枚书签改写规则:谁也不必被抹去"],
    "E09": [[{"op": "flag", "key": "truth_self"}, {"op": "flag", "key": "truth_core_key"}, _go("machine_core")], "我在那页纸上写下我自己的名字"],
    "E04": [[_go("bookstore")], "我用书签放你回去,回到你的书里"],
    "E02": [[{"op": "set", "var": "resonance", "value": 8}, {"op": "flag", "key": "closed_rin"}, {"op": "flag", "key": "closed_gu"},
             {"op": "flag", "key": "closed_kujo"}, {"op": "flag", "key": "closed_hawk"}], ""],
    "E08": [[{"op": "flag", "key": "closed_rin"}, {"op": "flag", "key": "closed_gu"}, {"op": "flag", "key": "closed_kujo"},
             {"op": "flag", "key": "closed_hawk"}], ""],
    "E03": [[{"op": "set", "var": "char.si-kuon01.hp", "value": 0}], ""],
    "E05": [[{"op": "set", "var": "resonance", "value": 0}], ""],
    "E06": [[{"op": "set", "var": "player.hp", "value": 0}], ""],
}


@pytest.mark.parametrize("ending", sorted(ENDINGS))
def test_every_ending_is_reachable(world, ending):
    ops, says = ENDINGS[ending]
    r = _beat(world, 1, "", ops)
    if says:
        r = _beat(world, 2, says)
    assert r.ended and r.ended["id"] == ending, (ending, r.ended)
    assert (settlement.read(world) or {}).get("exit", {}).get("id") == ending


def test_the_seventh_dawn_closes_the_run(world):
    r = None
    for n in range(7):
        _beat(world, 10 * n + 1, "入夜", [_phase("night")])
        _beat(world, 10 * n + 2, "天亮", [_phase("dawn")])
        r = _beat(world, 10 * n + 3, "新的一天", [_phase("day")])
        if r.ended:
            break
    assert r.ended and r.ended["id"] == "E07"
