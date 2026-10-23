"""七夜 (worldlines/templates/neon-rebirth.template) — an original reader × reborn battle royale on the rpg pack (10-14).

The template lints clean on its contract (mystery-trpg@1); the player makes a reader through the template's player
builder and picks one of four reborn companions (the other three never enter the run); five pairs (the player + four
state-approved teams) play seven nights on data alone (day → night → dawn; on scheduled dawns the machine erases a pair
when nobody was erased that night, never the last one standing against you); a reborn's law can be data (the hero's
blessing brings him back once); every ending — the true one, two wins, four ways to lose, the release and the reversal —
is reachable through the plot's triggers; bookmarks cost resonance and reach the companion; the folder carries none of
another work's proper nouns (outside the engine-generated ``spec/``)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from neonrp import packs, template
from neonrp.core import scene_cg, sdk, settlement
from neonrp.core.registry import load_registry

builder = pytest.importorskip("neonrp.template.builder")

TPL = Path(__file__).resolve().parents[1] / "worldlines" / "templates" / "neon-rebirth.template"
FORBIDDEN = re.compile(r"\bservant\b|\bmaster\b|令咒|圣杯|英灵|宝具|type-?moon|\bfate\b|从者|御主", re.IGNORECASE)
CANDIDATES = {"isse": "伊瑟", "yomi": "夜见", "kuon": "久远", "akari": "灯"}
READERS = {"九条迅", "顾晚", "Rin", "霍克", "白濑澪", "无名读者"}
AUTO = {2: "rin", 4: "gu", 6: "kujo"}  # the dawns the machine acts on, and whom it takes
DRAFT = {"fields": {"name": "早濑", "look": "黑色雨衣,左耳一枚银色耳钉", "origin": "hacker", "past": "在旧地铁网的网吧里长大",
                    "regret": "那天没有接的那通电话", "attrs": {"体": 4, "技": 5, "识": 4, "魂": 4, "运": 3}},
         "companion": "kuon"}


def _rules() -> dict:
    return json.loads((TPL / "world" / "game" / "rules" / "rebirth.json").read_text(encoding="utf-8"))


@pytest.fixture
def world(tmp_path: Path) -> Path:
    """A run made the way the play screen makes one: the builder's draft checked, the cast narrowed, built, written."""
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


def _var(root: Path, name: str):
    return load_registry(root).variables[name].value


def _flags(root: Path) -> set[str]:
    return {k[5:] for k, v in load_registry(root).variables.items() if k.startswith("flag.") and v.value}


def _exit(root: Path) -> str | None:
    return ((settlement.read(root) or {}).get("exit") or {}).get("id")


def _phase(root: Path, turn: int, phase: str):
    return _beat(root, turn, "……", [{"op": "set", "var": "phase", "value": phase}])


def _night(root: Path, turn: int, ops_at_night: list | None = None) -> tuple[int, object]:
    """One whole night: nightfall → (what the player does) → dawn → the next day. Returns (next turn, the dawn result)."""
    _phase(root, turn, "night")
    if ops_at_night:
        _beat(root, turn + 1, "……", ops_at_night)
    r = _phase(root, turn + 2, "dawn")
    if r.ended:
        return turn + 3, r
    r2 = _phase(root, turn + 3, "day")
    return turn + 4, (r2 if r2.ended else r)


# ── the template ─────────────────────────────────────────────────────────────

def test_lints_clean_on_its_contract():
    t = template.load(TPL)
    rep = template.lint(t)
    assert rep["counts"]["block"] == 0, [p for p in rep["problems"] if p["level"] == "block"]
    assert t.data["play_contract"] == "mystery-trpg@1" and t.pack_name == "rpg"
    plot = json.loads((TPL / "plots" / "P01" / "plot.json").read_text(encoding="utf-8"))
    assert {e: v["kind"] for e, v in plot["endings"].items()} == {"E01": "true", "E02": "alt", "E08": "alt", "E03": "fail", "E05": "fail",
                                                                  "E06": "fail", "E07": "fallback", "E04": "alt", "E09": "alt"}
    assert len(plot["stages"]) == 8 and plot["reveal"]["zh"]
    assert _rules()["groups"] == 5 and _rules()["nights"] == 7


