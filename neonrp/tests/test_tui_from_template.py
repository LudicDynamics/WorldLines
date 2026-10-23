"""`neonrp tui --from <x.template>` builds a run of the template, as the web's new game does (10-21: it copied the
package as-is, no run at all, and the old world-agent wrote the town, the NPCs and the quests file by file)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from _paths import PRODUCT_TEMPLATES


def test_tui_from_a_template_package_plays_a_built_run(tmp_path):
    from neonrp.commands.tui import tui
    from neonrp.core.paths import get_manifest_path

    seen: dict = {}
    with patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"), patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"), \
            patch("neonrp.tui.app.run_tui", lambda **kw: seen.update(kw)):
        res = CliRunner().invoke(tui, ["--from", str(PRODUCT_TEMPLATES / "stoneford-elena.template")])
    assert res.exit_code == 0, res.output
    root = Path(seen["root"])
    assert root.is_relative_to(tmp_path / "plays") and seen["mode"] == "play"
    assert get_manifest_path(root).exists() and not (root / "template.json").exists(), "a run, not the package"
    assert (root / ".neonrp" / "playthrough.json").exists() or (root / "playthrough.json").exists()
    assert list((root / "game").rglob("*.json")), "the template's world is built in"
    assert len(seen["startup_commands"]) == 1 and seen["startup_commands"][0].strip(), "a fresh run opens with its opening"


def test_tui_from_a_plain_world_folder_is_refused(tmp_path):
    """No more as-is copies of a world folder: --from takes a template package only."""
    from neonrp.commands.tui import tui

    (tmp_path / "w" / "game").mkdir(parents=True)
    with patch("neonrp.tui.app.run_tui") as run_tui:
        res = CliRunner().invoke(tui, ["--from", str(tmp_path / "w")])
    assert res.exit_code == 1 and "template package" in res.output
    run_tui.assert_not_called()


def test_a_client_sends_no_opening_into_a_host_already_playing(tmp_path, monkeypatch):
    """10-21 TUI --connect: the client read its own folder, found no turn, and sent 「开始游戏」 into a run three turns in."""
    from neonrp.commands import tui as T

    class Host:
        def __init__(self, url, token): pass
        total_turns = 3
        def get_messages(self): return []
        def close(self): pass

    monkeypatch.setattr("neonrp.net.client.RemoteClient", Host)
    seen: dict = {}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NEONRP_CONNECT_URL", "")  # tui --connect sets these for the process: restored after this test
    monkeypatch.setenv("NEONRP_CONNECT_TOKEN", "")
    with patch("neonrp.tui.app.run_tui", lambda **kw: seen.update(kw)):
        res = CliRunner().invoke(T.tui, ["--connect", "http://127.0.0.1:1", "--token", "t"])
    assert res.exit_code == 0, res.output
    assert seen["startup_commands"] == [] and seen["mode"] == "play"
    Host.total_turns = 0
    assert T._host_played("http://127.0.0.1:1", "t") is False
