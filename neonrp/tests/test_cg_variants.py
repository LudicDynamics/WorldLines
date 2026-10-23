"""结局 / 开场 / 阶段 CG 按玩家选的同伴取不同版本(niko 10-15,七夜)。

声明:结局 ``assets: {image, variants: {<sid>: 图}}``;开场 ``opening.cg[i]`` / 阶段 ``stage_cg.<n>`` 里 ``variants`` 同形。
槽位 ``<slot>@<sid>``;这一局的同伴 = 捏人选的(game/player/card.json),没有对应版本 → 通用版。

用 neon-rebirth 的拷贝自己写变体(不依赖正在补的正式图),两个同伴各开一局,结局图 / 开场 / 阶段过场各取各的;
第三个同伴没有变体 → 通用版。stub,不调模型。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from _paths import PRODUCT_TEMPLATES
from neonrp import template as TP
from neonrp.core import beat_events, sdk, settlement, stages
from neonrp.core.registry import load_registry
from neonrp.template import builder

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
DRAFT = {"fields": {"name": "早濑", "look": "黑色雨衣", "origin": "hacker", "past": "在旧地铁网的网吧里长大",
                    "regret": "那天没有接的那通电话", "attrs": {"体": 4, "技": 5, "识": 4, "魂": 4, "运": 3}}}


def _png(tag: str) -> bytes:
    return PNG + tag.encode()


@pytest.fixture(scope="module")
def tpl(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("store") / "neon-rebirth.template"
    shutil.copytree(PRODUCT_TEMPLATES / "neon-rebirth.template", d)
    pj_p = d / "plots" / "P01" / "plot.json"
    pj = json.loads(pj_p.read_text(encoding="utf-8"))
    pj["endings"]["E04"]["assets"] = {"image": "assets/t-E04.png", "variants": {"isse": "assets/t-E04-isse.png", "yomi": "assets/t-E04-yomi.png"}}
    pj["endings"]["E04"].pop("image_shows", None)
    pj["stage_cg"] = {"1": {"image": "assets/t-stage-1.png", "variants": {"yomi": "assets/t-stage-1-yomi.png"}}}
    pj_p.write_text(json.dumps(pj, ensure_ascii=False, indent=2), encoding="utf-8")
    for name in ("t-E04", "t-E04-isse", "t-E04-yomi", "t-stage-1", "t-stage-1-yomi"):
        (d / "plots" / "P01" / "assets" / f"{name}.png").write_bytes(_png(name))
    tj = json.loads((d / "template.json").read_text(encoding="utf-8"))
    tj["opening"] = {"cg": [{"image": "assets/opening/t-1.png", "variants": {"isse": "assets/opening/t-1-isse.png"}, "caption": "雨。"},
                            {"image": "assets/opening/t-2.png"}]}
    (d / "template.json").write_text(json.dumps(tj, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "assets" / "opening").mkdir(parents=True, exist_ok=True)
    for name in ("t-1", "t-1-isse", "t-2"):
        (d / "assets" / "opening" / f"{name}.png").write_bytes(_png(name))
    return d


def _run(tpl: Path, tmp: Path, sid: str) -> Path:
    t = TP.load(tpl)
    errs, norm = builder.check(t, {**DRAFT, "companion": sid})
    assert not errs, errs
    t = builder.select_cast(t, norm)
    dest = tmp / f"run-{sid}"
    TP.build(t, dest)
    builder.apply(t, dest, norm)
    return dest


def _end_e04(root: Path):
    r = sdk.apply(root, [], load_registry(root), turn=1, player_says="我用一枚书签写下:回到你的书里去吧", narration="……")
    assert r.ended and r.ended["id"] == "E04"
    return settlement.read(root) or {}


@pytest.fixture(scope="module")
def runs(tpl, tmp_path_factory) -> dict[str, Path]:
    tmp = tmp_path_factory.mktemp("runs")
    return {sid: _run(tpl, tmp, sid) for sid in ("isse", "yomi", "kuon")}


def test_two_companions_end_on_two_pictures(tpl, runs):
    t = TP.load(tpl)
    got = {}
    for sid in ("isse", "yomi"):
        root = runs[sid]
        assert TP.run_companion(root) == sid
        cg = _end_e04(root)["ending_cg"]
        assert (cg["slot"], cg["variant"]) == (f"plot:plots/P01:ending:E04@{sid}", sid)
        assert (root / cg["image"]).read_bytes() == _png(f"t-E04-{sid}")
        view = TP.run_view(root)
        assert view["companion"] == sid and view["ending"]["slot"] == cg["slot"]
        f = TP.slot_file(t, "plot:plots/P01:ending:E04", variant=sid)
        assert f == TP.slot_file(t, cg["slot"])
        got[sid] = f.read_bytes()
    assert got["isse"] != got["yomi"]


def test_no_variant_falls_back_to_the_generic_picture(tpl, runs):
    t = TP.load(tpl)
    cg = _end_e04(runs["kuon"])["ending_cg"]
    assert (cg["slot"], cg["variant"]) == ("plot:plots/P01:ending:E04", None)
    assert (runs["kuon"] / cg["image"]).read_bytes() == _png("t-E04")
    generic = TP.slot_file(t, "plot:plots/P01:ending:E04")
    assert generic.read_bytes() == _png("t-E04")
    assert TP.slot_file(t, "plot:plots/P01:ending:E04", variant="kuon") == generic
    assert TP.slot_file(t, "plot:plots/P01:ending:E04@kuon") == generic


def test_opening_and_stage_cg_follow_the_companion(runs):
    def opening(root):
        evs, _ = beat_events.from_traces([{"turn_seq": 0, "apply": {"beat": {"kind": "opening"}, "narration_plain": "雨。"}}], root=root)
        return next(d for k, d in evs if k == "plan.beat")["cg"]

    isse, yomi = opening(runs["isse"]), opening(runs["yomi"])
    assert (isse[0]["slot"], isse[0]["image"], isse[0]["variant"]) == ("opening.cg:1@isse", "assets/opening/t-1-isse.png", "isse")
    assert (yomi[0]["slot"], yomi[0]["variant"]) == ("opening.cg:1", None) and "variants" not in yomi[0]
    assert isse[1]["slot"] == "opening.cg:2"
    assert TP.run_view(runs["isse"])["opening"]["cg"][0]["slot"] == "opening.cg:1@isse"
    st = {r["plot"]: r for r in stages.changes(runs["yomi"], {"P01.stage": 0}, {"P01.stage": 1})}["P01"]
    assert (st["cg"]["slot"], st["cg"]["image"]) == ("stage.cg:P01.1@yomi", "assets/t-stage-1-yomi.png")
    st = {r["plot"]: r for r in stages.changes(runs["isse"], {"P01.stage": 0}, {"P01.stage": 1})}["P01"]
    assert (st["cg"]["slot"], st["cg"]["variant"]) == ("stage.cg:P01.1", None)
    sc = next(p for p in TP.run_view(runs["yomi"])["plots"] if p["id"] == "P01")["stage_cg"]
    assert sc[0]["slot"] == "stage.cg:P01.1@yomi"


def test_variant_slots_are_listed_filled_and_linted(tmp_path):
    d = tmp_path / "neon-rebirth.template"
    shutil.copytree(PRODUCT_TEMPLATES / "neon-rebirth.template", d)
    tj = json.loads((d / "template.json").read_text(encoding="utf-8"))
    tj["opening"] = {"cg": [{"image": "assets/opening/x.png"}]}
    (d / "template.json").write_text(json.dumps(tj, ensure_ascii=False), encoding="utf-8")
    TP.put_asset(TP.load(d), "opening.cg:1@akari", PNG)  # filling a companion's picture records it under variants
    t = TP.load(d)
    assert t.data["opening"]["cg"][0]["variants"] == {"akari": "assets/opening/cg-1-akari.png"}
    rows = {r["slot"]: r for r in TP.asset_slots(t)}
    v = rows["opening.cg:1@akari"]
    assert v["have"] and v["variant"] == "akari" and v["variant_of"] == "opening.cg:1"
    probs = TP.variant_problems(t, [{"id": "X", "endings": {"E": {"assets": {"image": "a.png", "variants": {"nobody": "b.png"}}}}}])
    assert [p.code for p in probs] == ["asset.variant"] and probs[0].level == "warn"
    from neonrp.packs.rpg import plot as rplot

    bad = rplot.lint({"id": "X", "endings": {"E": {"title": "e", "assets": {"image": "a.png", "variants": "b.png"}}}})
    assert any("variants" in p.where for p in bad)
