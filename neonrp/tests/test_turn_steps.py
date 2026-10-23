"""The turn's step catalog (10-17 第 4 批 S1): the graph's node steps are what the beat runs, and the editor reads every
step's settings with their value now and where it came from — read-only, nothing about the turn changes."""
from __future__ import annotations

import json
import threading
import urllib.request
from unittest.mock import patch

from neonrp.core import turn_steps
from neonrp.template import v3


def test_resolve_steps_are_the_catalog_and_every_setting_has_a_key_and_default():
    g = v3.graph_of("stoneford-elena")["graph"]
    assert g["nodes"]["resolve"]["steps"] == turn_steps.ids("resolve")
    ids = turn_steps.ids("resolve")
    assert ids.index("s1_plan") < ids.index("s2_souls") < ids.index("solve") < ids.index("verify") < ids.index("apply") < ids.index("land")
    keys = [p["key"] for s in turn_steps.steps_of("resolve") for p in s.get("params") or []]
    assert len(keys) == len(set(keys)) and all(k.startswith("turn.") for k in keys)
    assert {s["id"] for s in turn_steps.steps_of("resolve") if s.get("required")} == {"apply", "land"}
    provided = {x for s in turn_steps.steps_of("resolve") for x in s.get("provides") or []}
    assert all(r in provided for s in turn_steps.steps_of("resolve") for r in s.get("requires") or [])


def test_describe_reports_each_settings_value_and_its_source():
    d = turn_steps.describe(v3._graph_run(v3._template("stoneford-elena")))
    souls = next(s for s in d["nodes"]["resolve"] if s["id"] == "s2_souls")
    var = next(p for p in souls["params"] if p["name"] == "default_variant")
    assert var["value"] == "S-judge" and var["source"] == "orchestration"   # the world's uses.soul (10-19 stage A; the rpg pack's loop said the same)
    mx = next(p for p in souls["params"] if p["name"] == "max_workers")
    assert mx["value"] == 8 and mx["source"] == "builtin"


def test_planning_beat_brings_its_own_steps():
    g = v3.graph_of("stoneford-elena")["graph"]
    assert g["nodes"]["plan"]["steps"] == turn_steps.ids("plan") == ["pack", "gate", "souls", "host"]
    host = next(s for s in turn_steps.steps_of("plan") if s["id"] == "host")
    assert {p["key"] for p in host["params"]} >= {"turn.plan_loop_max_rounds", "turn.plan_loop_talk_limit"}


def test_hooks_route_gives_the_editor_steps_and_seams(tmp_path):
    from neonrp.commands.web import make_server

    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "studio"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/api/v1/play/engine/hooks?template=stoneford-elena"
            with urllib.request.urlopen(url, timeout=120) as r:
                d = json.loads(r.read())
            assert "soul_turn" in d["seams"] and d["handlers"]
            assert [s["id"] for s in d["steps"]["nodes"]["resolve"]] == turn_steps.ids("resolve")
            assert all("value" in p and "source" in p for s in d["steps"]["nodes"]["resolve"] for p in s.get("params") or [])
        finally:
            server.shutdown()


# ── S2: the graph is where a beat's settings live ──────────────────────────────────────────────────────────────────

def _override(root, d):
    from neonrp.core import orchestration as O

    p = O.override_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    O._CACHE.clear()


def test_step_params_in_the_graph_are_the_turns_settings(tmp_path):
    from test_engine_v3 import _install

    from neonrp.core import engine_config, orchestration as O
    from neonrp.core.paths import get_data_dir_name

    root = _install(tmp_path)
    assert engine_config.get(root, "turn.verify.gate.max_loops") == 1
    _override(root, {"nodes": {"resolve": {"step_params": {"verify": {"max_loops": 2}, "s2_souls": {"default_variant": "S-direct"},
                                                           "solve": {"max_ops": "nine"}, "pack": {"nope": 1}}}}})
    assert engine_config.get(root, "turn.verify.gate.max_loops") == 2
    assert engine_config.get(root, "turn.parallel.souls.default_variant") == "S-direct"
    assert engine_config.get(root, "turn.solve.max_ops") == 24   # a value that does not fit is left out …
    src = {k: s for k, _v, s in engine_config.explain(root)}
    assert src["turn.verify.gate.max_loops"] == "graph"
    lint = [x for x in O.graph(root)["lint"] if x["code"] == "orch.step_param"]
    assert any("max_ops" in x["msg"] for x in lint) and any("nope" in x["msg"] for x in lint)   # … and lint says why
    ej = root / get_data_dir_name(root) / "meta" / "engine.json"
    cfg = json.loads(ej.read_text(encoding="utf-8")) if ej.exists() else {}
    cfg.setdefault("turn", {}).setdefault("verify", {}).setdefault("gate", {})["max_loops"] = 3
    ej.write_text(json.dumps(cfg), encoding="utf-8")
    O._CACHE.clear()
    assert engine_config.get(root, "turn.verify.gate.max_loops") == 2   # the graph wins over the old engine.json
    assert any(x["code"] == "orch.legacy_turn_config" and "max_loops" in x["msg"] for x in O.graph(root)["lint"])


def test_writing_step_params_back_checks_them(tmp_path, monkeypatch):
    import shutil

    from neonrp import template as TP
    from neonrp.template import author

    mine = tmp_path / "stoneford-elena.template"
    shutil.copytree(TP.discover()["stoneford-elena"], mine)
    monkeypatch.setattr(author, "writable", lambda t: True)
    monkeypatch.setattr(v3, "SIG_TTL", 0.0)
    g = v3.graph_of(str(mine))["graph"]
    d = {k: g[k] for k in ("id", "start", "nodes", "edges")}
    d["nodes"]["resolve"] = {**d["nodes"]["resolve"], "step_params": {"verify": {"max_loops": 9}}}
    r = author.apply_ops(mine, [{"op": "set_orchestration", "graph": d}])
    assert not r["ok"] and "max_loops" in json.dumps(r["refused"], ensure_ascii=False)
    d["nodes"]["resolve"]["step_params"] = {"verify": {"max_loops": 2}}
    assert author.apply_ops(mine, [{"op": "set_orchestration", "graph": d}])["ok"]
    run = v3._graph_run(v3._template(str(mine)))
    verify = next(s for s in turn_steps.describe(run)["nodes"]["resolve"] if s["id"] == "verify")
    p = next(x for x in verify["params"] if x["name"] == "max_loops")
    assert p["value"] == 2 and p["source"] == "graph"
