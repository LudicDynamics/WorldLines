"""One-click into Obsidian ("Obsidian 的这个连接,我其实还没有跑通").

The two facts that shape `core/obsidian.py` — the URI only opens registered
vaults, and the registry is read only at launch — turn into three behaviours
under test: we register without disturbing the user's other vaults, we
restart a running Obsidian only when we actually changed its registry, and
callers that must not restart get told instead.
"""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

import pytest

from neonrp.core import obsidian as O


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    v.mkdir()
    (v / "世界.canvas").write_text("{}")
    return v


@pytest.fixture
def registry(tmp_path: Path, monkeypatch) -> Path:
    reg = tmp_path / "obsidian.json"
    monkeypatch.setattr(O, "registry_path", lambda: reg)
    return reg


# --- registry ----------------------------------------------------------------


def test_registry_path_per_platform(monkeypatch, tmp_path):
    monkeypatch.setattr(O.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(O.sys, "platform", "darwin")
    assert O.registry_path() == tmp_path / "Library" / "Application Support" / "obsidian" / "obsidian.json"

    monkeypatch.setattr(O.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert O.registry_path() == tmp_path / "Roaming" / "obsidian" / "obsidian.json"

    monkeypatch.setattr(O.sys, "platform", "linux")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert O.registry_path() == tmp_path / ".config" / "obsidian" / "obsidian.json"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert O.registry_path() == tmp_path / "xdg" / "obsidian" / "obsidian.json"


def test_register_keeps_other_vaults_and_is_idempotent(vault, registry):
    registry.write_text(json.dumps({"vaults": {"abc123": {"path": "/Users/x/notes", "ts": 1, "open": True}}}))

    assert O.register_vault(vault, registry) is True
    data = json.loads(registry.read_text())
    assert data["vaults"]["abc123"] == {"path": "/Users/x/notes", "ts": 1, "open": True}
    ours = data["vaults"][O.vault_id(vault)]
    assert ours["path"] == str(vault.resolve())
    assert O.is_registered(vault, registry)

    # Second call: nothing new, file untouched.
    before = registry.read_bytes()
    assert O.register_vault(vault, registry) is False
    assert registry.read_bytes() == before


def test_register_survives_missing_or_broken_registry(vault, registry):
    assert not registry.exists()
    assert O.register_vault(vault, registry) is True
    assert O.is_registered(vault, registry)

    registry.write_text("{not json")
    other = vault.parent / "other"
    other.mkdir()
    assert O.register_vault(other, registry) is True
    assert O.is_registered(other, registry)


def test_vault_id_is_16_hex_and_path_stable(vault):
    vid = O.vault_id(vault)
    assert len(vid) == 16 and int(vid, 16) >= 0
    assert vid == O.vault_id(vault / ".." / "vault")


# --- seeded config -----------------------------------------------------------


def test_seed_config_writes_once_and_never_overwrites(vault):
    assert sorted(O.seed_config(vault)) == ["app.json", "graph.json"]
    graph = json.loads((vault / ".obsidian" / "graph.json").read_text())
    assert any(g["query"] == "path:角色" for g in graph["colorGroups"])
    assert json.loads((vault / ".obsidian" / "app.json").read_text())["defaultViewMode"] == "preview"

    (vault / ".obsidian" / "app.json").write_text('{"mine": true}')
    assert O.seed_config(vault) == []
    assert json.loads((vault / ".obsidian" / "app.json").read_text()) == {"mine": True}


# --- open URI ----------------------------------------------------------------


def test_open_uri_targets_vault_or_file(vault):
    uri = O.open_uri(vault)
    assert uri.startswith("obsidian://open?path=")
    assert urllib.parse.unquote(uri.split("=", 1)[1]) == str(vault.resolve())
    uri = O.open_uri(vault, "世界.canvas")
    assert urllib.parse.unquote(uri.split("=", 1)[1]) == str(vault.resolve() / "世界.canvas")
    assert "世界" not in uri  # percent-encoded, not raw


# --- the one step ------------------------------------------------------------


class _Fake:
    def __init__(self, *, running: bool, quit_ok: bool = True):
        self.running = running
        self.quit_ok = quit_ok
        self.quit_calls = 0
        self.launched: list[str] = []

    def is_running(self):
        return self.running

    def quit_app(self, timeout=6.0):
        self.quit_calls += 1
        if self.quit_ok:
            self.running = False
        return self.quit_ok

    def launch(self, uri):
        self.launched.append(uri)


def _wire(monkeypatch, fake: _Fake, installed: bool = True):
    monkeypatch.setattr(O, "is_installed", lambda: installed)
    monkeypatch.setattr(O, "is_running", fake.is_running)
    monkeypatch.setattr(O, "quit_app", fake.quit_app)


def test_open_first_time_while_not_running_just_launches(vault, registry, monkeypatch):
    fake = _Fake(running=False)
    _wire(monkeypatch, fake)
    report = O.open_vault(vault, launcher=fake.launch)
    assert report.registered and report.launched and not report.restarted
    assert fake.quit_calls == 0
    assert "世界.canvas" in urllib.parse.unquote(fake.launched[0])
    assert O.is_registered(vault, registry)
    assert any("登记" in line for line in report.lines())


def test_open_first_time_while_running_restarts(vault, registry, monkeypatch):
    fake = _Fake(running=True)
    _wire(monkeypatch, fake)
    report = O.open_vault(vault, launcher=fake.launch)
    assert report.registered and report.restarted and report.launched
    assert fake.quit_calls == 1
    assert any("重启" in line for line in report.lines())


def test_open_already_registered_never_restarts(vault, registry, monkeypatch):
    O.register_vault(vault, registry)
    fake = _Fake(running=True)
    _wire(monkeypatch, fake)
    report = O.open_vault(vault, launcher=fake.launch)
    assert not report.registered and not report.restarted and report.launched
    assert fake.quit_calls == 0


def test_open_without_restart_permission_reports_instead(vault, registry, monkeypatch):
    """Agent tool calls must not yank the app: they get `needs_restart`."""
    fake = _Fake(running=True)
    _wire(monkeypatch, fake)
    report = O.open_vault(vault, restart=False, launcher=fake.launch)
    assert report.registered and report.needs_restart
    assert not report.launched and fake.quit_calls == 0 and fake.launched == []
    assert any("重启" in line for line in report.lines())


def test_open_when_quit_fails_tells_user(vault, registry, monkeypatch):
    fake = _Fake(running=True, quit_ok=False)
    _wire(monkeypatch, fake)
    report = O.open_vault(vault, launcher=fake.launch)
    assert report.needs_restart and not report.launched
    assert any("手动重启" in n for n in report.notes)


def test_open_when_not_installed_still_registers(vault, registry, monkeypatch):
    fake = _Fake(running=False)
    _wire(monkeypatch, fake, installed=False)
    report = O.open_vault(vault, launcher=fake.launch)
    assert not report.installed and report.registered and not report.launched
    assert fake.launched == []
    assert "没找到 Obsidian" in report.lines()[0]


def test_open_lands_on_vault_root_when_target_missing(vault, registry, monkeypatch):
    fake = _Fake(running=False)
    _wire(monkeypatch, fake)
    O.open_vault(vault, land_on="不存在.md", launcher=fake.launch)
    assert urllib.parse.unquote(fake.launched[0]).endswith(str(vault.resolve()))


def test_open_launch_failure_is_a_note_not_a_crash(vault, registry, monkeypatch):
    fake = _Fake(running=False)
    _wire(monkeypatch, fake)

    def boom(uri):
        raise RuntimeError("no handler")

    report = O.open_vault(vault, launcher=boom)
    assert not report.launched
    assert any("obsidian://open" in n for n in report.notes)


def test_open_unwritable_registry_is_a_note(vault, registry, monkeypatch):
    fake = _Fake(running=False)
    _wire(monkeypatch, fake)

    def refuse(*a, **k):
        raise OSError("read-only")

    monkeypatch.setattr(O, "register_vault", refuse)
    report = O.open_vault(vault, launcher=fake.launch)
    assert not report.launched and any("手动" in n for n in report.notes)
