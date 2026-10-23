"""编排台的草稿图也要有「画了但引擎跑不了」的警告(10-07):POST /api/v1/local/templates/<id>/graph-lint
在一次性的临时局里跑 orchestration.lint_runnable,什么都不写。"""

from __future__ import annotations

import copy
import json
import threading
import urllib.error
import urllib.request
from unittest.mock import patch

import pytest


def test_draft_graph_lint_over_http(tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "studio"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def call(path, body=None):
            req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                         method="GET" if body is None else "POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())
        try:
            g = call("/api/v1/play/engine/graph?template=pct-house")["graph"]
            assert call("/api/v1/local/templates/pct-house/graph-lint", {"graph": g})["lint"] == [], "引擎自己的图没有警告"
            d = copy.deepcopy(g)
            d["nodes"]["investigate"] = {"kind": "loop", "title": "调查"}
            d["edges"].append({"id": "x1", "from": "plan", "to": "combat", "on": {"host": "advance"}})
            codes = {x["code"] for x in call("/api/v1/local/templates/pct-house/graph-lint", {"graph": d})["lint"]}
            assert codes == {"orch.node_no_impl", "orch.edge_unrunnable"}
            with pytest.raises(urllib.error.HTTPError) as exc:
                call("/api/v1/local/templates/pct-house/graph-lint", {"graph": []})
            assert exc.value.code == 400
            with pytest.raises(urllib.error.HTTPError) as exc:
                call("/api/v1/local/templates/nope/graph-lint", {"graph": g})
            assert exc.value.code == 404
        finally:
            server.shutdown()


def test_editor_chat_test_runs_the_real_engine_over_http(tmp_path):
    """10-17 (第 2 批 2.3): the orchestration editor's chat test is the engine's graph-test in a child process — a stub
    model, a throwaway run — not a page-side mock; the editor's unsaved draft graph rides along."""
    from neonrp.commands.web import make_server

    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "studio"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def call(path, body=None):
            req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                         method="GET" if body is None else "POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=240) as r:
                return json.loads(r.read())
        try:
            r = call("/api/v1/local/templates/stoneford-elena/graph-test", {"lines": ["我去杂货铺买药", "定"]})
            assert [s["nodes"] for s in r["steps"]] == [["plan"], ["resolve"]]
            assert r["steps"][1]["advanced_by"] == "player" and "plan>resolve:words" in r["edges"]["walked"]
            assert set(r["model_calls"]) <= {"host", "narrate", "transition"}   # the stub, never a provider
            g = call("/api/v1/play/engine/graph?template=stoneford-elena")["graph"]
            d = copy.deepcopy(g)
            d["edges"] = [e for e in d["edges"] if e["id"] != "plan>resolve:words"]   # the draft drops the commit word
            r2 = call("/api/v1/local/templates/stoneford-elena/graph-test", {"lines": ["我去杂货铺买药", "定"], "graph": d})
            assert [s["nodes"] for s in r2["steps"]] == [["plan"], ["plan"]]
            d3 = copy.deepcopy(g)   # the planning node deleted in the draft: the plain turn from the first line
            d3["nodes"].pop("plan")
            d3["edges"] = [e for e in d3["edges"] if "plan" not in (e["from"], e["to"])]
            d3["start"] = "resolve"
            r3 = call("/api/v1/local/templates/stoneford-elena/graph-test", {"lines": ["我四处看看"], "graph": d3})
            assert [s["nodes"] for s in r3["steps"]] == [["resolve"]] and r3["steps"][0]["advanced_by"] is None
            with pytest.raises(urllib.error.HTTPError) as exc:
                call("/api/v1/local/templates/stoneford-elena/graph-test", {"lines": []})
            assert exc.value.code == 400
            with pytest.raises(urllib.error.HTTPError) as exc:
                call("/api/v1/local/templates/nope/graph-test", {"lines": ["hi"]})
            assert exc.value.code == 404
        finally:
            server.shutdown()


def test_editor_chat_test_on_the_real_model_goes_on_turn_by_turn(tmp_path, monkeypatch):
    """④ niko 10-17: the editor's chat test on the player's own model — no model → 409 no_model; a chat keeps its run,
    so each new line plays one turn (not the whole chat again); a changed draft starts over; a provider error comes back
    as a code the page turns into 人话."""
    from neonrp.commands import web as W
    from neonrp.commands.web import make_server
    from neonrp.core import graph_test
    from neonrp.webui import template_routes as TR

    calls = []

    def fake(script, timeout=0):
        calls.append(list(script["lines"]))
        if script["lines"][-1] == "boom":
            raise RuntimeError("Error code: 401 - invalid api key")
        return {"steps": [{"line": x, "nodes": ["plan"], "reply": "…"} for x in script["lines"]], "edges": {"walked": []}, "model": "real"}

    monkeypatch.setattr(graph_test, "run_isolated", fake)
    TR._REAL_TESTS.clear()
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "studio"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def call(body):
            req = urllib.request.Request(base + "/api/v1/local/templates/stoneford-elena/graph-test", data=json.dumps(body).encode(),
                                         method="POST", headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())
        try:
            monkeypatch.setattr(W, "_resolve_creation_preset", lambda explicit: "")
            st, d = call({"lines": ["hi"], "model": "real", "session": "s1"})
            assert st == 409 and d["error"] == "no_model" and not calls
            monkeypatch.setattr(W, "_resolve_creation_preset", lambda explicit: "deepseek")
            assert call({"lines": ["a"], "model": "real", "session": "s1"})[1]["ran"] == 1
            assert call({"lines": ["a", "b"], "model": "real", "session": "s1"})[1]["ran"] == 1
            assert calls[-1] == ["b"]   # went on from the kept run: one more turn
            assert call({"lines": ["a", "b", "c"], "model": "real", "session": "s1", "graph": {"nodes": {}, "edges": []}})[1]["ran"] == 3
            st, d = call({"lines": ["a", "b", "c", "boom"], "model": "real", "session": "s1", "graph": {"nodes": {}, "edges": []}})
            assert st == 502 and d["error"] == "auth"
        finally:
            server.shutdown()
            TR._drop_real_tests()
