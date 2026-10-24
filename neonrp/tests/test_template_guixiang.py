"""归乡 guixiang(从 Living Canvas 移植,10-13):客家民俗恐怖 × 百分骰调查。

模板 lint 干净;能开局(作者写好的开场);规则是 pct 包 + 世界数据(定力 = 一个技能栏 + 变量 player.dingli,
关掉 san op);主线走两个名字到村口老井,三个结局都落得下;自己写的文件里没有原作规则的说法。"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from _paths import PRODUCT_TEMPLATES
from neonrp import packs, template
from neonrp.core import sdk, settlement
from neonrp.core.registry import load_registry
from neonrp.packs.pct import tools as T

TPL = PRODUCT_TEMPLATES / "guixiang.template"
GENERATED = ("spec",)  # neonrp spec sync copies the engine's own specs here (contract / ops text is the engine's)
BANNED = re.compile(r"cthulhu|克苏鲁|\bcoc\b|sanity|理智|\bSAN\b", re.IGNORECASE)
# the one allowed hit: the key that switches the engine's own op off (an op name, not content)
ALLOWED = {("world/game/meta/actions.json", '"san": null,')}


@pytest.fixture
def world(tmp_path: Path) -> Path:
    dest = tmp_path / "run"
    template.build(template.load(TPL), dest)
    return dest


def _turn(world: Path, ops: list[dict], says: str = "", turn: int = 1):
    return sdk.apply(world, ops, load_registry(world), turn=turn, player_says=says)


def _to_the_well(world: Path, *, slips: tuple[str, ...] = ("adi_slip", "shuisheng_slip")) -> int:
    steps = [[{"op": "move_to", "who": "player", "to": "T001/y1947"}],
             [{"op": "move_to", "who": "player", "to": "T001/granary"}, {"op": "flag", "key": "ledger"}],
             [{"op": "move_to", "who": "player", "to": "T001/backwell"}],
             [*([{"op": "flag", "key": "adi_slip"}] if "adi_slip" in slips else []), {"op": "move_to", "who": "player", "to": "T001/hall"}],
             [{"op": "move_to", "who": "player", "to": "T001/y1978"}],
             [{"op": "move_to", "who": "player", "to": "T001/shed"}, {"op": "flag", "key": "tally"}],
             [{"op": "move_to", "who": "player", "to": "T001/sluice"}],
             [*([{"op": "flag", "key": "shuisheng_slip"}] if "shuisheng_slip" in slips else []), {"op": "move_to", "who": "player", "to": "T001/hall"}],
             [{"op": "move_to", "who": "player", "to": "T001/well"}]]
    for i, ops in enumerate(steps, 1):
        r = _turn(world, ops, turn=i)
        assert not r.refused, r.refused
    return len(steps)


def test_lint_is_clean_and_the_template_binds_pct_and_its_contract():
    rep = template.lint(template.load(TPL))
    assert rep["counts"]["block"] == 0, [p for p in rep["problems"] if p["level"] == "block"]
    t = template.load(TPL)
    assert t.data["play_contract"] == "mystery-trpg@1" and t.pack_name == "pct"
    assert (TPL / "LICENSE-NOTICE.md").is_file() and "ORC" in (TPL / "LICENSE-NOTICE.md").read_text(encoding="utf-8")


def test_it_opens_on_the_authored_scene(world):
    assert packs.template_of(world) == "pct"
    text = (world / "game" / "meta" / "game-start.json").read_text(encoding="utf-8")
    assert "豫章堂" in text and "莲妹" in text and "十九岁" in text
    reg = load_registry(world)
    assert reg.player_location == "T001/hall"
    assert [e.name for e in reg.of_class("soul")] == ["莲妹"]
    assert {e.name for e in reg.of_class("npc")} == {"罗德昌", "罗阿娣", "罗有根", "细妹"}


# what the player can read before the reveal: none of it says who she is (the GM's own files do)
PLAYER_READS = ("soul.md", "soul.json", "character/profile.json", "background/origin.md", "background/history.md",
                "long-term-memo/learned_facts.json", "long-term-memo/important_events.md", "persona/core_traits.json")
NAMES = {"zh": ("莲妹", "秀莲婆"), "en": ("Lily", "Granny Lil"), "ja": ("ヒデ子", "ヒデ婆"), "ko": ("연이", "수련 할매")}
AGE = {"zh": "七十八", "en": "seventy-eight", "ja": "七十八", "ko": "일흔여덟"}  # her age gives her away; the granny may be missed


def test_the_companion_is_lianmei_and_the_reveal_is_kept_back():
    """10-16 (as Living Canvas): the companion is 「莲妹」, Granny Xiulian at nineteen, and nothing says so before the
    reveal (the granny is only missed: 「今夜没看见她」) — same sid (the truth quiz still takes her home), same young portrait; her soul.json carries the elder form
    (name + charter only: portrait and voice stay). Each language's stage names her its own way."""
    import json

    soul = TPL / "world" / "souls" / "xiulian-si-xiulian0001"
    sj = json.loads((soul / "soul.json").read_text(encoding="utf-8"))
    assert sj["sid"] == "xiulian" and sj["name_local"] == "莲妹"
    assert set(sj["forms"]) == {"elder"} and sj["forms"]["elder"]["name_local"] == "秀莲婆"
    assert not {"portrait", "avatar", "voice"} & set(sj["forms"]["elder"]), "the portrait / voice stay the young one"
    assert (soul / sj["forms"]["elder"]["charter"]).is_file()
    assert json.loads((soul / "character" / "stats.json").read_text(encoding="utf-8"))["age"] == 19
    plot = json.loads((TPL / "plots" / "P01" / "plot.json").read_text(encoding="utf-8"))
    assert all(t["who"] == "xiulian" for tr in plot["triggers"].values() for t in tr["then"] if t.get("to") in ("soul", "form"))
    assert (TPL / "plots" / "P01" / plot["entries"]["G106"]["assets"]["image"]).is_file()
    for eid in ("E01", "E02", "E09"):  # every ending shows her as she is, and the girl is gone
        assert "秀莲婆" in plot["endings"][eid]["text"] and "湿头发" in plot["endings"][eid]["text"]
    card = json.loads((TPL / "template.json").read_text(encoding="utf-8"))["card"]["pitch"]
    assert "莲妹" in card and "十九岁的" not in card
    for lang, (young, old) in NAMES.items():
        layer = TPL / "i18n" / lang / "world" / "souls" / soul.name
        lj = json.loads((layer / "soul.json").read_text(encoding="utf-8")) if lang != "zh" else {**sj, **json.loads((layer / "soul.json").read_text(encoding="utf-8"))}
        assert lj["name"] == young and lj["forms"]["elder"]["name"] == old
        for rel in PLAYER_READS:
            f = (layer / rel) if (layer / rel).is_file() else (soul / rel)
            body = f.read_text(encoding="utf-8")
            if rel == "soul.json":
                body = json.dumps({k: v for k, v in json.loads(body).items() if k != "forms"}, ensure_ascii=False)
            assert AGE[lang] not in body and not re.search(r"(?<![\d九])78(?!\d)", body), (lang, rel)
        if lang != "zh":
            lp = json.loads((TPL / "i18n" / lang / "plots" / "P01" / "plot.json").read_text(encoding="utf-8"))
            assert not {t.get("who") for tr in lp["triggers"].values() for t in tr.get("then", [])} - {None, "xiulian"}  # ids stay
            assert all(old in lp["endings"][eid]["text"] for eid in ("E01", "E02", "E09"))
            start = json.loads((TPL / "i18n" / lang / "world" / "game" / "meta" / "game-start.json").read_text(encoding="utf-8"))
            assert young in start["startup"]["opening_choices"][lang][-1]


