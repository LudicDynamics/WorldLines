"""「neonrp 只更新 neonrp,worldlines 更新依赖(neonrp+worldlines);
清单里两个分开的版本号,兼容老客户端的 latest.stable 按 worldlines 填」。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_release_manifest as M  # noqa: E402

from neonrp.core import updater  # noqa: E402


# ── manifest builder (runs in release.yml) ────────────────────────────


def test_first_v2_write_from_a_v1_manifest_seeds_the_shim_from_pypi():
    """今天线上的 v1 是引擎发的(latest=0.4.1),不能把它当成 worldlines 的版本;
    worldlines 的版本以 PyPI 为准(seed),v1 的 releases 只并进 legacy 历史。"""
    v1 = {"product": "neonrp", "latest": {"stable": "0.4.1"}, "releases": {"0.4.1": {"channel": "stable"}}}
    out = M.build(v1, package="neonrp", version="0.4.1", published_at="t", seed={"worldlines": "0.4.0"})
    assert out["schema"] == 2
    assert out["packages"]["neonrp"]["latest"] == {"stable": "0.4.1"}
    assert out["packages"]["worldlines"]["latest"] == {"stable": "0.4.0"}, "shim 版本来自 PyPI"
    assert out["latest"] == {"stable": "0.4.0"}, "老客户端看到的是 worldlines 的版本"
    assert set(out["releases"]) == {"0.4.1"}


def test_each_repo_only_touches_its_own_entry():
    served = M.build({}, package="neonrp", version="0.4.1", published_at="t", seed={"worldlines": "0.4.0"})
    after_shell = M.build(served, package="worldlines", version="0.4.1", published_at="t2")
    assert after_shell["packages"]["neonrp"]["latest"] == {"stable": "0.4.1"}
    assert after_shell["packages"]["worldlines"]["latest"] == {"stable": "0.4.1"}
    assert after_shell["latest"] == {"stable": "0.4.1"}
    assert "0.4.1" in after_shell["packages"]["neonrp"]["releases"]
    # the engine releases again: shell entry untouched
    again = M.build(after_shell, package="neonrp", version="0.4.2", published_at="t3")
    assert again["packages"]["worldlines"]["latest"] == {"stable": "0.4.1"}
    assert again["latest"] == {"stable": "0.4.1"}, "legacy 跟 worldlines,不跟 0.4.2"
    assert again["packages"]["neonrp"]["latest"] == {"stable": "0.4.2"}


def test_unknown_other_package_falls_back_to_this_one():
    out = M.build({}, package="neonrp", version="0.4.1", published_at="t")
    assert out["latest"] == {"stable": "0.4.1"}, "完全不知道 worldlines 时才用自己的"


def test_cli_writes_a_file(tmp_path):
    existing = tmp_path / "e.json"
    existing.write_text(json.dumps({"latest": {"stable": "0.4.0"}, "releases": {}}), encoding="utf-8")
    out = tmp_path / "releases.json"
    assert M.main(["--package", "neonrp", "--version", "v0.4.1", "--existing", str(existing), "--out", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["packages"]["neonrp"]["latest"]["stable"] == "0.4.1"
    assert data["latest"]["stable"] == "0.4.1", "没 seed、不认识 worldlines 时才退回自己的版本"


# ── updater: which package, which version ─────────────────────────────

V2 = {
    "schema": 2,
    "latest": {"stable": "0.4.0"},
    "releases": {"0.4.0": {"notes_url": "legacy"}, "0.4.1": {"notes_url": "engine"}},
    "packages": {
        "neonrp": {"latest": {"stable": "0.4.1"}, "releases": {"0.4.1": {"notes_url": "engine"}}},
        "worldlines": {"latest": {"stable": "0.4.0"}, "releases": {"0.4.0": {"notes_url": "shell"}}},
    },
}


def test_latest_for_reads_the_package_entry_and_falls_back_to_legacy():
    assert updater.latest_for(V2, "neonrp", "stable") == ("0.4.1", {"notes_url": "engine"})
    assert updater.latest_for(V2, "worldlines", "stable") == ("0.4.0", {"notes_url": "shell"})
    v1 = {"latest": {"stable": "0.3.9"}, "releases": {"0.3.9": {"notes_url": "old"}}}
    assert updater.latest_for(v1, "worldlines", "stable") == ("0.3.9", {"notes_url": "old"})


def test_neonrp_entry_point_checks_the_engine(monkeypatch):
    monkeypatch.setattr(updater.sys, "argv", ["neonrp"])
    monkeypatch.setattr(updater, "is_distribution_installed", lambda name: name == "neonrp")
    monkeypatch.setattr(updater, "fetch_release_manifest", lambda ch: V2)
    monkeypatch.setattr(updater, "get_current_version", lambda package="neonrp": {"neonrp": "0.4.0", "worldlines": "0.4.0"}[package])
    r = updater.check_for_update("stable")
    assert r.package == "neonrp" and r.latest_version == "0.4.1" and r.update_available


def test_worldlines_entry_point_checks_the_shim_and_is_not_nagged(monkeypatch):
    """装 worldlines 0.4.0 的人:引擎有 0.4.1 也不提示 —— shim 没新版就不该升。"""
    monkeypatch.setattr(updater.sys, "argv", ["worldlines"])
    monkeypatch.setattr(updater, "is_distribution_installed", lambda name: True)
    monkeypatch.setattr(updater, "fetch_release_manifest", lambda ch: V2)
    monkeypatch.setattr(updater, "get_current_version", lambda package="neonrp": {"neonrp": "0.4.0", "worldlines": "0.4.0"}[package])
    r = updater.check_for_update("stable")
    assert r.package == "worldlines" and r.latest_version == "0.4.0" and not r.update_available


def test_worldlines_entry_without_the_shim_installed_falls_back_to_neonrp(monkeypatch):
    monkeypatch.setattr(updater.sys, "argv", ["worldlines"])
    monkeypatch.setattr(updater, "is_distribution_installed", lambda name: name == "neonrp")
    assert updater.upgrade_target() == "neonrp"


def test_cached_result_is_ignored_when_it_was_for_another_package(monkeypatch, tmp_path):
    import time

    monkeypatch.setattr(updater, "CACHE_PATH", tmp_path / "c.json")
    (tmp_path / "c.json").write_text(json.dumps({"ts": time.time(), "result": {"package": "worldlines", "latest_version": "9.9", "channel": "stable"}}), encoding="utf-8")
    monkeypatch.setattr(updater, "upgrade_target", lambda: "neonrp")
    monkeypatch.setattr(updater, "check_for_update", lambda channel=None, package=None: updater.UpdateCheckResult(
        current_version="0.4.1", latest_version="0.4.1", channel="stable", update_available=False,
        install_mode=updater.detect_install_mode(), package="neonrp"))
    r = updater.check_for_update_cached(channel="stable")
    assert r.package == "neonrp" and r.latest_version == "0.4.1", "别的包的缓存不能拿来用"


def test_bare_neonrp_runs_the_launch_time_update_check(monkeypatch):
    from click.testing import CliRunner

    import neonrp.cli as cli

    calls = []
    monkeypatch.setattr(cli, "_launch_time_update_check", lambda: calls.append(1))
    monkeypatch.setattr(cli, "worldlines_tui", lambda: None)
    monkeypatch.setattr("neonrp.worlds.migrate_legacy_games", lambda: None)
    CliRunner().invoke(cli.cli, [])
    assert calls == [1]
