"""TUI step 0 (10-08): dice lines drawn right, SAN / away lines styled, async tool lines kept off the screen."""
from __future__ import annotations

import pytest

from neonrp.core.stream_lines import LinesFilter
from neonrp.tui.app import ConversationView as C

GREEN, RED, GOLD, DARK = "#67c587", "#cf7f7f", "#f5c542", "#cf5b5b"


def _accent(line: str) -> str:
    w = C._build_dice_widget(line)
    assert w is not None, line
    return str(w.content.spans[0].style).split()[-1]


@pytest.mark.parametrize("line, color", [
    ("[找暗门: 37 ≤ 60] → 成功", GREEN),          # percentile pass (was drawn red)
    ("[找暗门: 77 > 60] → 失败", RED),
    ("[察觉: 03 ≤ 60] → 大成功", GOLD),           # BRP critical ≤ 1/20 of the skill (60 → 3)
    ("[察觉: 99 > 60] → 大失败", DARK),           # BRP fumble 99 / 00
    ("[潜行: 17+3=20 >= 15] → 成功", GREEN),
    ("[潜行: 7+3=10 < 15] → 失败", RED),
    ("[撬锁: 20-1=19 >= 12] → 成功", GOLD),       # natural 20 with a negative modifier
    ("[撬锁: 1-1=0 < 12] → 失败", DARK),
    ("[伤害: 3+4+2=9 >= 8] → 成功", GREEN),       # several dice: no crit read off the first one
])
def test_dice_colors(line, color):
    assert _accent(line) == color


def test_san_and_away_lines_have_their_own_style():
    assert C._semantic_line_class("[san 0/1d6 看见尸体] → SAN 检定 37 ≤ 55 —— 成功") == "semantic-san-line"
    for line in ("// 异地 · 罗文 @ 碧石镇:我去公会", "// elsewhere · Rowan @ Bishi:the guild", "// 다른 곳 · 로완 @ 벽석: 길드"):
        assert C._semantic_line_class(line) == "semantic-away-line", line
    assert C._semantic_line_class("// 商量") == "semantic-scene-header"


def test_async_lines_never_reach_the_screen():
    f = LinesFilter()
    out = f.feed("<lines>你推开门。\n[~map]\n[~write towns/T001/notes.md]\n第一行笔记\n第二行[/write]\n灯还亮着。\n</lines>")
    assert "你推开门。" in out and "灯还亮着。" in out
    assert "[~map]" not in out and "笔记" not in out and "[/write]" not in out


def test_a_waiting_request_still_stops_the_stream():
    f = LinesFilter()
    out = f.feed("<lines>你屏住呼吸。\n[dice 1d20+2 vs 12]撬锁[/dice]\n门开了。\n</lines>")
    assert "你屏住呼吸。" in out and "门开了" not in out
