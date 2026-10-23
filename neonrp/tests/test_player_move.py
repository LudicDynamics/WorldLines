"""P0 of docs/POSITION-GROUND-TRUTH.md — the player's procedural landing path.

Regression target: 2026-07-24 case A(玩家 0 跳)— narration moved the player
(gate_north → main_street) but game/meta/run_state.json never followed, so
next turn's scene_understanding judged presence off the stale node. The fix
gives the player the SAME adjudicated landing path souls use: the world-agent
emits ⟦CORRECTIONS⟧{"player": {"moved_to": ...}}, judge_move validates against
the town map (validity check, not hard movement logic), and the node lands in
run_state — pure code, no LLM in the landing.
"""

import json
import shutil
from pathlib import Path

from neonrp.core.conversation import _apply_player_move

_TPL = Path("src/neonrp/templates/stoneford-elena")


def _install(tmp_path: Path) -> Path:
    root = tmp_path / "w"
    shutil.copytree(_TPL, root)
    (root / ".neonrp").mkdir(exist_ok=True)
    shutil.copy(root / "playthrough.json", root / ".neonrp" / "playthrough.json")
    return root


def _player_loc(root: Path) -> dict:
    payload = json.loads(
        (root / "game" / "meta" / "run_state.json").read_text(encoding="utf-8")
    )
    return payload["location"]


def test_player_move_lands_adjacent_node(tmp_path: Path) -> None:
    # case A 回归:北门 → 主街必须真的落进 run_state(过去根本没有落地路径)。
    root = _install(tmp_path)
    assert _player_loc(root)["node"] == "gate_north"

    assert _apply_player_move(root, "main_street") is True

    loc = _player_loc(root)
    assert loc["node"] == "main_street"
    assert loc["node_id"] == "T001"
    # display 同步刷新(否则 UI 场景标签仍显示旧地点 — 又一层脱节)。
    assert loc["display"].endswith("主街")


def test_player_move_intra_town_is_free(tmp_path: Path) -> None:
    # 图退居「合法性校验」而非硬一跳逻辑:镇内节点存在
    # 即可落地,多跳由 world-agent 叙事裁量 — 北门直达河灯旅店(inn)允许。
    root = _install(tmp_path)
    assert _apply_player_move(root, "inn") is True
    assert _player_loc(root)["node"] == "inn"


def test_player_move_unknown_scoped_node_refused(tmp_path: Path) -> None:
    # 镇内幻觉节点(T001 里不存在)被 validation 拒绝:玩家原地不动,不脏状态。
    root = _install(tmp_path)
    assert _apply_player_move(root, "T001/atlantis_nowhere") is False
    assert _player_loc(root)["node"] == "gate_north"


def test_player_move_bare_unknown_is_wilderness_allowed(tmp_path: Path) -> None:
    # 现行政策(与 soul 完全一致,judge_move tier=unmapped):裸的未知节点
    # 视作荒野 —— 荒野是 world-agent 的叙事域,图管不到就放行。若未来要收紧
    # (荒野也要注册),改 judge_move 一处,soul/玩家同时生效。
    root = _install(tmp_path)
    assert _apply_player_move(root, "misty_ridge") is True
    assert _player_loc(root)["node"] == "misty_ridge"


def test_player_move_blank_is_noop(tmp_path: Path) -> None:
    root = _install(tmp_path)
    assert _apply_player_move(root, "") is False
    assert _apply_player_move(root, "   ") is False
    assert _player_loc(root)["node"] == "gate_north"


def test_player_move_same_node_is_noop(tmp_path: Path) -> None:
    # 落点与当前一致 ⇒ 无写入(幂等,不产生假 delta)。
    root = _install(tmp_path)
    assert _apply_player_move(root, "gate_north") is False
    assert _player_loc(root)["node"] == "gate_north"


def test_missing_corrections_reminder_roundtrip(tmp_path: Path) -> None:
    # 结算义务漏出检测的送达通道:排队的 [位置裁定] 线索必须一次性送达
    # (下回合 preflight 拿到、再取即空)。turn 8-10 玩家追出主街三回合位置
    # 未结算的实测根因 = 裁定块可选;现在漏出会排这条硬提醒。
    from neonrp.core.conversation import (
        _drain_location_judgments,
        _queue_location_judgment,
    )

    root = _install(tmp_path)
    _queue_location_judgment(root, "[system] 上回合你没有输出移动裁定块(测试)")
    lines = _drain_location_judgments(root)
    assert any("移动裁定块" in ln for ln in lines)
    assert _drain_location_judgments(root) == []  # deliver-once
