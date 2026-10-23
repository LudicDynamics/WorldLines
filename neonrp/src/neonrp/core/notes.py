"""统一便签通道(M30 V3)——四路 deliver-once 队列并入 mailbox。

旧世界:位置裁定 / 幕间直聊摘要 / 秘密解锁 / 秘密护栏各自一份
「json 列表文件 + read-and-unlink」实现(同一投递模式抄四份)。
新世界:一条便签 = 发给 world-agent 的 InboxMessage
(kind="note:<channel>", payload={"line": ...});drain 走 inbox 的
deliver-once(标读留档 ⇒ trace 免费),producer 侧支持 dedupe。

迁移:drain 时顺手清扫旧 json 文件(legacy_path),存档不断档。
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("neonrp")

CHANNELS = ("judgment", "chat_digest", "reveal", "guardrail", "escalation", "heartbeat")
_TO = "world-agent"


def post_note(
    root: Path, channel: str, line: str, *, sender: str = "engine", dedupe: bool = False
) -> None:
    """投一条便签给 world-agent(deliver-once;dedupe=未读中同文不重复)。"""
    from neonrp.core.inbox import InboxMessage, peek, send

    text = str(line or "").strip()
    if not text:
        return
    kind = f"note:{channel}"
    try:
        if dedupe and any(
            m.payload.get("line") == text for m in peek(root, _TO, kind=kind)
        ):
            return
        send(root, InboxMessage.new(kind, sender, _TO, {"line": text}))
    except Exception:  # noqa: BLE001 — 便签面故障不阻塞回合
        logger.warning("note post failed (%s)", channel, exc_info=True)


def drain_notes(
    root: Path, channel: str, *, legacy_path: Path | None = None
) -> list[str]:
    """读并标记已读(deliver-once)。legacy_path=旧 json 队列文件,
    存在则一次性清扫合并(迁移期兼容,读后删)。"""
    import json

    from neonrp.core.inbox import drain

    lines: list[str] = []
    if legacy_path is not None and legacy_path.exists():
        try:
            loaded = json.loads(legacy_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                lines.extend(str(x) for x in loaded)
        except (OSError, ValueError):
            pass
        try:
            legacy_path.unlink()
        except OSError:
            pass
    try:
        lines.extend(
            str(m.payload.get("line") or "")
            for m in drain(root, _TO, kind=f"note:{channel}")
        )
    except Exception:  # noqa: BLE001
        logger.warning("note drain failed (%s)", channel, exc_info=True)
    return [ln for ln in lines if ln]
