"""M18 Phase A — world-agent singleton wrapper tests.

Phase A is a pure wrapper with zero behaviour change. These tests pin:
  - A1: WorldAgent owns the active_agent.json + run_state.json reads.
  - A2: run_turn forwards verbatim to run_conversation_turn and returns it
    unchanged (legacy byte-identical path).
  - A3: playthrough.json is detected + logged once; nothing is spawned.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch

from neonrp.core.conversation import ConversationSession, ConversationTurnResult
from neonrp.core.world_agent import WorldAgent, read_playthrough

from test_conversation import _setup_project


class _RecordCapture(logging.Handler):
    """Capture records directly off the world_agent logger.

    pytest's ``caplog`` attaches to the root logger and relies on
    propagation. Another suite test (``test_cli_logging``) sets
    ``logging.getLogger("neonrp").propagate = False`` as a global side
    effect, which breaks root-level capture depending on test order. A
    handler bound straight to the module logger is order-independent.
    """

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _write_playthrough(root: Path) -> None:
    payload = {
        "schema_version": 2,
        "playthrough_id": "pt-test-0001",
        "world": {"wid": "dark-train", "instance_id": "wi-1", "version_hash": "abc", "head_commit": "c1"},
        "world_agent_team": {
            "seeded_from": "game/agents/manifest.json@abc",
            "agents": [
                {"id": "world-agent", "role": "orchestrator", "singleton": True},
                {"id": "combat-referee", "role": "domain"},
            ],
        },
        "souls": [
            {"sid": "elena", "instance_id": "si-a1", "version_hash": "v", "head_commit": "s1", "role": "player"},
            {"sid": "conductor", "instance_id": "si-b7", "version_hash": "v", "head_commit": "s2", "role": "npc"},
        ],
        "created_at": "2026-05-15T13:00:00Z",
    }
    (root / ".neonrp" / "playthrough.json").write_text(json.dumps(payload), encoding="utf-8")


class TestReadPlaythrough:
    def test_absent_returns_none(self, tmp_path: Path) -> None:
        root = _setup_project(tmp_path)
        assert read_playthrough(root) is None

    def test_invalid_json_returns_none(self, tmp_path: Path) -> None:
        root = _setup_project(tmp_path)
        (root / ".neonrp" / "playthrough.json").write_text("{ not json", encoding="utf-8")
        assert read_playthrough(root) is None

    def test_parsed_roster(self, tmp_path: Path) -> None:
        root = _setup_project(tmp_path)
        _write_playthrough(root)
        manifest = read_playthrough(root)
        assert manifest is not None
        assert [s["sid"] for s in manifest.souls] == ["elena", "conductor"]
        assert manifest.world_agent_team["agents"][0]["id"] == "world-agent"


class TestWorldAgentA2Delegation:
    def test_run_turn_is_pure_passthrough(self, tmp_path: Path) -> None:
        root = _setup_project(tmp_path)
        wa = WorldAgent(root)
        expected = ConversationTurnResult(success=True, run_id="r-passthrough", turns_used=1)
        with patch(
            "neonrp.core.conversation.run_conversation_turn", return_value=expected
        ) as mock_run:
            result = wa.run_turn(root=root, agent_id="test-agent", messages=[])
        assert result is expected
        mock_run.assert_called_once()
        assert mock_run.call_args.kwargs == {"root": root, "agent_id": "test-agent", "messages": []}

    def test_session_send_routes_through_world_agent_unchanged(self, tmp_path: Path) -> None:
        root = _setup_project(tmp_path)
        session = ConversationSession(root, "test-agent")
        expected = ConversationTurnResult(success=True, run_id="r-sess", turns_used=1)
        with patch(
            "neonrp.core.conversation.run_conversation_turn", return_value=expected
        ) as mock_run:
            result = session.send("hello")
        assert result.run_id == "r-sess"
        mock_run.assert_called_once()


class TestWorldAgentA3Detection:
    def _attach(self) -> tuple[logging.Logger, _RecordCapture, int]:
        logger = logging.getLogger("neonrp.core.world_agent")
        handler = _RecordCapture()
        logger.addHandler(handler)
        prev_level = logger.level
        logger.setLevel(logging.INFO)
        return logger, handler, prev_level

    def test_no_playthrough_no_log_no_spawn(self, tmp_path: Path) -> None:
        root = _setup_project(tmp_path)
        wa = WorldAgent(root)
        logger, handler, prev_level = self._attach()
        try:
            assert wa.detect_playthrough() is None
        finally:
            logger.removeHandler(handler)
            logger.setLevel(prev_level)
        assert not any("playthrough detected" in r.getMessage() for r in handler.records)

    def test_playthrough_logged_once_and_spawns_nothing(self, tmp_path: Path) -> None:
        root = _setup_project(tmp_path)
        _write_playthrough(root)
        wa = WorldAgent(root)
        logger, handler, prev_level = self._attach()
        try:
            m1 = wa.detect_playthrough()
            m2 = wa.detect_playthrough()
        finally:
            logger.removeHandler(handler)
            logger.setLevel(prev_level)
        assert m1 is not None and m2 is not None
        # Logged exactly once across two calls (detect-once gate).
        detect_records = [r for r in handler.records if "M18 playthrough detected" in r.getMessage()]
        assert len(detect_records) == 1
        line = detect_records[0].getMessage()
        assert "pt-test-0001" in line
        assert "'elena'" in line and "'conductor'" in line
        # Phase A spawns nothing: no character-agent / mailbox attributes.
        assert not hasattr(wa, "_character_agents")
        assert not hasattr(wa, "_mailboxes")
