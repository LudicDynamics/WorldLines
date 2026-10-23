"""回归:新建/owned 世界绝不能占用内置世界 id。

2026-09-11 的 bug:`~/.worldlines/worlds/stoneford-elena` 这个 owned 世界
与内置同 id → 去重把内置那份从列表挤掉、并被 owned(白模板/无立绘)顶替,
表现为"内置 stoneford-elena 的角色立绘没了"。两条 create 路径都必须改名规避。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import neonrp.worlds as W


@pytest.fixture
def homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(W, "WORLDS_HOME", tmp_path / "worlds")
    monkeypatch.setattr(W, "PLAYS_HOME", tmp_path / "plays")
    return tmp_path


def test_new_world_slug_avoids_builtin_id() -> None:
    """web create 路径(UI 新建世界走的)。"""
    from neonrp.commands.web import _new_world_slug

    assert "stoneford-elena" in W.WORLDS  # 前提:它是内置
    slug = _new_world_slug("stoneford-elena")
    assert slug not in W.WORLDS, f"slug {slug} 撞了内置 id"
    assert slug != "stoneford-elena"


def test_create_blank_world_avoids_builtin_id(homes: Path) -> None:
    """CLI /init 路径(create_blank_world)。"""
    assert "stoneford-elena" in W.WORLDS
    dest = W.create_blank_world("stoneford-elena")
    assert dest.name not in W.WORLDS, f"owned 世界落到了内置 id {dest.name}"
    assert dest.name != "stoneford-elena"
    assert dest.parent == W.WORLDS_HOME
    assert dest.exists()
