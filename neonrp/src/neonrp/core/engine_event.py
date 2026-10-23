"""M18 Phase 1 — the typed EngineEvent vocabulary.

The engine EMITS one typed event stream onto the session bus instead of
being wired to frontend-shaped callbacks. Two topics, by volume class:

- ``engine/event``  — lifecycle events (turn_started, tool_use, soul_status,
  turn_finished, …). Recorded into the per-turn trace.
- ``engine/stream`` — token-volume streaming (narration chunks, thinking
  deltas). Dispatched to subscribers but NEVER recorded (a turn would
  otherwise bloat the trace with per-token messages).

An ``EngineEvent`` is deliberately just ``kind + data`` — JSON-only, no
object references — so the same payload works over any future transport.
Phase 1 is dual-emit: the engine publishes events AND still calls any
explicitly passed callbacks, so existing frontends keep working while new
ones subscribe (the TUI/web migration is Phase 4.3).

NOTE: ``ask_user`` stays a callback — it is request/response (the turn
blocks on the human's answer), not a fire-and-forget event.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---- lifecycle kinds (engine/event) ---------------------------------------
TURN_STARTED = "turn_started"
TOOL_USE = "tool_use"
TOOL_RESULT = "tool_result"
SOUL_STATUS = "soul_status"
TURN_FINISHED = "turn_finished"

# ---- stream kinds (engine/stream) ------------------------------------------
STREAM_CHUNK = "chunk"
STREAM_THINKING = "thinking"


@dataclass(frozen=True)
class EngineEvent:
    """One typed engine event — ``kind`` + JSON-able ``data``."""

    kind: str
    data: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        return {"kind": self.kind, **self.data}
