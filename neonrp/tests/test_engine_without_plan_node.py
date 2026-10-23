"""Isolation judge: the engine plays every kind of game with the planning beat's code absent.

先商量、后清算 is one orchestration among many — werewolf, murder mysteries, galgames need neither beat. In releases it
comes from the private layer; the open engine has no such node. So: with ``neonrp.core.plan_loop`` unimportable, the
private layer off and the contracts' turn settings stripped (= the public contracts), every shipped template still
builds and plays turns on the plain turn alone — as an ordinary chat session (a table game like werewolf too:
10-09 its build gets the engine's table host and a complete playthrough)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from _paths import PRODUCT_TEMPLATES

_PROBE = r'''
import json, os, sys, tempfile
from pathlib import Path
os.environ["NEONRP_PRIVATE"] = "off"
os.environ["NEONRP_HOME"] = tempfile.mkdtemp()  # never the developer's own model config: stub only
os.environ["NEONRP_S1_BACKEND"] = "off"
os.environ.pop("NEONRP_PLAN_LOOP", None)
sys.modules["neonrp.core.plan_loop"] = None  # any import of it raises ImportError
from neonrp import template
from neonrp.core import node_kinds
from neonrp.core.conversation import ConversationSession
from neonrp.core.manifest import Manifest
from neonrp.core.paths import get_data_dir_name
assert node_kinds.get("plan") is None
out = {}
for tdir in sorted(d for d in Path(sys.argv[1]).iterdir() if (d / "template.json").is_file()):   # not shipped.json (10-17)
    root = Path(tempfile.mkdtemp()) / "run"
    template.build(template.load(tdir), root)
    meta = root / get_data_dir_name(root) / "meta" / "play_contract.json"
    if meta.exists():
        c = json.loads(meta.read_text(encoding="utf-8")); c.pop("engine", None); meta.write_text(json.dumps(c), encoding="utf-8")
    nr = root / ".neonrp"; nr.mkdir(exist_ok=True)
    if not (nr / "manifest.json").exists():
        m = Manifest(); m.branches["main"].head_event = -1
        (nr / "manifest.json").write_text(json.dumps(m.model_dump(), default=str), encoding="utf-8")
    (nr / "config.json").write_text(json.dumps({"llm": {"provider": "stub", "model": "stub-model"}}), encoding="utf-8")
    from neonrp.core import orchestration
    g = orchestration.graph(root)
    trig = {k for e in g["edges"] for k in (e.get("on") or {})}
    graph_ok = "plan" not in g["nodes"] and g["start"] == "resolve" and not (trig & {"words", "host", "dm", "judge"})
    s = ConversationSession(root, "world-agent", mode="play")
    res = [s.send(t) for t in ("开始", "我四处看看")]
    out[tdir.name] = {"ok": all(getattr(r, "success", False) for r in res), "graph_ok": graph_ok,
                      "routes": [str(getattr(r, "route_decision", "") or "") for r in res]}
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


@pytest.mark.timeout(600)
def test_every_template_plays_without_the_planning_node():
    tpl = PRODUCT_TEMPLATES
    p = subprocess.run([sys.executable, "-c", _PROBE, str(tpl)], capture_output=True, text=True, timeout=580,
                       cwd=Path(__file__).resolve().parents[1])
    line = next((x for x in p.stdout.splitlines() if x.startswith("RESULT ")), None)
    assert line, p.stderr[-3000:]
    res = json.loads(line[len("RESULT "):])
    assert len(res) == len([d for d in tpl.iterdir() if (d / "template.json").is_file()]) >= 2, res   # open-source repo: the shipped two (10-17)
    for name, r in res.items():
        assert r["ok"] and r["graph_ok"], (name, r)  # and its graph has no planning node / trigger
        assert not any(x.startswith("plan_loop") for x in r["routes"]), (name, r)  # no planning beat took a turn
        assert all(x.startswith("multi_agent_commit") or x == "opening" for x in r["routes"]) and r["routes"][-1].startswith("multi_agent_commit"), (name, r)  # the v3 turn, not the legacy loop (an authored opening is served as is)