def _reveal(world: Path) -> dict:
    """What the reveal left on the run: her name, aliases, charter, the shows the turns carried."""
    import json

    sd = world / "souls" / "xiulian-si-xiulian0001"
    sj = json.loads((sd / "soul.json").read_text(encoding="utf-8"))
    stp = world / "game" / "meta" / "trigger_state.json"
    st = stp.read_text(encoding="utf-8") if stp.is_file() else ""
    return {"form": sj.get("form"), "name": sj["name_local"], "aliases": sj.get("aliases") or [],
            "charter": (sd / "soul.md").read_text(encoding="utf-8"), "fired": st}


def _shown(res) -> list[str]:
    return [s["slot"] for s in res.shows]


def test_the_reveal_by_resting_both_names(world):
    """Main road: the second name settles → the well lets go of her once (name + charter, the 井水倒影 CG, a line to
    her); portrait and the sid stay, and 「莲妹」 still finds her."""
    art = world / "souls" / "xiulian-si-xiulian0001" / "assets"  # her pictures (whatever the template ships) stay put
    before = sorted(p.name for p in art.iterdir()) if art.is_dir() else []
    steps = [[{"op": "move_to", "who": "player", "to": "T001/y1947"}],
             [{"op": "flag", "key": "adi_slip"}, {"op": "move_to", "who": "player", "to": "T001/hall"}],
             [{"op": "move_to", "who": "player", "to": "T001/y1978"}]]
    for i, ops in enumerate(steps, 1):
        _turn(world, ops, turn=i)
    assert _reveal(world)["form"] is None, "one name is not enough"
    r = _turn(world, [{"op": "flag", "key": "shuisheng_slip"}], turn=4)
    got = _reveal(world)
    assert got["form"] == "elder" and got["name"] == "秀莲婆" and "莲妹" in got["aliases"]
    assert "秀莲婆" in got["charter"] and "你就是秀莲婆" in got["charter"]
    assert any(s.endswith(":entry:G106") for s in _shown(r)), r.shows
    reg = load_registry(world)
    soul = reg.of_class("soul")[0]
    assert soul.name == "秀莲婆" and reg.resolve("莲妹") == soul.id == reg.resolve("xiulian")
    assert (sorted(p.name for p in art.iterdir()) if art.is_dir() else []) == before
    memo = (world / "souls" / "xiulian-si-xiulian0001" / "short-term-memo" / "recent_events.json").read_text(encoding="utf-8")
    assert "你就是秀莲婆" in memo
    r2 = _turn(world, [{"op": "move_to", "who": "player", "to": "T001/hall"}], "你就是秀莲婆吧", turn=5)
    assert not any(s.endswith(":entry:G106") for s in _shown(r2)), "revealed once"


