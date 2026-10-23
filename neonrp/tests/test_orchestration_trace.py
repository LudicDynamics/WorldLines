"""M18 §7 — per-turn orchestration trace."""

from __future__ import annotations

from pathlib import Path

from neonrp.core.orchestration_trace import (
    SoulTraceEntry,
    TurnTrace,
    append_turn_trace,
    read_turn_traces,
)


def test_turn_trace_round_trips(tmp_path: Path) -> None:
    t = TurnTrace(
        turn_seq=3,
        player_input="和 elena 说话",
        player_intent_kind="declared_action",
        world_location="north-gate",
    )
    t.souls.append(
        SoulTraceEntry(
            sid="elena", instance_id="si-elena0001", activated=True,
            reason="in active_souls", state="completed", speech="我想不起来。",
        )
    )
    t.souls.append(
        SoulTraceEntry(sid="rowan", instance_id="si-rowan0001", activated=False, reason="off-stage")
    )
    t.world_commit_id = "abc123abc123"
    t.landed_ok = True
    t.narration_chars = 412

    append_turn_trace(tmp_path, "main", t)
    recs = read_turn_traces(tmp_path, "main")

    assert len(recs) == 1
    rec = recs[0]
    assert rec["turn_seq"] == 3
    assert rec["player"]["intent_kind"] == "declared_action"
    assert rec["world_location"] == "north-gate"
    assert rec["land"] == {"commit_id": "abc123abc123", "ok": True}
    assert [(s["sid"], s["activated"]) for s in rec["souls"]] == [
        ("elena", True),
        ("rowan", False),
    ]


def test_activated_soul_carries_speech_inactive_does_not(tmp_path: Path) -> None:
    t = TurnTrace(turn_seq=1)
    t.souls.append(
        SoulTraceEntry(sid="elena", instance_id="si-e", activated=True, speech="hi")
    )
    t.souls.append(
        SoulTraceEntry(sid="rowan", instance_id="si-r", activated=False, speech="")
    )
    append_turn_trace(tmp_path, "main", t)
    rec = read_turn_traces(tmp_path, "main")[0]
    elena, rowan = rec["souls"]
    assert elena["speech"] == "hi" and "tool_calls" in elena
    # An inactive soul records no speech / tool_calls — it did not run.
    assert "speech" not in rowan and "tool_calls" not in rowan


def test_traces_append_in_order(tmp_path: Path) -> None:
    for n in (1, 2, 3):
        append_turn_trace(tmp_path, "main", TurnTrace(turn_seq=n))
    recs = read_turn_traces(tmp_path, "main")
    assert [r["turn_seq"] for r in recs] == [1, 2, 3]
    assert [r["turn_seq"] for r in read_turn_traces(tmp_path, "main", last=2)] == [2, 3]


def test_branch_name_with_slash_is_safe(tmp_path: Path) -> None:
    append_turn_trace(tmp_path, "dev/feature", TurnTrace(turn_seq=7))
    assert read_turn_traces(tmp_path, "dev/feature")[0]["turn_seq"] == 7


def test_read_missing_trace_is_empty(tmp_path: Path) -> None:
    assert read_turn_traces(tmp_path, "main") == []


def test_record_tool_call_preview(tmp_path: Path) -> None:
    t = TurnTrace(turn_seq=1)
    t.record_tool_call("set_active_souls", {"active": ["elena"]})
    rec = TurnTrace.to_dict(t)
    assert rec["world_agent"]["tool_calls"][0]["name"] == "set_active_souls"
    assert "elena" in rec["world_agent"]["tool_calls"][0]["args"]


def test_bus_messages_round_trip(tmp_path: Path) -> None:
    # M18 Phase 2c: the per-turn bus stream the runtime drains into the
    # trace must survive the JSONL round-trip intact and in order.
    from neonrp.core.message_bus import InProcessBus

    bus = InProcessBus()
    bus.start_recording()
    bus.publish("world/scene", {"turn_seq": 1})
    bus.publish("soul/si-e/response", {"state": "completed"})
    bus.publish("world/narration", {"narration_chars": 200})

    t = TurnTrace(turn_seq=1)
    t.bus_messages = [m.to_dict() for m in bus.drain_log()]
    append_turn_trace(tmp_path, "main", t)

    rec = read_turn_traces(tmp_path, "main")[0]
    assert [m["topic"] for m in rec["bus_messages"]] == [
        "world/scene",
        "soul/si-e/response",
        "world/narration",
    ]
    assert [m["seq"] for m in rec["bus_messages"]] == [1, 2, 3]


def test_bus_messages_default_empty(tmp_path: Path) -> None:
    append_turn_trace(tmp_path, "main", TurnTrace(turn_seq=1))
    assert read_turn_traces(tmp_path, "main")[0]["bus_messages"] == []


def test_find_by_commit_and_replay_stream(tmp_path: Path) -> None:
    """M18 §7.3: commit → trace lookup, and replay republishes the recorded
    stream in order onto a fresh bus."""
    from neonrp.core.message_bus import InProcessBus
    from neonrp.core.orchestration_trace import (
        find_trace_by_commit,
        replay_turn_stream,
    )

    t = TurnTrace(turn_seq=4, player_input="x", world_location="inn")
    t.world_commit_id = "wc-replayme"
    t.landed_ok = True
    t.bus_messages = [
        {"topic": "world/scene", "payload": {"turn_seq": 4}, "seq": 1, "ts": "T1"},
        {"topic": "soul/si-a1/response", "payload": {"digest": "d"}, "seq": 2, "ts": "T2"},
        {"topic": "world/narration", "payload": {"text": "n"}, "seq": 3, "ts": "T3"},
    ]
    append_turn_trace(tmp_path, "main", t)
    append_turn_trace(tmp_path, "main", TurnTrace(turn_seq=5))

    found = find_trace_by_commit(tmp_path, "main", "wc-replayme")
    assert found is not None and found["turn_seq"] == 4
    assert find_trace_by_commit(tmp_path, "main", "nope") is None

    bus = InProcessBus()
    seen: list[tuple[str, int]] = []
    bus.subscribe("#", lambda m: seen.append((m.topic, m.payload.get("replay_of_seq"))))
    n = replay_turn_stream(bus, found)
    assert n == 3
    assert seen == [
        ("world/scene", 1),
        ("soul/si-a1/response", 2),
        ("world/narration", 3),
    ]
