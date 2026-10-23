"""Player builder (面板玩家, niko 10-14): the template declares the sheet, the screen renders it, the engine checks
the made character and writes it into the run before the opening (template/builder.py)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from neonrp import template as TP
from neonrp.template import builder as B

REPO = Path(__file__).resolve().parents[1]
PCT = REPO / "worldlines" / "templates" / "pct-house.template"
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32

BUILDER = {
    "title": {"zh": "捏一个调查员", "en": "Make your investigator"},
    "fields": [
        {"id": "name", "kind": "text", "label": {"zh": "名字"}, "required": True, "max": 12, "to": "player/profile.json:name"},
        {"id": "look", "kind": "text", "multiline": True, "to": "player/profile.json:appearance"},
        {"id": "origin", "kind": "choice", "required": True, "to": "player/profile.json:origin", "options": [
            {"id": "doc", "label": {"zh": "地下医生"}, "grants": {
                "append": {"player/stats.json:skills": [{"name": "急救", "value": 70}], "player/inventory.json:items": [{"id": "kit", "name": "药箱", "qty": 1}]},
                "set": {"meta/run_state.json:location": {"node_id": "T001", "subnode_id": "study"}},
                "add": {"player/stats.json:attributes.int": 1}}},
            {"id": "cop", "label": {"zh": "退役刑警"}}]},
        {"id": "traits", "kind": "multi", "max": 2, "to": "player/profile.json:traits",
         "options": [{"id": "calm", "label": "冷静"}, {"id": "lucky", "label": "走运"}, {"id": "stubborn", "label": "固执"}]},
        {"id": "attrs", "kind": "points", "total": 20, "min": 1, "max": 8, "exact": True, "to": "player/stats.json:attributes",
         "var": "player.attr", "stats": [{"id": "ti", "label": {"zh": "体"}}, {"id": "ji", "label": {"zh": "技"}},
                                         {"id": "shi", "label": {"zh": "识"}}, {"id": "hun", "label": {"zh": "魂"}}, {"id": "yun", "label": {"zh": "运"}}]},
        {"id": "face", "kind": "portrait", "options": [{"id": "a", "src": "assets/player/a.png"}, {"id": "b", "src": "assets/player/b.png"}]},
    ],
    "companion": {"role": "companion", "pick": 1, "required": True, "cards": {"kid": {"tier": "A", "blurb": {"zh": "从绘本里来的孩子"}}}},
    "labels": {"attributes.int": {"zh": "智力", "en": "INT"}},
}

GOOD = {"fields": {"name": "真白", "look": "灰色风衣", "origin": "doc", "traits": ["calm", "lucky"],
                   "attrs": {"ti": 4, "ji": 4, "shi": 4, "hun": 4, "yun": 4}, "face": "b"}, "companion": "kid"}


@pytest.fixture
def tpl(tmp_path: Path):
    td = tmp_path / "pb.template"
    shutil.copytree(PCT, td)
    (td / "assets" / "player").mkdir(parents=True)
    for n in ("a", "b"):
        (td / "assets" / "player" / f"{n}.png").write_bytes(PNG)
    kid = td / "souls" / "kid"
    shutil.copytree(td / "world" / "souls" / "chara-si-chara0001", kid)
    sj = json.loads((kid / "soul.json").read_text(encoding="utf-8"))
    sj.update(sid="kid", name="Kid", name_local="小雀")
    (kid / "soul.json").write_text(json.dumps(sj, ensure_ascii=False), encoding="utf-8")
    d = json.loads((td / "template.json").read_text(encoding="utf-8"))
    d["id"] = "pb"
    d["souls"] = [{"sid": "chara", "role": "companion"}, {"sid": "kid", "path": "souls/kid", "role": "companion"}]
    d["player"] = {"builder": BUILDER}
    (td / "template.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return TP.load(td)


def _edit(t, fn) -> object:
    d = json.loads((t.dir / "template.json").read_text(encoding="utf-8"))
    fn(d)
    (t.dir / "template.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return TP.load(t.dir)


def _j(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def test_no_builder_block_means_nothing_changes():
    t = TP.load(PCT)
    assert not B.declared(t) and B.view(t) == {"declared": False} and B.problems(t) == []
    assert B.check(t, GOOD)[0] == ["this template declares no player builder"]


def test_view_lists_the_fields_and_the_companion_candidates(tpl):
    v = B.view(tpl)
    assert v["declared"] and v["problems"] == []
    assert [f["id"] for f in v["builder"]["fields"]] == ["name", "look", "origin", "traits", "attrs", "face"]
    face = v["builder"]["fields"][-1]
    assert all(o["image"] is True and "src" not in o for o in face["options"]), "the screen gets image flags, never paths"
    cands = {c["sid"]: c for c in v["companion"]["candidates"]}
    assert set(cands) == {"chara", "kid"}
    assert cands["kid"]["name"] == "小雀" and cands["kid"]["tier"] == "A" and cands["kid"]["blurb"]["zh"].startswith("从绘本")
    assert B.companion_image(tpl, "chara") is not None or cands["chara"]["portrait"] is False
    assert B.option_image(tpl, "face", "b").name == "b.png" and B.option_image(tpl, "face", "zz") is None


def test_check_refuses_overspent_points_and_missing_fields(tpl):
    over = json.loads(json.dumps(GOOD))
    over["fields"]["attrs"] = {"ti": 8, "ji": 8, "shi": 4, "hun": 1, "yun": 1}
    errs, _ = B.check(tpl, over)
    assert any("22 points spent, only 20" in e for e in errs)
    under = json.loads(json.dumps(GOOD))
    under["fields"]["attrs"] = {"ti": 1, "ji": 1, "shi": 1, "hun": 1, "yun": 1}
    assert any("spend all 20" in e for e in B.check(tpl, under)[0]), "exact: every point must be spent"
    bad = {"fields": {"name": "", "origin": "pirate", "traits": ["calm", "lucky", "stubborn"], "attrs": {"ti": 9, "luck": 1}, "face": "a"},
           "companion": "nobody"}
    joined = "\n".join(B.check(tpl, bad)[0])
    for want in ("name: required", "origin: 'pirate' is not an option", "traits: pick 0..2, got 3", "attrs.ti: 9 is outside 1..8",
                 "attrs: unknown stats luck", "companion: not a candidate: nobody"):
        assert want in joined, want
    assert "companion: pick 1" in "\n".join(B.check(tpl, {**GOOD, "companion": None})[0])
    long = json.loads(json.dumps(GOOD))
    long["fields"]["name"] = "x" * 13
    assert any("longer than 12" in e for e in B.check(tpl, long)[0])
    assert B.check(tpl, GOOD)[0] == []


def test_lint_reports_a_broken_declaration(tpl):
    t = _edit(tpl, lambda d: d["player"]["builder"]["fields"].extend([
        {"id": "name", "kind": "text"},
        {"id": "x", "kind": "slider"},
        {"id": "y", "kind": "text", "to": "../../etc/passwd.json:x"},
        {"id": "z", "kind": "points", "total": 3, "min": 1, "stats": [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}]},
        {"id": "p", "kind": "portrait", "options": [{"id": "q", "src": "../outside.png"}]},
        {"id": "c", "kind": "choice", "options": [{"id": "o", "grants": {"remove": {}}}]},
    ]))
    msgs = {(w, m) for lv, code, w, m in B.problems(t) if lv == "block" and code == "player.builder"}
    joined = "\n".join(f"{w}: {m}" for w, m in msgs)
    for want in ("duplicate id 'name'", "unknown kind 'slider'", "fields.y.to", "cannot spend 3 points", "fields.p.options.q.src",
                 "grants is {set, append, add}"):
        assert want in joined, want
    assert any(p["code"] == "player.builder" for p in TP.lint(t)["problems"]), "the template lint carries it"
    assert B.check(t, GOOD)[0], "a broken declaration never lets a run start"
    t2 = _edit(tpl, lambda d: d["player"]["builder"]["companion"].update(pick=3))
    assert any("pick 3 but 2 candidate" in m for _lv, _c, _w, m in B.problems(t2))


def test_apply_writes_the_card_into_the_run(tpl, tmp_path):
    errs, norm = B.check(tpl, GOOD)
    assert errs == []
    t = B.select_cast(tpl, norm)
    run = tmp_path / "run"
    rec = TP.build(t, run)
    assert rec["built"]["cast"] == ["kid"], "the companion not picked does not enter the run"
    card = B.apply(t, run, norm)
    g = run / "game"
    prof, stats, inv, rs = _j(g / "player" / "profile.json"), _j(g / "player" / "stats.json"), _j(g / "player" / "inventory.json"), _j(g / "meta" / "run_state.json")
    assert prof["name"] == "真白" and prof["appearance"] == "灰色风衣" and prof["origin"] == "doc" and prof["traits"] == ["calm", "lucky"]
    assert prof["pid"] == "player", "fields the sheet does not touch stay"
    assert stats["attributes"]["ti"] == 4 and stats["attributes"]["shi"] == 4
    assert stats["attributes"]["int"] == 15, "the origin's add lands on top of the world's value (14 + 1)"
    assert stats["attributes"]["str"] == 10, "the world's own attributes stay"
    assert {"name": "急救", "value": 70} in stats["skills"] and len(stats["skills"]) == 10, "append keeps the world's skills"
    assert [i["id"] for i in inv["items"]] == ["flashlight", "notebook", "kit"]
    assert rs["location"] == {"node_id": "T001", "subnode_id": "study"}, "the origin's opening place"
    assert (g / "player" / "assets" / "portrait.png").read_bytes() == PNG
    saved = _j(g / "player" / "card.json")
    assert saved == card and saved["schema"] == B.CARD_SCHEMA and saved["companion"] == ["kid"]
    assert saved["labels"]["origin"] == {"zh": "地下医生"} and saved["values"]["attrs"]["yun"] == 4
    variables = _j(g / "meta" / "variables.json")
    assert variables["player.attr.hun"] == {"type": "int", "path": "game/player/stats.json", "key": "attributes.hun", "min": 0, "doc": "魂"}
    from neonrp.core.registry import load_registry

    reg = load_registry(run)
    assert reg.variables["player.attr.ji"].value == 4
    assert reg.entries["player"].name == "真白" or "真白" in reg.entries["player"].aliases, "the registry's player is the made one"
    pt = _j(run / "playthrough.json")
    assert [s["sid"] for s in pt["souls"]] == ["kid"]
    assert not list((run / "souls").glob("chara-*")), "the candidate not picked leaves the run's disk (the map scans souls/)"
    assert list((run / "souls").glob("kid-*")) and (tpl.dir / "world" / "souls").is_dir(), "the template keeps its copy"
    from neonrp.core.worldmap import build_map_tree

    assert {e["id"] for e in build_map_tree(run)["entities"] if e["kind"] == "soul"} == {"kid"}


def test_run_card_reads_the_values_back_live(tpl, tmp_path):
    errs, norm = B.check(tpl, GOOD)
    t = B.select_cast(tpl, norm)
    run = tmp_path / "run"
    TP.build(t, run)
    B.apply(t, run, norm)
    sp = run / "game" / "player" / "stats.json"
    st = _j(sp)
    st["attributes"]["hun"] = 1  # play changed it (a bookmark used)
    sp.write_text(json.dumps(st), encoding="utf-8")
    c = B.run_card(run)
    assert c["live"]["attrs"] == {"ti": 4, "ji": 4, "shi": 4, "hun": 1, "yun": 4} and c["live"]["name"] == "真白"
    assert c["portrait"] is True and c["values"]["attrs"]["hun"] == 4, "values = what was made, live = now"
    assert B.run_card(tmp_path) is None


def test_library_companions_join_as_links(tpl, tmp_path):
    from neonrp.core import souls as S

    lib = Path(S.SOUL_HOME) / "mira"
    shutil.copytree(tpl.dir / "souls" / "kid", lib)
    sj = _j(lib / "soul.json")
    sj.update(sid="mira", name="Mira", name_local="米拉")
    (lib / "soul.json").write_text(json.dumps(sj, ensure_ascii=False), encoding="utf-8")
    t = _edit(tpl, lambda d: d["player"]["builder"]["companion"].update({"from": ["cast", "library"]}))
    cands = {c["sid"]: c for c in B.companions(t)}
    assert cands["mira"]["from"] == "library" and cands["mira"]["name"] == "米拉"
    errs, norm = B.check(t, {**GOOD, "companion": "mira"})
    assert errs == []
    t2 = B.select_cast(t, norm)
    run = tmp_path / "run"
    rec = TP.build(t2, run)
    assert rec["built"]["cast"] == ["mira"]


def test_new_run_checks_first_and_builds_nothing_on_refusal(tpl, tmp_path, monkeypatch):
    import neonrp.worlds as W

    made: list[Path] = []

    def fake_dir(prefix: str) -> Path:
        d = tmp_path / "plays" / f"{prefix}-{len(made)}"
        d.mkdir(parents=True)
        made.append(d)
        return d

    monkeypatch.setattr(W, "create_run_dir", fake_dir)
    monkeypatch.setattr(W, "seed_run_model", lambda *a, **k: None)
    over = json.loads(json.dumps(GOOD))
    over["fields"]["attrs"]["ti"] = 8
    with pytest.raises(B.BuilderError) as ei:
        TP.new_run(tpl, player=over)
    assert any("24 points spent" in e for e in ei.value.errors)
    assert made == [], "a refused character builds no run"
    run = TP.new_run(tpl, player=GOOD)
    assert _j(run / "game" / "player" / "card.json")["values"]["name"] == "真白"
    plain = TP.new_run(tpl)
    assert not (plain / "game" / "player" / "card.json").exists(), "without a made character the run opens as before"
    assert _j(plain / "game" / "player" / "profile.json")["name"] == "调查员"


def test_http_builder_screen_and_session_start(tpl, tmp_path, monkeypatch):
    """The screen's three calls: read the sheet, check a draft, start the run with it (400 = nothing built)."""
    import threading
    import urllib.error
    import urllib.request
    from unittest.mock import patch

    from neonrp.commands.web import make_server

    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(tpl.dir.parent))
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "studio"),
        patch("neonrp.commands.web.WebRuntime.gateway_start", lambda self: {"sid": "local", "root": self.root.name}),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def call(path, body=None, raw=False):
            req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                         method="GET" if body is None else "POST", headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    data = r.read()
                    return (r.status, data) if raw else (r.status, json.loads(data))
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read() or b"{}")
        try:
            st, v = call("/api/v1/local/templates/pb/builder")
            assert st == 200 and v["declared"] and {c["sid"] for c in v["companion"]["candidates"]} == {"chara", "kid"}
            st, img = call("/api/v1/local/templates/pb/builder/image?field=face&option=a", raw=True)
            assert st == 200 and img == PNG
            over = json.loads(json.dumps(GOOD))
            over["fields"]["attrs"]["ti"] = 8
            st, r = call("/api/v1/local/templates/pb/builder/check", over)
            assert st == 200 and r["ok"] is False and any("24 points spent" in e for e in r["errors"])
            st, r = call("/api/v1/play/session", {"slug": "tpl--pb", "output_lang": "zh", "player": over})
            assert st == 400 and r["ok"] is False and any("24 points" in e for e in r["errors"])
            assert not (tmp_path / "plays").exists() or not any((tmp_path / "plays").iterdir()), "refused = no run"
            st, r = call("/api/v1/play/session", {"slug": "tpl--pb", "output_lang": "zh", "player": GOOD})
            assert st == 200, r
            st, card = call("/api/v1/play/engine/player-card")
            assert card["values"]["name"] == "真白" and card["companion"] == ["kid"] and card["live"]["attrs"]["ti"] == 4
            st, img = call("/api/v1/play/portrait?id=player", raw=True)
            assert st == 200 and img == PNG, "the chosen face is the player's avatar"
            st, _ = call("/api/v1/play/session", {"slug": "tpl--pct-house", "output_lang": "zh"})
            st, v = call("/api/v1/local/templates/pct-house/builder")
            assert v == {"declared": False}
            assert call("/api/v1/play/engine/player-card")[1] == {}, "a template without a builder opens as before"
        finally:
            server.shutdown()