def test_the_art_is_in_its_slots():
    """10-14 art: cover, opening CG (in play order), the second-night cut-scene, nine endings, maps, every soul's portrait
    (the four reborn, the four readers, the two outsiders), the rival reborn, the nine places and three items."""
    t = template.load(TPL)
    rows = {r["slot"]: r for r in template.asset_slots(t)}
    want = (["card:cover", "level.map:world", "level.map:T001", "stage.cg:P01.1"]
            + [f"opening.cg:{n}" for n in range(1, 8)]
            + [f"plot:plots/P01:ending:{e}" for e in ("E01", "E02", "E03", "E04", "E05", "E06", "E07", "E08", "E09")]
            + [f"soul.portrait:{s}" for s in (*CANDIDATES, "kujo", "gu", "rin", "hawk", "shirase", "nameless")]
            + [f"npc.portrait:{s}" for s in ("saku", "shen", "yoon", "hai")]
            + [f"place.scene:T001/{p}" for p in ("bookstore", "shinjuku_dome", "bayside", "clinic", "datacenter", "kujo_tower",
                                                  "machine_core", "neon_alley", "underground")]
            + [f"item.icon:{i}" for i in ("I801", "I802", "I804")])
    missing = [s for s in want if not (rows.get(s) or {}).get("have")]
    assert not missing, missing
    assert scene_cg.opening(t.data)[-1][1]["caption"]["zh"].startswith("书架之间")  # the reborn steps out last, then the first beat
    for s in ("opening.cg:1", "stage.cg:P01.1", "soul.portrait:kuon"):
        f = template.slot_file(t, s)
        assert f is not None and f.suffix == ".webp" and f.stat().st_size < 1_500_000, s
    assert all(builder.companion_image(t, sid) for sid in CANDIDATES)  # the pick screen shows each reborn's portrait


def test_the_opening_cg_reaches_the_run(world):
    view = template.run_view(world) or {}
    cg = (view.get("opening") or {}).get("cg") or []
    assert [c["slot"] for c in cg] == [f"opening.cg:{n}" for n in range(1, 8)]
    assert any(c.get("slot") == "stage.cg:P01.1" for p in view.get("plots") or [] for c in p.get("stage_cg") or [])


def test_the_builder_declares_a_reader_and_four_reborn():
    t = template.load(TPL)
    v = builder.view(t)
    assert v["declared"] and not v["problems"]
    fields = {f["id"]: f for f in v["builder"]["fields"]}
    assert set(fields) == {"name", "gender", "face", "look", "origin", "past", "regret", "attrs"}
    assert [o["id"] for o in fields["gender"]["options"]] == ["female", "male", "unset"] and not fields["gender"].get("required")
    assert all(builder.option_image(t, "face", o["id"]) for o in fields["face"]["options"]), "each default portrait is in the template"
    pts = fields["attrs"]
    assert (pts["total"], pts["min"], pts["max"]) == (20, 1, 7) and [s["id"] for s in pts["stats"]] == ["体", "技", "识", "魂", "运"]
    assert len(fields["origin"]["options"]) == 6
    cands = {c["sid"]: c for c in v["companion"]["candidates"]}
    assert set(cands) == set(CANDIDATES) and v["companion"]["pick"] == 1
    R = _rules()["rebirth"]["tiers"]
    for sid, c in cands.items():
        assert c["name"] == CANDIDATES[sid] and c["tier"].startswith("笔力")
        st = json.loads((TPL / "world" / "souls" / f"{sid}-si-{sid}01" / "character" / "stats.json").read_text(encoding="utf-8"))
        depth = re.search(r"厚度([SABCD])", c["tier"]).group(1)
        assert st["hp"] == R["depth"][depth]["hp"], f"{sid}: hp is the depth tier's"
    errs, _ = builder.check(t, {**DRAFT, "fields": {**DRAFT["fields"], "attrs": {"体": 7, "技": 7, "识": 4, "魂": 4, "运": 3}}})
    assert any("20" in e for e in errs), "25 points do not fit 20"
    errs, _ = builder.check(t, {**DRAFT, "companion": "raike"})
    assert errs, "a rival's reborn is not a candidate"