@pytest.mark.parametrize("how", ["keyword", "host"])
def test_the_reveal_by_naming_her_to_her_face(world, how):
    """Optional road, any time: the player names her to her face — the keyword fallback, or the host's [flag named_her]
    (it judges by meaning). Merely asking where Granny Xiulian went is not it."""
    _turn(world, [], "秀莲婆去哪了?", turn=1)
    assert _reveal(world)["form"] is None
    r = (_turn(world, [], "你就是秀莲婆,对不对?", turn=2) if how == "keyword"
         else _turn(world, [{"op": "flag", "key": "named_her"}], "你的簪子和秀莲婆那支一模一样……", turn=2))
    got = _reveal(world)
    assert got["form"] == "elder" and got["name"] == "秀莲婆"
    assert any(s.endswith(":entry:G106") for s in _shown(r)), r.shows
    assert load_registry(world).variables["flag.named_her"].value
    n = _to_the_well(world)  # the second name settling later does not reveal her twice
    assert _reveal(world)["fired"].count('"P01.true_face"') <= 1
    _turn(world, [], "我把两张名帖放进井水", turn=n + 1)
    st = settlement.read(world)
    assert st is not None and st["exit"]["id"] == "E01"


def test_an_ending_without_the_reveal_still_shows_her_as_she_is(world):
    """Every ending is a reveal (as Living Canvas): the eighth name taken before either road → she is 秀莲婆 when the
    truth quiz takes her home."""
    _turn(world, [{"op": "set", "var": "player.dingli", "value": 0}])
    assert settlement.read(world)["exit"]["id"] == "E09"
    assert _reveal(world)["name"] == "秀莲婆"


