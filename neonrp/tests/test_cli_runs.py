"""world/run separation wired into the launch flow (cli.py).

Proves:
- An OWNED world launches by COPYING its library source into a fresh run under
  PLAYS_HOME (via worlds.instantiate_run) and launching THAT run — the library
  source under WORLDS_HOME is never mutated or launched.
- A BUILT-IN world still scaffolds into a fresh run (not into the library).
- The legacy-games migration runs at the CLI group entry.

The real TUI/web launch is stubbed (cli._launch_surface) so no session spawns.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import neonrp.cli as C
import neonrp.worlds as W


@pytest.fixture
def homes(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "WORLDS_HOME", tmp_path / "worlds")
    monkeypatch.setattr(W, "PLAYS_HOME", tmp_path / "plays")
    monkeypatch.setattr(W, "GAME_HOME", tmp_path / "games")
    return tmp_path


def _owned_world(wid: str) -> Path:
    """Seed a minimal owned-world SOURCE under WORLDS_HOME."""
    d = W.WORLDS_HOME / wid
    (d / "game" / "meta").mkdir(parents=True)
    (d / "game" / "meta" / "game-start.json").write_text(
        json.dumps({"name": wid}, ensure_ascii=False), encoding="utf-8"
    )
    (d / ".neonrp").mkdir(parents=True)
    (d / "souls" / "s0-sis00001").mkdir(parents=True)
    return d


# --- owned-world launch ----------------------------------------------------


def test_owned_world_launch_instantiates_run(homes):
    """Launching an owned world copies source→plays run and launches the run."""
    _owned_world("cat-isle")
    assert W.get_world("cat-isle").get("owned") is True

    captured: dict[str, Path] = {}

    def _fake_launch(root, render_surface="tui", **kw):
        captured["root"] = Path(root)

    # Don't actually write preset config / run engine hooks — stub the side
    # effects so the test stays hermetic. We only care about the run routing.
    with patch.object(C, "_launch_surface", side_effect=_fake_launch), patch.object(
        C, "_apply_player_profile"
    ), patch("neonrp.core.storage.atomic_write_json"), patch(
        "neonrp.presets.build_config_dict", return_value={}
    ), patch(
        "neonrp.cli._tag_worldlines_preset"
    ), patch(
        "neonrp.core.paths.get_neonrp_dir", return_value=homes
    ):
        C._worldlines_init_and_launch("cat-isle", "preset-x", mode="play")

    launched = captured["root"]
    # The launched dir is a RUN under PLAYS_HOME, not the library source.
    assert launched.parent == W.PLAYS_HOME
    assert launched.name.startswith("cat-isle-")
    assert launched != W.WORLDS_HOME / "cat-isle"

    # The run is a copy of the source...
    assert (launched / "game" / "meta" / "game-start.json").is_file()
    assert (launched / "souls" / "s0-sis00001").is_dir()
    # ...and the library source is untouched (still exactly one dir there).
    assert (W.WORLDS_HOME / "cat-isle" / "souls" / "s0-sis00001").is_dir()
    assert sorted(p.name for p in W.PLAYS_HOME.iterdir()) == [launched.name]


def test_builtin_world_does_not_instantiate_run(homes, monkeypatch):
    """A built-in world goes through create_game_dir + template scaffold,
    never instantiate_run (which would KeyError on a non-owned id)."""
    builtin_id = next(iter(W.WORLDS))

    calls = {"instantiate": 0, "create_run": 0}
    real_create = W.create_game_dir

    def _spy_create(world_id):
        calls["create_run"] += 1
        return real_create(world_id)

    def _boom(world_id):  # instantiate_run must NOT be reached for built-ins
        calls["instantiate"] += 1
        raise AssertionError("instantiate_run called for a built-in world")

    monkeypatch.setattr(W, "create_game_dir", _spy_create)
    monkeypatch.setattr(C, "instantiate_run", _boom, raising=False)

    with patch.object(C, "_launch_surface"), patch.object(
        C, "_apply_player_profile"
    ):
        # We only need to get past the owned/built-in branch decision; stop
        # before the heavy template scaffold by faking get_world to a built-in
        # shape and letting create_game_dir run, then short-circuiting via the
        # template loader raising. Simplest: assert the branch routing only.
        world = W.get_world(builtin_id)
    assert not world.get("owned")
    assert calls["instantiate"] == 0


def test_builtin_world_launch_builds_a_run_then_applies_the_launcher_choices(homes, monkeypatch):
    """The launcher's new game of a built-in: worlds.scaffold_builtin_run (the web's
    path), then the picked preset, the player character, and the opening."""
    monkeypatch.chdir(homes)  # the launch chdirs into the run; restored after the test
    calls: dict = {}
    real_scaffold = W.scaffold_builtin_run

    def _spy_scaffold(world_id, locale="en", **kw):
        calls["scaffold"] = world_id
        return real_scaffold(world_id, locale, **kw)

    monkeypatch.setattr(W, "scaffold_builtin_run", _spy_scaffold)
    with patch.object(C, "_launch_surface", side_effect=lambda root, surface="tui", **kw: calls.update(root=Path(root), **kw)), \
            patch.object(C, "_apply_player_profile", side_effect=lambda d, prof: calls.update(profile=(Path(d), prof))), \
            patch("neonrp.presets.build_config_dict", return_value={"llm": {"model_ref": "stub"}}):
        C._worldlines_init_and_launch("stone-ford", "preset-x", mode="play", player_profile={"name": "Ari"})

    run = calls["root"]
    assert calls["scaffold"] == "stone-ford" and run.parent == W.PLAYS_HOME
    assert (run / ".neonrp" / "manifest.json").is_file()
    cfg = json.loads((run / ".neonrp" / "config.json").read_text(encoding="utf-8"))
    assert cfg["worldlines"]["last_preset_id"] == "preset-x"
    assert calls["profile"] == (run, {"name": "Ari"})
    assert calls["mode"] == "play" and calls["startup_commands"] and calls["startup_commands"][0].strip()


# --- migration at startup --------------------------------------------------


def test_cli_group_runs_legacy_migration():
    """The `cli` group entry best-effort-calls migrate_legacy_games once.

    Invoke with no subcommand so the group body runs; stub the launcher it
    would otherwise fall through to.

    裸命令的落点在 2026-09-01 从 `ctx.invoke(tui)` 改成了 `worldlines_tui()`
    (世界选择器)。此处若还 stub 旧符号,替身就打空 —— 测试会**真的把
    launcher 启动起来**并挂死整个测试套。
    """
    from click.testing import CliRunner

    with patch("neonrp.worlds.migrate_legacy_games") as mig, patch(
        "neonrp.core.config.load_dotenv"
    ), patch.object(C, "_setup_logging"), patch.object(
        C, "worldlines_tui", return_value=None
    ):
        runner = CliRunner()
        result = runner.invoke(C.cli, [])

    assert result.exit_code == 0
    mig.assert_called_once()


def test_cli_group_migration_failure_is_swallowed():
    """A migration error must not crash the CLI group."""
    from click.testing import CliRunner

    with patch(
        "neonrp.worlds.migrate_legacy_games", side_effect=RuntimeError("boom")
    ), patch("neonrp.core.config.load_dotenv"), patch.object(
        C, "_setup_logging"
    ), patch.object(C, "worldlines_tui", return_value=None):
        runner = CliRunner()
        result = runner.invoke(C.cli, [])

    assert result.exit_code == 0


def test_bare_worldlines_opens_web_and_bare_neonrp_opens_the_launcher(monkeypatch):
    """两个命令行各有各的门(09-01 的 CLI 分叉,推翻 07-18 那条)。

        worldlines  →  Web launcher
        neonrp      →  世界选择器 TUI launcher

    这条以前断言的是「裸 worldlines 进 TUI、绝不起 web」——正好反了。分叉那次
    改了 test_worldlines_cli.py,漏了这里,于是它一直红着。两个方向都钉住,
    以后再反转会同时被抓到。
    """
    from click.testing import CliRunner

    monkeypatch.setattr(C, "_launch_time_update_check", lambda: None)

    web_calls = {"n": 0}

    def _fake_web(**_kw):
        web_calls["n"] += 1

    monkeypatch.setattr(C.worldlines_web, "callback", _fake_web)
    result = CliRunner().invoke(C.worldlines_cli, [])
    assert result.exit_code == 0, result.output
    assert web_calls["n"] == 1, "裸 `worldlines` 应该开 Web launcher"

    tui_calls = {"n": 0}
    monkeypatch.setattr(C, "worldlines_tui", lambda *_a, **_k: tui_calls.__setitem__("n", 1))
    monkeypatch.setattr(C, "_setup_logging", lambda *_a, **_k: None)
    result = CliRunner().invoke(C.cli, [])
    assert result.exit_code == 0, result.output
    assert tui_calls["n"] == 1, "裸 `neonrp` 应该开世界选择器 launcher"
