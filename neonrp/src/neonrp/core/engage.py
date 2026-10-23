"""engage_soul(M30 V2a)——world-agent 点名:某 soul 全档思考一轮。

与 ask_soul(纯问答,轻调用)镜像互补:engage 是**全档**——soul 走自己的
backend(默认 spawn soul-agent,带工具,可写自己的 soul 文件夹),按
soul JSON 报文契约回 digest。判断(点谁/何时点/给什么情境)归 leader;
引擎只投递与带回(M30 §2)。

未点名的 soul 本回合不思考(V2 点名制)——这是算力与主权的双重收敛。

协议留痕:inbox engage_request → soul_response(request_id 关联,
与 ask_soul 同族信封)。sticky 会话历史不在此维护(soul 记忆由它自己
在全档回合里写文件夹;跨回合连续性走 soul 记忆而非进程内历史)。
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger("neonrp")

ENGAGE_MAX_TURNS = 8

# ── 回合级 delta 收集(V2b):engage 发生在 world-agent 回合内部,
# land_turn 需要 CharacterDelta 才会 commit soul 记忆——conversation 在
# 回合开始 reset、land 前 drain。S2(exp/jev-system-one)在线程池里并行
# engage,所以加锁;drain 按 iid 排序,land 的 delta 哈希不随线程时序变。
_TURN_ENGAGEMENTS: list[dict[str, Any]] = []
_ENG_LOCK = threading.Lock()


def reset_turn_engagements() -> None:
    with _ENG_LOCK:
        _TURN_ENGAGEMENTS.clear()


def drain_turn_engagements() -> list[dict[str, Any]]:
    with _ENG_LOCK:
        out = list(_TURN_ENGAGEMENTS)
        _TURN_ENGAGEMENTS.clear()
    out.sort(key=lambda e: str(e.get("instance_id")))
    return out


def _role_contract(role: str) -> str:
    if role == "player":
        return (
            "【角色权限】你是玩家 avatar 的内在/记忆层,不是自动驾驶。"
            "human player 的输入才是权威行动;不要替玩家选择路线、说话或行动。"
            "若玩家只是开始/继续/观察,请同步身体感、内心压力和记忆,并把"
            "intended_action 写成 await human player choice。"
        )
    return (
        "【角色权限】你是自主 NPC soul;可以根据人格、记忆和场景压力"
        "自主行动、说话或保持沉默。"
    )


def engage_soul_run(
    root: Path,
    target: str,
    note: str = "",
    *,
    provider: str | None = None,
    mode: str = "play",
    max_turns: int | None = None,
) -> dict[str, Any]:
    """点名执行:构建该 soul 的本体视角 → 全档一轮 → 报文带回。

    `note` = leader 转达的情境(「玩家刚拔剑指向你」)。soul 反应的是
    场景与情境,永远不见玩家原文(M20 边界不变)。
    """
    from neonrp.core.inbox import InboxMessage, send as _inbox_send
    from neonrp.core.light_chat import _soul_node, _soul_place_label
    from neonrp.core.ontology import _resolve_soul, _soul_dir
    from neonrp.core.player_controller import PlayerTurnIntent, build_scene_packet
    from neonrp.core.scene_understanding import _soul_packet
    from neonrp.core.soul_agent import make_soul_agent_id
    from neonrp.core.soul_backend import resolve_soul_backend
    from neonrp.core.soul_result import parse_soul_turn_report

    token = str(target or "").strip()
    if not token:
        return {"ok": False, "error": "soul 必填(名字或 instance_id)"}
    _pt, ref = _resolve_soul(root, token)
    if ref is None:
        return {"ok": False, "error": f"查无此人:{token}(不在 playthrough 名册)"}
    sdir = _soul_dir(root, ref.sid, ref.instance_id)
    if not sdir.is_dir():
        return {"ok": False, "error": f"soul 目录缺失:{sdir.name}"}

    request_id = f"eg-{uuid.uuid4().hex[:10]}"
    _inbox_send(
        root,
        InboxMessage.new(
            "engage_request",
            "world-agent",
            ref.instance_id,
            {"request_id": request_id, "note": note},
        ),
    )

    # 本体视角:她所在地点的场景包(不是玩家视角的基包)。
    base = build_scene_packet(
        root, PlayerTurnIntent(raw_input="", kind="start_or_continue")
    )
    node = _soul_node(root, sdir)
    pkt = _soul_packet(base, node=node, root=root)
    role = (str(getattr(ref, "role", "") or "npc").strip().lower()) or "npc"
    perception_parts = [
        pkt.to_prompt_block(),
        _role_contract(role),
        "【视角】你以第一人称存在与行动。场景旁白是从他人视角写的:其中以"
        "第三人称出现、与你同名或符合你身份的角色就是你本人。旁白里的"
        "「你」「玩家」指的是独立的人类玩家,不是你。",
    ]
    if note.strip():
        perception_parts.append(f"【此刻(主持人转述)】{note.strip()}")
    perception_parts.append(
        "【你】依据你自己的人格与记忆做出反应——留下、行动、等待、或想离开。"
        "**你的去向由 world-agent 裁定,不要自己报 moved_to**;想去哪就写进"
        "你的言行/意图里。把该记住的写进你自己的 soul 文件夹。"
    )
    perception = "\n".join(perception_parts)

    from neonrp.core.character_agent import _hash_soul_folder
    from neonrp.core.llm import Message

    backend = resolve_soul_backend(root, ref)
    before_hash = _hash_soul_folder(sdir)
    t0 = time.monotonic()
    try:
        res = _respond(backend,
        root=root,
        agent_id=make_soul_agent_id(ref.sid, ref.instance_id),
        messages=[Message(role="user", content=perception)],
        mode=mode,
        provider=provider,
        max_turns=max_turns or ENGAGE_MAX_TURNS,
        run_id=f"engage:{ref.instance_id}:{request_id}",
    )
    except Exception as exc:  # noqa: BLE001 — 工具失败带回 loop,leader 自决
        logger.warning("engage_soul backend failed for %s", ref.instance_id, exc_info=True)
        return {
            "ok": False,
            "iid": ref.instance_id,
            "error": f"soul 执行失败(隔离,不破坏回合):{exc}",
        }
    report = parse_soul_turn_report(
        res.assistant_message or "", success=res.success
    )
    name = _name_of(sdir, ref.sid)
    digest = report.digest_line(name, role=role)

    _inbox_send(
        root,
        InboxMessage.new(
            "soul_response",
            ref.instance_id,
            "world-agent",
            {
                "request_id": request_id,
                "instance_id": ref.instance_id,
                "state": report.state,
                "digest": digest,
            },
        ),
    )
    _entry = {
        "sid": ref.sid,
        "instance_id": ref.instance_id,
        "version_hash": str(getattr(ref, "version_hash", "") or ""),
        "role": role,
        "state": report.state,
        "digest": digest,
        "inner_voice": str(report.inner_voice or ""),
        "confidence": float(report.confidence or 0.0),
        "urgency": float(report.urgency or 0.0),
        "memory_delta": str(report.memory_delta or ""),
        "before_hash": before_hash,
        "after_hash": _hash_soul_folder(sdir),
    }
    with _ENG_LOCK:
        _TURN_ENGAGEMENTS.append(_entry)
    return {
        "ok": True,
        "iid": ref.instance_id,
        "name": name,
        "state": report.state,
        "digest": digest,
        "inner_voice": str(report.inner_voice or ""),
        "intended_action": str(report.intended_action or ""),
        "needs_world_decision": bool(getattr(report, "needs_world_decision", False)),
        "location": _soul_place_label(root, sdir),
        "duration_ms": int((time.monotonic() - t0) * 1000),
    }


def _respond(backend, **kw):  # noqa: ANN001, ANN003 — thin seam for try/except
    return backend.respond(**kw)


def _name_of(soul_dir: Path, fallback: str) -> str:
    from neonrp.core.light_chat import _display_name

    return _display_name(soul_dir, fallback)


HEARTBEAT_CAP = 3


def heartbeat_soul_run(
    root: Path, ref: Any, context_line: str
) -> dict[str, Any]:
    """在场轻档心跳(M30 lifecycle)。

    未被点名的**在场**角色每回合保底一次轻调用:一两句第一人称的细微
    反应(动作/神态/短语),不推进剧情、不移动、无工具。产物:
    - 当回合:总线 soul_response(state=heartbeat)→ UI 在场栏/泳道即时动
    - 下回合:便签通道 kind=heartbeat → leader preflight 可见
    - 该 soul 自己的 recent_events memo(她记得自己的反应)
    失败回落纯 memo(调用方处理),永不破坏回合。
    """
    from neonrp.core.light_chat import (
        _adapter,
        _display_name,
        _persona_digest,
        _soul_memory_digest,
        _soul_place_label,
    )
    from neonrp.core.llm import Message
    from neonrp.core.ontology import _soul_dir

    sdir = _soul_dir(root, ref.sid, ref.instance_id)
    if not sdir.is_dir():
        return {"ok": False, "error": "soul 目录缺失"}
    name = _display_name(sdir, ref.sid)
    system = (
        f"你是{name},此刻在:{_soul_place_label(root, sdir)}。\n"
        f"【你的人格】\n{_persona_digest(sdir)}\n\n"
        f"【你的记忆】\n{_soul_memory_digest(sdir)}\n\n"
        "现在只做一件事:对刚刚发生的场景,以第一人称给出**一两句**细微"
        "反应(一个动作、一个神态、至多一句短语)。不推进剧情、不离开"
        "此地、不代替别人。只输出反应本身,无引号无前缀。"
    )
    user = f"刚刚发生:{(context_line or '').strip()[:600] or '(场景静默推进)'}"
    try:
        res = _adapter(root).chat([Message(role="system", content=system),
                                   Message(role="user", content=user)])
        line = str(getattr(getattr(res, "message", None), "content", "") or "").strip()
    except Exception as exc:  # noqa: BLE001 — 心跳失败回落 memo,不破回合
        logger.debug("heartbeat failed for %s: %s", ref.instance_id, exc)
        return {"ok": False, "error": str(exc)}
    if not line:
        return {"ok": False, "error": "empty"}
    line = line[:200]
    return {"ok": True, "iid": ref.instance_id, "name": name, "line": line}