@pytest.mark.parametrize("lang", ["en", "ja", "ko"])
def test_each_language_reveals_her_under_its_own_names(tmp_path, lang):
    young, old = NAMES[lang]
    dest = tmp_path / lang
    template.build(template.load(TPL), dest, lang=lang)
    assert [e.name for e in load_registry(dest).of_class("soul")] == [young]
    says = {"en": "You're Granny Lil, aren't you?", "ja": "あんたがヒデ婆なんだろ", "ko": "네가 수련 할매지?"}[lang]
    r = _turn(dest, [], says, turn=1)
    got = _reveal(dest)
    assert got["name"] == old and young in got["aliases"]
    assert any(s.endswith(":entry:G106") for s in _shown(r)), r.shows


def test_composure_is_a_skill_and_a_variable_and_the_san_op_is_off(world):
    reg = load_registry(world)
    assert "san" not in reg.actions and "dice" in reg.actions
    assert "定力" in reg.actions["dice"].doc and "孤注一掷" in reg.actions["dice"].doc
    assert reg.variables["player.dingli"].value == 60 and reg.variables["player.hp"].value == 10
    r = T.dice(world, reg, {"dice": "定力", "seed_key": "k"}, seed="s")
    assert r["ok"] and r["vs"] == 60 and r["label"] == "定力"
    _turn(world, [{"op": "add", "var": "player.dingli", "delta": -3}])
    reg = load_registry(world)
    assert reg.variables["player.dingli"].value == 57
    r = T.dice(world, reg, {"dice": "定力", "seed_key": "k2"}, seed="s")
    assert r["vs"] == 57, "the check reads the eroded value"


def test_the_second_name_waits_for_the_first(world):
    _turn(world, [{"op": "move_to", "who": "player", "to": "T001/y1978"}], turn=1)
    st = (world / "game" / "meta" / "trigger_state.json").read_text(encoding="utf-8")
    assert "P01.gate1978" in st and "P01.enter1978" not in st


@pytest.mark.parametrize("says,ending", [("我把两张名帖放进井水", "E01"), ("我决定封井,把井封死", "E02"),
                                         ("井里有人喊我的小名——我应一声", "E09")])
def test_the_main_line_reaches_each_ending_at_the_well(world, says, ending):
    n = _to_the_well(world)
    reg = load_registry(world)
    assert reg.variables["P01.names"].value == 2 and reg.variables["P01.stage"].value == 3
    _turn(world, [], says, turn=n + 1)
    st = settlement.read(world)
    assert st is not None and st["exit"]["id"] == ending, st


def test_the_well_refuses_half_the_names(world):
    n = _to_the_well(world, slips=("adi_slip",))
    _turn(world, [], "我把名帖放进井水", turn=n + 1)
    assert settlement.read(world) is None
    assert "P01.not_accepted" in (world / "game" / "meta" / "trigger_state.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("var", ["player.dingli", "player.hp"])
def test_composure_or_body_at_zero_is_the_eighth_name(world, var):
    _turn(world, [{"op": "set", "var": var, "value": 0}])
    st = settlement.read(world)
    assert st is not None and st["exit"]["id"] == "E09", st


def test_own_files_carry_none_of_the_source_rules_words():
    hits = []
    for p in TPL.rglob("*"):
        rel = p.relative_to(TPL)
        if not p.is_file() or rel.parts[0] in GENERATED or p.suffix not in (".md", ".json", ".txt"):
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if BANNED.search(line) and (str(rel), line.strip()) not in ALLOWED:
                hits.append(f"{rel}:{i}")
    assert not hits, hits