def test_rival_reborn_stats_come_from_the_tier_table():
    R = _rules()["rebirth"]["tiers"]
    npcs = json.loads((TPL / "world" / "game" / "towns" / "T001" / "npcs.json").read_text(encoding="utf-8"))["npcs"]
    assert {n["id"] for n in npcs} == {"saku", "shen", "yoon", "hai"}
    for n in npcs:
        p, d = R["power"][n["tier"]["power"]], R["depth"][n["tier"]["depth"]]
        assert (n["hp"], n["def"], n["atk"], n["dmg"]) == (d["hp"], d["def"], p["atk"], p["dmg"]), n["id"]
        assert n["finale"] == R["finale"][n["tier"]["finale"]]


def test_without_a_draft_every_candidate_is_on_hand(tmp_path):
    dest = tmp_path / "run"
    template.build(template.load(TPL), dest)
    reg = load_registry(dest)
    assert {e.name for e in reg.of_class("soul")} == set(CANDIDATES.values()) | READERS


# ── the reader the player made ───────────────────────────────────────────────

def test_the_draft_lands_and_only_the_picked_reborn_enters(world):
    assert packs.template_of(world) == "rpg"
    reg = load_registry(world)
    assert reg.player_location == "T001/bookstore"
    assert {e.name for e in reg.of_class("soul")} == {"久远"} | READERS
    assert {e.id for e in reg.of_class("place")} >= {f"T001/{p}" for p in ("bookstore", "datacenter", "machine_core", "kujo_tower")}
    p = reg.entries["player"].props
    assert p["name"] == "早濑" and p["class"] == "骇客" and p["summary"] == "那天没有接的那通电话"
    assert p["attributes"] == {"体": 4, "技": 6, "识": 4, "魂": 4, "运": 3}, "the hacker origin adds 1 to 技"
    assert "骇入" in p["sheet"] and "改装过的终端" in p["sheet"]
    assert reg.variables["player.attr.技"].value == 6
    assert (_var(world, "bookmarks"), _var(world, "resonance"), _var(world, "night"), _var(world, "groups.left")) == (3, 3, 1, 5)
    installed = json.loads((world / "game" / "plots" / "P01" / "plot.json").read_text(encoding="utf-8"))
    whos = [e.get("who") for e in installed["triggers"]["P01.bookmark"]["then"] if e.get("to") == "soul"]
    assert whos == ["久远"], "the bookmark reaches only the reborn the player picked"


def test_life_and_resonance_come_from_the_points(tmp_path):
    t = template.load(TPL)
    errs, norm = builder.check(t, {**DRAFT, "fields": {**DRAFT["fields"], "origin": "doctor", "attrs": {"体": 7, "技": 3, "识": 3, "魂": 6, "运": 1}}})
    assert not errs, errs
    t = builder.select_cast(t, norm)
    dest = tmp_path / "run"
    template.build(t, dest)
    builder.apply(t, dest, norm)
    st = json.loads((dest / "game" / "player" / "stats.json").read_text(encoding="utf-8"))
    assert st["attributes"]["体"] == 8, "the doctor origin adds 1 to 体"
    assert st["hp"] == {"current": 22, "max": 22}, "6 + 体×2, after the origin's grant"
    assert st["resonance"] == 4, "2 + floor(魂 / 3)"
    assert _var(dest, "player.hp") == 22 and _var(dest, "resonance") == 4


def test_a_bookmark_costs_resonance_and_reaches_the_reborn(world):
    r = _beat(world, 1, "我抽出一枚书签:「别管我,先救那个孩子」", [{"op": "add", "var": "bookmarks", "delta": -1}])
    assert any(t.get("trigger") == "P01.bookmark" for t in r.triggered)
    assert (_var(world, "bookmarks"), _var(world, "resonance")) == (2, 2)
    st = json.loads((world / "game" / "player" / "stats.json").read_text(encoding="utf-8"))
    assert st["bookmarks"] == 2 and st["resonance"] == 2


