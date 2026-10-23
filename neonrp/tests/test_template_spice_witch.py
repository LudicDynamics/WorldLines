"""香料魔女 · 格洛克蒙德的黄昏 (worldlines/templates/spice-witch.template) — ported from the multi-agent example world (10-14).

The template lints clean on its contract (open-adventure@1), builds on the rpg pack with its two souls (the Maestro as the
companion, the inquisitor) and five light NPCs, opens and plays beats with a stub model, the clock turns days (a segment
is settled each time) and brings thirst at night, the scripted events fire, and every ending is reachable through the
plot's triggers (leaving by the third sundown, selling the violin, exposure, the last sundown, falling)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from neonrp import packs, template
from neonrp.core import sdk, settlement
from neonrp.core.registry import load_registry

TPL = Path(__file__).resolve().parents[1] / "worldlines" / "templates" / "spice-witch.template"
PLACES = {f"T001/{n}" for n in ("highway", "city_gate", "market", "tavern", "church", "manor", "alley")}


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


def test_lints_clean_on_its_contract():
    rep = template.lint(template.load(TPL))
    assert rep["counts"]["block"] == 0, [p for p in rep["problems"] if p["level"] == "block"]
    t = template.load(TPL)
    assert t.data["play_contract"] == "open-adventure@1" and t.pack_name == "rpg"
    plot = json.loads((TPL / "plots" / "P01" / "plot.json").read_text(encoding="utf-8"))
    assert set(plot["endings"]) == {"E01", "E02", "E03", "E04", "E05"}
    assert (TPL / t.data["card"]["cover"]).is_file()


def test_builds_on_rpg_with_its_cast_town_and_meters(world):
    assert packs.template_of(world) == "rpg"
    reg = load_registry(world)
    assert reg.player_location == "T001/city_gate"
    assert {e.name for e in reg.of_class("soul")} == {"乐师", "塞维林"}
    assert {e.name for e in reg.of_class("npc")} == {"加伦", "奥德", "玛戈", "瓦尔泽伯爵", "暗巷里流血的陌生人"}
    assert {e.id for e in reg.of_class("place")} == PLACES
    v = reg.variables
    assert (v["stay.left"].value, v["player.suspicion"].value, v["player.thirst"].value, v["bond.maestro"].value) == (8, 0, 2, 60)
    assert v["player.silver"].value == 18 and v["time.day"].value == 1 and v["time.clock"].value == "18:00"
    assert "小提琴与琴盒" in reg.entries["player"].props["sheet"]
    pt = json.loads((world / "playthrough.json").read_text(encoding="utf-8"))
    assert {s["sid"]: s["role"] for s in pt["souls"]} == {"maestro": "companion", "severin": "npc"}
    for sid, iid in (("maestro", "si-maestro01"), ("severin", "si-severin1")):
        assert (world / "souls" / f"{sid}-{iid}" / "assets" / "portrait.webp").is_file()


def test_days_turn_settle_segments_and_bring_thirst(world):
    r = _beat(world, 1, "进城找个地方住下", [{"op": "add", "var": "stay.left", "delta": -1}])
    assert _fired(r, "P01.night_one") and _var(world, "player.thirst") == 3
    _beat(world, 2, "睡到天亮", [{"op": "add", "var": "stay.left", "delta": -1}])
    assert _var(world, "time.day") == 2 and _var(world, "P01.stage") == 1
    assert (world / "game" / "meta" / "segments" / "day-1.json").is_file(), "open-adventure settles a day as a segment"
    for i in range(3, 6):
        _beat(world, i, "……", [{"op": "add", "var": "stay.left", "delta": -1}])
    assert _var(world, "player.thirst") == 4 and _var(world, "time.day") == 2
    _beat(world, 6, "……", [{"op": "add", "var": "stay.left", "delta": -1}])
    assert _var(world, "time.day") == 3 and _var(world, "P01.stage") == 2
    assert (world / "game" / "meta" / "segments" / "day-2.json").is_file()


def test_the_three_day_promise_is_the_true_ending(world):
    _beat(world, 1, "我是来自东方的香料商人", [{"op": "flag", "key": "gate_passed"}, {"op": "add", "var": "player.silver", "delta": -3},
                                            {"op": "move_to", "who": "player", "to": "T001/market"}])
    _beat(world, 2, "摆摊卖桂皮和丁香", [{"op": "add", "var": "player.silver", "delta": 8}, {"op": "flag", "key": "sold_spice"},
                                    {"op": "add", "var": "stay.left", "delta": -1}])
    r = _beat(world, 3, "回城门", [{"op": "move_to", "who": "player", "to": "T001/city_gate"}])
    assert not r.ended
    r = _beat(world, 4, "趁天还没黑,出城上路")
    assert r.ended and r.ended["id"] == "E01" and _exit(world) == "E01"


def test_leaving_empty_handed_or_watched_does_not_end(world):
    r = _beat(world, 1, "算了,直接出城")
    assert not r.ended and _fired(r, "P01.leave_without_trade"), "the Maestro reminds her the spice is unsold"
    _beat(world, 2, "卖香料", [{"op": "flag", "key": "sold_spice"}, {"op": "add", "var": "player.suspicion", "delta": 30}])
    _beat(world, 3, "被人瞥见了红眼睛", [{"op": "add", "var": "player.suspicion", "delta": 30}])
    r = _beat(world, 4, "被守卫认出来了", [{"op": "add", "var": "player.suspicion", "delta": 15}])
    assert _fired(r, "P01.chapel_talk") and "inquisitor_alerted" in _flags(world)
    r = _beat(world, 5, "出城")
    assert not r.ended and _fired(r, "P01.leave_watched"), "with suspicion ≥ 70 the gate is watched"


def test_selling_the_violin_is_the_lonely_ending(world):
    r = _beat(world, 1, "去伯爵府见伯爵", [{"op": "move_to", "who": "player", "to": "T001/manor"}, {"op": "flag", "key": "met_noble"}])
    assert _fired(r, "P01.soiree") and "noble_soiree_done" in _flags(world)
    r = _beat(world, 2, "好,琴卖给你,换你的马车送我出城", [{"op": "flag", "key": "sold_violin"}])
    assert r.ended and r.ended["id"] == "E02" and _exit(world) == "E02"


def test_the_alley_is_bait_once_suspicion_is_high(world):
    _beat(world, 1, "说辞对不上", [{"op": "add", "var": "player.suspicion", "delta": 30}])
    _beat(world, 2, "又对不上", [{"op": "add", "var": "player.suspicion", "delta": 15}])
    _beat(world, 3, "去集市", [{"op": "move_to", "who": "player", "to": "T001/market"}])
    r = _beat(world, 4, "顺着血腥味走进暗巷", [{"op": "move_to", "who": "player", "to": "T001/alley"}])
    assert _fired(r, "P01.alley_bait")
    assert {"stranger_bait", "inquisitor_alerted"} <= _flags(world) and _var(world, "player.suspicion") == 55


def test_feeding_quenches_thirst_and_spikes_suspicion(world):
    r = _beat(world, 1, "跟着那个醉汉进了巷子", [{"op": "flag", "key": "fed"}])
    assert _fired(r, "P01.fed") and _var(world, "player.thirst") == 0 and _var(world, "player.suspicion") == 25


def test_exposure_is_the_fail_ending(world):
    r = None
    for i in range(1, 6):
        r = _beat(world, i, "……", [{"op": "add", "var": "player.suspicion", "delta": 25}])
        if r.ended:
            break
    assert r.ended and r.ended["id"] == "E03" and _exit(world) == "E03"


def test_the_third_sundown_ends_the_stay(world):
    r = None
    for i in range(1, 6):
        r = _beat(world, i, "……", [{"op": "add", "var": "stay.left", "delta": -2}])
        if r.ended:
            break
    assert r.ended and r.ended["id"] == "E04" and _exit(world) == "E04"


def test_falling_is_a_fail_ending(world):
    r = None
    for i in range(1, 6):
        r = _beat(world, i, "……", [{"op": "add", "var": "player.hp", "delta": -5}])
        if r.ended:
            break
    assert r.ended and r.ended["id"] == "E05" and _exit(world) == "E05"


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
    s = ConversationSession(world, "world-agent", mode="play")
    for text in ("开始游戏", "我走向城门,说我是来自东方的香料商人", "我去集市看看告示板"):
        assert s.send(text).success, text
    assert load_registry(world).player_location in PLACES
