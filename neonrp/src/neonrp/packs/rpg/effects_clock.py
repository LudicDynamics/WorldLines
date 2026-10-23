"""Effects that run out on the world clock (「倒计时按 turn 还是按 clock;clock 是 rpg 里的内容,rpg layer 统一」).

The core counts effects down in resolves (core/effects.py ``turns``). A rule line that says how long in game time
(``持续 12 小时`` → ``hours``, core/effect_rules.py) is the rpg layer's: this tick turns ``hours`` into ``until`` (minutes
on the world clock, ``time.day`` · ``time.clock``) once, then removes the effect when the clock passes it. A long sleep in
one resolve wears off what a few steps would not. Worlds without a clock keep only the resolve countdown.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def now_minutes(reg: Any) -> int | None:
    """Minutes since day 1 00:00 on the world clock, or None (no clock)."""
    v = reg.variables
    if "time.day" not in v or "time.clock" not in v:
        return None
    m = re.match(r"^\s*(\d{1,2}):(\d{2})", str(v["time.clock"].value or ""))
    if not m:
        return None
    try:
        day = int(v["time.day"].value or 1)
    except (TypeError, ValueError):
        return None
    return (day - 1) * 1440 + int(m.group(1)) * 60 + int(m.group(2))


def clock_text(minutes: int) -> str:
    d, rest = divmod(int(minutes), 1440)
    return f"D{d + 1} {rest // 60:02d}:{rest % 60:02d}"


def tick(root: Path, reg: Any, *, turn: int = 0, res: Any = None) -> list[dict[str, Any]]:
    from neonrp.core import effects

    now = now_minutes(reg)
    if now is None:
        return []
    ops: list[dict[str, Any]] = []
    for e in effects.instances(reg, None):
        until = e.props.get("until")
        if until in (None, ""):
            try:
                hours = float(e.props.get("hours") or 0)
            except (TypeError, ValueError):
                hours = 0.0
            if hours > 0:
                u = now + int(round(hours * 60))
                ops.append({"op": "patch", "who": e.id, "props": {"until": u, "until_text": clock_text(u)}})
            continue
        try:
            if now >= int(until):
                ops.append({"op": "remove", "who": e.id})
        except (TypeError, ValueError):
            continue
    return ops


# O7 (10-06): what this background unit may write (an effect's own countdown on the world clock)
tick.unit = {"on": "apply", "llm": False, "writes": ["op:patch", "op:remove"]}  # type: ignore[attr-defined]