# ── the seven nights ─────────────────────────────────────────────────────────

def test_the_machine_erases_on_its_dawns_and_leaves_the_last_pair_to_you(world):
    turn = 1
    for n in range(1, 8):
        assert _var(world, "night") == n
        left = _var(world, "groups.left")
        turn, r = _night(world, turn)
        if n in AUTO:
            gid = AUTO[n]
            assert any(t.get("trigger") == f"P01.dawn_erase_{gid}" for t in r.triggered), (n, gid)
            assert f"closed_{gid}" in _flags(world) and _var(world, "groups.left") == left - 1
        else:
            assert _var(world, "groups.left") == left, n
        if n < 7:
            assert not r.ended, n
    assert _var(world, "groups.left") == 2 and "closed_hawk" not in _flags(world), "the last pair against you is never the machine's"
    assert r.ended and r.ended["id"] == "E07" and _exit(world) == "E07", "the seventh night passes with two pairs left"


def test_erasing_a_pair_yourself_spares_the_machines_turn(world):
    turn, _ = _night(world, 1)
    turn, r = _night(world, turn, [{"op": "add", "var": "char.shen.hp", "delta": -22}])
    assert "closed_gu" in _flags(world) and _var(world, "groups.left") == 4
    assert not any(t.get("trigger", "").startswith("P01.dawn_erase_") for t in r.triggered)
    assert any(t.get("trigger") == "P01.dawn_quiet" for t in r.triggered)
    assert "closed_rin" not in _flags(world)
    turn, _ = _night(world, turn)
    turn, r = _night(world, turn)
    assert any(t.get("trigger") == "P01.dawn_erase_rin" for t in r.triggered), "on its next dawn the machine resumes"


def test_the_heros_blessing_brings_him_back_once(world):
    _phase(world, 1, "night")
    r = _beat(world, 2, "灯一刀砍穿了白披风", [{"op": "add", "var": "char.saku.hp", "delta": -26}])
    assert any(t.get("trigger") == "P01.saku_blessing" for t in r.triggered)
    assert "closed_kujo" not in _flags(world) and _var(world, "char.saku.hp") == 13
    _beat(world, 3, "再来一次", [{"op": "add", "var": "char.saku.hp", "delta": -13}])
    assert "closed_kujo" in _flags(world) and _var(world, "groups.left") == 4


@pytest.mark.parametrize("resonance, ending", [(3, "E08"), (7, "E02")], ids=["won-apart", "won-together"])
def test_the_last_pair_standing_wins_and_how(world, resonance, ending):
    if resonance > 3:
        _beat(world, 1, "……", [{"op": "add", "var": "resonance", "delta": 2}])
        _beat(world, 2, "……", [{"op": "add", "var": "resonance", "delta": 2}])
    turn, _ = _night(world, 3, [{"op": "add", "var": "char.hai.hp", "delta": -18}])
    for _ in range(4):  # nights 2–5: the machine takes Rin and Gu, then stops — two pairs left
        turn, r = _night(world, turn)
        assert not r.ended
    assert _var(world, "groups.left") == 2 and _var(world, "night") == 6
    _phase(world, turn, "night")
    _beat(world, turn + 1, "……", [{"op": "add", "var": "char.saku.hp", "delta": -26}])
    r = _beat(world, turn + 2, "……", [{"op": "add", "var": "char.saku.hp", "delta": -13}])
    assert r.ended and r.ended["id"] == ending and _exit(world) == ending
    assert _var(world, "groups.left") == 1


