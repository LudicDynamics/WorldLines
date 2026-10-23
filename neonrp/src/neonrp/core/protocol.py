"""M18 §2 — the pinned message protocol.

The bus payloads ARE the protocol: this module declares, per topic family,
the fields every message MUST carry, and validates a message/stream against
it. The protocol is the project's stability contract — changed deliberately,
never casually (M18 §2.2): the test suite validates a full turn's recorded
stream, so any code change that drops a required field fails loudly.

Validation is test/diagnostic tooling — the runtime does not pay for it on
every publish. ``protocol_version`` rides on every BusMessage envelope.
"""

from __future__ import annotations

from typing import Any

from neonrp.core.message_bus import topic_matches

# Required payload fields per topic family. A field listed here must be
# PRESENT (it may be None where noted in comments) — presence is the contract.
SCHEMAS: dict[str, frozenset[str]] = {
    # world-agent → souls: the scene framing for the turn
    "world/scene": frozenset({"turn_seq", "scene_label", "active_souls"}),
    # integration trigger: which integrator, which souls
    "world/integrate": frozenset({"turn_seq", "world_agent_id", "active_souls"}),
    # narrative material — location-scoped (location may be None = unknown)
    "world/narration": frozenset({"turn_seq", "world_agent_id", "location", "text"}),
    # world-state transitions (turn land AND session bootstrap variants)
    "world/state": frozenset({"turn_seq", "world_agent_id", "active_souls"}),
    # two-pass (Plan→Correct→Apply): the world-agent's per-soul move
    # corrections this turn (observability; Pass B applies them). The
    # `corrections` map is instance_id → moved_to ("" = move cancelled).
    "world/corrections": frozenset({"turn_seq", "world_agent_id", "corrections"}),
    # per-soul perception (the ScenePacket on the wire)
    "soul/+/request": frozenset(
        {"instance_id", "scene_label", "location", "last_narration"}
    ),
    # per-soul report (the SoulTurnReport digest on the wire)
    "soul/+/response": frozenset(
        {"sid", "instance_id", "state", "role", "feeds_world", "digest"}
    ),
    # presentation directives for one player
    "player/+/output": frozenset({"kind", "text"}),
    # lifecycle events
    "engine/event": frozenset({"kind"}),
    # token-volume stream events (transient; never recorded)
    "engine/stream": frozenset({"kind"}),
}


def validate_message(topic: str, payload: dict[str, Any]) -> list[str]:
    """Return violations ([] = valid). Unknown topics are violations too —
    the namespace is closed by design (M18 §2.1)."""
    for pattern, required in SCHEMAS.items():
        if topic_matches(pattern, topic):
            missing = sorted(required - set(payload.keys()))
            return [f"{topic}: missing {missing}"] if missing else []
    return [f"{topic}: unknown topic (not in the M18 §2.1 namespace)"]


def validate_stream(messages: list[Any]) -> list[str]:
    """Validate a recorded bus stream (BusMessage objects or to_dict() dicts).
    Returns every violation found."""
    violations: list[str] = []
    for msg in messages:
        topic = msg.get("topic") if isinstance(msg, dict) else getattr(msg, "topic", "")
        payload = (
            msg.get("payload") if isinstance(msg, dict) else getattr(msg, "payload", {})
        )
        violations.extend(validate_message(str(topic), payload or {}))
    return violations
