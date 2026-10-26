"""Bare ``neonrp`` (the TUI launcher) lists the player's own templates — ``~/.worldlines/templates`` — the way the web
launcher ``worldlines`` does: a template an author (or their coding agent) just made there opens from the launcher."""
from __future__ import annotations

import json

from click.testing import CliRunner

import neonrp.cli as cli


def test_bare_neonrp_sees_the_template_store(tmp_path, monkeypatch):
    home = tmp_path / "home"
    tpl = home / ".worldlines" / "templates" / "mine.template"
    tpl.mkdir(parents=True)
    (tpl / "template.json").write_text(json.dumps({"schema": "worldlines.template/1", "id": "mine", "card": {"title": "Mine"},
                                                   "world": {"builtin": "white-blank"}}), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    for k in ("NEONRP_TEMPLATE_PATH", "NEONRP_TEMPLATE_WRITE_DIR", "NEONRP_OFFICIAL_DIR"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "_setup_logging", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "_launch_time_update_check", lambda: None)
    seen: dict = {}

    def launcher() -> None:
        from neonrp import template as TP

        seen["ids"] = set(TP.discover())

    monkeypatch.setattr(cli, "worldlines_tui", launcher)
    r = CliRunner().invoke(cli.cli, [])
    assert r.exit_code == 0, r.output
    assert "mine" in seen["ids"]
