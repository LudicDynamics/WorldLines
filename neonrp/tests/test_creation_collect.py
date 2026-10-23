"""Limited creation + collection: a template declares
what it opens to creators; the world's author writes who can be collected; settlement lists what a run granted."""
from __future__ import annotations

import json
from pathlib import Path

from test_contract_settlement import _run, _tpl

from neonrp.core import sdk
from neonrp.core.registry import load_registry
from neonrp.template import creation as K
from neonrp.template import load as load_template
from _paths import PRODUCT, PRODUCT_TEMPLATES

OPEN = {"add": ["soul", "plot", "ending", "rule"], "triggers": {"when": ["text", "flag"], "then": ["narration", "flag", "end"]},
        "collect": ["clear", "ending"]}


def _open_tpl(tmp_path: Path, creation: dict | None) -> object:
    t, _w = _tpl(tmp_path, "open-adventure@1")
    if creation is not None:
        d = json.loads((t.dir / "template.json").read_text(encoding="utf-8"))
        d["creation"] = creation
        (t.dir / "template.json").write_text(json.dumps(d), encoding="utf-8")
    return load_template(t.dir)


def test_nothing_is_open_without_a_creation_block(tmp_path):
    t = _open_tpl(tmp_path, None)
    assert K.form(t)["open"] is False and K.form(t)["sections"] == []
    assert K.check(t, {"soul": [{"name": "a", "persona": "b"}]}) == ["this template does not open anything to creators"]


def test_the_form_follows_what_the_template_opens(tmp_path):
    t = _open_tpl(tmp_path, OPEN)
    f = K.form(t)
    assert [s["key"] for s in f["sections"]] == ["soul", "plot", "ending", "rule"], "clue is not opened"
    rule = next(s for s in f["sections"] if s["key"] == "rule")["fields"][1]
    assert rule["when"] == ["text", "flag"] and rule["then"] == ["narration", "flag", "end"]
    soul = {x["name"]: x for x in f["sections"][0]["fields"]}
    assert soul["collect"]["options"] == ["clear", "ending"], "only the collect ways the template opens"


def test_check_keeps_creators_inside_the_open_layer(tmp_path):
    t = _open_tpl(tmp_path, OPEN)
    ok = {"soul": [{"name": "阿沐", "persona": "探路队的孩子", "collect": "clear", "rarity": "rare"}],
          "rule": [{"trigger": {"when": {"text": "player"}, "if": [{"text": "护身符"}], "then": [{"to": "flag", "key": "amulet"}]}}]}
    assert K.check(t, ok) == []
    bad = K.check(t, {"clue": [{"name": "x", "summary": "y"}],
                      "soul": [{"name": "", "persona": "p", "collect": "flag"}],
                      "rule": [{"trigger": {"when": {"var": "player.gold"}, "then": [{"to": "var", "var": "player.hp", "add": -1}]}}]})
    joined = "\n".join(bad)
    assert "does not let creators add 'clue'" in joined
    assert "soul[0].name: required" in joined and "soul[0].collect: must be one of clear, ending" in joined
    assert "'var' is not open" in joined and "trigger.then: 'var' is not open" in joined


def test_unknown_names_in_the_creation_block_warn(tmp_path):
    t = _open_tpl(tmp_path, {"add": ["soul", "map"], "collect": ["keyword"]})
    codes = {(lv, where) for lv, _c, where, _m in K.spec_problems(t)}
    assert codes == {("warn", "creation.add"), ("warn", "creation.collect")}
    assert K.spec(t)["add"] == ["soul"] and K.spec(t)["collect"] == []


PLOT = {"id": "P1", "endings": {"E1": {"title": "雾退", "kind": "true"}, "E9": {"title": "雾合", "kind": "fail"}},
        "entries": {"N201": {"class": "npc", "name": "阿沐"}},
        "collect": {"N201": {"on": "clear"}, "a": {"on": {"ending": "E1"}, "rarity": "rare"}}}


def test_lint_only_world_characters_and_real_endings(tmp_path):
    t, w = _tpl(tmp_path, "open-adventure@1")
    assert K.lint(t, [PLOT], w, {"collect": {"souls": True, "min": 0}}) == []
    bad = {**PLOT, "collect": {"路人": "clear", "N201": {"on": {"ending": "E7"}}, "a": {"on": "keyword"}}}
    probs = {(code, where) for _lv, code, where, _m in K.lint(t, [bad], w, None)}
    assert ("collect.who", "P1.collect.路人") in probs, "only characters that live in the world"
    assert ("collect.on", "P1.collect.N201") in probs and ("collect.on", "P1.collect.a") in probs
    floor = {code for _lv, code, _w, _m in K.lint(t, [PLOT], w, {"collect": {"souls": True, "min": 3}})}
    assert floor == {"collect.contract"}, "the contract sets the floor"


