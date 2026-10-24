"""创作台的编排模板(10-18 / 10-19 阶段 A):网页默认区 / iOS / 本地创作台从官方模板里选一套,选了看这套的执行图 —— 只读。

- 世界的选项 = 编排模板(core/orch_templates:引擎 neonrp/orchestrations/ + 私有层 orchestrations/<id>/);开源引擎有
  「一句一拍 · legacy」「一句一拍 · S-judge」,私有层加「两拍 · S-judge」(快商量是它的参数 pace=quick,不再是单独一套)
- 每个模板对每个开放创作的世界都出一张图:核心节点(带步骤)+ 世界自己的层 + 边,文字四语
- 私有编排只露节点名和说明:不带提示词、工具、参数名和值(参数只露名字和每个选项的说明)
- 表单多一份 orchestration {default, options};作品把选中的存成 template.json 的 uses(每次从世界算,换模板不留旧设置)
- 路由 GET /api/v1/local/templates/<id>/creation/orchestration"""
from __future__ import annotations

import json
import os
import shutil
import threading
import urllib.request
from pathlib import Path

import pytest

from neonrp import template as TP
from neonrp.core import node_kinds, orch_presets as O
from neonrp.core.paths import private_dir
from neonrp.template import creation
from _paths import PRODUCT

TPLS = PRODUCT / "templates"
LANGS = {"zh", "en", "ja", "ko"}
PRIVATE = node_kinds.get("plan") is not None and private_dir("orchestrations") is not None
needs_private = pytest.mark.skipif(not PRIVATE, reason="needs the private layer (the planning beat's presets)")


@pytest.fixture
def desk(tmp_path, monkeypatch):
    ro, mine = tmp_path / "official", tmp_path / "mine"
    for n in ("stoneford-town", "pct-house"):
        shutil.copytree(TPLS / f"{n}.template", ro / f"{n}.template", ignore=shutil.ignore_patterns("__pycache__"))
    mine.mkdir()
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", f"{mine}{os.pathsep}{ro}")
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(mine))
    return mine


def _t(tid):
    return TP.load(TP.discover()[tid])


def _open(tid):
    """A copy of ``tid`` that opens a creation layer (pct-house itself opens none)."""
    t = _t(tid)
    if not t.data.get("creation"):
        f = t.dir / "template.json"
        d = json.loads(f.read_text(encoding="utf-8"))
        d["creation"] = {"add": ["soul", "ending"], "collect": ["clear"]}
        f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        t = _t(tid)
    return t


def _texts(v, path=""):
    """Every {lang: text} dict in a view, with where it is."""
    if isinstance(v, dict) and v and set(v) <= LANGS:
        yield path, v
    elif isinstance(v, dict):
        for k, x in v.items():
            yield from _texts(x, f"{path}.{k}")
    elif isinstance(v, list):
        for i, x in enumerate(v):
            yield from _texts(x, f"{path}[{i}]")


def _keys(v):
    if isinstance(v, dict):
        for k, x in v.items():
            yield k
            yield from _keys(x)
    elif isinstance(v, list):
        for x in v:
            yield from _keys(x)


def test_the_open_engine_offers_the_single_beat_only(monkeypatch):
    monkeypatch.setenv("NEONRP_PRIVATE", "off")
    assert [p["id"] for p in O.presets()] == ["one_beat"]


@needs_private
def test_the_private_layer_adds_the_two_beat_template():
    assert [p["id"] for p in O.presets()] == ["two_beat", "one_beat"]
    assert O.get("two_beat")["nodes"] == ["plan", "resolve"]
    assert O.get("two_beat?pace=quick")["id"] == "two_beat", "a choice with a parameter names its template"
    assert O.presets()[0]["params"] == {"pace": ["normal", "quick"]}, "the quick pace is a parameter, not a preset"


@needs_private
def test_each_world_plays_the_template_it_names(desk):
    assert O.default_for(_t("stoneford-town")) == "two_beat", "10-19: every world plays the two beats in the private layer"
    assert O.default_for(_t("pct-house")) == "two_beat"


def test_on_the_open_engine_a_private_template_falls_back(desk, monkeypatch):
    monkeypatch.setenv("NEONRP_PRIVATE", "off")
    assert O.default_for(_t("pct-house")) == "one_beat", "the plain turn"


@needs_private
def test_an_old_package_without_uses_gets_the_template_it_used_to_imply(desk):
    for tid, want in (("stoneford-town", "two_beat"), ("pct-house", "two_beat")):
        t = _t(tid)
        f = t.dir / "template.json"
        d = json.loads(f.read_text(encoding="utf-8"))
        d.pop("uses")
        f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        assert O.default_for(_t(tid)) == want, tid


