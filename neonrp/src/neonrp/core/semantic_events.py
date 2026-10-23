"""Semantic event schema (L14.5) for play mode transcript rendering.

Only play mode runs this pipeline. Sandbox and build keep their
existing raw-tool-call rendering because they are author-facing surfaces
where the diff + raw-trace view is more useful than story-first folding.

Pipeline:
1. Agents return semi-structured payloads (JSON blocks + markdown narration).
   We do NOT change the agent prompt — the parsing is purely retroactive.
2. `parse_semantic_events(payload)` walks the payload and yields a list of
   `SemanticEvent`s. Unrecognized fragments fall back to `world_utterance`
   so no text is lost.
3. The TUI renders L1 (narrative) by default, L2 (semantic summary) when
   a block is expanded, and L3 (raw trace) only when verbose.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Literal


SemanticEventType = Literal[
    "scene_header",
    "world_utterance",
    "character_utterance",
    "inner_monologue",
    "rule_check",
    "state_update",
    "transaction",
    "awaiting_player_action",
    "execution_summary",
    "raw_trace",
]

# Mode gate — parser is only applied when session.mode is in this set.
SEMANTIC_EVENT_ENABLED_MODES = {"play"}


@dataclass
class SemanticEvent:
    """One renderable unit in the transcript."""

    type: SemanticEventType
    layer: Literal["L1", "L2", "L3"]
    speaker: str = ""
    text: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)
_JSON_OBJECT_RE = re.compile(r"\{[^\{\}]*(?:\{[^\{\}]*\}[^\{\}]*)*\}", re.DOTALL)
_SCENE_HEADER_RE = re.compile(r"^(//|═══|# ).*", re.MULTILINE)
_INNER_THOUGHT_RE = re.compile(r"(内心独白|internal thought|inner thought)[:：]\s*(.+)", re.IGNORECASE)


def parse_semantic_events(
    agent_text: str,
    *,
    speaker_hint: str = "world",
    mode: str | None = None,
) -> list[SemanticEvent]:
    """Extract semantic events from an agent's assistant_text payload.

    Args:
        agent_text: the raw assistant_text returned by the model.
        speaker_hint: fallback speaker id for utterance events.
        mode: session mode. If given and not in SEMANTIC_EVENT_ENABLED_MODES,
              returns an empty list (caller should render raw instead).
    """
    if mode is not None and mode not in SEMANTIC_EVENT_ENABLED_MODES:
        return []
    if not isinstance(agent_text, str) or not agent_text.strip():
        return []

    events: list[SemanticEvent] = []
    remaining = agent_text

    # --- Pass 1: JSON fenced blocks produced by domain agents
    for match in _JSON_FENCE_RE.finditer(agent_text):
        payload = match.group(1).strip()
        try:
            data = json.loads(payload)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        events.extend(_events_from_domain_packet(data, speaker_hint))
        remaining = remaining.replace(match.group(0), "", 1)

    # --- Pass 2: plain-text narrative / inner thoughts / scene headers
    for block in _split_narrative_blocks(remaining):
        block = block.strip()
        if not block:
            continue
        if _SCENE_HEADER_RE.match(block):
            events.append(SemanticEvent(type="scene_header", layer="L1", text=block))
            continue
        inner = _INNER_THOUGHT_RE.search(block)
        if inner:
            events.append(
                SemanticEvent(
                    type="inner_monologue",
                    layer="L1",
                    speaker=speaker_hint,
                    text=inner.group(2).strip(),
                )
            )
            continue
        # Default: plain narration
        events.append(
            SemanticEvent(
                type="world_utterance",
                layer="L1",
                speaker=speaker_hint,
                text=block,
            )
        )

    return events


def _events_from_domain_packet(data: dict[str, Any], speaker_hint: str) -> list[SemanticEvent]:
    """Turn a domain-agent JSON packet into events.

    Recognized fields (all optional):
    - `dialogue` / `reaction`     → character_utterance (L1)
    - `internal_thought`          → inner_monologue   (L1)
    - `state_delta` / `state_updates` / `mood_change` / `flags_to_set`
                                  → state_update      (L2)
    - `rule_check` / `roll`       → rule_check        (L2)
    - `player_options` / `options`→ awaiting_player_action (L1)
    - `summary`                   → execution_summary (L2)
    """
    events: list[SemanticEvent] = []
    speaker = str(data.get("speaker") or data.get("agent") or speaker_hint)

    dialogue = data.get("dialogue") or data.get("reaction")
    if isinstance(dialogue, str) and dialogue.strip():
        events.append(
            SemanticEvent(
                type="character_utterance",
                layer="L1",
                speaker=speaker,
                text=dialogue.strip(),
            )
        )

    inner = data.get("internal_thought") or data.get("inner_monologue")
    if isinstance(inner, str) and inner.strip():
        events.append(
            SemanticEvent(
                type="inner_monologue",
                layer="L1",
                speaker=speaker,
                text=inner.strip(),
            )
        )

    for key in ("state_delta", "state_updates", "npc_state_updates", "faction_state_updates", "mood_change"):
        value = data.get(key)
        if value in (None, "", [], {}):
            continue
        events.append(
            SemanticEvent(
                type="state_update",
                layer="L2",
                speaker=speaker,
                text=_summarize_state_delta(key, value),
                data={"key": key, "value": value},
            )
        )

    flags = data.get("flags_to_set") or data.get("flag_to_set")
    if flags:
        if isinstance(flags, str):
            flags = [flags]
        for flag in flags:
            events.append(
                SemanticEvent(
                    type="state_update",
                    layer="L2",
                    speaker=speaker,
                    text=f"flag set: {flag}",
                    data={"key": "flag", "value": flag},
                )
            )

    rule = data.get("rule_check") or data.get("roll")
    if rule:
        events.append(
            SemanticEvent(
                type="rule_check",
                layer="L2",
                speaker=speaker,
                text=_summarize_rule_check(rule),
                data={"rule": rule},
            )
        )

    options = data.get("player_options") or data.get("options")
    if isinstance(options, list) and options:
        events.append(
            SemanticEvent(
                type="awaiting_player_action",
                layer="L1",
                speaker=speaker,
                text="",
                data={"options": options},
            )
        )

    summary = data.get("summary")
    if isinstance(summary, str) and summary.strip():
        events.append(
            SemanticEvent(
                type="execution_summary",
                layer="L2",
                speaker=speaker,
                text=summary.strip(),
            )
        )

    return events


def _summarize_state_delta(key: str, value: Any) -> str:
    if isinstance(value, dict):
        parts = [f"{k}={v}" for k, v in list(value.items())[:6]]
        return f"{key}: " + ", ".join(parts)
    if isinstance(value, list):
        return f"{key}: {len(value)} change(s)"
    return f"{key}: {value}"


def _summarize_rule_check(rule: Any) -> str:
    if isinstance(rule, dict):
        what = str(rule.get("what") or rule.get("check") or "check")
        outcome = str(rule.get("outcome") or rule.get("result") or "")
        total = rule.get("total") or rule.get("roll")
        tail = f" = {outcome}" if outcome else ""
        if total is not None:
            tail += f" (roll {total})"
        return f"{what}{tail}"
    return str(rule)


def _split_narrative_blocks(text: str) -> list[str]:
    """Split by horizontal rules or blank lines so each narrative paragraph
    becomes its own world_utterance event."""
    # Normalize both HR styles into a single marker, then split.
    normalized = re.sub(r"\n---+\n", "\n\n", text)
    return [block for block in normalized.split("\n\n") if block.strip()]
