"""末班车 · 断云隧道 (worldlines/templates/last-train.template) — ported from Living Canvas's last-train (10-13).

The template lints clean on its contract (mystery-trpg@1), builds on the pct pack with its four souls and two light NPCs,
opens and plays beats with a stub model, every ending is reachable through the plot's triggers (the true ending by two
evidence chains, the train leaving when the clock runs out, collapsing on hp or composure), and the folder carries none
of another rulebook's words (outside the engine-generated ``spec/``)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from neonrp import packs, template
from neonrp.core import sdk, settlement
from neonrp.core.registry import load_registry
from neonrp.packs.pct import tools as T

TPL = Path(__file__).resolve().parents[1] / "worldlines" / "templates" / "last-train.template"
FORBIDDEN = re.compile(r"cthulhu|克苏鲁|\bcoc\b|sanity|理智|\bSAN\b", re.IGNORECASE)


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


def test_lints_clean_on_its_contract():
    rep = template.lint(template.load(TPL))
    assert rep["counts"]["block"] == 0, [p for p in rep["problems"] if p["level"] == "block"]
    t = template.load(TPL)
    assert t.data["play_contract"] == "mystery-trpg@1" and t.pack_name == "pct"
    assert {e for e in json.loads((TPL / "plots" / "P01" / "plot.json").read_text(encoding="utf-8"))["endings"]} == {"E01", "E02", "E03"}


def test_builds_on_pct_with_its_cast_clock_and_composure(world):
    assert packs.template_of(world) == "pct"
    reg = load_registry(world)
    assert reg.player_location == "T001/seated_car"
    assert {e.name for e in reg.of_class("soul")} == {"夏澄", "钟怀礼", "周子航", "老贺"}
    assert {e.name for e in reg.of_class("npc")} == {"老秦", "苏禾"}
    assert {e.id for e in reg.of_class("place")} == {f"T001/{n}" for n in ("cab", "seated_car", "sleeper", "dining_car", "freight_car")}
    assert reg.variables["departure.left"].value == 8 and reg.variables["player.composure"].value == 60
    assert reg.variables["player.hp"].value == 10 and reg.variables["time.clock"].value == "01:10"
    assert "定力 60%" in reg.entries["player"].props["sheet"]
    assert "dice" in reg.actions and "san" not in reg.actions, "pct's own mind check is switched off; composure is a d100 skill"
    assert not FORBIDDEN.search(reg.actions["dice"].doc) and "定力" in reg.actions["dice"].doc, "the model reads this world's dice words"
    r = T.dice(world, reg, {"dice": "定力", "seed_key": "k"}, seed="s")
    assert r["ok"] and r["vs"] == 60 and r["label"] == "定力"


def test_composure_loss_lands_in_the_sheet(world):
    _beat(world, 1, "看见她发紫的嘴唇", [{"op": "add", "var": "player.composure", "delta": -3}])
    st = json.loads((world / "game" / "player" / "stats.json").read_text(encoding="utf-8"))
    assert st["skills"]["定力"] == 57 and _var(world, "player.composure") == 57


def test_the_logbook_route_reaches_the_true_ending(world):
    _beat(world, 1, "我拿起17号座上的笔记本看看")
    assert "got_notebook" in _flags(world)
    _beat(world, 2, "问问20号的学生", [{"op": "add", "var": "departure.left", "delta": -1}, {"op": "flag", "key": "got_witness"}])
    assert _var(world, "P01.stage") == 1
    _beat(world, 3, "去餐车", [{"op": "move_to", "who": "player", "to": "T001/dining_car"}])
    _beat(world, 4, "搜餐车", [{"op": "add", "var": "departure.left", "delta": -2}, {"op": "flag", "key": "got_key_half"}])
    r = _beat(world, 5, "请老贺帮我把煤斗倒出来")
    assert "got_key" in _flags(world) and _var(world, "departure.left") == 4, "the long way round: the key, one more step"
    assert any(t.get("trigger") == "P01.long_way_dining" for t in r.triggered)
    _beat(world, 6, "去行李车", [{"op": "move_to", "who": "player", "to": "T001/freight_car"}])
    assert _var(world, "P01.stage") == 2
    _beat(world, 7, "苏禾!我扶她起来")
    assert "got_testimony" in _flags(world)
    _beat(world, 8, "拦住他", [{"op": "add", "var": "departure.left", "delta": -1}, {"op": "flag", "key": "got_logbook"}])
    r = _beat(world, 9, "夏澄,你去驾驶室用电台向调度报告")
    assert r.ended and r.ended["id"] == "E01"
    assert _exit(world) == "E01"


def test_pills_and_bill_are_the_other_chain(world):
    for i, (says, ops) in enumerate([
        ("去行李车", [{"op": "flag", "key": "got_key"}, {"op": "move_to", "who": "player", "to": "T001/freight_car"}]),
        ("扶起苏禾,听她说", []),
        ("拦住他", [{"op": "flag", "key": "got_corner"}, {"op": "flag", "key": "got_pills"}, {"op": "flag", "key": "got_bill"}]),
    ], start=1):
        _beat(world, i, says, ops)
    r = _beat(world, 4, "我们报告给调度吧")
    assert r.ended and r.ended["id"] == "E01"


def test_a_short_report_costs_time_and_the_locked_car_stays_locked(world):
    r = _beat(world, 1, "直接去行李车", [{"op": "move_to", "who": "player", "to": "T001/freight_car"}])
    assert any(t.get("trigger") == "P01.freight_locked" for t in r.triggered), "no key: the door is locked"
    _beat(world, 2, "回驾驶室", [{"op": "move_to", "who": "player", "to": "T001/cab"}])
    r = _beat(world, 3, "我用电台向岭口调度报告")
    assert not r.ended and _var(world, "departure.left") == 7


def test_the_train_leaves_when_the_clock_runs_out(world):
    for i in range(1, 4):
        r = _beat(world, i, "……", [{"op": "add", "var": "departure.left", "delta": -3}])
    assert r.ended and r.ended["id"] == "E02" and _exit(world) == "E02"


@pytest.mark.parametrize("var, delta", [("player.hp", -5), ("player.composure", -10)])
def test_collapsing_is_the_fail_ending(world, var, delta):
    r = None
    for i in range(1, 8):
        r = _beat(world, i, "……", [{"op": "add", "var": var, "delta": delta}])
        if r.ended:
            break
    assert r.ended and r.ended["id"] == "E03" and _exit(world) == "E03"


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
    for text in ("开始游戏", "我拿起17号座上的笔记本看看", "我去卧铺看看"):
        assert s.send(text).success, text
    assert "got_notebook" in _flags(world)
    assert load_registry(world).player_location in {f"T001/{n}" for n in ("cab", "seated_car", "sleeper", "dining_car", "freight_car")}


def test_no_other_rulebook_words_in_the_folder():
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
