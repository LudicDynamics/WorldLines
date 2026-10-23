"""编排图写回(1.0 带创作写回):编排台把整张图交给 set_orchestration,存成相对玩法包默认图的补丁,
建局后引擎生效的图就是编辑后的那张;改回默认就去掉覆盖。"""

from __future__ import annotations

import copy
import json
import shutil

import pytest

from _paths import PRODUCT_TEMPLATES


@pytest.fixture
def mine(tmp_path, monkeypatch):
    s = tmp_path / "mine"
    shutil.copytree(PRODUCT_TEMPLATES / "pct-house.template", s / "pct-mine.template")
    d = json.loads((s / "pct-mine.template" / "template.json").read_text(encoding="utf-8"))
    d["id"] = "pct-mine"
    (s / "pct-mine.template" / "template.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(s))
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(s))
    return s / "pct-mine.template"


def test_write_back_lands_in_the_built_run_and_reverts(mine, tmp_path):
    from neonrp import template as TP
    from neonrp.core import orchestration
    from neonrp.template import author

    base = author.base_graph(TP.load(mine))
    g = copy.deepcopy(base)
    g["nodes"]["investigate"] = {"kind": "loop", "title": "调查"}
    g["edges"].append({"id": "x1", "from": "resolve", "to": "investigate", "on": {"op": "investigate"}})
    dropped = g["edges"].pop(0)
    r = author.apply_ops(mine, [{"op": "set_orchestration", "graph": g}])
    assert r["ok"], r
    t = TP.load(mine)
    assert t.data["orchestration"] == "orchestration.json"
    patch = TP.template_orchestration(t)
    assert patch["nodes"] == {"investigate": {"kind": "loop", "title": "调查"}} and patch["remove"] == [author._eid(dropped)]
    TP.build(t, tmp_path / "run")
    eff = orchestration.graph(tmp_path / "run")
    assert "investigate" in eff["nodes"] and any(e.get("id") == "x1" for e in eff["edges"])
    assert not any(e.get("id") == author._eid(dropped) for e in eff["edges"])
    # 改回和默认一样 → 覆盖去掉
    r = author.apply_ops(mine, [{"op": "set_orchestration", "graph": base}])
    assert r["ok"] and "orchestration" not in TP.load(mine).data


def test_bad_graphs_are_refused_and_nothing_is_written(mine):
    from neonrp import template as TP
    from neonrp.template import author

    base = author.base_graph(TP.load(mine))
    bad = copy.deepcopy(base)
    bad["edges"].append({"id": "x2", "from": "plan", "to": "nowhere", "on": {"op": "x"}})
    r = author.apply_ops(mine, [{"op": "set_orchestration", "graph": bad}])
    assert not r["ok"] and "does not exist" in r["refused"][0]["why"]
    r = author.apply_ops(mine, [{"op": "set_orchestration", "graph": {"nodes": []}}])
    assert not r["ok"]
    assert "orchestration" not in TP.load(mine).data


def test_a_rewritten_edge_keeps_its_return_point():
    """10-17: the editor re-writes an engine edge (a guard added) — the patch keeps ``return`` (entering a layer pushes a
    return point), else the layer's exit would have nowhere to go back to."""
    from neonrp.template.author import graph_patch

    base = {"nodes": {"resolve": {}, "combat": {}},
            "edges": [{"id": "resolve>combat:op", "from": "resolve", "to": "combat", "on": {"op": "combat"}, "return": True}]}
    g = copy.deepcopy(base)
    g["edges"][0]["when"] = [{"var": "turn", ">=": 0}]
    add = graph_patch(base, g)["add"]
    assert add == [{"id": "resolve>combat:op", "from": "resolve", "to": "combat", "on": {"op": "combat"},
                    "when": [{"var": "turn", ">=": 0}], "return": True}]


def test_the_editor_reads_back_what_it_just_wrote(mine):
    """10-21 e2e 编排台: the graph read right after a write-back (and after 「恢复默认」) was the one before it — the
    template's signature is remembered for SIG_TTL and apply_ops did not forget it."""
    import copy

    from neonrp import template as TP
    from neonrp.template import author, v3

    base = author.base_graph(TP.load(mine))
    assert "plan" in v3.graph_of(str(mine))["graph"]["nodes"]
    g = copy.deepcopy(base)
    g["nodes"].pop("plan")
    g["edges"] = [e for e in g["edges"] if "plan" not in (e.get("from"), e.get("to"))]
    g["start"] = "resolve"
    assert author.apply_ops(mine, [{"op": "set_orchestration", "graph": g}])["ok"]
    assert "plan" not in v3.graph_of(str(mine))["graph"]["nodes"], "read back at once: the deleted node is gone"
    assert author.apply_ops(mine, [{"op": "set_orchestration", "graph": base}])["ok"]
    assert "plan" in v3.graph_of(str(mine))["graph"]["nodes"], "restored at once"
