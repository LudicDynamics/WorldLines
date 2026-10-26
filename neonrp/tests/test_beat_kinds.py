"""R2/R3 (10-09, APP-REQUESTS-PACK-BEATS-1009): the engine tells the screen how this run's beats are shown, and every
stream piece says which beat it belongs to — the screen knows no beat by itself."""
from __future__ import annotations

import json
from pathlib import Path

from test_engine_v3 import _install

from neonrp.core import node_kinds, orchestration


def test_two_beats_declared_by_the_plan_plugin(tmp_path: Path, monkeypatch):
    root = _install(tmp_path)
    monkeypatch.setenv("NEONRP_PLAN_LOOP", "1")   # 10-25: a run with the talk beat off has no plan node, so declares no beats
    bk = orchestration.beat_kinds(root)
    assert bk["start"] == "plan" and set(bk["kinds"]) >= {"plan", "resolve"}
    assert bk["kinds"]["plan"]["tone"] == "plan" and bk["kinds"]["resolve"]["divider_from"]["plan"]
    assert bk["kinds"]["plan"]["board"]["actions"][0]["say"]


def test_no_plugin_no_declaration(tmp_path: Path, monkeypatch):
    root = _install(tmp_path)
    monkeypatch.setenv("NEONRP_PRIVATE", "off")  # the open engine: no planning plugin, nothing declared
    assert node_kinds.get("plan") is None
    assert orchestration.beat_kinds(root) == {"kinds": {}}


def test_the_run_can_override_a_beat(tmp_path: Path, monkeypatch):
    from neonrp.core.paths import get_data_dir_name

    root = _install(tmp_path)
    monkeypatch.setenv("NEONRP_PLAN_LOOP", "1")
    f = root / get_data_dir_name(root) / "meta" / "template.json"
    rec = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    rec["ui"] = {**(rec.get("ui") or {}), "beats": {"kinds": {"plan": {"label": "说话拍"}}}}
    f.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    k = orchestration.beat_kinds(root)["kinds"]["plan"]
    assert k["label"] == "说话拍" and k["tone"] == "plan"  # the rest of the plugin's declaration stays


def test_stream_chunks_carry_their_beat(tmp_path: Path):
    from neonrp.core import topics
    from neonrp.core.conversation import ConversationSession

    root = _install(tmp_path)
    s = ConversationSession(root, "world-agent", mode="play")
    seen: list[dict] = []
    s.bus().subscribe(topics.ENGINE_STREAM, lambda m: seen.append(dict(m.payload)))
    s._beat_node = "resolve"
    s._enter_beat("resolve")
    # the on_chunk wrapper is built inside send(); drive one stub turn
    (root / ".neonrp" / "config.json").write_text(json.dumps({"llm": {"provider": "stub", "model": "stub-model"}}), encoding="utf-8")
    s.send("我四处看看", on_chunk=lambda t: None)
    chunks = [p for p in seen if p.get("kind") == "chunk"]
    assert chunks and all(p.get("beat") for p in chunks), chunks[:3]
    assert not any("// 商量" in str(p.get("text")) for p in chunks)


def test_deleting_the_planning_node_in_the_graph_turns_the_planning_beat_off(tmp_path: Path, monkeypatch):
    """The planning beat is decoupled in the orchestration editor — delete its node and the run has no
    planning beat: the plugin no longer takes the turn, its edges go, the graph starts at the Resolve."""
    from neonrp.core.paths import get_data_dir_name

    monkeypatch.setenv("NEONRP_PLAN_LOOP", "1")
    root = _install(tmp_path)
    assert orchestration.node_kind_live(root, "plan") and orchestration.graph(root)["start"] == "plan"
    ov = root / get_data_dir_name(root) / "meta" / "orchestration.json"
    ov.parent.mkdir(parents=True, exist_ok=True)
    ov.write_text(json.dumps({"nodes": {"plan": None, "resolve": {"state": "jev"}}}), encoding="utf-8")
    g = orchestration.graph(root)
    assert "plan" not in g["nodes"] and g["start"] == "resolve"
    assert not any("plan" in (e.get("from"), e.get("to")) for e in g["edges"])
    assert not orchestration.node_kind_live(root, "plan")
    assert g["nodes"]["resolve"]["state"] == "jev" and g["state"]["asked"] == "jev"  # the Resolve's parameter, same graph
    assert "plan" not in (orchestration.beat_kinds(root).get("kinds") or {})


def test_the_editor_writes_the_deleted_planning_node_and_the_state_mode_back(tmp_path: Path, monkeypatch):
    import copy
    import shutil

    from _paths import PRODUCT_TEMPLATES

    from neonrp import template as TP
    from neonrp.template import author

    monkeypatch.setenv("NEONRP_PLAN_LOOP", "1")
    s = tmp_path / "mine"
    shutil.copytree(PRODUCT_TEMPLATES / "pct-house.template", s / "pct-mine.template")
    d = json.loads((s / "pct-mine.template" / "template.json").read_text(encoding="utf-8"))
    d["id"] = "pct-mine"
    (s / "pct-mine.template" / "template.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(s))
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(s))
    t = s / "pct-mine.template"
    g = copy.deepcopy(author.base_graph(TP.load(t)))
    assert "plan" in g["nodes"]
    g["nodes"].pop("plan")
    g["edges"] = [e for e in g["edges"] if "plan" not in (e.get("from"), e.get("to"))]
    g["start"] = "resolve"
    g["nodes"]["resolve"] = {**g["nodes"]["resolve"], "state": "jev"}
    r = author.apply_ops(t, [{"op": "set_orchestration", "graph": g}])
    assert r["ok"], r
    TP.build(TP.load(t), tmp_path / "run")
    eff = orchestration.graph(tmp_path / "run")
    assert "plan" not in eff["nodes"] and eff["start"] == "resolve" and eff["state"]["asked"] == "jev"
    bad = copy.deepcopy(g)
    bad["nodes"]["resolve"]["state"] = "telepathy"
    assert not author.apply_ops(t, [{"op": "set_orchestration", "graph": bad}])["ok"]
