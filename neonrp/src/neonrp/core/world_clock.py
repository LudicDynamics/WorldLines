"""Engine-owned world clock (M23).

Single authoritative time source: ``game/meta/run_state.json`` → ``time``.

The clock is advanced by PURE CODE at the very top of every multi-agent turn,
**before any perception is built** — so souls, the player, and away-location
agents all perceive the SAME freshly-advanced time this turn. This is the fix
for three coupled bugs that came from advancing time at the *end* of the turn
inside an LLM (clock-keeper):

1. souls perceived last-turn's time (one-turn lag);
2. two divergent time sources (run_state vs timeline/current.json);
3. away lines (e.g. a soul waiting at a gate) never saw the world move.

With the tick at the top, time is monotonic, deterministic, replay-safe, and
read identically by every line. ``clock-keeper`` no longer owns time.

The tick is idempotent per turn (guarded by ``_clock_ticked_for`` at the
run_state top level, NOT inside ``time`` so the perceived time dict stays clean)
— replay/retry of the same turn never double-advances.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from neonrp.core.paths import get_data_dir_name

logger = logging.getLogger(__name__)

DEFAULT_TICK_MINUTES = 10
_MINUTES_PER_DAY = 24 * 60


def _period_for_hour(hour: int) -> str:
    """Coarse time-of-day band — kept in sync with how content speaks of时段."""
    if 5 <= hour < 11:
        return "morning"
    if 11 <= hour < 17:
        return "day"
    if 17 <= hour < 21:
        return "evening"
    return "night"


def _parse_clock(clock: Any) -> tuple[int, int] | None:
    """Parse ``"HH:MM"`` → (hour, minute), or None if not a wall-clock string."""
    try:
        hh, mm = str(clock).strip().split(":")
        return int(hh), int(mm)
    except (ValueError, AttributeError):
        return None


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def tick_world(
    root: Path, *, delta_minutes: int = DEFAULT_TICK_MINUTES
) -> dict[str, Any]:
    """Advance the world clock by ``delta_minutes``; return the new ``time`` dict.

    - Reads ``turn_count`` from run_state itself. The **opening turn**
      (``turn_count <= 0``) is left at the seed time — the world only starts
      moving once the player has taken a real turn.
    - Idempotent per ``turn_count`` via the top-level ``_clock_ticked_for``
      marker.
    - Period-only clocks (no ``HH:MM``, e.g. kagura) are not numerically
      advanced here — only the idempotency marker is stamped — leaving their
      period to content. Wall-clock worlds (stoneford) roll minutes → hours →
      day.
    - Never raises: an unreadable/unwritable run_state simply isn't advanced
      and the turn proceeds.
    """
    path = root / get_data_dir_name(root) / "meta" / "run_state.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.debug("world clock tick skipped (run_state unreadable)", exc_info=True)
        return {}
    if not isinstance(state, dict):
        return {}

    time = state.get("time")
    if not isinstance(time, dict):
        time = {}

    turn_count = _coerce_int(state.get("turn_count"))
    if turn_count <= 0:
        # Opening turn: world begins at its seed time.
        return time
    if state.get("_clock_ticked_for") == turn_count:
        # Already ticked this turn (replay/retry) — do not double-advance.
        return time

    parsed = _parse_clock(time.get("clock"))
    if parsed is not None:
        hh, mm = parsed
        total = hh * 60 + mm + max(0, int(delta_minutes))
        day_roll, minutes = divmod(total, _MINUTES_PER_DAY)
        new_hh, new_mm = divmod(minutes, 60)
        time["clock"] = f"{new_hh:02d}:{new_mm:02d}"
        time["period"] = _period_for_hour(new_hh)
        if day_roll:
            time["day"] = _coerce_int(time.get("day"), 1) + day_roll

    state["time"] = time
    state["_clock_ticked_for"] = turn_count
    try:
        path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        logger.debug("world clock tick write skipped", exc_info=True)
    return time
