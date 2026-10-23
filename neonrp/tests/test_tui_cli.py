"""Tests for TUI CLI entry behavior."""

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from neonrp.cli import cli


def test_tui_launches_without_init(tmp_path: Path):
    """`neonrp tui` should launch TUI even when project is not initialized."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        expected_root = Path.cwd()
        with patch("neonrp.tui.app.run_tui") as run_tui:
            result = runner.invoke(cli, ["tui"])

        assert result.exit_code == 0, result.output
        run_tui.assert_called_once_with(
            root=expected_root, branch=None, provider=None, continue_session=False, startup_commands=[], verbose=False, mode="build"
        )


def test_cli_no_subcommand_opens_the_world_picker(tmp_path: Path):
    """裸 `neonrp` 打开的是**世界选择器 launcher**,不是当前目录的引擎 TUI
    (要在某个 project 目录直开引擎面用 `neonrp tui`)。

    这条以前 patch 的是 `neonrp.tui.app.run_tui`,而裸命令改成走
    `worldlines_tui()` 之后那个 patch 就打空了 —— 于是测试**真的把 launcher
    启动起来**,进事件循环等键盘,把整个测试套挂死(`--timeout` 用 signal
    方式也打不断)。所以这条必须 patch CLI 真正调用的那个符号。
    """
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        with patch("neonrp.cli.worldlines_tui") as launcher:
            result = runner.invoke(cli, [])

        assert result.exit_code == 0, result.output
        launcher.assert_called_once()


def test_bare_cli_never_starts_a_real_ui(tmp_path: Path):
    """守卫:任何「裸命令」测试都不许真的起 UI。

    起来了就是把 CI 挂死 —— 这次的症状是整套测试跑到 19% 停住,而
    pytest-timeout 杀不掉它。断言 patch 生效比断言参数更要紧。
    """
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        with patch("neonrp.cli.worldlines_tui") as launcher:
            runner.invoke(cli, [])
        assert launcher.called, "裸命令没有走被替身拦住的入口 —— 它会起真 UI"


def test_tui_continue_flag_passes_continue_mode(tmp_path: Path):
    """`--continue` should request continuing previous session."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        expected_root = Path.cwd()
        with patch("neonrp.tui.app.run_tui") as run_tui:
            result = runner.invoke(cli, ["tui", "--continue"])

        assert result.exit_code == 0, result.output
        run_tui.assert_called_once_with(
            root=expected_root, branch=None, provider=None, continue_session=True, startup_commands=[], verbose=False, mode="build"
        )


def test_tui_verbose_flag_passes_debug_mode(tmp_path: Path):
    """`--verbose` should enable verbose debug mode in TUI."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        expected_root = Path.cwd()
        with patch("neonrp.tui.app.run_tui") as run_tui:
            result = runner.invoke(cli, ["tui", "--verbose"])

        assert result.exit_code == 0, result.output
        run_tui.assert_called_once_with(
            root=expected_root, branch=None, provider=None, continue_session=False, startup_commands=[], verbose=True, mode="build"
        )


def test_tui_new_and_continue_conflict(tmp_path: Path):
    """`--new` and `--continue` cannot be used together."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["tui", "--new", "--continue"])

    assert result.exit_code == 1
    assert "cannot be used together" in result.output


def test_tui_legacy_flag_is_not_supported(tmp_path: Path):
    """Legacy flag should be removed."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["tui", "--legacy"])

    assert result.exit_code == 2
    assert "No such option: --legacy" in result.output


def test_tui_import_card_passes_startup_command(tmp_path: Path):
    """`--import-card` should queue a startup /import command inside TUI."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        expected_root = Path.cwd()
        Path("card.png").write_bytes(b"png")
        with patch("neonrp.tui.app.run_tui") as run_tui:
            result = runner.invoke(cli, ["tui", "--import-card", "card.png", "--import-id", "hero"])

        assert result.exit_code == 0, result.output
        run_tui.assert_called_once_with(
            root=expected_root,
            branch=None,
            provider=None,
            continue_session=False,
            startup_commands=["/import sillytavern-card card.png --id hero"],
            verbose=False,
            mode="build",
        )


def test_tui_new_flag_starts_fresh_session(tmp_path: Path):
    """`--new` should explicitly keep startup in fresh-session mode."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        expected_root = Path.cwd()
        with patch("neonrp.tui.app.run_tui") as run_tui:
            result = runner.invoke(cli, ["tui", "--new"])

        assert result.exit_code == 0, result.output
        run_tui.assert_called_once_with(
            root=expected_root,
            branch=None,
            provider=None,
            continue_session=False,
            startup_commands=[],
            verbose=False,
            mode="build",
        )


def test_tui_import_id_requires_import_card(tmp_path: Path):
    """`--import-id` alone should be rejected clearly."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["tui", "--import-id", "hero"])

    assert result.exit_code == 1
    assert "--import-id requires --import-card" in result.output