def test_rewriting_the_rule_is_the_true_ending(world):
    r = _beat(world, 1, "去数据中心", [{"op": "move_to", "who": "player", "to": "T001/underground"},
                                      {"op": "move_to", "who": "player", "to": "T001/datacenter"}])
    vr = sdk.verify(world, [{"op": "move_to", "who": "player", "to": "T001/machine_core"}], load_registry(world))
    assert vr.refused and not vr.accepted, "no white bookmark: the door stays shut (machine_core enter_if)"
    _beat(world, 3, "白濑说出了真相", [{"op": "move_to", "who": "player", "to": "T001/datacenter"}, {"op": "flag", "key": "truth_eating"}])
    _beat(world, 4, "无名读者把白色的书签交给我", [{"op": "flag", "key": "truth_core_key"}])
    r = _beat(world, 5, "进去", [{"op": "move_to", "who": "player", "to": "T001/machine_core"}])
    assert any(t.get("trigger") == "P01.core_open" for t in r.triggered) and _var(world, "P01.stage") == 7
    r = _beat(world, 6, "我把书签按在那页空白的纸上,写下新的规则:谁也不必被抹去")
    assert r.ended and r.ended["id"] == "E01" and _exit(world) == "E01"
    assert _var(world, "bookmarks") == 2


def test_writing_your_own_name_is_the_reversal(world):
    _beat(world, 1, "无名读者看着我:你就是那个孩子", [{"op": "flag", "key": "truth_self"}, {"op": "flag", "key": "truth_core_key"},
                                                  {"op": "move_to", "who": "player", "to": "T001/underground"}])
    _beat(world, 2, "……", [{"op": "move_to", "who": "player", "to": "T001/datacenter"}])
    _beat(world, 3, "……", [{"op": "move_to", "who": "player", "to": "T001/machine_core"}])
    r = _beat(world, 4, "我用书签在那页纸上写下我的名字")
    assert r.ended and r.ended["id"] == "E09" and _exit(world) == "E09"


def test_no_bookmark_left_no_rewrite(world):
    _beat(world, 1, "……", [{"op": "flag", "key": "truth_eating"}, {"op": "flag", "key": "truth_core_key"},
                          {"op": "move_to", "who": "player", "to": "T001/underground"}])
    _beat(world, 2, "……", [{"op": "move_to", "who": "player", "to": "T001/datacenter"}])
    _beat(world, 3, "……", [{"op": "move_to", "who": "player", "to": "T001/machine_core"}])
    for i in range(3):
        _beat(world, 4 + i, "/bookmark", [{"op": "add", "var": "bookmarks", "delta": -1}])
    r = _beat(world, 8, "我用书签改写规则")
    assert not (r.ended and r.ended.get("id") == "E01")


@pytest.mark.parametrize("ops, ending", [
    ([{"op": "flag", "key": "closed_player"}], "E03"),
    ([{"op": "add", "var": "resonance", "delta": -2}, {"op": "add", "var": "resonance", "delta": -1}], "E05"),
    ([{"op": "add", "var": "player.hp", "delta": -14}], "E06"),
], ids=["reborn-falls", "resonance-fades", "reader-falls"])
def test_each_way_to_lose_has_its_own_ending(world, ops, ending):
    r = None
    for i, op in enumerate(ops, start=1):
        r = _beat(world, i, "……", [op])
    assert r.ended and r.ended["id"] == ending and _exit(world) == ending


def test_a_female_reader_is_written_as_her(tmp_path):
    """10-15: the reader may be a woman — the sheet says so, the avatar is hers, and nothing in the folder fixes the
    player (or the companion, two of whom are women) to 他."""
    w = _run(tmp_path, "yomi", gender="female", face="reader-f")
    prof = json.loads((w / "game" / "player" / "profile.json").read_text(encoding="utf-8"))
    assert (prof["gender"], prof["pronouns"]) == ("女", "她")
    assert (w / "game" / "player" / "assets" / "portrait.webp").read_bytes() == (TPL / "assets" / "player" / "reader-f.webp").read_bytes()
    assert "pronouns" in (TPL / "prompts" / "world.md").read_text(encoding="utf-8"), "the world agent is told how to refer to the player"
    plot = json.loads((TPL / "plots" / "P01" / "plot.json").read_text(encoding="utf-8"))
    said = [e["text"] for e in plot["endings"].values()] + [x.get("text", "") for tr in plot["triggers"].values() for x in tr.get("then") or []
                                                             if isinstance(x, dict) and x.get("to") in ("narration", "soul")]
    assert not [t for t in said if re.search(r"你的转生者[^。]*他|你和他|他看你", t)], "the companion is not 他 by default"


