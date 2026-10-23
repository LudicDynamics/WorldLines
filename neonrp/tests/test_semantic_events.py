"""Unit tests for the L14.5 semantic event parser."""

from __future__ import annotations

from neonrp.core.semantic_events import (
    SEMANTIC_EVENT_ENABLED_MODES,
    SemanticEvent,
    parse_semantic_events,
)


def _types(events: list[SemanticEvent]) -> list[str]:
    return [e.type for e in events]


def test_parser_returns_empty_for_disabled_mode() -> None:
    text = "Some narration.\n\n```json\n{\"dialogue\": \"hi\"}\n```"
    assert parse_semantic_events(text, mode="build") == []
    assert parse_semantic_events(text, mode="sandbox") == []


def test_parser_enabled_modes_is_play_only() -> None:
    assert SEMANTIC_EVENT_ENABLED_MODES == {"play"}


def test_parser_extracts_dialogue_and_state_delta_from_json_block() -> None:
    text = """Scene opens.

```json
{
  "dialogue": "Mira looks up.",
  "internal_thought": "The dead don't give gifts.",
  "state_delta": { "affection": -1, "mood": "wary" },
  "flags_to_set": ["mira_token_confrontation"],
  "player_options": [
    {"label": "Apologize"},
    {"label": "Press further"}
  ]
}
```

She doesn't blink."""
    events = parse_semantic_events(text, speaker_hint="mira", mode="play")
    kinds = _types(events)
    # Core expected event types appeared
    assert "character_utterance" in kinds
    assert "inner_monologue" in kinds
    assert "state_update" in kinds
    assert "awaiting_player_action" in kinds
    # Plain narration after the fenced block became a world_utterance
    assert "world_utterance" in kinds


def test_parser_extracts_scene_header_prefix() -> None:
    text = "// Day 2, 06:45 — Stoneford market\n\nYou walk into the square."
    events = parse_semantic_events(text, mode="play")
    assert events[0].type == "scene_header"
    assert "Stoneford" in events[0].text


def test_parser_layer_classification() -> None:
    text = """```json
{"state_delta": {"hp": -3}, "dialogue": "I'm fine."}
```"""
    events = parse_semantic_events(text, speaker_hint="hero", mode="play")
    layers = {e.type: e.layer for e in events}
    # Utterance is L1 (always visible), state update is L2 (chip).
    assert layers.get("character_utterance") == "L1"
    assert layers.get("state_update") == "L2"


def test_parser_state_update_text_summarizes_delta() -> None:
    text = """```json
{"state_delta": {"affection": -1, "mood": "wary"}}
```"""
    events = parse_semantic_events(text, mode="play")
    state_updates = [e for e in events if e.type == "state_update"]
    assert state_updates, "expected at least one state_update event"
    summary = state_updates[0].text
    assert "affection" in summary
    assert "mood" in summary


def test_parser_flag_only_payload() -> None:
    text = """```json
{"flags_to_set": ["first_meeting"]}
```"""
    events = parse_semantic_events(text, mode="play")
    assert any(e.type == "state_update" and "first_meeting" in e.text for e in events)