def test_granted_by_clear_ending_and_flag():
    plots = [{**PLOT, "collect": {**PLOT["collect"], "N202": {"on": {"flag": "joined.N202"}}}}]
    true = K.granted(plots, ending={"id": "E1", "kind": "true"}, flags={})
    assert {(g["who"], g["why"]) for g in true} == {("N201", "clear:E1"), ("a", "ending:E1")}
    assert K.granted(plots, ending={"id": "E9", "kind": "fail"}, flags={}) == [], "a fail ending is not a clear"
    assert [g["who"] for g in K.granted(plots, ending=None, flags={"joined.N202": True})] == ["N202"]


def test_settlement_lists_who_the_run_granted(tmp_path):
    root = _run(tmp_path, "open-adventure@1", endings={"E1": {"title": "雾退", "kind": "true"}}, trigger_end="E1")
    pd = tmp_path / "plot"
    d = json.loads((pd / "plot.json").read_text(encoding="utf-8"))
    d["collect"] = {"艾琳娜": {"on": "clear", "rarity": "epic"}}
    from neonrp.packs.rpg import plot as P

    (pd / "plot.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    P.install(root, pd)
    res = sdk.apply(root, [], load_registry(root), turn=3)
    st = res.settled or json.loads((root / "game" / "meta" / "settlement.json").read_text(encoding="utf-8"))
    assert [{k: c[k] for k in ("who", "plot", "rarity", "why")} for c in st["collected"]] == [{"who": "艾琳娜", "plot": "P9", "rarity": "epic", "why": "clear:E1"}]
    assert st["collected"][0]["name"] == "艾琳娜" and st["collected"][0]["cls"] == "soul", "the screen's face from the run's entry (10-18)"


def test_the_official_contracts_carry_a_collect_floor():
    from neonrp.template import contract as C

    for ref in ("mystery-trpg@1", "open-adventure@1", "murder-mystery@1", "romance-companion@1"):
        assert C.load(ref)["collect"] == {"souls": True, "min": 0}, ref


def test_creation_desk_http(tmp_path, monkeypatch):
    """GET …/creation is the form; POST …/creation/check validates; POST …/creation writes one plot into a fork only."""
    import os
    import shutil
    import threading
    import urllib.error
    import urllib.request
    from unittest.mock import patch

    import pytest

    from neonrp.commands.web import make_server

    store, mine = tmp_path / "store", tmp_path / "mine"
    if not (PRODUCT_TEMPLATES / "stoneford-town.template").is_dir():
        pytest.skip("stoneford-town is not in this release")
    shutil.copytree(PRODUCT_TEMPLATES / "stoneford-town.template", store / "stoneford-town.template")
    mine.mkdir()
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", f"{mine}{os.pathsep}{store}")
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(mine))
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "lib" / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "lib" / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "lib" / "studio"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}/api/v1/local/templates"

        def call(path, body=None):
            req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                         method="GET" if body is None else "POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())
        try:
            f = call("/stoneford-town/creation")
            assert f["open"] and {s["key"] for s in f["sections"]} == {"soul", "plot", "clue", "ending", "rule"}
            add = {"plot": [{"title": "灯塔的信"}], "soul": [{"name": "守灯人", "persona": "独居灯塔", "collect": "ending", "collect_ending": "#1"}],
                   "ending": [{"title": "信送到了", "kind": "true"}],
                   "rule": [{"trigger": {"when": {"text": "player"}, "if": [{"text": "信"}], "then": [{"to": "end", "ending": "#1"}], "once": True}}]}
            assert call("/stoneford-town/creation/check", {"addition": add}) == {"ok": True, "problems": []}
            bad = call("/stoneford-town/creation/check", {"addition": {"rule": [{"trigger": {"when": {"turn": True}, "then": [{"to": "log"}]}}]}})
            assert not bad["ok"] and any("'turn' is not open" in p for p in bad["problems"])
            with pytest.raises(urllib.error.HTTPError) as exc:
                call("/stoneford-town/creation", {"addition": add, "id": "C01"})
            assert exc.value.code == 403, "built-in: fork first"
            fid = call("/stoneford-town/fork", {"id": "town-mine", "title": "我的小镇"}).get("id") or "town-mine"
            out = call(f"/{fid}/creation", {"addition": add, "id": "C01"})
            assert out["ok"] and out["plot"] == "plots/C01"
            assert not [p for p in out["lint"]["problems"] if p["code"].startswith(("collect.", "creation."))], out["lint"]["problems"]
            plot = json.loads((mine / f"{fid}.template" / "plots" / "C01" / "plot.json").read_text(encoding="utf-8"))
            assert plot["collect"] == {"C01_N01": {"on": {"ending": "C01_E1"}, "rarity": "common"}}
            assert plot["entries"]["C01_N01"]["name"] == "守灯人" and "C01_E1" in plot["endings"], "#1 → this plot's first ending"
            assert plot["triggers"]["C01_R01"]["then"][0]["ending"] == "C01_E1"
        finally:
            server.shutdown()
