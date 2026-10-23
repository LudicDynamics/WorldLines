"""TUI step 1 (10-08): each beat as it lands goes out on engine/beat as contract 1.0 events — dispatched to subscribers
(the TUI renders from them), never recorded into the turn's bus log."""
from __future__ import annotations

from test_engine_v3 import _install

from neonrp.core.conversation import ConversationSession
from neonrp.core.orchestration_trace import TurnTrace


def _trace(seq, kind, **ap):
    t = TurnTrace(turn_seq=seq, player_input="x", world_location="T001/gate_north")
    t.apply = {"beat": {"kind": kind, **ap.pop("beat", {})}, "narration_plain": "…", **ap}
    return t


def test_beats_reach_subscribers_and_are_not_recorded(tmp_path):
    root = _install(tmp_path)
    s = ConversationSession(root, "test-agent", mode="play")
    got: list[dict] = []
    s.bus().subscribe("engine/beat", lambda m: got.append(m.payload))
    s._emit_beats(_trace(1, "plan", beat={"checks": [{"who": "player", "attr": "DEX"}]}))
    s._emit_beats(_trace(1, "resolve", beat={"advanced_by": "player"}, tool_returns=[{"request": "dice 1d20", "text": "14"}],
                         applied=[{"op": "add", "var": "player.hp", "from": 10, "to": 9}]))
    kinds = [e["kind"] for e in got]
    assert kinds == ["node.enter", "plan.beat", "node.leave", "node.enter", "resolve.beat", "dice", "state.changed"]
    assert got[1]["checks"][0]["attr"] == "DEX" and got[-1]["applied"][0]["to"] == 9
    assert not [m for m in s.bus().drain_log() if m.topic == "engine/beat"]
