"""hash-first violation 复现(诊断用,xfail 基线不挡)。

线上一次(2026-08-10 16:32,pt-kagura-dream1):

    RuntimeError: hash-first violation: composed world_commit_id 'f51ad662c1e3'
    != landed '045baf4c7dd3' (working tree diverged from the collected delta
    — commit refused, ref unchanged)

``WorldAgent.land_turn`` 先 ``_assemble_collection``(从磁盘重算所有 hash)
再 ``compose_commit``,然后 ``land_commit`` **又从磁盘重算一遍**。两次重算
之间任何分歧都会让 id 对不上、回合被拒、玩家进度丢失。

这里把两条分歧路径各钉一个失败用例。两个用例都断言「应当落账」——
今天都落不了账,所以标 xfail;修好之后会 XPASS。全程零 LLM。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from neonrp.core import commit_subsystem as _commit_subsystem
from neonrp.core.character_agent import CharacterDelta
from neonrp.core.playthrough import (
    Playthrough,
    SoulRef,
    WorldAgentTeam,
    WorldRef,
    write_playthrough,
)
from neonrp.core.world_agent import WorldAgent

_SID = "elena"
_IID = "si-0000000000aa"
# 真实存档里 soul 的 version_hash 与 world 的 version_hash 天然不同
# (各自来自各自的 bundle)——这正是 fallback 分歧能被观测到的前提。
_SOUL_VERSION = "sha256:soul-bundle-v1"
_WORLD_VERSION = "sha256:world-bundle-v1"


def _seed_playthrough(tmp_path: Path, *, with_memo: bool = True) -> tuple[Path, Path]:
    """最小可 land 的多智能体存档:game/ + 一个 soul + playthrough.json。"""
    root = tmp_path / "kagura-wi-0000000000ff"
    (root / "game" / "meta").mkdir(parents=True)
    (root / "game" / "meta" / "run_state.json").write_text(
        json.dumps({"turn_count": 1}, ensure_ascii=False), encoding="utf-8"
    )
    soul_dir = root / "souls" / f"{_SID}-{_IID}"
    (soul_dir / "short-term-memo").mkdir(parents=True)
    (soul_dir / "soul.json").write_text(
        json.dumps({"name": "Elena"}, ensure_ascii=False), encoding="utf-8"
    )
    if with_memo:
        (soul_dir / "short-term-memo" / "recent_events.json").write_text(
            json.dumps({"events": []}, ensure_ascii=False), encoding="utf-8"
        )
    write_playthrough(
        root,
        Playthrough(
            schema_version=2,
            playthrough_id="pt-kagura-repro",
            world=WorldRef(
                wid="kagura",
                instance_id="wi-0000000000ff",
                version_hash=_WORLD_VERSION,
                head_commit="",
            ),
            world_agent_team=WorldAgentTeam(seeded_from="repro@test", agents=[]),
            souls=[
                SoulRef(
                    sid=_SID,
                    instance_id=_IID,
                    version_hash=_SOUL_VERSION,
                    head_commit="",
                    role="npc",
                )
            ],
            created_at="2026-08-10T16:32:00Z",
            active_souls=(_IID,),
        ),
    )
    return root, soul_dir


def test_soul_without_delta_still_lands(tmp_path: Path) -> None:
    """回归(原假说③,已修):manifest 里的 soul 本回合没产出 CharacterDelta
    也必须能落账。

    曾经的分歧:compose 侧对无 delta 的 soul 回落 ``world_version`` 当
    version_hash,而 land_commit 严格用 manifest 的 ``sref.version_hash``
    —— soul_commit_id 不同,world id 必然对不上,每回合必炸。现 compose
    同源取 manifest(world_agent.soul_versions);conversation.py 的
    off-stage memo 循环也不再因 memo 读写失败吞掉 delta。
    """
    root, _ = _seed_playthrough(tmp_path)
    world_agent = WorldAgent(root)

    commit_id = asyncio.run(
        world_agent.land_turn([], turn_seq=1, branch="main")
    )

    assert commit_id


@pytest.mark.xfail(
    strict=False,
    reason="compose 与 land 之间 soul 文件夹被写 —— 两次 compute_game_hash "
    "不同,soul_commit_id 变了,world id 跟着变",
)
def test_late_soul_folder_write_still_lands(tmp_path: Path) -> None:
    """竞态分歧:soul 文件夹在 compose→land 的窗口里被写。

    线上形态(v0.3.6 引擎 fan-out era):soul 跑超时被判 degraded 后,
    ``_ex.shutdown(wait=False, cancel_futures=True)`` 只是不再等它 ——
    线程还活着,LLM 一返回就继续往自己的 soul 文件夹写。回合此时已经
    走到 land_turn,那些写入正好落在窗口里。

    这里用 land_commit 的 monkeypatch 把「迟到的写」钉在窗口正中间,
    让本来概率性的竞态变成确定性复现;窗口宽度 = land_commit 里
    game/ 重算 hash + tar/gzip 打包的耗时(真实存档 0.1-0.5s)。
    """
    root, soul_dir = _seed_playthrough(tmp_path)
    world_agent = WorldAgent(root)
    real_land_commit = _commit_subsystem.land_commit
    memo = soul_dir / "short-term-memo" / "recent_events.json"

    def _land_commit_with_straggler(*args, **kwargs):
        # 超时那个 soul 的线程终于返回,把记忆写进自己的文件夹。
        memo.write_text(
            json.dumps({"events": [{"kind": "late-write"}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        return real_land_commit(*args, **kwargs)

    _commit_subsystem.land_commit = _land_commit_with_straggler
    try:
        delta = CharacterDelta(
            sid=_SID,
            instance_id=_IID,
            version_hash=_SOUL_VERSION,
            state="degraded",
            soul_folder_hash="sha256:collected-at-timeout",
        )
        commit_id = asyncio.run(
            world_agent.land_turn([delta], turn_seq=1, branch="main")
        )
    finally:
        _commit_subsystem.land_commit = real_land_commit

    assert commit_id


def test_clean_turn_lands(tmp_path: Path) -> None:
    """对照组:delta 齐、窗口内无写 —— 必须落账(守住上面两个用例的说服力)。"""
    root, _ = _seed_playthrough(tmp_path)
    world_agent = WorldAgent(root)
    delta = CharacterDelta(
        sid=_SID,
        instance_id=_IID,
        version_hash=_SOUL_VERSION,
        # 收集期的 state/hash 都是过期的,_assemble_collection 会重算 ——
        # 这正是设计意图,所以 degraded + 假 hash 也不该影响落账。
        state="degraded",
        soul_folder_hash="sha256:stale-on-purpose",
    )

    commit_id = asyncio.run(
        world_agent.land_turn([delta], turn_seq=1, branch="main")
    )

    assert commit_id