def test_derive_from_the_points_after_the_grants(tpl, tmp_path):
    """读者 hp = 6 + 体×2、共鸣 = 2 + floor(魂/3):线性 + 整除,算在出身的加成之后。"""
    t = _edit(tpl, lambda d: d["player"]["builder"].update(derive=[
        {"to": "player/stats.json:hp.current", "also": ["player/stats.json:hp.max"], "base": 6, "per": {"ti": 2}, "label": "生命"},
        {"to": "player/stats.json:resonance", "base": 2, "per": {"hun": 1}, "div": 3}]))
    d = json.loads((t.dir / "template.json").read_text(encoding="utf-8"))
    d["player"]["builder"]["fields"][2]["options"][0]["grants"]["add"]["player/stats.json:attributes.ti"] = 1
    (t.dir / "template.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    t = TP.load(t.dir)
    assert B.problems(t) == []
    draft = json.loads(json.dumps(GOOD))
    draft["fields"]["attrs"] = {"ti": 5, "ji": 4, "shi": 4, "hun": 5, "yun": 2}
    errs, norm = B.check(t, draft)
    assert errs == []
    run = tmp_path / "run"
    TP.build(B.select_cast(t, norm), run)
    card = B.apply(t, run, norm)
    st = _j(run / "game" / "player" / "stats.json")
    assert st["attributes"]["ti"] == 6, "the origin's +1"
    assert st["hp"] == {"current": 18, "max": 18}, "6 + 6×2, both targets"
    assert st["resonance"] == 3, "2 + floor(5 / 3)"
    assert card["derived"] == {"player/stats.json:hp.current": 18, "player/stats.json:resonance": 3}
    assert B.run_card(run)["live"]["__derived"] == {"player/stats.json:hp.current": 18}, "labelled ones show on the panel"
    bad = _edit(t, lambda d: d["player"]["builder"].update(derive=[{"to": "x", "per": {"nope": 1}, "div": 0}]))
    joined = "\n".join(m for _lv, _c, _w, m in B.problems(bad))
    assert "to / also" in joined and "no points stat nope" in joined and "div an int" in joined


def test_generate_a_free_text_field(tpl):
    """生平随便写(niko 10-14):没配模型 / stub → 模板的示例;配了模型 → 模型写,上下文只有玩家已经填的,不带世界设定。"""
    t = _edit(tpl, lambda d: d["player"]["builder"]["fields"].append(
        {"id": "life", "kind": "text", "multiline": True, "max": 3000, "generate": {"zh": "写一段生平"}, "label": {"zh": "生平"},
         "example": [{"zh": "你在海边长大。", "en": "You grew up by the sea."}], "to": "player/profile.json:life"}))
    assert B.problems(t) == []
    from neonrp.core.llm_stub import StubAdapter

    r = B.generate(t, "life", GOOD, lang="en", adapter=StubAdapter())
    assert r == {"text": "You grew up by the sea.", "source": "example"}
    seen = {}

    class Fake:
        def generate(self, system, user, tools=None):
            seen.update(system=system, user=user)
            return type("R", (), {"raw_output": "  你在雨里长大。 ", "proposal_text": None, "error": None})()

    r = B.generate(t, "life", GOOD, lang="zh", adapter=Fake())
    assert r == {"text": "你在雨里长大。", "source": "model"}
    assert "名字: 真白" in seen["user"] and "origin: 地下医生" in seen["user"] and "face" not in seen["user"] and "写一段生平" in seen["user"]
    assert "灰橡宅" not in seen["user"], "the world's setting is left out: the player's life is free"
    with pytest.raises(B.BuilderError):
        B.generate(t, "name", GOOD)
    long = json.loads(json.dumps(GOOD))
    long["fields"]["life"] = "长" * 3000
    assert B.check(t, long)[0] == [], "a long free text fits"
    assert B.problems(_edit(t, lambda d: d["player"]["builder"]["fields"][2].update(generate=True)))[0][2].endswith("origin.generate")


def test_option_cards_name_what_they_bring(tpl):
    """出身「带来」:加的数字用模板 labels(目标 / 点号键 / 最后一段)或点数栏的名字,列表里加的东西用 name;没名字才退回键名,lint 提醒。"""
    origin = next(f for f in B.view(tpl)["builder"]["fields"] if f["id"] == "origin")
    doc = next(o for o in origin["options"] if o["id"] == "doc")
    assert doc["brings"] == [{"label": {"zh": "智力", "en": "INT"}, "key": "int", "add": 1}, {"label": "急救"}, {"label": "药箱"}]
    assert "brings" not in next(o for o in origin["options"] if o["id"] == "cop"), "no grants, nothing to say"
    b = B.raw(tpl)
    assert B.brings(b, {"add": {"player/stats.json:attributes.ji": 2}})[0]["label"] == {"zh": "技"}, "a points stat names itself"
    assert B.brings({**b, "labels": {"player/stats.json:attributes.ji": "手艺"}}, {"add": {"player/stats.json:attributes.ji": 1}})[0]["label"] == "手艺", \
        "labels win over the stat's own name"
    t = _edit(tpl, lambda d: d["player"]["builder"].pop("labels"))
    raw_key = next(o for f in B.view(t)["builder"]["fields"] if f["id"] == "origin" for o in f["options"] if o["id"] == "doc")["brings"][0]
    assert raw_key == {"label": None, "key": "int", "add": 1}
    warns = [(w, m) for lv, code, w, m in B.problems(t) if lv == "warn" and code == "player.builder"]
    assert warns and warns[0][0].endswith("options.doc.grants.add") and "'int' has no label" in warns[0][1]
    assert not [p for p in B.problems(t) if p[0] == "block"], "only a warning: the run still opens"
