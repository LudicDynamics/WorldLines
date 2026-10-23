"""Tests for the public `worldlines` launcher entry."""

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from neonrp.cli import _worldlines_continue_game_with_preset, cli, worldlines_cli
from neonrp.tui.app import WorldLinesLaunchSelection


def test_worldlines_cli_new_game_uses_launcher_selection(tmp_path: Path):
    selection = WorldLinesLaunchSelection(
        mode="new",
        world_id="stone-ford",
        preset_id="stub-test",
        runtime_mode="play",
        player_profile={"name": "Ari"},
    )

    runner = CliRunner()
    with patch("neonrp.tui.app.run_worldlines_launcher", return_value=selection), patch("neonrp.presets.ensure_preset_key", return_value=True), patch(
        "neonrp.cli._worldlines_init_and_launch"
    ) as init_and_launch:
        result = runner.invoke(cli, [])

    assert result.exit_code == 0, result.output
    init_and_launch.assert_called_once_with(
        "stone-ford",
        "stub-test",
        mode="play",
        player_profile={"name": "Ari"},
        bring_in_souls=(),
        engine_mode="orchestrator",
        npc_placements=None,
        npc_locations=None,
        render_surface="tui",
    )


def test_worldlines_cli_continue_game_uses_launcher_selection(tmp_path: Path):
    game_path = tmp_path / "save-1"
    selection = WorldLinesLaunchSelection(
        mode="continue",
        preset_id="stub-test",
        runtime_mode="play",
        game_path=game_path,
    )

    runner = CliRunner()
    with patch("neonrp.tui.app.run_worldlines_launcher", return_value=selection), patch("neonrp.presets.ensure_preset_key", return_value=True), patch(
        "neonrp.cli._worldlines_continue_game_with_preset"
    ) as continue_game:
        result = runner.invoke(cli, [])

    assert result.exit_code == 0, result.output
    # runtime_mode / startup_commands ride along so the dashboard's 创作
    # flows can land a continue-launch in build mode with the agent's brief.
    continue_game.assert_called_once_with(game_path, "stub-test", "tui", runtime_mode="play", startup_commands=[])


def test_worldlines_cli_cancelled_launcher_exits_cleanly():
    runner = CliRunner()
    with patch("neonrp.tui.app.run_worldlines_launcher", return_value=None), patch(
        "neonrp.cli._worldlines_init_and_launch"
    ) as init_and_launch:
        result = runner.invoke(cli, [])

    assert result.exit_code == 0, result.output
    init_and_launch.assert_not_called()


def test_worldlines_cli_character_import_launches_soul_talk():
    # An imported character card routes into soul-talk with a pending-import
    # player. Regression: _after_character_import used to forget world_id, so
    # the selection carried world_id=None and the launch silently no-op'd.
    selection = WorldLinesLaunchSelection(
        mode="new",
        world_id="soul-talk",
        preset_id="stub-test",
        runtime_mode="play",
        player_profile={
            "__pending_import__": True,
            "__skill__": "character-card-authoring",
            "source_path": "/tmp/card.png",
        },
    )
    runner = CliRunner()
    with patch("neonrp.tui.app.run_worldlines_launcher", return_value=selection), patch("neonrp.presets.ensure_preset_key", return_value=True), patch(
        "neonrp.cli._worldlines_init_and_launch"
    ) as init_and_launch:
        result = runner.invoke(cli, [])

    assert result.exit_code == 0, result.output
    init_and_launch.assert_called_once()
    args, kwargs = init_and_launch.call_args
    assert args[0] == "soul-talk"
    assert kwargs["player_profile"]["__pending_import__"] is True


def test_worldlines_cli_no_world_surfaces_error_not_blank():
    # A "new" selection carrying no world (the character-import bug) must print
    # a diagnostic instead of dropping the user to a blank shell.
    selection = WorldLinesLaunchSelection(
        mode="new",
        world_id=None,
        preset_id="stub-test",
        runtime_mode="play",
        player_profile={"name": "X"},
    )
    runner = CliRunner()
    with patch("neonrp.tui.app.run_worldlines_launcher", return_value=selection), patch("neonrp.presets.ensure_preset_key", return_value=True), patch(
        "neonrp.cli._worldlines_init_and_launch"
    ) as init_and_launch:
        result = runner.invoke(cli, [])

    assert result.exit_code == 0, result.output
    init_and_launch.assert_not_called()
    assert "Nothing to launch" in result.output


def test_worldlines_cli_aborts_when_preset_key_setup_fails(tmp_path: Path):
    selection = WorldLinesLaunchSelection(
        mode="new",
        world_id="stone-ford",
        preset_id="stub-test",
        runtime_mode="play",
    )

    runner = CliRunner()
    with patch("neonrp.tui.app.run_worldlines_launcher", return_value=selection), patch("neonrp.presets.ensure_preset_key", return_value=False), patch(
        "neonrp.cli._worldlines_init_and_launch"
    ) as init_and_launch:
        result = runner.invoke(cli, [])

    assert result.exit_code == 0, result.output
    init_and_launch.assert_not_called()


def test_continue_game_runs_without_locale_handoff_state(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # the continue path chdirs into the save; restored after the test
    game_path = tmp_path / "save-1"
    neonrp_dir = game_path / ".neonrp"
    neonrp_dir.mkdir(parents=True)
    (neonrp_dir / "config.json").write_text(json.dumps({}, ensure_ascii=False), encoding="utf-8")

    with patch("neonrp.presets.build_config_dict", return_value={}), patch(
        "neonrp.core.storage.atomic_write_json"
    ), patch("neonrp.core.config.load_dotenv"), patch("neonrp.tui.app.run_tui") as run_tui:
        ok = _worldlines_continue_game_with_preset(game_path, "stub-test")

    assert ok is True
    run_tui.assert_called_once()
    assert "pending_locale_handoff" not in run_tui.call_args.kwargs


def test_worldlines_bare_defaults_to_web():
    """入口主权线:bare `worldlines` = **Web launcher**
    (:8787/local);TUI launcher 走 `neonrp`。bare worldlines 必须转发 web
    子命令,不走 TUI 启动器。(`--port/--no-browser` 传给 web。)"""
    runner = CliRunner()
    with patch("neonrp.commands.web.web") as web_cmd, patch(
        "neonrp.tui.app.run_worldlines_launcher", return_value=None
    ) as tui_launcher:
        result = runner.invoke(worldlines_cli, ["--no-browser", "--port", "9123"])

    assert result.exit_code == 0, result.output
    web_cmd.assert_called_once()
    tui_launcher.assert_not_called()


def test_neonrp_bare_routes_to_terminal_launcher():
    """bare `neonrp` = TUI 世界选择器 launcher(`worldlines tui` 已退役
    2026-09-01)。裸命令进 TUI 启动器,不起 web。"""
    runner = CliRunner()
    with patch(
        "neonrp.tui.app.run_worldlines_launcher", return_value=None
    ) as tui_launcher, patch("neonrp.commands.web.web") as web_cmd:
        result = runner.invoke(cli, [])

    assert result.exit_code == 0, result.output
    tui_launcher.assert_called_once()
    web_cmd.assert_not_called()
