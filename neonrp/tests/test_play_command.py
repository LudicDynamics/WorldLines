"""Tests for the `neonrp play` command (one-shot + REPL plumbing, no LLM)."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from neonrp.commands.play import play
from neonrp.core.manifest import Manifest


def _init_project(root: Path) -> None:
    neon = root / ".neonrp"
    (neon / "sessions").mkdir(parents=True)
    (neon / "events").mkdir(parents=True)
    m = Manifest()
    m.branches["main"].head_event = -1
    (neon / "manifest.json").write_text(
        json.dumps(m.model_dump(), default=str), encoding="utf-8"
    )
    (root / "game").mkdir()


def test_uninitialized_project_fails_cleanly(tmp_path: Path) -> None:
    result = CliRunner().invoke(play, ["hi", "--project", str(tmp_path)])
    assert result.exit_code == 1
    # click <8.2 的 CliRunner 默认 stderr 混入 output,单独访问 .stderr 会
    # raise("stderr not separately captured")——按版本鲁棒地拼接。
    try:
        err = str(result.stderr or "")
    except ValueError:
        err = ""
    assert "Not initialized" in (result.output + err)


def test_json_without_query_is_an_error(tmp_path: Path) -> None:
    _init_project(tmp_path)
    result = CliRunner().invoke(play, ["--project", str(tmp_path), "--json"])
    assert result.exit_code == 1
    assert "requires a QUERY" in result.output


def test_repl_quits_cleanly_without_llm(tmp_path: Path) -> None:
    _init_project(tmp_path)
    result = CliRunner().invoke(
        play, ["--project", str(tmp_path)], input="/help\n/trace\n/debug\n/quit\n"
    )
    assert result.exit_code == 0
    assert "/trace" in result.output            # /help listed commands
    assert "(no trace yet)" in result.output     # /trace with no turns
    assert "no agent calls recorded" in result.output  # /debug empty buffer