@needs_private
def test_old_preset_ids_still_read(desk):
    """A desk draft from before templates may carry a preset id: read as the template it now is."""
    t = _t("stoneford-town")
    assert O.normalize(t, "talk_then_act") == "two_beat"
    assert O.normalize(t, "quick_talk") == "two_beat?pace=quick"
    assert O.normalize(t, "one_beat") == "one_beat"
    assert O.check(t, "quick_talk") is None and O.check(t, "two_beat?pace=slow")


@pytest.mark.parametrize("tid", ["stoneford-town", "pct-house"])
def test_every_preset_draws_a_graph(desk, tid):
    t = _t(tid)
    vs = O.views(t)
    assert {k.partition("?")[0] for k in vs["views"]} == {p["id"] for p in O.presets()} and vs["default"] in vs["views"]
    for pid, v in vs["views"].items():
        ids = [n["id"] for n in v["nodes"]]
        assert v["readonly"] is True and v["preset"] == pid.partition("?")[0] and v["start"] in ids
        assert v.get("ref", pid) == pid, "a view is keyed by its ref (template + the choices that differ from the default)"
        assert [n["id"] for n in v["nodes"] if n["kind"] == "core"] == O.get(pid)["nodes"]
        for n in v["nodes"]:
            if n["kind"] == "core":
                assert n["steps"] and all(s["title"] and s["by"] in ("python", "llm", "jev") for s in n["steps"])
        assert v["edges"] and all(e["from"] in ids and e["to"] in ids and e["labels"] for e in v["edges"])
        for where, txt in _texts(v):
            assert set(txt) == LANGS and all(isinstance(s, str) for s in txt.values()), where
        assert all(txt["en"] for where, txt in _texts(v) if where.endswith(".title")), "every node / step has a name"
    if tid == "pct-house":   # the template's own layers are on the graph: a fight, a dungeon room, the rules referee
        one = vs["views"]["one_beat"]
        assert {"combat", "dungeon", "referee"} <= {n["id"] for n in one["nodes"]}
        assert {(e["from"], e["to"]) for e in one["edges"]} >= {("resolve", "combat"), ("combat", "resolve"), ("resolve", "dungeon"), ("dungeon", "resolve")}


@needs_private
def test_each_pace_draws_its_own_graph(desk):
    """10-23: 「As usual」 and 「Quick talk」 looked the same — one view per template, no setting on it. Now each
    parameter choice has its own view, and the node it changes carries those settings, so the two read differently."""
    vs = O.views(_t("stoneford-town"))["views"]
    assert {"two_beat", "two_beat?pace=quick"} <= set(vs) and "one_beat" in vs
    sets = {k: {s["id"]: s for n in vs[k]["nodes"] for s in n.get("settings") or []} for k in ("two_beat", "two_beat?pace=quick")}
    assert sets["two_beat"] and set(sets["two_beat"]) == set(sets["two_beat?pace=quick"]), "the same settings, on the same node"
    differ = [i for i in sets["two_beat"] if sets["two_beat"][i]["shows"] != sets["two_beat?pace=quick"][i]["shows"]]
    assert differ, "at least one setting differs between the two paces"
    assert all(sets["two_beat?pace=quick"][i].get("changed") for i in differ) and not any(s.get("changed") for s in sets["two_beat"].values())
    assert all(sets["two_beat"][i]["short"]["zh"] != sets["two_beat?pace=quick"][i]["short"]["zh"] for i in differ), "the graph line says it"
    for k in sets:
        for s in sets[k].values():
            assert all(s["title"][lg] and s["short"][lg] for lg in LANGS), (k, s["id"])
    plan = next(n for n in vs["two_beat?pace=quick"]["nodes"] if n["id"] == "plan")
    assert plan["settings"] and vs["two_beat?pace=quick"]["choice"] == {"pace": "quick"} and vs["two_beat"]["choice"] == {"pace": "normal"}
    assert not any(n.get("settings") for n in vs["one_beat"]["nodes"]), "a template without parameters shows none"


