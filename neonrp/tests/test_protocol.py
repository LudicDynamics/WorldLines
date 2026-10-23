"""M18 §2 — the pinned message protocol (the wire format's regression teeth)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from neonrp.core.conversation import ConversationSession, ConversationTurnResult
from neonrp.core.orchestration_trace import read_turn_traces
from neonrp.core.protocol import validate_message, validate_stream
from neonrp.core.runtime_contract import set_router_execution_mode

from test_multiagent_mode import _make_soul_dir, _write_playthrough
from test_conversation import _setup_project


def test_unknown_topic_is_a_violation() -> None:
    assert validate_message("rogue/topic", {"x": 1})


def test_missing_required_field_is_reported() -> None:
    violations = validate_message("world/narration", {"turn_seq": 1, "text": "x"})
    assert violations and "world_agent_id" in violations[0]


def test_full_turn_stream_conforms(tmp_path: Path) -> None:
    """THE contract test: every message a real multi-agent turn publishes
    (incl. session bootstrap, soul moved_to, location groups) validates
    against the pinned schemas. Dropping a required field fails here."""
    root = _setup_project(tmp_path)
    set_router_execution_mode(root, "multi-agent")
    _write_playthrough(root)
    _make_soul_dir(root, "elena", "si-a1")
    (root / "souls" / "elena-si-a1" / "run_state.json").write_text(
        json.dumps({"sid": "elena", "instance_id": "si-a1", "location": "inn"}),
        encoding="utf-8",
    )
    meta = root / "game" / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "run_state.json").write_text(
        json.dumps({"location": {"node": "north-gate"}, "turn_count": 0}),
        encoding="utf-8",
    )

    # mode="play": since e5f8ef4 the soul-team wrapper is a PLAY-mode
    # construct (build/studio turns stay solo world-agent by design), so the
    # full multi-agent stream this test pins only exists in play mode.
    session = ConversationSession(root, "test-agent", mode="play")

    def _fake_run(*, agent_id: str, **kwargs) -> ConversationTurnResult:
        if agent_id.startswith("soul:"):
            return ConversationTurnResult(
                success=True, run_id="r-soul",
                assistant_message=(
                    '{"state":"completed","confidence":0.6,"urgency":0.2,'
                    '"speech":"x","moved_to":"inn-2"}'
                ),
                turns_used=1,
            )
        return ConversationTurnResult(
            success=True, run_id="r-world",
            assistant_message="The fog holds.", turns_used=1,
        )

    async def _land(deltas, *, turn_seq: int, branch: str = "main") -> str:
        return "wc-protocol"

    with (
        patch(
            "neonrp.core.conversation.run_conversation_turn",
            side_effect=_fake_run,
        ),
        patch(
            "neonrp.core.world_agent.WorldAgent.land_turn",
            side_effect=_land,
        ),
    ):
        result = session.send("look")

    assert result.success is True
    rec = read_turn_traces(root, session.branch)[-1]
    violations = validate_stream(rec["bus_messages"])
    assert violations == [], violations
