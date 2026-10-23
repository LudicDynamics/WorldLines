"""灰橡宅 pct-house — the 10-14 supplements (niko): the butler is a soul with a name (奥斯温), the owner (埃德蒙) never
appears but is in the hall portrait and the stopped watch, the fresh plaster is an item (I803) beside the letter and the
watch, five more places (宅前石阶 · 管家房 · 二楼走廊 · 宅主人卧室 on top of the four), opening / stage CG and a player
avatar slot declared, 「心神」 shown for the sanity score (rules.json display names; op and variable keys unchanged), no
other rulebook's words in the folder, one set of map coordinates (location.json = the client's art.json). All stub."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from _paths import PRODUCT_TEMPLATES
from neonrp import template as TP
from neonrp.core import effects, player_action, sdk, settlement
from neonrp.core.registry import load_registry

TPL = PRODUCT_TEMPLATES / "pct-house.template"
ART = Path(__file__).resolve().parents[1] / "worldlines" / "examples" / "clients" / "art" / "pct-house" / "art.json"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
FORBIDDEN = re.compile(r"cthulhu|克苏鲁|\bcoc\b|理智|(?-i:\bSAN\b)|类 ?COC|测试", re.IGNORECASE)
PLACES = {"steps", "hall", "butler_room", "corridor", "study", "bedroom", "garden", "cellar"}


@pytest.fixture
def world(tmp_path: Path) -> Path:
    dest = tmp_path / "run"
    TP.build(TP.load(TPL), dest)
    return dest


def _beat(root: Path, turn: int, says: str = "", ops: list | None = None):
    return sdk.apply(root, list(ops or []), load_registry(root), turn=turn, player_says=says, narration=says)


def test_no_other_rulebook_words_in_the_folder():
    hits = []
    for f in TPL.rglob("*"):
        if f.is_file() and f.suffix in (".json", ".md", ".txt") and f.relative_to(TPL).parts[0] != "spec":  # spec/ is the engine's
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if FORBIDDEN.search(line):
                    hits.append(f"{f.relative_to(TPL)}:{n}: {line.strip()[:60]}")
    assert not hits, hits


def test_the_butler_is_a_named_soul_and_answers_to_butler(world):
    reg = load_registry(world)
    souls = {e.props["sid"]: e for e in reg.of_class("soul")}
    assert set(souls) == {"chara", "butler"} and souls["butler"].name == "奥斯温" and souls["chara"].name == "温妮"
    assert not reg.of_class("npc"), "no nameless NPC left"
    assert reg.lookup("管家").ids == [souls["butler"].id] and reg.lookup("Oswin Hale").ids == [souls["butler"].id]
    assert souls["butler"].parent == "T001/hall" and "老爷吩咐过" in souls["butler"].props["persona"]
    rows = {r["slot"] for r in TP.asset_slots(TP.load(TPL))}
    assert {"soul.portrait:butler", "soul.sprite:butler", "soul.portrait:chara"} <= rows


def test_the_owner_never_appears_but_his_things_do(world):
    reg = load_registry(world)
    assert not any("埃德蒙" in e.name for e in reg.of_class("soul")), "the owner is not cast"
    portrait, watch, plaster, letter = (reg.entries[i] for i in ("I806", "I805", "I803", "I804"))
    assert portrait.parent == "T001/hall" and portrait.props.get("fixed") and "看不清" in portrait.props["summary"]
    assert watch.parent == "T001/butler_room" and "给温妮" in watch.props["summary"]
    assert plaster.parent == "T001/cellar" and plaster.props.get("fixed")
    assert letter.parent == "player"
    pj = json.loads((TPL / "plots" / "P01" / "plot.json").read_text(encoding="utf-8"))
    assert "怀表" in pj["endings"]["E01"]["text"] and "给温妮" in pj["endings"]["E01"]["text"], "the true ending lands on him"


def test_places_links_and_one_set_of_coordinates():
    locs = {}
    for f in (TPL / "world" / "game" / "locations" / "T001").glob("*/location.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        locs[d["id"]] = d
    assert set(locs) == PLACES
    for pid, d in locs.items():
        assert d.get("summary"), pid
        for c in d["connections"]:
            assert pid in locs[c]["connections"], f"{pid} ↔ {c}"
    art = json.loads(ART.read_text(encoding="utf-8"))
    rooms = art["map"]["rooms"]
    assert set(rooms) == {f"T001/{p}" for p in PLACES} and set(art["scenes"]) == set(rooms)
    for pid, d in locs.items():
        assert (rooms[f"T001/{pid}"]["x"], rooms[f"T001/{pid}"]["y"]) == (d["pos"]["x"], d["pos"]["y"]), pid
    links = {tuple(sorted(x)) for x in art["map"]["links"]}
    assert links == {tuple(sorted((f"T001/{a}", f"T001/{b}"))) for a, d in locs.items() for b in d["connections"]}


def test_opening_stage_cg_and_the_player_avatar_are_declared_slots(tmp_path):
    d = tmp_path / "pct-house.template"
    shutil.copytree(TPL, d)
    rows = {r["slot"]: r for r in TP.asset_slots(TP.load(d))}
    assert [s for s in rows if s.startswith("opening.cg:")] == ["opening.cg:1", "opening.cg:2", "opening.cg:3"]
    assert all(rows[s]["label"] for s in rows if s.startswith("opening.cg:")), "each carries its caption"
    assert {"stage.cg:P01.1", "stage.cg:P01.2", "stage.cg:P01.3"} <= set(rows)
    pr = rows["player.portrait:player"]
    assert pr["need"] is False and "调查员" in pr["prompt"]  # 10-15 起已接 niko 出的调查员头像(have 可为 True)
    TP.put_asset(TP.load(d), "player.portrait:player", PNG)
    assert (d / "world-overlay" / "game" / "player" / "assets" / "portrait.png").is_file()
    assert {r["slot"]: r for r in TP.asset_slots(TP.load(d))}["player.portrait:player"]["have"]
    run = tmp_path / "run"
    TP.build(TP.load(d), run)
    assert (run / "game" / "player" / "assets" / "portrait.png").is_file(), "where the play screen reads the player's avatar"


def test_nerve_is_what_the_sanity_score_is_called_here(world, monkeypatch):
    from neonrp.packs.pct import tools as T

    reg = load_registry(world)
    assert "心神 55" in reg.entries["player"].props["sheet"] and "player.san" in reg.variables, "the variable key stays"
    assert "心神" in reg.actions["san"].doc and "理智" not in reg.actions["san"].doc, "the op stays san; its words are the world's"
    monkeypatch.setattr(T, "_d100", lambda seed, key: 90)  # BRP: half the score lost in one beat (55 → 25) breaks it
    out = T.san(world, reg, {"spec": "1/30", "why": "看见墙缝里的东西"}, seed="z")
    assert out["text"].startswith("心神检定 90 > 55") and "(心神 55→25)" in out["text"] and "SAN" not in out["text"]
    sdk.apply(world, [], load_registry(world), turn=1)
    assert [e.name for e in effects.instances(load_registry(world))] == ["临时失控"]
    sdk.apply(world, [{"op": "set", "var": "player.san", "value": 0}], load_registry(world), turn=2)
    assert "长久失控" in [e.name for e in effects.instances(load_registry(world))]
    assert settlement.read(world)["exit"]["id"] == "E09"


def test_a_world_without_its_own_names_keeps_the_packs(tmp_path, monkeypatch):
    from neonrp.packs.pct import tools as T

    d = tmp_path / "plain.template"
    shutil.copytree(TPL, d)
    (d / "world" / "game" / "rules" / "rules.json").unlink()
    root = tmp_path / "run"
    TP.build(TP.load(d), root)
    reg = load_registry(root)
    assert "SAN 55" in reg.entries["player"].props["sheet"]
    monkeypatch.setattr(T, "_d100", lambda seed, key: 10)
    assert T.san(root, reg, {"spec": "0/1d6", "why": "x"}, seed="z")["text"].startswith("理智检定 10 ≤ 55")


def test_the_clues_and_the_watch_reach_the_true_ending(world):
    _beat(world, 1, ops=[{"op": "move_to", "who": "player", "to": "T001/study"}])
    player_action.perform(world, "pick", "I801", turn=2)
    _beat(world, 3, ops=[{"op": "move_to", "who": "player", "to": "T001/garden"}])
    player_action.perform(world, "pick", "I802", turn=4)
    _beat(world, 5, ops=[{"op": "move_to", "who": "player", "to": "T001/cellar"}])
    assert load_registry(world).variables["P01.stage"].value == 3
    assert "布料线头" in player_action.perform(world, "inspect", "墙上的新灰", turn=6)["text"]
    assert player_action.perform(world, "pick", "I803", turn=7)["action"]["why"] == "cannot_pick", "the plaster is part of the wall"
    _beat(world, 8, ops=[{"op": "move_to", "who": "player", "to": "T001/butler_room"}])
    out = player_action.perform(world, "pick", "I805", turn=9)
    assert out["action"]["ok"] and out["text"].endswith("指针停在十一点四十。")
    _beat(world, 10, "我把看见的真相说出来:他在墙后面。")
    st = settlement.read(world)
    assert st["exit"]["id"] == "E01" and "给温妮" in st["epilogue"]


def test_back_out_on_the_steps_is_the_other_way(world):
    _beat(world, 1, "我在书房壁炉里翻出一本日记")
    _beat(world, 2, ops=[{"op": "move_to", "who": "player", "to": "T001/steps"}])
    _beat(world, 3, "我们离开这里,逃出这座宅子。")
    assert settlement.read(world)["exit"]["id"] == "E02"


def _english(root: Path) -> None:
    p = root / "game" / "meta" / "run_state.json"
    st = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    p.write_text(json.dumps({**st, "output_lang": "en"}, ensure_ascii=False), encoding="utf-8")


def test_in_english_the_check_line_opens_with_a_capital_and_uses_the_worlds_word(world, monkeypatch):
    from neonrp.packs.pct import tools as T

    _english(world)
    reg = load_registry(world)
    monkeypatch.setattr(T, "_d100", lambda seed, key: 10)
    text = T.san(world, reg, {"spec": "0/1d6", "why": "x"}, seed="z")["text"]
    assert text.startswith("Nerve check 10 ≤ 55") and "(Nerve 55→55)" in text and "sanity" not in text.lower(), text


def test_the_packs_english_default_is_composure_not_sanity(tmp_path, monkeypatch):
    from neonrp import prompts
    from neonrp.packs.pct import tools as T

    d = tmp_path / "plain.template"
    shutil.copytree(TPL, d)
    (d / "world" / "game" / "rules" / "rules.json").unlink()
    root = tmp_path / "run"
    TP.build(TP.load(d), root)
    _english(root)
    reg = load_registry(root)
    assert "Composure 55" in reg.entries["player"].props["sheet"]
    monkeypatch.setattr(T, "_d100", lambda seed, key: 90)  # BRP: half the score lost in one beat breaks it
    text = T.san(root, reg, {"spec": "1/30", "why": "x"}, seed="z")["text"]
    assert text.startswith("Composure check 90 > 55") and "(Composure 55→25)" in text, text
    sdk.apply(root, [], load_registry(root), turn=1)
    assert [e.name for e in effects.instances(load_registry(root))] == ["Losing control"]
    shown = json.dumps(prompts.strings("pct", "en"), ensure_ascii=False) + (Path(T.__file__).parent / "data" / "status.en.md").read_text(encoding="utf-8")
    assert "sanity" not in shown.lower() and not re.search(r"\bSAN\b", shown), "no borrowed rulebook word in the pack's English"
