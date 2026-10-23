"""寻址接口(@/#)— M24 §0.5:输入进哪一拍,引擎级统一解析。

一套语法、单一实现,TUI(文字频道)与 Web(手势=隐式寻址)同源:

    @艾琳娜 早          → 对话拍·直聊(target=si-elena0001)
    #大家早 / # 大家早   → 对话拍·群聊(此地房间)
    推门走进旅店         → 世界拍(现状管线,不经此层改动)

@ 匹配 roster:soul.json 的 name / name_local / 名字首词 / sid / iid,
casefold 宽松匹配。解析失败(@ 后没有已知名字)⇒ 落回世界拍——寻址永远
不吞玩家输入。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("neonrp.address")

_AT = ("@", "@")  # ASCII + 全角
_HASH = ("#", "#")


def soul_aliases(root: Path) -> list[tuple[str, set[str]]]:
    """[(iid, {别名…})];别名含 name/name_local/名字首词/sid/iid,casefold。"""
    from neonrp.core.playthrough import read_playthrough

    pt = read_playthrough(root)
    if pt is None:
        return []
    out: list[tuple[str, set[str]]] = []
    for ref in pt.souls:
        soul_dir = root / "souls" / f"{ref.sid}-{ref.instance_id}"
        names: set[str] = {ref.sid.casefold(), ref.instance_id.casefold()}
        try:
            data = json.loads((soul_dir / "soul.json").read_text(encoding="utf-8"))
            for n in [data.get("name"), data.get("name_local"), *(data.get("aliases") or [])]:  # aliases: a form's old names
                if isinstance(n, str) and n.strip():
                    n = n.strip()
                    names.add(n.casefold())
                    first = n.split()[0]
                    if first:
                        names.add(first.casefold())
        except (OSError, ValueError):
            pass
        out.append((ref.instance_id, names))
    return out


def parse_address(root: Path, text: str) -> dict[str, Any]:
    """解析寻址输入 → {lane, target, text}。

    lane ∈ {"world", "dialogue", "room"};dialogue 时 target=iid。
    永不失败:任何解析不确定都落回 {"lane": "world", "text": 原文}。
    """
    raw = str(text or "")
    stripped = raw.strip()
    if not stripped:
        return {"lane": "world", "target": None, "text": raw}

    head = stripped[0]
    if head in _HASH:
        # 裸 "#"(无正文)→ text 为空:调用方视作「打开房间/看在场」,
        # 不把 "#" 本身当话发出去。
        body = stripped[1:].strip()
        return {"lane": "room", "target": None, "text": body}

    if head in _AT:
        rest = stripped[1:].lstrip()
        if rest:
            # 先试全名匹配(容纳带空格的名字),再试首词。
            aliases = soul_aliases(root)
            low = rest.casefold()
            for iid, names in aliases:
                for n in sorted(names, key=len, reverse=True):
                    if n and low.startswith(n):
                        after = rest[len(n):].lstrip(" ,,、::").strip()
                        if after:
                            return {"lane": "dialogue", "target": iid, "text": after}
                        # 只 @ 了名字没说话 → 仍进直聊(开个空线程由 UI 处理)
                        return {"lane": "dialogue", "target": iid, "text": ""}
        # @ 后没有可识别的名字 → 世界拍兜底,不吞输入。
        logger.debug("address: unresolved @ in %r → world", stripped[:40])
    return {"lane": "world", "target": None, "text": raw}
