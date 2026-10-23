"""M23 engine world clock — pure-code, idempotent, replay-safe time advance."""

from __future__ import annotations

import json
from pathlib import Path

from neonrp.core.world_clock import DEFAULT_TICK_MINUTES, tick_world


def _write_run_state(root: Path, **fields) -> Path:
    meta = root / "game" / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    path = meta / "run_state.json"
    path.write_text(json.dumps(fields, ensure_ascii=False), encoding="utf-8")
    return path


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_tick_advances_clock_by_delta(tmp_path: Path) -> None:
    path = _write_run_state(
        tmp_path, turn_count=1, time={"day": 1, "clock": "09:00", "period": "morning"}
    )
    out = tick_world(tmp_path)
    assert out["clock"] == f"09:{DEFAULT_TICK_MINUTES:02d}"
    assert _read(path)["time"]["clock"] == "09:10"


def test_tick_custom_delta_and_period(tmp_path: Path) -> None:
    _write_run_state(tmp_path, turn_count=1, time={"day": 1, "clock": "16:55"})
    out = tick_world(tmp_path, delta_minutes=10)
    assert out["clock"] == "17:05"
    assert out["period"] == "evening"  # 17:00 enters the evening band [17,21)


def test_period_bands(tmp_path: Path) -> None:
    from neonrp.core.world_clock import _period_for_hour

    assert _period_for_hour(8) == "morning"
    assert _period_for_hour(13) == "day"
    assert _period_for_hour(19) == "evening"
    assert _period_for_hour(2) == "night"


def test_tick_rolls_over_day(tmp_path: Path) -> None:
    _write_run_state(tmp_path, turn_count=1, time={"day": 1, "clock": "23:55"})
    out = tick_world(tmp_path, delta_minutes=10)
    assert out["clock"] == "00:05"
    assert out["day"] == 2
    assert out["period"] == "night"


def test_idempotent_per_turn(tmp_path: Path) -> None:
    """Re-ticking the same turn (replay/retry) must not double-advance."""
    path = _write_run_state(tmp_path, turn_count=1, time={"day": 1, "clock": "09:00"})
    tick_world(tmp_path)
    tick_world(tmp_path)
    tick_world(tmp_path)
    assert _read(path)["time"]["clock"] == "09:10"  # advanced exactly once


def test_advances_again_on_next_turn(tmp_path: Path) -> None:
    path = _write_run_state(tmp_path, turn_count=1, time={"day": 1, "clock": "09:00"})
    tick_world(tmp_path)
    # simulate engine bumping turn_count for the next turn
    state = _read(path)
    state["turn_count"] = 2
    path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    tick_world(tmp_path)
    assert _read(path)["time"]["clock"] == "09:20"


def test_opening_turn_not_advanced(tmp_path: Path) -> None:
    """turn_count<=0 is the opening — world stays at seed time."""
    path = _write_run_state(tmp_path, turn_count=0, time={"day": 1, "clock": "08:00"})
    tick_world(tmp_path)
    assert _read(path)["time"]["clock"] == "08:00"
    assert "_clock_ticked_for" not in _read(path)


def test_marker_kept_out_of_time_dict(tmp_path: Path) -> None:
    """Idempotency marker lives at run_state top level, not in perceived time."""
    path = _write_run_state(tmp_path, turn_count=1, time={"day": 1, "clock": "09:00"})
    tick_world(tmp_path)
    state = _read(path)
    assert state["_clock_ticked_for"] == 1
    assert "_clock_ticked_for" not in state["time"]
    assert "_ticked_for" not in state["time"]


def test_period_only_clock_not_corrupted(tmp_path: Path) -> None:
    """A period-only world (no HH:MM) is stamped but not numerically advanced."""
    path = _write_run_state(
        tmp_path, turn_count=1, time={"day": 1, "period": "morning"}
    )
    out = tick_world(tmp_path)
    assert out.get("period") == "morning"  # untouched
    assert _read(path)["_clock_ticked_for"] == 1


def test_unreadable_run_state_is_safe(tmp_path: Path) -> None:
    """No run_state ⇒ no crash, empty result, turn proceeds."""
    assert tick_world(tmp_path) == {}
