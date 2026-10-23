"""Library delete: delete_owned_world (+ its runs) and delete_soul.

These are the backend half of the launcher 一览/delete feature. They are
best-effort, never-raise, and must refuse to touch packaged/built-in worlds.
We monkeypatch WORLDS_HOME / PLAYS_HOME / SOUL_HOME onto tmp_path so the real
~/.worldlines is never read or written.
"""

from __future__ import annotations

import pytest

from neonrp import worlds
from neonrp.core import souls


def _make_world(home, world_id: str) -> None:
    d = home / world_id
    (d / "game").mkdir(parents=True)
    (d / "game" / "world.json").write_text("{}", encoding="utf-8")


def _make_run(plays, world_id: str, ts: str) -> "object":
    run = plays / f"{world_id}-{ts}"
    run.mkdir(parents=True)
    (run / ".neonrp").mkdir()
    return run


@pytest.fixture
def world_dirs(tmp_path, monkeypatch):
    worlds_home = tmp_path / "worlds"
    plays_home = tmp_path / "plays"
    worlds_home.mkdir()
    plays_home.mkdir()
    monkeypatch.setattr(worlds, "WORLDS_HOME", worlds_home)
    monkeypatch.setattr(worlds, "PLAYS_HOME", plays_home)
    return worlds_home, plays_home


def test_delete_owned_world_removes_source_and_runs(world_dirs):
    worlds_home, plays_home = world_dirs
    _make_world(worlds_home, "my-world")
    run_a = _make_run(plays_home, "my-world", "20260101-101010")
    run_b = _make_run(plays_home, "my-world", "20260102-202020")
    # An unrelated world's run must survive.
    other = _make_run(plays_home, "other-world", "20260103-303030")

    assert worlds.delete_owned_world("my-world") is True

    assert not (worlds_home / "my-world").exists()
    assert not run_a.exists()
    assert not run_b.exists()
    assert other.exists()


def test_delete_owned_world_keeps_unrelated_prefix_run(world_dirs):
    # A run dir without a timestamp suffix (or a different world that merely
    # shares a name prefix) must NOT be swept.
    worlds_home, plays_home = world_dirs
    _make_world(worlds_home, "dark")
    # "dark-train-..." is a different world that prefix-matches "dark-"; its
    # suffix "train-..." is not timestamp-shaped, so it must be left alone.
    sibling = _make_run(plays_home, "dark", "train-20260101-101010")

    assert worlds.delete_owned_world("dark") is True
    assert sibling.exists()


def test_delete_owned_world_refuses_builtin(world_dirs):
    # Pick any real built-in manifest id; it must be refused even if a
    # same-named dir somehow exists under WORLDS_HOME.
    worlds_home, _ = world_dirs
    builtin_id = next(iter(worlds.WORLDS))
    _make_world(worlds_home, builtin_id)

    assert worlds.delete_owned_world(builtin_id) is False
    assert (worlds_home / builtin_id).exists()


def test_delete_owned_world_refuses_missing(world_dirs):
    assert worlds.delete_owned_world("does-not-exist") is False


@pytest.fixture
def soul_home(tmp_path, monkeypatch):
    home = tmp_path / "souls"
    home.mkdir()
    monkeypatch.setattr(souls, "SOUL_HOME", home)
    return home


def test_delete_soul_removes_dir(soul_home):
    d = soul_home / "elena-20260101-101010"
    (d / "persona").mkdir(parents=True)
    (d / "soul.json").write_text('{"sid": "elena", "name": "Elena"}', encoding="utf-8")

    assert souls.delete_soul("elena-20260101-101010") is True
    assert not d.exists()


def test_delete_soul_refuses_missing_and_unsafe(soul_home):
    assert souls.delete_soul("nope-20260101-101010") is False
    assert souls.delete_soul("") is False
    assert souls.delete_soul(".hidden") is False
    assert souls.delete_soul("../escape") is False
