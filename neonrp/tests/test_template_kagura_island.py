"""神乐岛 · 第三夜的神乐 (worldlines/templates/kagura-island.template) — ported from the multi-agent example world (10-14).

The template lints clean on its contract (mystery-trpg@1), builds on the pct pack with its seven souls (Hane as the
companion) and fifteen places, opens and plays beats with a stub model, the loop clock turns days and the tide, Tsubasa
dies if nobody stops the bleeding, and every ending is reachable through the plot's triggers (the true ending with the
present magatama, leaving with Hane's white one, sitting with the guest, sailing with Shiro, falling, the loop closing).
The folder carries none of another rulebook's or mythos' words (outside the engine-generated ``spec/``)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from neonrp import packs, template
from neonrp.core import sdk, settlement
from neonrp.core.registry import load_registry
from neonrp.packs.pct import tools as T

TPL = Path(__file__).resolve().parents[1] / "worldlines" / "templates" / "kagura-island.template"
FORBIDDEN = re.compile(r"cthulhu|克苏鲁|\bcoc\b|sanity|理智|\bSAN\b|yith|ユゴス|伊斯", re.IGNORECASE)
PLACES = {f"T001/{n}" for n in ("south_shore", "town", "cafe", "cafe_basement", "undersea_tunnel", "school", "museum",
                                "monument", "shrine", "shrine_underground", "ancient_base", "crater", "islet_surface",
                                "islet_ledge", "islet_dock")}
SOULS = {"hane": "si-hane0001", "yuto": "si-yuto0001", "tsubasa": "si-tsubasa01", "shiro": "si-shiro0001",
         "kagami": "si-kagami001", "makoto": "si-makoto001", "miyaji": "si-miyaji001"}


@pytest.fixture
def world(tmp_path: Path) -> Path:
    dest = tmp_path / "run"
    template.build(template.load(TPL), dest)
    return dest


def _beat(root: Path, turn: int, says: str = "", ops: list | None = None):
    return sdk.apply(root, list(ops or []), load_registry(root), turn=turn, player_says=says, narration=says)


def _flags(root: Path) -> set[str]:
    return {k[5:] for k, v in load_registry(root).variables.items() if k.startswith("flag.") and v.value}


def _var(root: Path, name: str):
    return load_registry(root).variables[name].value


def _exit(root: Path) -> str | None:
    return ((settlement.read(root) or {}).get("exit") or {}).get("id")


def _fired(r, name: str) -> bool:
    return any(t.get("trigger") == name for t in r.triggered)


def _go(place: str) -> dict:
    return {"op": "move_to", "who": "player", "to": f"T001/{place}"}


def _step(root: Path, turn: int, says: str = "", ops: list | None = None):
    """verify then apply — the way a turn lands (a place's own way in is checked in verify)."""
    reg = load_registry(root)
    vr = sdk.verify(root, list(ops or []), reg)
    return vr, sdk.apply(root, vr.accepted, reg, turn=turn, refused=vr.refused, player_says=says, narration=says)


def _check(root: Path, turn: int, skill: str, passed: bool, says: str = "", lang_label: bool = False):
    """A named check rolled this turn (as the dice tool reports it), then the beat lands."""
    from neonrp.core import tool_watch

    tool_watch.notify(root, "dice", {"dice": skill, "who": "player"},
                      {"ok": True, "dice": "1d100", "total": 3 if passed else 97, "vs": 50, "passed": passed,
                       "level": "success" if passed else "fumble", "label": skill}, turn=turn)
    return _beat(root, turn, says)


def _here(root: Path) -> str | None:
    return load_registry(root).player_location


def test_lints_clean_on_its_contract():
    rep = template.lint(template.load(TPL))
    assert rep["counts"]["block"] == 0, [p for p in rep["problems"] if p["level"] == "block"]
    t = template.load(TPL)
    assert t.data["play_contract"] == "mystery-trpg@1" and t.pack_name == "pct"
    plot = json.loads((TPL / "plots" / "P01" / "plot.json").read_text(encoding="utf-8"))
    assert set(plot["endings"]) == {"E01", "E02", "E03", "E04", "E05", "E06"}
    assert plot["endings"]["E01"]["kind"] == "true" and set(plot["reveal"]) == {"zh", "en", "ja", "ko"}
    assert (TPL / t.data["card"]["cover"]).is_file()
    for e in plot["endings"].values():
        assert (TPL / "plots" / "P01" / e["assets"]["image"]).is_file()


def test_builds_on_pct_with_its_seven_souls_and_the_island(world):
    assert packs.template_of(world) == "pct"
    reg = load_registry(world)
    assert reg.player_location == "T001/south_shore"
    assert {e.name for e in reg.of_class("soul")} == {"羽", "悠人", "翼", "白", "镜子", "真琴", "宫司一真"}
    assert not list(reg.of_class("npc")), "every named islander is a soul"
    assert {e.id for e in reg.of_class("place")} == PLACES
    v = reg.variables
    assert (v["loop.left"].value, v["player.composure"].value, v["player.hp"].value) == (9, 55, 10)
    assert (v["trust.islanders"].value, v["trust.kagami"].value, v["trust.miyaji"].value) == (50, 20, 10)
    assert v["time.day"].value == 1 and v["time.clock"].value == "21:00"
    assert "定力 55%" in reg.entries["player"].props["sheet"] and "民俗学" in reg.entries["player"].props["sheet"]
    assert "dice" in reg.actions and "san" not in reg.actions, "pct's own mind check is switched off; composure is a d100 skill"
    assert not FORBIDDEN.search(reg.actions["dice"].doc) and "定力" in reg.actions["dice"].doc
    r = T.dice(world, reg, {"dice": "定力", "seed_key": "k"}, seed="s")
    assert r["ok"] and r["vs"] == 55 and r["label"] == "定力"
    pt = json.loads((world / "playthrough.json").read_text(encoding="utf-8"))
    assert {s["sid"]: s["role"] for s in pt["souls"]} == {"hane": "companion", **{s: "npc" for s in SOULS if s != "hane"}}
    for sid, iid in SOULS.items():
        assert (world / "souls" / f"{sid}-{iid}" / "assets" / "portrait.webp").is_file(), sid
    where = {e.name: e.parent for e in reg.of_class("soul")}
    assert where["翼"] == "T001/islet_ledge" and where["白"] == "T001/islet_dock" and where["镜子"] == "T001/cafe"


def test_the_clock_turns_days_and_the_tide(world):
    r = _beat(world, 1, "在砂滩上等到天亮", [{"op": "add", "var": "loop.left", "delta": -1}])
    assert _fired(r, "P01.day_two") and _var(world, "time.day") == 2 and _var(world, "P01.stage") == 1
    assert (_var(world, "time.clock"), _var(world, "time.period")) == ("06:00", "朝"), "the engine owns the clock"
    vr, _ = _step(world, 2, "趁退潮涉水去离岛", [_go("islet_surface")])
    assert not vr.refused and _here(world) == "T001/islet_surface", "dawn: the tide is out"
    _step(world, 3, "回南岸", [_go("south_shore"), {"op": "add", "var": "loop.left", "delta": -2}])
    assert (_var(world, "time.clock"), _var(world, "time.period")) == ("17:00", "夕")
    vr, _ = _step(world, 4, "再去离岛", [_go("islet_surface")])
    assert vr.refused and "潮水" in vr.refused[0].why and _here(world) == "T001/south_shore", "afternoon: the sea is back"
    r = _beat(world, 5, "……", [{"op": "add", "var": "loop.left", "delta": -2}])
    assert _var(world, "time.day") == 3 and _var(world, "P01.stage") == 2 and _var(world, "time.clock") == "06:00"


def test_the_model_cannot_write_the_clock(world):
    reg = load_registry(world)
    vr = sdk.verify(world, [{"op": "set", "var": "time.clock", "value": "12:00"}, {"op": "set", "var": "time.day", "value": 3}], reg)
    assert len(vr.refused) == 2 and not vr.accepted


def test_six_lines_in_one_period_move_the_clock(world):
    for i in range(1, 6):
        _beat(world, i, f"我和羽说话({i})")
    assert _var(world, "loop.left") == 9 and _var(world, "loop.beats") == 5
    r = _beat(world, 6, "我还在说")
    assert _fired(r, "P01.beats_cap") and _var(world, "loop.left") == 8 and _var(world, "time.day") == 2
    assert _var(world, "loop.beats") == 0


def test_yuto_wakes_and_tsubasa_dies_unless_someone_stops_the_bleeding(world):
    r = _beat(world, 1, "我走向远处倒下的人影")
    assert _fired(r, "P01.yuto_wakes") and "yuto_woke" in _flags(world)
    _beat(world, 2, "天亮了", [{"op": "add", "var": "loop.left", "delta": -1}])
    assert "tsubasa_dead" not in _flags(world), "she holds on until the morning"
    r = _beat(world, 3, "中午了", [{"op": "add", "var": "loop.left", "delta": -1}])
    assert _fired(r, "P01.tsubasa_dies") and "tsubasa_dead" in _flags(world)


def test_hidden_ways_stay_shut_until_found(world):
    vr, _ = _step(world, 1, "去咖啡馆地下", [_go("cafe_basement")])
    assert vr.refused and _here(world) == "T001/south_shore"
    _step(world, 2, "去咖啡馆", [_go("cafe")])
    _beat(world, 3, "我把勾玉的事告诉镜子", [{"op": "add", "var": "trust.kagami", "delta": 20}])
    assert _var(world, "trust.kagami") == 55 and "kagami_confided" in _flags(world)
    _beat(world, 4, "帮她照顾孤儿院的孩子", [{"op": "add", "var": "trust.kagami", "delta": 5}])
    assert "basement_known" in _flags(world)
    vr, _ = _step(world, 5, "直接去海底通道", [_go("undersea_tunnel")])
    assert vr.refused, "the tunnel opens only from the basement or the dock"
    vr, _ = _step(world, 6, "下地下室,走海底通道", [_go("cafe_basement"), _go("undersea_tunnel")])
    assert not vr.refused and _here(world) == "T001/undersea_tunnel" and "got_murals" in _flags(world)
    vr, _ = _step(world, 7, "去离岛船坞,再上地上", [_go("islet_dock"), _go("islet_surface")])
    assert not vr.refused and _here(world) == "T001/islet_surface", "the tunnel goes under the sea at any tide"
    vr, _ = _step(world, 8, "去神社地下", [_go("shrine"), _go("shrine_underground")])
    assert vr.refused and _here(world) == "T001/shrine"


def test_a_search_at_the_cafe_finds_the_basement_door(world):
    _step(world, 1, "去咖啡馆", [_go("cafe")])
    r = _check(world, 2, "侦查", True, "我在储物间仔细找找")
    assert _fired(r, "P01.cafe_search") and "basement_known" in _flags(world)


def test_the_ledge_needs_the_blood_trail_and_a_failed_search_costs_a_period(world):
    _beat(world, 1, "天亮,退潮", [{"op": "add", "var": "loop.left", "delta": -1}])
    _step(world, 2, "涉水去离岛", [_go("islet_surface")])
    vr, _ = _step(world, 3, "下到岩棚", [_go("islet_ledge")])
    assert vr.refused and _here(world) == "T001/islet_surface"
    r = _check(world, 4, "侦查", False, "我在祭坛旁边搜一搜")
    assert _fired(r, "P01.trail_slow") and "found_blood_trail" in _flags(world) and _var(world, "loop.left") == 7
    assert "tsubasa_dead" in _flags(world), "the search took too long: noon came"
    vr, _ = _step(world, 5, "下到岩棚", [_go("islet_ledge")])
    assert not vr.refused and _here(world) == "T001/islet_ledge"


def test_first_aid_on_the_ledge_saves_her_by_the_check_itself(world):
    _beat(world, 1, "天亮,退潮", [{"op": "add", "var": "loop.left", "delta": -1}])
    _step(world, 2, "涉水去离岛", [_go("islet_surface")])
    r = _check(world, 3, "侦查", True, "顺着灌木里的血迹往下找")
    assert _fired(r, "P01.trail_found") and _var(world, "loop.left") == 8
    _step(world, 4, "下到岩棚", [_go("islet_ledge")])
    r = _check(world, 5, "急救", False, "我按住她的伤口")
    assert _fired(r, "P01.aid_failed") and "tsubasa_rescued" not in _flags(world)
    r = _check(world, 6, "First Aid", True, "再试一次", lang_label=True)  # any of the skill's names
    assert _fired(r, "P01.aid_saved") and {"tsubasa_rescued", "got_magatama_present"} <= _flags(world)


def test_a_check_is_heard_once(world):
    _step(world, 1, "去咖啡馆", [_go("cafe")])
    _check(world, 2, "侦查", False, "找找")
    r = _check(world, 3, "侦查", True, "再找找")
    assert _fired(r, "P01.cafe_search")
    r = _beat(world, 4, "……")
    assert not any(t["trigger"].startswith("P01.cafe") for t in r.triggered)


def test_yutos_lunge_hurts_on_a_failed_dodge(world):
    _beat(world, 1, "我走向远处倒下的人影")
    r = _check(world, 2, "闪避", False, "躲开他的手")
    assert _fired(r, "P01.yuto_lunge") and _var(world, "player.hp") == 8


def test_the_most_talked_to_islander_on_the_first_night_vanishes(world):
    _step(world, 1, "去咖啡馆", [_go("cafe")])
    _beat(world, 2, "镜子小姐,这是哪里?")
    _beat(world, 3, "镜子,你认识我吗?")
    assert _var(world, "talk.kagami") == 2
    _step(world, 4, "去学校", [_go("school")])
    _beat(world, 5, "真琴老师,晚上好")
    r = _beat(world, 6, "等到天亮", [{"op": "add", "var": "loop.left", "delta": -1}])
    assert _fired(r, "P01.vanish_kagami") and not _fired(r, "P01.vanish_makoto")
    assert {"vanished_kagami", "someone_vanished"} <= _flags(world)
    where = {e.name: e.parent for e in load_registry(world).of_class("soul")}
    assert where["镜子"] == "T001" and where["真琴"] == "T001/school", "gone from every place on the island"


def test_nobody_vanishes_when_nobody_was_named(world):
    r = _beat(world, 1, "等到天亮", [{"op": "add", "var": "loop.left", "delta": -1}])
    assert not any(t["trigger"].startswith("P01.vanish") for t in r.triggered) and "someone_vanished" not in _flags(world)


def test_a_heavy_erosion_adds_its_status(world):
    _beat(world, 1, "……", [{"op": "add", "var": "player.composure", "delta": -5}])
    assert [e.name for e in load_registry(world).of_class("status")] == ["噪蚀"]
    _beat(world, 2, "……", [{"op": "add", "var": "player.composure", "delta": -5}])
    assert [e.name for e in load_registry(world).of_class("status")] == ["噪蚀"], "not twice"


def test_the_museum_checks_find_the_notebook_and_the_past_magatama(world):
    _step(world, 1, "去博物馆", [_go("museum")])
    r = _check(world, 2, "查阅资料", True, "在资料室里找")
    assert _fired(r, "P01.library") and "got_notebook" in _flags(world) and "got_magatama_past" not in _flags(world)
    r = _check(world, 3, "潜行", True, "摸进保管区")
    assert "got_magatama_past" in _flags(world) and "taboo_6" in _flags(world) and _var(world, "trust.islanders") == 40


def test_the_crater_alone_is_a_taboo_with_company_it_is_not(world, tmp_path):
    _step(world, 1, "上山", [_go("shrine")])
    _step(world, 2, "一个人上火山口", [_go("crater")])
    assert "taboo_4" in _flags(world)
    r = _check(world, 3, "闪避", False, "稳住脚")
    assert _fired(r, "P01.crater_fall") and _var(world, "player.hp") == 5
    other = tmp_path / "other"
    template.build(template.load(TPL), other)
    _step(other, 1, "和羽一起上山", [_go("shrine"), {"op": "move_to", "who": "si-hane0001", "to": "T001/shrine"}])
    r = _beat(other, 2, "一起去火山口", [_go("crater"), {"op": "move_to", "who": "si-hane0001", "to": "T001/crater"}])
    assert _fired(r, "P01.crater_with") and "taboo_4" not in _flags(other)


def test_the_night_taboo_changes_the_morning(world):
    _step(world, 1, "上山去神社", [_go("shrine")])
    _beat(world, 2, "我推门进本殿看看")
    r = _beat(world, 3, "天亮", [{"op": "add", "var": "loop.left", "delta": -1}])
    assert _fired(r, "P01.taboo_shrine_morning")


def test_the_skill_descriptions_cover_the_whole_sheet(world):
    from neonrp.core import sheet

    for lang in ("zh", "en", "ja", "ko"):
        sh = sheet.sheet(world, lang)
        empty = [r["key"] for k in ("attrs", "skills") for r in sh[k] if not r.get("desc")]
        assert not empty, (lang, empty)


def test_common_actions_have_labels():
    a = json.loads((TPL / "world" / "game" / "meta" / "actions.json").read_text(encoding="utf-8"))
    assert all(r.get("label") for r in a["actions"]) and {r["name"] for r in a["actions"] if r.get("common")} == {"go", "talk", "search", "wait"}


def test_the_night_shrine_is_a_taboo(world):
    _beat(world, 1, "上山去神社", [_go("shrine")])
    r = _beat(world, 2, "我推门进本殿看看")
    assert _fired(r, "P01.taboo_shrine") and {"taboo_1", "underground_found"} <= _flags(world)
    assert _var(world, "trust.islanders") == 35 and _var(world, "trust.miyaji") == 0


def test_the_true_ending_with_the_present_magatama(world):
    _beat(world, 1, "天亮,退潮", [{"op": "add", "var": "loop.left", "delta": -1}])
    _beat(world, 2, "涉水去离岛", [_go("islet_surface")])
    r = _beat(world, 3, "顺着灌木里的血迹往下找")
    assert _fired(r, "P01.blood_trail")
    r = _beat(world, 4, "下到岩棚", [_go("islet_ledge")])
    assert "tsubasa_found" in _flags(world)
    r = _beat(world, 5, "我按住她的伤口止血", [{"op": "flag", "key": "tsubasa_rescued"}])
    assert "got_magatama_present" in _flags(world)
    _beat(world, 6, "中午了", [{"op": "add", "var": "loop.left", "delta": -1}])
    assert "tsubasa_dead" not in _flags(world), "rescued: she lives through the noon"
    _beat(world, 7, "去博物馆的保管区翻", [_go("museum"), {"op": "flag", "key": "got_notebook"}])
    _beat(world, 8, "从咖啡馆地下走海底通道回离岛", [{"op": "flag", "key": "basement_known"}, _go("cafe_basement"), _go("undersea_tunnel")])
    r = _beat(world, 9, "上到离岛地上", [_go("islet_surface")])
    assert not _fired(r, "P01.tide_blocks")
    r = _beat(world, 10, "我把翼的黑勾玉放进祭坛")
    assert r.ended and r.ended["id"] == "E01" and _exit(world) == "E01"


def test_hanes_white_magatama_only_lets_you_leave(world):
    hane_too = {"op": "move_to", "who": "si-hane0001", "to": "T001/islet_surface"}
    _beat(world, 1, "天亮,退潮", [{"op": "add", "var": "loop.left", "delta": -1}, _go("islet_surface")])
    r = _beat(world, 2, "羽把白勾玉交给我,我们一起放进祭坛", [{"op": "flag", "key": "got_magatama_future"}])
    assert not r.ended, "Hane is still on the beach: the white one is hers to set in"
    _beat(world, 3, "羽也过来了", [hane_too])
    r = _beat(world, 4, "我们一起把勾玉放进祭坛")
    assert r.ended and r.ended["id"] == "E02" and _exit(world) == "E02"


def test_naming_the_white_one_leaves_even_when_the_true_ending_is_ready(world):
    for k in ("got_magatama_present", "tsubasa_rescued", "got_notebook", "got_magatama_future"):
        _beat(world, 1, "", [{"op": "flag", "key": k}])
    _beat(world, 2, "天亮,一起涉水", [{"op": "add", "var": "loop.left", "delta": -1}, _go("islet_surface"),
                                   {"op": "move_to", "who": "si-hane0001", "to": "T001/islet_surface"}])
    r = _beat(world, 3, "我和羽把白勾玉放进祭坛")
    assert r.ended and r.ended["id"] == "E02"


def test_sitting_with_the_guest_is_the_waen_ending(world):
    _beat(world, 1, "白天去读碑", [{"op": "add", "var": "loop.left", "delta": -1}, _go("monument")])
    _beat(world, 2, "读碑文")
    assert "got_monument" in _flags(world)
    _beat(world, 3, "去离岛船坞", [_go("islet_dock")])
    _beat(world, 4, "读墙上的刻字")
    assert "got_wall" in _flags(world)
    _beat(world, 5, "回咖啡馆和镜子说话", [_go("cafe"), {"op": "add", "var": "trust.kagami", "delta": 20},
                                          {"op": "add", "var": "trust.kagami", "delta": 15}])
    assert "kagami_confided" in _flags(world)
    _beat(world, 6, "去神社地下的基地", [{"op": "flag", "key": "underground_found"}, _go("ancient_base")])
    r = _beat(world, 7, "我坐下来,想和那位客人谈谈")
    assert r.ended and r.ended["id"] == "E03" and _exit(world) == "E03"


def test_sailing_with_shiro_on_the_past_magatama(world):
    _beat(world, 1, "去博物馆", [_go("museum"), {"op": "flag", "key": "got_magatama_past"}])
    assert "taboo_6" in _flags(world) and _var(world, "trust.islanders") == 40
    _beat(world, 2, "去船坞", [{"op": "flag", "key": "basement_known"}, _go("islet_dock")])
    _beat(world, 3, "我把墙上的字念出来")
    r = _beat(world, 4, "白,把这枚勾玉给你,我们一起坐船离开")
    assert r.ended and r.ended["id"] == "E04" and _exit(world) == "E04"


@pytest.mark.parametrize("var, delta", [("player.hp", -5), ("player.composure", -10)])
def test_collapsing_is_the_fail_ending(world, var, delta):
    r = None
    for i in range(1, 8):
        r = _beat(world, i, "……", [{"op": "add", "var": var, "delta": delta}])
        if r.ended:
            break
    assert r.ended and r.ended["id"] == "E05" and _exit(world) == "E05"


def test_the_loop_closes_when_the_third_night_ends(world):
    r = None
    for i in range(1, 6):
        r = _beat(world, i, "……", [{"op": "add", "var": "loop.left", "delta": -2}])
        if r.ended:
            break
    assert r.ended and r.ended["id"] == "E06" and _exit(world) == "E06"
    assert any(_fired(r, n) for n in ("P01.end_loop",))


def test_opens_and_plays_beats_with_a_stub_model(world, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("NEONRP_HOME", str(tmp_path / "home" / ".neonrp"))
    from neonrp.core.conversation import ConversationSession
    from neonrp.core.manifest import Manifest

    neo = world / ".neonrp"
    (neo / "events").mkdir(parents=True, exist_ok=True)
    (neo / "sessions").mkdir(exist_ok=True)
    m = Manifest()
    m.branches["main"].head_event = -1
    (neo / "manifest.json").write_text(json.dumps(m.model_dump(), default=str), encoding="utf-8")
    (neo / "config.json").write_text(json.dumps({"llm": {"provider": "stub", "model": "stub-model"}}), encoding="utf-8")
    # the template's beats, not the planning layer: every line resolves straight away (with the private layer the
    # contract turns the planning beat on, and the stub never ends a talk)
    eng = world / "game" / "meta" / "engine.json"
    cfg = json.loads(eng.read_text(encoding="utf-8")) if eng.exists() else {}
    cfg.setdefault("turn", {})["plan_loop"] = "off"
    eng.parent.mkdir(parents=True, exist_ok=True)
    eng.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    s = ConversationSession(world, "world-agent", mode="play")
    for text in ("开始游戏", "我走向远处倒下的人影", "我去城镇看看"):
        assert s.send(text).success, text
    assert "yuto_woke" in _flags(world)
    assert load_registry(world).player_location in PLACES


def test_no_other_rulebook_or_mythos_words_in_the_folder():
    hits = []
    for f in TPL.rglob("*"):
        if f.is_file() and f.suffix in (".json", ".md", ".txt") and f.relative_to(TPL).parts[0] != "spec":  # spec/ is the engine's
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                # the one exception: the key that switches off pct's built-in op in the world's actions overlay — an
                # engine op id, not content (the op itself is gone from the registry: see the cast test)
                if f.relative_to(TPL).as_posix() == "world/game/meta/actions.json" and line.strip() == '"san": null,':
                    continue
                if FORBIDDEN.search(line):
                    hits.append(f"{f.relative_to(TPL)}:{n}")
    assert not hits, hits
