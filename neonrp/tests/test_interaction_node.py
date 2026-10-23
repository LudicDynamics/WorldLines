"""Node kinds taking the turn: interaction nodes, the opening: a game client's interaction takes the turn through a node kind of its own.

The seam is public: any node-kind plugin whose ``active`` holds takes the turn before the plain one (it used to be only
the planning beat). The interaction graphs themselves (move · examine · talk · approach · encounter) are the open
engine's own since 10-19 (core/interaction_node, they used to be a private-layer plugin): checked here on the stub model with
the private layer off — a gate refuses without touching the world, a move lands (place · turn · clock), a theft rolls and
lands its effect."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_HEAD = r'''
import json, os, sys, tempfile, random
from pathlib import Path
os.environ["NEONRP_HOME"] = tempfile.mkdtemp()  # never the developer's own model config: stub only
os.environ["NEONRP_S1_BACKEND"] = "off"
from neonrp import template
from neonrp.core.conversation import ConversationSession, ConversationTurnResult
from neonrp.core.manifest import Manifest
from neonrp.core.paths import get_data_dir_name

def run(tid):
    root = Path(tempfile.mkdtemp()) / "run"
    template.build(template.load(template.discover()[tid]), root)
    nr = root / ".neonrp"; nr.mkdir(exist_ok=True)
    if not (nr / "manifest.json").exists():
        m = Manifest(); m.branches["main"].head_event = -1
        (nr / "manifest.json").write_text(json.dumps(m.model_dump(), default=str), encoding="utf-8")
    (nr / "config.json").write_text(json.dumps({"llm": {"provider": "stub", "model": "stub-model"}}), encoding="utf-8")
    return root

def rs(root):
    return json.loads((root / get_data_dir_name(root) / "meta" / "run_state.json").read_text(encoding="utf-8"))
'''

_SEAM = _HEAD + r'''
os.environ["NEONRP_PRIVATE"] = "off"
from neonrp.core import node_kinds

class Toy:
    kind = "zz-toy"
    def active(self, root, text): return text.startswith("TOY")
    def take_turn(self, session, *, user_text, trace, run_id, on_chunk):
        return ConversationTurnResult(success=True, run_id=run_id, assistant_message="toy!", route_decision="toy")

node_kinds.register(Toy())
root = run("stoneford-elena")
s = ConversationSession(root, "world-agent", mode="play")
a = s.send("TOY move"); b = s.send("我四处看看")
print("RESULT " + json.dumps({"toy": a.route_decision, "toy_text": a.assistant_message, "plain": str(b.route_decision or "")}))
'''

_TOWN = _HEAD + r'''
random.seed(7)
os.environ["NEONRP_PRIVATE"] = "off"
from neonrp.core.registry import load_registry
from neonrp.core.orchestration_trace import read_turn_traces
I = lambda d, w="": "<interaction>" + json.dumps(d, ensure_ascii=False) + "</interaction>" + w
root = run("stoneford-town")
s = ConversationSession(root, "world-agent", mode="play")
t0 = rs(root)
gate = s.send(I({"kind": "move", "to": "T001/road_camp"}))
t1 = rs(root)
move = s.send(I({"kind": "move", "to": "T001/market-square"}))
t2 = rs(root)
steal = s.send(I({"kind": "approach", "target": "NPC007", "approach": "steal"}, "趁他转身,我去摸车厢里的账本。"))
reg = load_registry(root)
tr = read_turn_traces(root, "main", last=1)[-1]["apply"]
flags = sorted(k for k in reg.variables if k.startswith("flag.stole") or k == "town.alert")
print("RESULT " + json.dumps({
  "gate_route": gate.route_decision, "gate_text": gate.assistant_message, "gate_kept": t1["location"] == t0["location"] and t1["time"] == t0["time"],
  "move_route": move.route_decision, "moved": "market" in json.dumps(t2["location"]), "turned": int(t2.get("turn_count") or 0) == int(t1.get("turn_count") or 0) + 1,
  "clock": [t1["time"]["clock"], t2["time"]["clock"]],
  "steal_route": steal.route_decision, "beat": tr["beat"]["kind"], "rolled": bool(tr.get("tool_returns")),
  "landed": "flag.stole.NPC007" in reg.variables or int(reg.variables["town.alert"].value or 0) == 1,
}, ensure_ascii=False))
'''


def _probe(code: str, *args: str) -> dict:
    p = subprocess.run([sys.executable, "-c", code, *args], capture_output=True, text=True, timeout=280, cwd=ROOT)
    line = next((x for x in p.stdout.splitlines() if x.startswith("RESULT ")), None)
    assert line, p.stderr[-3000:]
    return json.loads(line[len("RESULT "):])


@pytest.mark.timeout(300)
def test_any_active_node_kind_takes_the_turn():
    r = _probe(_SEAM)
    assert r["toy"] == "toy" and r["toy_text"] == "toy!"
    assert r["plain"] != "toy"  # an ordinary line still plays the plain turn


@pytest.mark.timeout(300)
def test_town_interactions_land_through_their_own_graph():
    r = _probe(_TOWN)
    assert r["gate_route"] == "interaction:move" and "委托" in r["gate_text"] and r["gate_kept"], r  # refused: nothing moved, no time spent
    assert r["move_route"] == "interaction:move" and r["moved"] and r["turned"], r
    assert r["clock"][0] != r["clock"][1], r
    assert r["steal_route"] == "interaction:approach" and r["beat"] == "interaction.approach" and r["rolled"] and r["landed"], r


def test_a_template_names_its_first_beat(tmp_path):
    """ui.beats survives into the run's record (merge_ui used to drop it): the town opens on its interaction node."""
    from neonrp import template as TP
    from neonrp.core import orchestration

    if "stoneford-town" not in TP.discover():
        pytest.skip("stoneford-town is not in this release")
    root = tmp_path / "run"
    TP.build(TP.load(TP.discover()["stoneford-town"]), root)
    assert orchestration.beat_kinds(root).get("start") == "interaction.move"


_OPEN = _HEAD + r'''
os.environ["NEONRP_PRIVATE"] = "off"
root = run("stoneford-elena")
s = ConversationSession(root, "world-agent", mode="play")
a = s.send("开始游戏")
from neonrp.core.orchestration_trace import read_turn_traces
tr = read_turn_traces(root, "main", last=1)[-1]["apply"]
b = s.send("开始游戏")   # a second start cue is an ordinary line: the world has been opened
print("RESULT " + json.dumps({"route": a.route_decision, "beat": tr["beat"]["kind"], "text": a.assistant_message[:40],
                              "again": str(b.route_decision or "")}, ensure_ascii=False))
'''


@pytest.mark.timeout(300)
def test_the_public_engine_opens_a_world_with_its_authored_opening():
    """10-11: the authored opening was only in the private planning beat — the public engine's first beat went to the
    model, the screen never saw an opening. Now it is the engine's own node kind: no model, no talk."""
    r = _probe(_OPEN)
    assert r["route"] == "opening" and r["beat"] == "opening" and r["text"], r
    assert r["again"] != "opening", r