def test_every_gender_has_its_own_portraits(tmp_path):
    """10-15: 女 has women's portraits, 不指定 has androgynous ones (not just the hood), each a real image of its own;
    every language labels all of them."""
    tj = json.loads((TPL / "template.json").read_text(encoding="utf-8"))
    face = next(f for f in tj["player"]["builder"]["fields"] if f["id"] == "face")
    ids = [o["id"] for o in face["options"]]
    assert {"reader-f", "reader-f2", "reader-f3", "reader-m", "reader-n", "reader-n2", "reader-hood"} <= set(ids)
    blobs = [(TPL / o["src"]).read_bytes() for o in face["options"]]
    assert len(set(blobs)) == len(blobs), "no two portrait options are the same picture"
    at = [f["id"] for f in tj["player"]["builder"]["fields"]].index("face")   # language layers line up by position
    for lang in ("en", "ja", "ko"):
        lj = json.loads((TPL / "i18n" / lang / "template.json").read_text(encoding="utf-8"))
        opts = lj["player"]["builder"]["fields"][at]["options"]
        assert len(opts) == len(ids) and all(o.get("label") for o in opts), lang
    w = _run(tmp_path, "kuon", gender="unset", face="reader-n")
    prof = json.loads((w / "game" / "player" / "profile.json").read_text(encoding="utf-8"))
    assert prof["gender"] == "未指定"
    assert (w / "game" / "player" / "assets" / "portrait.webp").read_bytes() == (TPL / "assets" / "player" / "reader-n.webp").read_bytes()


def _run(tmp_path: Path, sid: str, **fields) -> Path:
    t = template.load(TPL)
    errs, norm = builder.check(t, {**DRAFT, "fields": {**DRAFT["fields"], **fields}, "companion": sid})
    assert not errs, errs
    t = builder.select_cast(t, norm)
    dest = tmp_path / sid
    template.build(t, dest)
    builder.apply(t, dest, norm)
    return dest


def _win_together(world: Path) -> None:
    _beat(world, 1, "……", [{"op": "add", "var": "resonance", "delta": 2}])
    _beat(world, 2, "……", [{"op": "add", "var": "resonance", "delta": 2}])
    turn, _ = _night(world, 3, [{"op": "add", "var": "char.hai.hp", "delta": -18}])
    for _ in range(4):
        turn, _r = _night(world, turn)
    _phase(world, turn, "night")
    _beat(world, turn + 1, "……", [{"op": "add", "var": "char.saku.hp", "delta": -26}])
    r = _beat(world, turn + 2, "……", [{"op": "add", "var": "char.saku.hp", "delta": -13}])
    assert r.ended and r.ended["id"] == "E02"


def test_the_ending_art_shows_the_companion_you_picked(tmp_path):
    """10-15: 一起留下 has a picture per reborn (variants); two runs with two companions end on two different pictures —
    run_view, the settlement and the slot file all agree; the generic slot stays the template's own picture."""
    t = template.load(TPL)
    seen = {}
    for sid in ("isse", "yomi"):
        w = _run(tmp_path, sid, gender="female")
        assert template.run_companion(w) == sid
        _win_together(w)
        st = settlement.read(w) or {}
        cg = st.get("ending_cg") or {}
        assert cg.get("id") == "E02" and cg.get("variant") == sid and cg["slot"] == f"plot:plots/P01:ending:E02@{sid}"
        assert (w / cg["image"]).is_file() and cg["image"].endswith(f"ending-E02-{sid}.webp")
        view = template.run_view(w) or {}
        assert view["companion"] == sid and view["ending"]["slot"] == cg["slot"]
        f = template.slot_file(t, "plot:plots/P01:ending:E02", variant=sid)
        assert f is not None and f == template.slot_file(t, cg["slot"])
        seen[sid] = f.read_bytes()
    assert seen["isse"] != seen["yomi"], "each companion ends on their own picture"
    assert template.slot_file(t, "plot:plots/P01:ending:E02").name == "ending-E02-isse.webp", "no variant asked → the generic one"


