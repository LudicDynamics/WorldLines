"""10-06: the orchestration editor switches between templates and can draw what the engine cannot run.

- every template's graph builds without a session and has nothing unrunnable;
- a drawn-but-dead node / edge warns (orch.node_no_impl / orch.edge_unrunnable); a runnable added edge does not;
- a whole graph written back as the override reads back the same (the editor's save round-trips).
"""
from __future__ import annotations

import json

import pytest
from test_engine_v3 import _install

from neonrp import template as TP
from neonrp.core import node_kinds, orchestration as O
from neonrp.template import v3

TEMPLATES = sorted(TP.discover())


@pytest.mark.parametrize("ref", TEMPLATES)
def test_each_template_graph_builds_and_runs(ref):
    r = v3.graph_of(ref)
    g = r["graph"]
    # 10-25: the graph is what the run plays — the two beats' worlds have the talk node, a single-beat world (狼人村) not
    plays_two = TP.load(TP.discover()[ref]).data.get("uses", {}).get("template") == "two_beat" and node_kinds.get("plan") is not None
    assert g["schema"] == O.SCHEMA and "resolve" in g["nodes"] and ("plan" in g["nodes"]) == plays_two
    assert not [x for x in g["lint"] if x["code"] in ("orch.edge_unrunnable", "orch.node_no_impl", "orch.phase_var")]


def test_switching_shows_different_shapes():
    shapes = {ref: tuple(sorted(v3.graph_of(ref)["graph"]["nodes"])) for ref in TEMPLATES}
    assert len(set(shapes.values())) >= 2
    if "werewolf-night-village" in shapes:
        assert {"day", "night"} <= set(shapes["werewolf-night-village"])


def _codes(root):
    O._CACHE.clear()
    return [(x["code"], x["msg"]) for x in O.graph(root)["lint"]]


def test_dead_edges_and_nodes_warn_runnable_ones_do_not(tmp_path, monkeypatch):
    root = _install(tmp_path)
    monkeypatch.setenv("NEONRP_PLAN_LOOP", "1")   # the talk node is in the graph (off, edges from it are left out with it)
    p = O.override_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"add": [
        {"id": "x:host-into-combat", "from": "plan", "to": "combat", "on": {"host": "advance"}},
        {"id": "x:own-words", "from": "plan", "to": "resolve", "on": {"words": ["动手吧"]}},
        {"id": "x:bad-class", "from": "*", "to": "combat", "on": {"here_class": "no_such_class"}},
        {"id": "x:wrong-op", "from": "resolve", "to": "combat", "on": {"op": "dungeon"}},
        {"id": "x:to-nowhere", "from": "resolve", "to": "investigate", "on": {"op": "investigate"}},
    ], "nodes": {"investigate": {"kind": "mode", "title": "investigate"}}}, ensure_ascii=False), encoding="utf-8")
    got = _codes(root)
    dead = {m.split(":")[0] + ":" + m.split(":")[1] for c, m in got if c == "orch.edge_unrunnable"}
    assert {"x:host-into-combat", "x:bad-class", "x:wrong-op", "x:to-nowhere"} <= dead
    assert "x:own-words" not in dead
    assert any(c == "orch.node_no_impl" and m.startswith("investigate") for c, m in got)


def test_an_always_edge_no_node_kind_reads_warns(tmp_path):
    """10-17: the engine reads 'always' only where a node kind claims it (resolve → plan) — anywhere else it is dead."""
    root = _install(tmp_path)
    p = O.override_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"add": [{"id": "x:always-on", "from": "resolve", "to": "combat", "on": {"always": True}}]}), encoding="utf-8")
    assert any(c == "orch.edge_unrunnable" and m.startswith("x:always-on") for c, m in _codes(root))


def test_interaction_nodes_are_the_plugins_own(tmp_path):
    """10-17: a template's interaction nodes (the game client's) run in the interaction plugin, not a pack layer — no
    false 'nothing to run there'; an interaction the plugin does not have still warns."""
    root = _install(tmp_path)
    p = O.override_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"nodes": {"interaction.talk": {"kind": "interaction", "title": "talk"},
                                       "interaction.fly": {"kind": "interaction", "title": "fly"}},
                             "add": [{"id": "x:talk", "from": "*", "to": "interaction.talk", "on": {"interaction": "talk"}},
                                     {"id": "x:fly", "from": "*", "to": "interaction.fly", "on": {"interaction": "fly"}}]}), encoding="utf-8")
    got = _codes(root)
    assert not [m for c, m in got if m.startswith("interaction.talk") or m.startswith("x:talk")]
    assert any(c == "orch.node_no_impl" and m.startswith("interaction.fly") for c, m in got)
    assert any(c == "orch.edge_unrunnable" and m.startswith("x:fly") for c, m in got)


def test_whole_graph_round_trips(tmp_path):
    root = _install(tmp_path)
    O._CACHE.clear()
    g = O.graph(root)
    p = O.override_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({k: g[k] for k in ("id", "start", "nodes", "edges")}, ensure_ascii=False), encoding="utf-8")
    O._CACHE.clear()
    g2 = O.graph(root)
    assert g2["nodes"] == g["nodes"] and g2["edges"] == g["edges"] and not [x for x in g2["lint"] if x["code"].startswith("orch.edge") or x["code"].startswith("orch.node")]


def test_template_graph_reads_reuse_one_run_until_the_template_changes(tmp_path, monkeypatch):
    """10-17 (审计 1.6): graph / lint for the editor no longer build a throwaway run per request — one kept run per
    template, rebuilt when the template folder changes."""
    import shutil

    import neonrp.template as TPm

    src = TP.discover()["stoneford-elena"]
    mine = tmp_path / "stoneford-elena.template"
    shutil.copytree(src, mine)
    builds = []
    real = TPm.build
    monkeypatch.setattr(TPm, "build", lambda *a, **k: (builds.append(1), real(*a, **k))[1])
    monkeypatch.setattr(v3, "SIG_TTL", 0.0)
    g = v3.graph_of(str(mine))["graph"]
    assert v3.graph_of(str(mine))["graph"]["edges"] == g["edges"]
    assert v3.lint_graph_of(str(mine), {k: g[k] for k in ("id", "start", "nodes", "edges")}) == []
    assert len(builds) == 1
    from neonrp.template import author

    monkeypatch.setattr(author, "writable", lambda t: True)   # the copy sits outside the player's template store
    d = {k: g[k] for k in ("id", "start", "nodes", "edges")}
    d["edges"] = [e for e in d["edges"] if e["id"] != "plan>resolve:judge"]
    assert author.apply_ops(mine, [{"op": "set_orchestration", "graph": d}])["ok"]   # (its own re-lint builds too)
    n = len(builds)
    assert "plan>resolve:judge" not in {e["id"] for e in v3.graph_of(str(mine))["graph"]["edges"]}
    v3.graph_of(str(mine))
    assert len(builds) == n + 1   # the changed template: one new run, then reused
