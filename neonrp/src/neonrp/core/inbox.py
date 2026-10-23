"""文件收件箱 — v0.4.0 team 引擎的通信地基(HARNESS-TEAM-DESIGN §5 / T2)。

CC team 考古的直接移植(file-as-mailbox,与 file-as-router 同宗):
每个收件人一个 ``.neonrp/inboxes/<agent>.jsonl``,消息 append-only 落盘。
落盘 = trace 免费、崩溃可恢复、observe 窗可直接可视化"谁在跟谁说话"。

设计约束:
- 所有读写方都在同一进程(http 线程 + 引擎线程)⇒ 并发用模块级
  threading.Lock 串行化;文件本身只是持久化面,不做跨进程锁。
- 消息不背状态(位置/事实仍只走结算链);收件箱只载通信。
- kind 是开放集合;当前通道:
    perception      world → soul(感知包投递,替代单发广播)
    chat            玩家 → soul(直聊,T1 的线程之上的统一投递面)
    chat_room       玩家 → 房间(群聊;收件人=房间内每个 soul)
    retake_request  world → soul(重拍,T3;payload 带 request_id)
    soul_response   soul → world(回包/重拍响应;request_id 关联)
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("neonrp.inbox")

_LOCK = threading.Lock()

# 单收件箱保留的消息上限(旧的滚出;线程历史等长态归各自通道自管)。
INBOX_CAP = 200


@dataclass(frozen=True)
class InboxMessage:
    """一条收件箱消息(JSON 一行)。"""

    id: str
    kind: str
    sender: str
    to: str
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = 0.0
    read: bool = False

    @staticmethod
    def new(kind: str, sender: str, to: str, payload: dict[str, Any] | None = None) -> "InboxMessage":
        return InboxMessage(
            id=uuid.uuid4().hex[:12],
            kind=kind,
            sender=sender,
            to=to,
            payload=dict(payload or {}),
            ts=time.time(),
        )


def _inboxes_dir(root: Path) -> Path:
    return root / ".neonrp" / "inboxes"


def inbox_path(root: Path, agent: str) -> Path:
    safe = "".join(c for c in agent if c.isalnum() or c in "-_.") or "agent"
    return _inboxes_dir(root) / f"{safe}.jsonl"


def _read_all(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
    except OSError:
        logger.warning("inbox read failed: %s", path, exc_info=True)
    return rows


def _write_all(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows[-INBOX_CAP:])
    path.write_text(body + ("\n" if body else ""), encoding="utf-8")


def send(root: Path, msg: InboxMessage) -> str:
    """投递一条消息到 ``msg.to`` 的收件箱;返回消息 id。"""
    with _LOCK:
        path = inbox_path(root, msg.to)
        rows = _read_all(path)
        rows.append(asdict(msg))
        _write_all(path, rows)
    logger.debug("inbox: %s -[%s]-> %s (%s)", msg.sender, msg.kind, msg.to, msg.id)
    return msg.id


def send_many(root: Path, msgs: list[InboxMessage]) -> list[str]:
    """批量投递(如群聊:同一 payload 发给房间内每个 soul)。"""
    return [send(root, m) for m in msgs]


def peek(root: Path, agent: str, *, kind: str | None = None, unread_only: bool = True) -> list[InboxMessage]:
    """读消息(不标已读)。oldest→newest。"""
    with _LOCK:
        rows = _read_all(inbox_path(root, agent))
    out: list[InboxMessage] = []
    for r in rows:
        if unread_only and r.get("read"):
            continue
        if kind is not None and r.get("kind") != kind:
            continue
        try:
            out.append(InboxMessage(**{k: r.get(k) for k in ("id", "kind", "sender", "to", "payload", "ts", "read")}))
        except TypeError:
            continue
    return out


def drain(root: Path, agent: str, *, kind: str | None = None) -> list[InboxMessage]:
    """读并标记已读(deliver-once 语义;消息仍留在文件里作 trace)。"""
    with _LOCK:
        path = inbox_path(root, agent)
        rows = _read_all(path)
        out: list[InboxMessage] = []
        dirty = False
        for r in rows:
            if r.get("read"):
                continue
            if kind is not None and r.get("kind") != kind:
                continue
            try:
                out.append(InboxMessage(**{k: r.get(k) for k in ("id", "kind", "sender", "to", "payload", "ts", "read")}))
            except TypeError:
                continue
            r["read"] = True
            dirty = True
        if dirty:
            _write_all(path, rows)
    return out


def reply_of(root: Path, agent: str, request_id: str) -> InboxMessage | None:
    """在 ``agent`` 的收件箱里找回显 ``request_id`` 的响应(T3 重拍关联)。

    不标已读——调用方拿到后自行 drain;None = 尚未到达。
    """
    for m in peek(root, agent, unread_only=True):
        if str(m.payload.get("request_id") or "") == request_id:
            return m
    return None