def test_without_a_variant_the_generic_picture_shows(world):
    """久远 has no picture of his own for 放回书里: the run gets the generic slot; asking for his variant falls back to it."""
    t = template.load(TPL)
    r = _beat(world, 1, "我用一枚书签写下:回到你的书里去吧")
    assert r.ended and r.ended["id"] == "E04"
    st = settlement.read(world) or {}
    assert st["ending_cg"]["slot"] == "plot:plots/P01:ending:E04" and st["ending_cg"]["variant"] is None
    assert (template.run_view(world) or {})["ending"]["slot"] == "plot:plots/P01:ending:E04"
    generic = template.slot_file(t, "plot:plots/P01:ending:E04")
    assert generic is not None and template.slot_file(t, "plot:plots/P01:ending:E04", variant="kuon") == generic
    assert template.slot_file(t, "plot:plots/P01:ending:E04@kuon") == generic


def test_variants_are_linted():
    """A variant for someone who is not a soul here is warned; a generic picture that draws one companion is warned for
    the others until they have theirs (10-15: 一起留下 and E01 now have all four)."""
    t = template.load(TPL)
    probs = template.variant_problems(t, [{"id": "X", "endings": {"E": {"assets": {"image": "a.webp", "variants": {"nobody": "b.webp"}}}}}])
    assert [p.code for p in probs] == ["asset.variant"] and "nobody" in probs[0].where
    rep = template.lint(t)
    shows = [p for p in rep["problems"] if p["code"] == "asset.variant"]
    assert {p["where"].split(".")[2] for p in shows} == {"E04", "E05", "E06", "E08", "E09"}, shows
    assert all(p["level"] == "warn" for p in shows)


def test_putting_him_back_in_the_book(world):
    r = _beat(world, 1, "我用一枚书签写下:回到你的书里去吧")
    assert r.ended and r.ended["id"] == "E04" and _exit(world) == "E04"


def test_hawks_notebook_is_left_behind_once_he_is_erased(world):
    _beat(world, 1, "……", [{"op": "move_to", "who": "player", "to": "T001/underground"}])
    _beat(world, 2, "……", [{"op": "move_to", "who": "player", "to": "T001/bayside"}])
    _beat(world, 3, "翻他车里的记事本")
    assert "hawk_note" not in _flags(world), "not while he is still in the game"
    _beat(world, 4, "……", [{"op": "flag", "key": "closed_hawk"}])
    _beat(world, 5, "翻翻地上的记事本")
    assert "hawk_note" in _flags(world)


# ── play ─────────────────────────────────────────────────────────────────────

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
    for text in ("开始游戏", "「……你是从书里出来的?」", "看看手里的书签", "我们去新宿的广场看看"):
        assert s.send(text).success, text
    reg = load_registry(world)
    assert reg.player_location in {e.id for e in reg.of_class("place")}
    assert _var(world, "night") == 1


# ── words ────────────────────────────────────────────────────────────────────

def test_no_other_works_words_in_the_folder():
    hits = []
    for f in TPL.rglob("*"):
        if f.is_file() and f.suffix in (".json", ".md", ".txt") and f.relative_to(TPL).parts[0] != "spec":  # spec/ is the engine's
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if FORBIDDEN.search(line):
                    hits.append(f"{f.relative_to(TPL)}:{n}")
    assert not hits, hits


def test_the_names_live_in_one_table():
    terms = json.loads((TPL / "world" / "game" / "rules" / "terms.json").read_text(encoding="utf-8"))
    rules = (TPL / "world" / "game" / "rules" / "rules.md").read_text(encoding="utf-8")
    for key in ("world", "machine", "rebirth", "reader", "bookmark", "resonance", "finale", "rule", "power", "depth", "closed", "other_world", "same_world"):
        assert terms[key]["zh"] in rules, key
