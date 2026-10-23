"""Ontology 数据面(M30 V1)——世界实体数据的唯一权威工具层。

**非 LLM 模块**:world-agent(team leader)的读写都经这里的工具;
校验(place_nav 裁判)在工具内脏,判断永远归 leader(M30 §4)。

- get_roster:在场/离场名册(唯一数据,含所属关系与位置)
- get_location:任意实体(player / soul iid)的位置
- get_scene:地点数据 + 场景层状态(scene_state.json)
- move_entity:结算=工具调用——裁判校验后写入;拒绝即报错带回

数据源单一化:玩家位置 = game/meta/run_state.json;soul 位置 =
souls/<sid>-<iid>/run_state.json;地点 = 地图 + game/locations/。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any


logger = logging.getLogger("neonrp")


# ── 内部取数(复用既有单一事实源,不另存副本)────────────────────────


def _soul_dir(root: Path, sid: str, iid: str) -> Path:
    return root / "souls" / f"{sid}-{iid}"


def _place_view(root: Path, node: str | None) -> dict[str, Any]:
    """scoped 地址 → 人话视图 {node, town, name}。node 为空给显式未知。"""
    if not node:
        return {"node": None, "town": None, "name": "(未知)"}
    from neonrp.core.place_nav import split_location, town_node_view

    town, bare = split_location(node)
    view = town_node_view(root, bare or node, prefer_town=town) or {}
    return {
        "node": node,
        "town": town,
        "name": view.get("name") or bare or node,
    }


def _resolve_soul(root: Path, token: str):
    """名字/别名/iid → SoulRef(playthrough 名册为准)。None=查无此人。"""
    from neonrp.core.address import soul_aliases
    from neonrp.core.playthrough import read_playthrough

    pt = read_playthrough(root)
    if pt is None:
        return None, None
    token_l = token.strip().lower()
    for ref in pt.souls:
        if ref.instance_id == token or ref.sid == token:
            return pt, ref
    for iid, names in soul_aliases(root):
        if token_l in {n.lower() for n in names}:
            ref = next((s for s in pt.souls if s.instance_id == iid), None)
            if ref is not None:
                return pt, ref
    return pt, None


# ── 工具面 ──────────────────────────────────────────────────────────────


def get_roster(root: Path) -> dict[str, Any]:
    """在场/离场名册:玩家 + 全部 souls,各带唯一位置与同场标记。"""
    from neonrp.core.light_chat import _display_name, _player_node, _soul_node
    from neonrp.core.playthrough import read_playthrough

    player_node = _player_node(root)
    out: dict[str, Any] = {
        "player": {"location": _place_view(root, player_node)},
        "present": [],
        "away": [],
    }
    pt = read_playthrough(root)
    if pt is None:
        return out
    for ref in pt.souls:
        sdir = _soul_dir(root, ref.sid, ref.instance_id)
        node = _soul_node(root, sdir) if sdir.is_dir() else None
        # 无位置视作同场(镜像 scene_understanding 的保守缺省)。
        co_located = not (node is not None and player_node is not None and node != player_node)
        row = {
            "instance_id": ref.instance_id,
            "sid": ref.sid,
            "name": _display_name(sdir, ref.sid) if sdir.is_dir() else ref.sid,
            "location": _place_view(root, node),
        }
        out["present" if co_located else "away"].append(row)
    return out


def get_location(root: Path, entity: str) -> dict[str, Any]:
    """实体位置(唯一数据)。entity="player" 或 soul 的名字/iid。"""
    from neonrp.core.light_chat import _player_node, _soul_node

    token = str(entity or "").strip()
    if not token:
        return {"ok": False, "error": "entity 必填(player 或 soul 名/iid)"}
    if token.lower() in {"player", "玩家"}:
        return {"ok": True, "entity": "player", "location": _place_view(root, _player_node(root))}
    _pt, ref = _resolve_soul(root, token)
    if ref is None:
        return {"ok": False, "error": f"查无此人:{token}(不在 playthrough 名册)"}
    sdir = _soul_dir(root, ref.sid, ref.instance_id)
    node = _soul_node(root, sdir) if sdir.is_dir() else None
    return {"ok": True, "entity": ref.instance_id, "location": _place_view(root, node)}


def get_scene(root: Path, node: str) -> dict[str, Any]:
    """地点数据 + 场景层状态。node 接受裸名或 T###/node。"""
    from neonrp.core.place_nav import qualify_location, split_location, town_node_view
    from neonrp.core.scene_understanding import scene_state_path

    token = str(node or "").strip()
    if not token:
        return {"ok": False, "error": "node 必填"}
    scoped = qualify_location(root, token) or token
    town, bare = split_location(scoped)
    view = town_node_view(root, bare or scoped, prefer_town=town)
    if not view:
        return {"ok": False, "error": f"地图上没有这个地点:{token}"}
    state: dict[str, Any] = {}
    try:
        state = json.loads(
            scene_state_path(root, bare or scoped).read_text(encoding="utf-8")
        )
        if not isinstance(state, dict):
            state = {}
    except (OSError, ValueError):
        state = {}
    return {
        "ok": True,
        "node": scoped,
        "name": view.get("name") or bare or scoped,
        "data": view,
        "scene_state": state,
    }


