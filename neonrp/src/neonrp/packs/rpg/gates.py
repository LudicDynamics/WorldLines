"""rpg pre-turn gate — what the engine itself does before the narrator writes: draw the map when the player asks the way,
show the sheet when asked. Whether a fight happens is not the gate's (D-20261018-combat-one-shot-node): the talk decides
who does what, the narrator calls [combat] (a road stop's foes come from the hazards table), and the fight settles the stop.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# The player looks at the map or asks the way → the engine draws it (async: a card for the player, the
# narrator is not asked and does not wait). In the probe the model drew it on its own 1 time in 4.
MAP_RE = re.compile(r"地图|在哪儿?|怎么走|哪条路|往哪(边|儿)?走|方位|\bmap\b|where am i|which way|how do (i|we) get|地図|どこ(にいる|だ)|道順|どっちへ", re.IGNORECASE)


# adversarial2 F2: 「显示一下我的属性面板」 → the narrator read every number into the prose. The sheet is the engine's to show.
# asking to SEE one's sheet / bag (10-02 L6:「点着背包里的罩灯」 is using the bag, not looking at it)
SHEET_RE = re.compile(r"(看|查看|显示|打开|翻看|翻一翻|列出)[一下看我的自己]*(属性|面板|人物卡|角色卡|状态栏|背包|行囊)|属性面板|人物卡|角色卡|状态栏"
                      r"|\b(show|check|open|see)\b.{0,12}\b(stats?|inventory|sheet)\b|character sheet|ステータス(を|画面)|持ち物を(見|確認)|キャラシート", re.IGNORECASE)


def wants_sheet(reg: Any, user_text: str) -> bool:
    a = reg.actions.get("sheet") if reg is not None else None
    return bool(a is not None and a.enabled and SHEET_RE.search(user_text or ""))


def wants_map(reg: Any, user_text: str) -> bool:
    a = reg.actions.get("map") if reg is not None else None
    return bool(a is not None and a.enabled and MAP_RE.search(user_text or ""))


def pre_turn(root: Path, reg: Any, *, user_text: str = "", intent_kind: str = "", turn: int = 0, **_kw: Any) -> dict[str, Any]:
    fire = ([{"op": "map"}] if wants_map(reg, user_text) else []) + ([{"op": "sheet"}] if wants_sheet(reg, user_text) else [])
    return {"fire": fire} if fire else {}
