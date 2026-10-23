"""The run's commit DAG over HTTP (webui/commit_routes.py): nodes, parents, branch tips, current head."""
from __future__ import annotations

import json
from pathlib import Path

from neonrp.webui.commit_routes import commit_graph


def _w(p: Path, d) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d) if not isinstance(d, str) else d, encoding="utf-8")


def test_commit_graph_forks_and_heads(tmp_path):
    root = tmp_path / "run"
    cr = root / ".neonrp" / "commits"
    # main: a → b → c ; rollback-x forked at a: a → d
    for cid, parent, seq, br in (("a", "seed", 0, "main"), ("b", "a", 1, "main"), ("c", "b", 2, "main"), ("d", "a", 1, "rollback-x")):
        _w(cr / "worlds" / f"{cid}.json", {"world_commit_id": cid, "parent": parent, "turn_seq": seq, "branch": br})
    _w(cr / "refs" / "w" / "branches" / "main", "c")
    _w(cr / "refs" / "w" / "branches" / "rollback-x", "d")
    _w(root / ".neonrp" / "manifest.json", {"current_branch": "rollback-x", "branches": {
        "main": {"kind": "main"}, "rollback-x": {"kind": "sandbox", "parent": "main"}}})
    g = commit_graph(root)
    assert g["branch"] == "rollback-x" and g["head"] == "d"
    assert g["branches"]["main"]["tip"] == "c" and g["branches"]["rollback-x"]["parent"] == "main"
    assert [n["id"] for n in g["nodes"]][:1] == ["a"] and {n["id"]: n["parent"] for n in g["nodes"]}["d"] == "a"
    assert len(g["nodes"]) == 4


def test_empty_run_has_no_nodes(tmp_path):
    g = commit_graph(tmp_path)
    assert g["nodes"] == [] and g["head"] is None