def move_entity(root: Path, entity: str, to: str) -> dict[str, Any]:
    """结算=工具调用(M30 §4):裁判校验后写入唯一位置;拒绝即报错带回。

    物理层在此:place_nav.judge_move 是工具内脏,不是流水线阶段。
    world-agent 收到拒绝后自行改口或绕路——判断仍归 leader。
    """
    token = str(entity or "").strip()
    target = str(to or "").strip()
    if not token or not target:
        return {"ok": False, "error": "entity 与 to 必填"}

    if token.lower() in {"player", "玩家"}:
        from neonrp.core.turn_settlement import _apply_player_move

        moved = _apply_player_move(root, target)
        from neonrp.core.light_chat import _player_node

        landed = _player_node(root)
        return {
            "ok": True,
            "entity": "player",
            "moved": bool(moved),
            "location": _place_view(root, landed),
            "note": None if moved else "未移动(目标不可达/被裁判拒绝/原地)",
        }

    _pt, ref = _resolve_soul(root, token)
    if ref is None:
        return {"ok": False, "error": f"查无此人:{token}(不在 playthrough 名册)"}
    sdir = _soul_dir(root, ref.sid, ref.instance_id)
    if not sdir.is_dir():
        return {"ok": False, "error": f"soul 目录缺失:{sdir.name}"}

    from neonrp.core.light_chat import _soul_node
    from neonrp.core.place_nav import judge_move

    current = _soul_node(root, sdir)
    try:
        verdict = judge_move(root, current_location=current, target=target)
    except Exception:  # noqa: BLE001 — 裁判失败不破坏调用,按原样落
        logger.warning("ontology judge failed; landing as-is", exc_info=True)
        verdict = None

    if verdict is not None and not verdict.allowed and not verdict.clamped_to:
        return {
            "ok": False,
            "entity": ref.instance_id,
            "error": f"移动被拒绝:{verdict.reason or '目标不可达'}(她仍在原地)",
            "location": _place_view(root, current),
        }
    landing = (
        target
        if verdict is None
        else (verdict.resolved or verdict.clamped_to or target)
    )
    from neonrp.core.turn_settlement import _apply_soul_move

    moved = _apply_soul_move(sdir, landing, root=root, allow_cross_town=True)
    node_after = _soul_node(root, sdir)
    out: dict[str, Any] = {
        "ok": True,
        "entity": ref.instance_id,
        "moved": bool(moved),
        "location": _place_view(root, node_after),
    }
    if verdict is not None and verdict.clamped_to and not verdict.allowed:
        out["note"] = f"目标不可直达,裁判落点:{verdict.clamped_to}({verdict.reason or ''})"
    elif not moved:
        out["note"] = "未移动(原地或不可达)"
    return out
