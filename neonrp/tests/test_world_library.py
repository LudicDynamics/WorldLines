"""world/run separation: WORLDS_HOME = library, PLAYS_HOME = runs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import neonrp.worlds as W


@pytest.fixture
def homes(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "WORLDS_HOME", tmp_path / "worlds")
    monkeypatch.setattr(W, "PLAYS_HOME", tmp_path / "plays")
    monkeypatch.setattr(W, "GAME_HOME", tmp_path / "games")
    return tmp_path


def _world(root: Path, wid: str, *, hub: bool = False, souls: int = 1) -> Path:
    d = root / wid
    (d / "game" / "meta").mkdir(parents=True)
    (d / "game" / "meta" / "game-start.json").write_text(
        json.dumps({"name": wid}, ensure_ascii=False), encoding="utf-8"
    )
    if hub:
        (d / ".worldhub.json").write_text(json.dumps({"slug": wid}), encoding="utf-8")
    for i in range(souls):
        (d / "souls" / f"s{i}-sis{i}0001").mkdir(parents=True)
    return d


def test_owned_world_in_library_and_count_grows(homes):
    base = len([w for w in W.list_worlds() if not w.get("owned")])
    _world(W.WORLDS_HOME, "cat-isle")
    worlds = W.list_worlds()
    owned = [w for w in worlds if w.get("owned")]
    assert [w["id"] for w in owned] == ["cat-isle"]
    assert owned[0]["origin"] == "created"
    assert len(worlds) == base + 1  # the 世界库 count grows


def test_downloaded_world_origin(homes):
    _world(W.WORLDS_HOME, "dark-train", hub=True)
    entry = next(w for w in W.list_owned_worlds() if w["id"] == "dark-train")
    assert entry["origin"] == "downloaded"


def test_get_world_resolves_owned(homes):
    _world(W.WORLDS_HOME, "cat-isle")
    info = W.get_world("cat-isle")
    assert info["owned"] is True and info["source_dir"] == W.WORLDS_HOME / "cat-isle"
    with pytest.raises(KeyError):
        W.get_world("does-not-exist")


def test_instantiate_run_copies_source_to_plays(homes):
    _world(W.WORLDS_HOME, "cat-isle", souls=2)
    run = W.instantiate_run("cat-isle")
    assert run.parent == W.PLAYS_HOME
    assert run.name.startswith("cat-isle-")
    # full source copied (souls + game) — the run is the mutable instance
    assert (run / "souls" / "s0-sis00001").is_dir()
    assert (run / "game" / "meta" / "game-start.json").is_file()
    # the library source is untouched
    assert (W.WORLDS_HOME / "cat-isle" / "souls" / "s0-sis00001").is_dir()


def test_instantiate_run_rejects_non_owned(homes):
    with pytest.raises(KeyError):
        W.instantiate_run("not-a-world")


def test_create_run_dir_lands_in_plays(homes):
    run = W.create_run_dir("stoneford-elena")
    assert run.parent == W.PLAYS_HOME and run.name.startswith("stoneford-elena-")
    # back-compat alias points at the same place
    assert W.create_game_dir("x").parent == W.PLAYS_HOME


def test_register_owned_world(homes):
    src = _world(homes / "scratch", "authored")
    lib = W.register_owned_world(src, "authored")
    assert lib == W.WORLDS_HOME / "authored"
    assert (lib / "souls" / "s0-sis00001").is_dir()
    # idempotent
    assert W.register_owned_world(src, "authored") == lib


def test_migration_classifies_worlds_vs_plays(homes):
    g = W.GAME_HOME
    # a created world with two runs, a hub download, a hosted-play save, and a
    # built-in run (stoneford-elena IS a packaged world id)
    _world(g, "cat-isle-20260623-010000", souls=3)
    _world(g, "cat-isle-20260623-020000", souls=3)
    _world(g, "dark-train", hub=True)
    _world(g, "stoneford-elena-20260622-190305", souls=2)
    sess = g / "restored-save"
    sess.mkdir(parents=True)
    (sess / ".session-meta.json").write_text("{}", encoding="utf-8")

    report = W.migrate_legacy_games()

    libs = sorted(p.name for p in W.WORLDS_HOME.iterdir())
    plays = sorted(p.name for p in W.PLAYS_HOME.iterdir())
    assert "cat-isle" in libs            # created world → library (first run)
    assert "dark-train" in libs          # hub download → library
    assert "stoneford-elena" not in libs  # built-in run → NOT a library world
    assert "restored-save" in plays      # hosted-play save → run
    assert "stoneford-elena-20260622-190305" in plays  # built-in run → run
    # the second run of the created world → a run, not a duplicate library world
    assert "cat-isle-20260623-020000" in plays
    assert report["worlds"] == 2 and report["plays"] >= 2


def test_migration_is_idempotent(homes):
    _world(W.GAME_HOME, "cat-isle-20260623-010000", souls=1)
    W.migrate_legacy_games()
    second = W.migrate_legacy_games()  # games/ now empty
    assert second == {"worlds": 0, "plays": 0, "skipped": 0}


def test_instantiate_run_migrates_root_playthrough(homes):
    """回归:下载/导出形状的世界把 playthrough.json 放在根,引擎只认
    .neonrp/playthrough.json —— 不迁移的话 multi-agent 新局被静默降级成
    GM 独奏(hosted 实测:无 soul_status + souls/** 权限报错)。"""
    src = _world(W.WORLDS_HOME, "dl-world")
    (src / "playthrough.json").write_text('{"schema_version": 2}', encoding="utf-8")
    run = W.instantiate_run("dl-world")
    dest = run / ".neonrp" / "playthrough.json"
    assert dest.is_file()
    assert dest.read_text(encoding="utf-8") == '{"schema_version": 2}'


def test_instantiate_run_keeps_existing_canonical_playthrough(homes):
    """已是正规形状(.neonrp/playthrough.json 在位)时,根上的副本不得覆盖它。"""
    src = _world(W.WORLDS_HOME, "canon-world")
    (src / ".neonrp").mkdir(parents=True, exist_ok=True)
    (src / ".neonrp" / "playthrough.json").write_text('{"v": "canonical"}', encoding="utf-8")
    (src / "playthrough.json").write_text('{"v": "stale-root"}', encoding="utf-8")
    run = W.instantiate_run("canon-world")
    assert (run / ".neonrp" / "playthrough.json").read_text(encoding="utf-8") == '{"v": "canonical"}'
