"""10-24: neonrp did not update itself — a released install only *offered* the upgrade. ``updates.mode``: auto
(default: upgrade and relaunch, one line) · prompt (ask) · notify (banner only); editable installs stay notify-only."""
from __future__ import annotations

import click
import pytest

from neonrp import cli
from neonrp.core import updater


def _result(allow: bool = True) -> updater.UpdateCheckResult:
    return updater.UpdateCheckResult(current_version="1.0.2", latest_version="1.0.3", channel="stable", update_available=True,
                                     install_mode=updater.InstallMode(kind="released" if allow else "editable", detail="x",
                                                                      allow_auto_apply=allow),
                                     release_notes_url=None, package="neonrp")


@pytest.fixture
def seams(monkeypatch):
    applied: list[str] = []
    monkeypatch.setattr(updater, "check_for_update_cached", lambda *a, **k: _result())
    monkeypatch.setattr(updater, "apply_update_in_background", lambda *a, **k: (applied.append("apply"), (True, ""))[1])
    monkeypatch.setattr(updater, "relaunch_self", lambda *a, **k: applied.append("relaunch"))
    monkeypatch.setattr(click, "prompt", lambda *a, **k: (applied.append("asked"), "n")[1])
    return applied


def test_auto_mode_upgrades_without_asking_and_relaunches(seams, monkeypatch):
    monkeypatch.setattr(updater, "get_update_settings", lambda: {"enabled": True, "check_on_launch": True, "mode": "auto"})
    with pytest.raises(SystemExit):
        cli._launch_time_update_check()
    assert seams == ["apply", "relaunch"]


def test_prompt_mode_asks_first(seams, monkeypatch):
    monkeypatch.setattr(updater, "get_update_settings", lambda: {"enabled": True, "check_on_launch": True, "mode": "prompt"})
    cli._launch_time_update_check()
    assert seams == ["asked"]


def test_notify_mode_only_tells(seams, monkeypatch):
    monkeypatch.setattr(updater, "get_update_settings", lambda: {"enabled": True, "check_on_launch": True, "mode": "notify"})
    cli._launch_time_update_check()
    assert seams == []


def test_editable_install_never_auto_applies(seams, monkeypatch):
    monkeypatch.setattr(updater, "check_for_update_cached", lambda *a, **k: _result(allow=False))
    monkeypatch.setattr(updater, "get_update_settings", lambda: {"enabled": True, "check_on_launch": True, "mode": "auto"})
    cli._launch_time_update_check()
    assert seams == []


def test_mode_names():
    assert updater.launch_mode({"mode": "prompt-and-update"}) == "prompt"
    assert updater.launch_mode({}) == "auto" and updater.launch_mode({"mode": "weird"}) == "auto"