@needs_private
def test_the_private_beat_shows_names_and_lines_only(desk):
    v = O.views(_t("pct-house"))
    plan = next(n for n in v["views"]["two_beat"]["nodes"] if n["id"] == "plan")
    assert [s["id"] for s in plan["steps"]] == ["pack", "gate", "souls", "host"]
    assert all(set(s["title"]) == LANGS and s["title"]["en"] != s["title"]["zh"] for s in plan["steps"]), "four languages"
    keys = set(_keys(v["views"]))
    bad = {"params", "prompt", "tools", "engine", "step_params", "key", "default", "value", "choices"}
    assert not keys & bad, keys & bad
    s = json.dumps(v, ensure_ascii=False)
    for secret in ("plan_sys", "plan_loop", "max_rounds", "talk_limit", "settle_at", "turn.", "\"mic\"", "\"board\"", "\"narrate\""):
        assert secret not in s, secret
    priv = private_dir("prompts")
    body = (priv / "plan_sys.zh.md").read_text(encoding="utf-8")
    lines = [ln.strip() for ln in body.splitlines() if len(ln.strip()) > 12][:20]
    assert lines and not [ln for ln in lines if ln in s], "no line of the private prompt"
    opts = creation.form(_open("pct-house"))["orchestration"]["options"]
    assert all(set(o) <= {"id", "title", "summary", "params"} for o in opts), "the form names the templates, never their settings"
    two = next(o for o in opts if o["id"] == "two_beat")
    assert [(p["id"], p["default"], [c["id"] for c in p["choices"]]) for p in two["params"]] == [("pace", "normal", ["normal", "quick"])]
    s = json.dumps(opts, ensure_ascii=False)
    for secret in ("plan_loop", "max_rounds", "talk_limit", "nudge_at"):
        assert secret not in s, secret


def test_the_form_offers_the_presets(desk):
    f = creation.form(_t("stoneford-town"))
    part = f["orchestration"]
    assert part["default"] == O.default_for(_t("stoneford-town"))
    assert [o["id"] for o in part["options"]] == [p["id"] for p in O.presets()]
    assert all(set(o["title"]) == LANGS and all(o["title"].values()) and all(o["summary"].values()) for o in part["options"])


def test_check_takes_a_template_only(desk):
    t = _t("stoneford-town")
    add = {"ending": [{"title": "雾散", "kind": "true"}]}
    assert creation.check(t, {**add, "orchestration": "one_beat"}) == []
    assert creation.check(t, {**add, "orchestration": ""}) == []
    probs = creation.check(t, {**add, "orchestration": "my_own_graph"})
    assert probs and probs[0].startswith("orchestration: must be one of")
    assert creation.check(t, {**add, "orchestration": "one_beat?pace=quick"})[0].startswith("orchestration: one_beat: no parameter")


@needs_private
def test_the_work_stores_the_template_as_uses(desk):
    """The work names the template (``uses``); its ``pack.engine`` is the world's less what a template decides — so the
    world's own ``plan_loop: off`` never keeps a work on the two beats single-beat; switching back restores it all."""
    from neonrp.core import engine_config

    t = _t("stoneford-town")
    add = {"ending": [{"title": "雾散", "kind": "true"}]}
    own = json.loads((t.dir / "template.json").read_text(encoding="utf-8"))
    tj = lambda w: json.loads((w.dir / "template.json").read_text(encoding="utf-8"))  # noqa: E731
    w = creation.save(t, {**add, "orchestration": "two_beat?pace=quick"}, work_id="stoneford-town-mine")
    d = tj(w)
    assert d["uses"] == {"template": "two_beat", "version": "1.0", "soul": "S-judge", "params": {"pace": "quick"}}
    assert d["pack"]["engine"] == {"turn": {"mode": "v3"}}, "the world's single-beat switch is the template's to say"
    assert O.default_for(w) == "two_beat?pace=quick", "the work plays as the template it stored"
    TP.build(w, desk.parent / "run-quick")
    assert engine_config.get(desk.parent / "run-quick", "turn.plan_loop") == "on"
    assert engine_config.get(desk.parent / "run-quick", "turn.plan_loop_max_rounds") == 2
    w = creation.save(t, {**add, "orchestration": "two_beat"}, work_id="stoneford-town-mine")
    assert tj(w)["uses"] == {"template": "two_beat", "version": "1.0", "soul": "S-judge"}, "switching leaves nothing of the earlier choice"
    assert O.default_for(w) == "two_beat"
    w = creation.save(t, {**add, "orchestration": "quick_talk"}, work_id="stoneford-town-mine")
    assert O.default_for(w) == "two_beat?pace=quick", "an old draft's preset id"
    w = creation.save(t, add, work_id="stoneford-town-mine")
    assert tj(w)["uses"] == own["uses"] and tj(w)["pack"]["engine"] == own["pack"]["engine"], "none chosen = the world's own"
    TP.build(w, desk.parent / "run")
    assert engine_config.get(desk.parent / "run", "turn.plan_loop") == "on"
    w = creation.save(t, {**add, "orchestration": "one_beat"}, work_id="stoneford-town-mine")
    assert tj(w)["uses"] == {"template": "one_beat", "version": "1.0", "soul": "S-judge"}
    TP.build(w, desk.parent / "run-one")
    assert engine_config.get(desk.parent / "run-one", "turn.plan_loop", "off") == "off", "an author may still pick the single beat"


