"""Tests for event_log module."""

import json
from pathlib import Path

from neonrp.core.event_log import GameEvent, append_event, read_events


class TestGameEvent:
    """Unit tests for GameEvent model."""

    def test_event_with_actor(self):
        """Should serialize and deserialize event with actor field."""
        event = GameEvent(id=1, type="user", payload={"text": "hello"}, actor="player")
        data = event.model_dump()
        assert data["actor"] == "player"

        # Roundtrip
        event2 = GameEvent(**data)
        assert event2.actor == "player"

    def test_event_without_actor(self):
        """Should handle event without actor (backward compatibility)."""
        event = GameEvent(id=1, type="user", payload={"text": "hello"})
        assert event.actor is None

        data = event.model_dump()
        event2 = GameEvent(**data)
        assert event2.actor is None

    def test_event_backward_compatible_deserialization(self):
        """Should deserialize old events that don't have actor field."""
        # Simulate old event format without actor
        old_data = {"id": 1, "timestamp": "2026-01-29T12:00:00+00:00", "type": "user", "payload": {"text": "hello"}}
        event = GameEvent(**old_data)
        assert event.actor is None

    def test_event_with_agent_actor(self):
        """Should handle agent events with agent_id as actor."""
        event = GameEvent(id=1, type="agent", payload={"run_id": "20260129T235900Z_a1b2c3"}, actor="town-master")
        assert event.actor == "town-master"
        assert event.type == "agent"


class TestEventLogRoundtrip:
    """Integration tests for event log with actor field."""

    def test_append_and_read_with_actor(self, tmp_path: Path):
        """Should persist actor field through append and read."""
        # Setup: create events directory
        events_dir = tmp_path / ".neonrp" / "events"
        events_dir.mkdir(parents=True)

        # Append events with different actors
        event1 = GameEvent(id=0, type="user", payload={"text": "hi"}, actor="player")
        event2 = GameEvent(id=1, type="system", payload={"text": "hello"}, actor="system")
        event3 = GameEvent(id=2, type="agent", payload={"action": "update"}, actor="test-agent")

        append_event(tmp_path, "main", event1)
        append_event(tmp_path, "main", event2)
        append_event(tmp_path, "main", event3)

        # Read back
        events = read_events(tmp_path, "main")
        assert len(events) == 3
        assert events[0].actor == "player"
        assert events[1].actor == "system"
        assert events[2].actor == "test-agent"

    def test_read_mixed_events(self, tmp_path: Path):
        """Should read events with and without actor field."""
        events_dir = tmp_path / ".neonrp" / "events"
        events_dir.mkdir(parents=True)

        # Write events manually - some with actor, some without
        events_file = events_dir / "main.jsonl"
        with open(events_file, "w", encoding="utf-8") as f:
            # Old format without actor
            f.write(
                json.dumps(
                    {"id": 0, "timestamp": "2026-01-29T12:00:00+00:00", "type": "user", "payload": {"text": "old"}}
                )
                + "\n"
            )
            # New format with actor
            f.write(
                json.dumps(
                    {
                        "id": 1,
                        "timestamp": "2026-01-29T12:01:00+00:00",
                        "type": "user",
                        "payload": {"text": "new"},
                        "actor": "player",
                    }
                )
                + "\n"
            )

        events = read_events(tmp_path, "main")
        assert len(events) == 2
        assert events[0].actor is None  # Old event
        assert events[1].actor == "player"  # New event
