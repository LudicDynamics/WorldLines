"""TUI step 3 (10-08): /status · /lang · /dev and /undo list|<turn> — the two-beat play's commands (≤ 25 live)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from test_engine_v3 import _install

from neonrp.tui.app import ConversationView, NeonRPApp


def _texts(view, cls: str) -> list[str]:
    return [str(getattr(w, "content", "")) for w in view.query(f".{cls}")]


def test_play_commands(tmp_path: Path):
    root = _install(tmp_path)
    app = NeonRPApp(root=root, provider="stub", mode="play")

    async def scenario() -> None:
        async with app.run_test(size=(150, 50)) as pilot:
            view = app.query_one("#conversation-view", ConversationView)
            run = app._handle_slash_command
            run("/status plan")  # 10-23: a screen of tabs — the board sits on its usage tab
            await pilot.pause(0.2)
            tabs = str(app.screen.query_one("#status-tab-body").content)
            assert "计划板上还没有东西" in tabs or "No plan" in tabs
            app._apply_beat_event({"kind": "dice", "turn": 1, "request": "dice 1d20+2 vs 12", "rolls": [14], "total": 16, "vs": 12,
                                   "passed": True, "reason": "撬锁"})
            run("/status dice 5")
            run("/status agents")
            await pilot.pause(0.1)
            tabs = str(app.screen.query_one("#status-tab-body").content)
            run("/status contract")
            run("/status settlement")
            run("/lang ja")
            run("/dev graph")
            run("/dev beats on")
            run("/dev template")
            run("/dev nope")
            run("/undo list")
            await pilot.pause(0.3)
            out = "\n".join(_texts(view, "pc-out") + _texts(view, "pc-status") + _texts(view, "pc-template"))
            assert len(_texts(view, "semantic-dice-line")) >= 2  # the event's die + /status dice
            assert "艾琳娜" in tabs and "pct-house" in out
            assert len(view.query(".pc-graph")) == 1
            meta = root / "game" / "meta"
            assert json.loads((meta / "run_state.json").read_text(encoding="utf-8"))["output_lang"] == "ja"
            assert json.loads((meta / "engine.json").read_text(encoding="utf-8"))["turn"]["display"]["beats"] == "on"
            assert "/dev graph" in out  # usage for an unknown /dev item

    asyncio.run(scenario())


def test_undo_with_a_turn_forks_a_new_line(tmp_path: Path, monkeypatch):
    from neonrp.core import rollback as R

    root = _install(tmp_path)
    app = NeonRPApp(root=root, provider="stub", mode="play")
    calls: list[tuple] = []
    monkeypatch.setattr(R, "commit_for_turn", lambda r, t, b=None: "c-3" if t == 3 else None)
    monkeypatch.setattr(R, "rollback", lambda r, cid, src: calls.append((cid, src)) or {"ok": True, "branch": "rollback-x", "turn_seq": 3})

    async def scenario() -> None:
        async with app.run_test() as pilot:
            app._handle_slash_command("/undo 3")
            await pilot.pause(0.2)
            assert calls and calls[0][0] == "c-3" and app.branch == "rollback-x" and app.session is not None
            app._handle_slash_command("/undo 9")
            await pilot.pause(0.1)
            assert len(calls) == 1

    asyncio.run(scenario())


def test_planning_takes_lines_to_whoever_is_here(tmp_path: Path, monkeypatch):
    from neonrp.core.light_chat import resolve_room_souls

    root = _install(tmp_path)
    here = {iid for iid, _d, _n in resolve_room_souls(root)}
    assert "si-elena0001" in here and "si-rowan0001" not in here
    monkeypatch.setenv("NEONRP_PLAN_LOOP", "1")
    take = NeonRPApp._planning_takes
    assert take(root, {"lane": "dialogue", "target": "si-elena0001", "text": "你来按住门"})
    assert take(root, {"lane": "room", "target": None, "text": "大家听我说"})
    assert not take(root, {"lane": "dialogue", "target": "si-rowan0001", "text": "你在哪"})  # elsewhere: the direct chat
    monkeypatch.delenv("NEONRP_PLAN_LOOP")
    assert not take(root, {"lane": "dialogue", "target": "si-elena0001", "text": "你来按住门"})  # no planning beat: as before


def test_dev_and_status_carry_the_kept_retired_commands(tmp_path: Path):
    """Validate / mcp / bridge / debug (= verbose) under /dev, stats as /status usage."""
    from unittest.mock import MagicMock

    app = NeonRPApp(root=tmp_path)
    app.query_one = MagicMock(return_value=MagicMock())
    for h in ("_forward_cli_command", "_cmd_mcp", "_cmd_bridge", "_cmd_debug", "_cmd_verbose", "_cmd_stats"):
        setattr(app, h, MagicMock())
    run = app._handle_slash_command
    run("/dev validate")
    assert app._forward_cli_command.call_args[0][0].command == "validate"
    run("/dev mcp status")
    app._cmd_mcp.assert_called_once_with(["status"])
    run("/dev bridge")
    app._cmd_bridge.assert_called_once_with([])
    run("/dev debug")
    app._cmd_debug.assert_called_once_with([])
    run("/dev debug off")
    app._cmd_verbose.assert_called_once_with(["off"])
    run("/status usage")
    app._cmd_stats.assert_called_once()