def test_the_route_serves_every_view(desk, tmp_path, monkeypatch):
    from unittest.mock import patch

    from neonrp.commands.web import make_server

    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "lib" / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "lib" / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "lib" / "studio"),
    ):
        srv = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            base = f"http://127.0.0.1:{srv.server_address[1]}/api/v1/local/templates"
            with urllib.request.urlopen(f"{base}/stoneford-town/creation/orchestration", timeout=30) as r:
                body = json.loads(r.read())
            assert body["default"] and set(body["views"]) == set(O.views(_t("stoneford-town"))["views"])
            assert body == json.loads(json.dumps(O.views(_t("stoneford-town")), ensure_ascii=False))
        finally:
            srv.shutdown()


# ── a character's orchestration (subject: soul; lead 10-18: the desk's added characters pick one) ─────────────────────

@pytest.fixture
def soul_presets(tmp_path, monkeypatch):
    """The engine's presets + one more soul preset (chat · its own day), so a desk has something besides the default."""
    d = json.loads(O._FILE.read_text(encoding="utf-8"))
    d["presets"].append({"id": "chat_tick", "subject": "soul", "order": 20,
                         "graph": {"start": "chat", "nodes": {"chat": {"kind": "chat"}, "day": {"kind": "tick"}},
                                   "edges": [{"id": "chat>chat", "from": "chat", "to": "chat", "on": {"chat": "message"}},
                                             {"id": "chat>day", "from": "chat", "to": "day", "on": {"idle": 30}}]}})
    f = tmp_path / "orch_presets.json"
    f.write_text(json.dumps(d), encoding="utf-8")
    monkeypatch.setattr(O, "_FILE", f)
    return f


def test_soul_presets_are_their_own_list(soul_presets):
    assert [p["id"] for p in O.presets()] == [p["id"] for p in O.presets("world")], "world presets stay as they were"
    ids = [p["id"] for p in O.presets("soul")]
    assert ids[0] == "chat_only" and "chat_tick" in ids and O.soul_options()["default"] == "chat_only"
    assert not set(ids) & {p["id"] for p in O.presets("world")}


def test_every_soul_preset_draws_a_graph_without_settings(soul_presets):
    from neonrp.core import soul_orchestration as SO

    vs = O.soul_views()
    assert set(vs["views"]) == {p["id"] for p in O.presets("soul")}
    for pid, v in vs["views"].items():
        assert v["readonly"] and v["subject"] == "soul" and v["start"] in [n["id"] for n in v["nodes"]]
        assert all(n["steps"] for n in v["nodes"]) and v["edges"]
        for where, txt in _texts(v):
            assert set(txt) == LANGS and all(isinstance(s, str) for s in txt.values()), (pid, where)
            assert where.endswith(".doc") or (pid == "chat_tick" and where in (".title", ".summary")) or all(txt.values()), (pid, where)
        assert not set(_keys(v)) & {"params", "prompt", "tools", "history", "doc_cap", "daily_max", "interval_min"}
        SO.check(O.soul_graph(pid))   # what the desk writes is a graph the engine takes
    chat = vs["views"]["chat_only"]
    words = {s["id"]: s["title"]["ja"] for s in chat["nodes"][0]["steps"]}
    assert all(words[i] != i for i in ("docs", "history", "reply", "bubbles")), "the engine's own steps have words"
    assert chat["edges"][0]["labels"][0]["en"] and chat["nodes"][0]["title"]["en"] != "chat"


def test_the_desk_has_no_per_character_picker(desk, soul_presets):
    """10-19: an orchestration is one system of the template (world and characters together), never a pick per
    character — the form offers none, and a row that still carries one (an old draft) writes nothing into the work."""
    t = _t("stoneford-town")
    assert "soul_orchestration" not in creation.form(t)
    add = {"soul": [{"name": "阿青", "persona": "沉默的猎人", "orchestration": "chat_tick"}]}
    assert creation.check(t, add) == []
    w = creation.save(t, add, work_id="stoneford-town-mine")
    assert not (w.dir / "prompts" / "souls").exists()
    assert "souls" not in O.views(t), "the desk's graphs are the world's only"
