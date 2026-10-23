"""M18 Phase E — TUI surfacing of the multi-agent runtime.

Phase E is cosmetic: it renders the world-agent's CharacterRuntime
registry (E1), wires a cancel hotkey to the committed
``world_agent.interrupt`` primitive (E2). These tests mock the
world-agent surface; they never drive a real turn.

Style mirrors ``tests/test_app.py`` (lightweight widget/method tests,
MagicMock collaborators).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from neonrp.tui.app import (
    CharacterStatusLane,
    NeonRPApp,
    _runtime_state,
    _runtime_tokens,
    format_character_status_lines,
    format_soul_status_lines,
)


# ---------------------------------------------------------------------------
# Helpers — fake CharacterRuntime / task without an event loop.
# ---------------------------------------------------------------------------

def _done_task(*, result=None, cancelled=False, exc=None):
    """A stand-in for an asyncio.Task that is already finished."""
    t = MagicMock()
    t.done.return_value = True
    t.cancelled.return_value = cancelled
    t.exception.return_value = exc
    t.result.return_value = result
    return t


def _running_task():
    t = MagicMock()
    t.done.return_value = False
    return t


def _runtime(sid, *, task=None, turn=0, state=None, tokens=None):
    agent = SimpleNamespace(sid=sid, turn_index=turn)
    if tokens is not None:
        agent.tokens = tokens
    if task is None and state is not None:
        delta = SimpleNamespace(state=state)
        if tokens is not None:
            delta.tokens = tokens
        task = _done_task(result=delta)
    return SimpleNamespace(agent=agent, task=task, cancel_event=MagicMock())


# ---------------------------------------------------------------------------
# E1 — status line rendering from a mocked registry.
# ---------------------------------------------------------------------------

class TestE1StatusLine:
    def test_idle_when_no_task(self):
        rts = {"elena": _runtime("elena", turn=3)}
        assert format_character_status_lines(rts) == ["elena · turn 3 · idle · 0 tok"]

    def test_thinking_when_task_running(self):
        rts = {"elena": _runtime("elena", task=_running_task(), turn=7)}
        assert format_character_status_lines(rts) == [
            "elena · turn 7 · thinking · 0 tok"
        ]

    def test_completed_collapses_to_idle(self):
        rts = {"e": _runtime("e", turn=2, state="completed")}
        assert _runtime_state(rts["e"]) == "idle"

    def test_interrupted_state_passthrough(self):
        rts = {"e": _runtime("e", turn=1, state="interrupted")}
        assert format_character_status_lines(rts) == [
            "e · turn 1 · interrupted · 0 tok"
        ]

    def test_degraded_state_passthrough(self):
        rts = {"e": _runtime("e", turn=9, state="degraded")}
        assert format_character_status_lines(rts) == ["e · turn 9 · degraded · 0 tok"]

    def test_crashed_task_is_degraded(self):
        rts = {"e": _runtime("e", task=_done_task(exc=RuntimeError("boom")))}
        assert _runtime_state(rts["e"]) == "degraded"

    def test_cancelled_task_is_degraded(self):
        rts = {"e": _runtime("e", task=_done_task(cancelled=True))}
        assert _runtime_state(rts["e"]) == "degraded"

    def test_token_count_read_from_delta_when_present(self):
        rts = {"e": _runtime("e", turn=4, state="completed", tokens=1234)}
        assert _runtime_tokens(rts["e"]) == 1234
        assert format_character_status_lines(rts) == ["e · turn 4 · idle · 1234 tok"]

    def test_lines_sorted_by_sid(self):
        rts = {
            "zoe": _runtime("zoe", turn=1),
            "amy": _runtime("amy", turn=2),
        }
        lines = format_character_status_lines(rts)
        assert lines[0].startswith("amy") and lines[1].startswith("zoe")

    def test_lane_widget_collapses_when_empty(self):
        lane = CharacterStatusLane()
        lane.update = MagicMock()
        lane.render_runtimes({})
        assert lane.display is False
        lane.update.assert_called_once_with("")

    def test_lane_widget_renders_and_shows_when_populated(self):
        lane = CharacterStatusLane()
        lane.update = MagicMock()
        lane.render_runtimes({"e": _runtime("e", turn=5, state="interrupted")})
        assert lane.display is True
        lane.update.assert_called_once_with("e · turn 5 · interrupted · 0 tok")

    def test_app_reads_registry_without_constructing_world_agent(self):
        app = NeonRPApp(mode="play")
        # No session ⇒ empty registry, never forces a world-agent.
        assert app._character_runtimes() == {}
        # Session present but world-agent not yet lazily built ⇒ still empty
        # (we must NOT call _get_world_agent here — that would construct one).
        app.session = SimpleNamespace(_world_agent=None)
        assert app._character_runtimes() == {}
        # World-agent live ⇒ a *copy* of its _characters dict.
        wa = SimpleNamespace(_characters={"e": _runtime("e")})
        app.session = SimpleNamespace(_world_agent=wa)
        snap = app._character_runtimes()
        assert set(snap) == {"e"}
        assert snap is not wa._characters  # defensive copy, not aliased

    def test_soul_lane_shows_inactive_souls_as_background_action(self):
        snapshot = {
            "si-elena": {"name": "Elena", "role": "active", "state": "queued"},
            "si-rowan": {
                "name": "Rowan",
                "role": "inactive",
                "state": "background",
            },
        }

        assert format_soul_status_lines(snapshot, "zh") == [
            "在场灵魂 · 2",
            "  · Elena · 待命",
            "  ◌ Rowan · 后台行动",
        ]

    def test_soul_lane_keeps_legacy_offstage_as_background_action(self):
        snapshot = {
            "si-rowan": {
                "name": "Rowan",
                "role": "inactive",
                "state": "offstage",
            }
        }

        assert format_soul_status_lines(snapshot, "zh") == [
            "在场灵魂 · 1",
            "  ◌ Rowan · 后台行动",
        ]

    def test_apply_soul_status_snapshot_preserves_each_transition(self):
        app = NeonRPApp(mode="play")
        rendered = []

        def _capture_refresh():
            rendered.append(app._soul_status_snapshot)

        app._refresh_character_lane = _capture_refresh

        running = {
            "si-elena": {"name": "Elena", "role": "active", "state": "running"}
        }
        completed = {
            "si-elena": {"name": "Elena", "role": "active", "state": "completed"}
        }

        app._apply_soul_status_snapshot(running)
        app._apply_soul_status_snapshot(completed)
        running["si-elena"]["state"] = "completed"

        assert rendered[0]["si-elena"]["state"] == "running"
        assert rendered[1]["si-elena"]["state"] == "completed"


# ---------------------------------------------------------------------------
# E2 — cancel hotkey calls world_agent.interrupt(sid).
# ---------------------------------------------------------------------------

class TestE2CancelHotkey:
    def test_focused_sid_prefers_running_character(self):
        app = NeonRPApp(mode="play")
        wa = SimpleNamespace(
            _characters={
                "idle_one": _runtime("idle_one"),
                "busy_one": _runtime("busy_one", task=_running_task()),
            }
        )
        app.session = SimpleNamespace(_world_agent=wa)
        assert app._focused_character_sid() == "busy_one"

    def test_focused_sid_falls_back_to_first_when_none_running(self):
        app = NeonRPApp(mode="play")
        wa = SimpleNamespace(
            _characters={"zoe": _runtime("zoe"), "amy": _runtime("amy")}
        )
        app.session = SimpleNamespace(_world_agent=wa)
        assert app._focused_character_sid() == "amy"

    def test_focused_sid_none_when_registry_empty(self):
        app = NeonRPApp(mode="play")
        assert app._focused_character_sid() is None

    def test_cancel_action_invokes_committed_interrupt_with_focused_sid(self):
        app = NeonRPApp(mode="play")

        async def _fake_interrupt(sid):  # the committed coroutine primitive
            return True

        wa = MagicMock()
        wa._characters = {"elena": _runtime("elena", task=_running_task())}
        wa.interrupt = MagicMock(side_effect=_fake_interrupt)
        app.session = SimpleNamespace(_world_agent=wa)
        app._refresh_character_lane = MagicMock()  # no widget tree in unit test

        # Drive the loop ourselves so the scheduled coroutine actually runs.
        loop = asyncio.new_event_loop()
        try:
            app.call_later = lambda fn, *a: fn(*a)  # run inline
            asyncio.set_event_loop(loop)
            app.action_cancel_character()
            pending = asyncio.all_tasks(loop)
            loop.run_until_complete(asyncio.gather(*pending))
        finally:
            asyncio.set_event_loop(None)
            loop.close()

        wa.interrupt.assert_called_once_with("elena")

    def test_cancel_action_noop_without_world_agent(self):
        app = NeonRPApp(mode="play")
        app.session = None
        # Must not raise even though there is nothing to cancel.
        app.action_cancel_character()
