"""The play hints in the TUI (10-23, as the standard front end): `/` skills with value and line next to our commands,
`/skill ` targets, `@` people, `#` places and things inside a line, the quick bar, the sheet on /status, the dice
card's why / for."""
from __future__ import annotations

import asyncio
from pathlib import Path

from test_engine_v3 import _install

from neonrp.tui import play_hints as H


def _menu(tmp_path: Path) -> dict:
    H.invalidate()
    return H.menu(_install(tmp_path), ttl=0)


def test_slash_lists_skills_with_their_line_and_a_colliding_name_goes_by_marker(tmp_path):
    m = _menu(tmp_path)
    rows = H.skill_rows(m, "", set(), "zh")
    assert [c for _l, c in rows] == ["/快斩", "/立定招架"]
    assert "先手贴近时更容易命中" in rows[0][0] and "技能" in rows[0][0]
    assert H.skill_rows(m, "立", set(), "zh")[0][1] == "/立定招架"
    assert H.skill_rows(m, "", {"快斩"}, "zh")[0][1] == "[skill 快斩]"  # also one of ours → the engine's marker


def test_skill_then_space_offers_targets_and_tokens_fill_in(tmp_path):
    m = _menu(tmp_path)
    row, rest = H.skill_typed(m, "快斩 艾")
    assert row["label"] == "快斩" and rest == "艾"
    assert [c for _l, c in H.target_rows(m, "/快斩", rest, "zh")] == ["/快斩 艾琳娜"]
    assert ("我去 #主街" in [c for _l, c in H.token_rows(m, "我去 #主", "zh")])
    assert any(c == "看看 #罩灯" for _l, c in H.token_rows(m, "看看 #", "zh"))
    assert H.token_rows(m, "#主", "zh") == []  # a line that starts with # talks to the room
    assert [c for _l, c in H.token_rows(m, "问问 @", "zh")] == ["问问 @艾琳娜"]


def test_sheet_quick_and_dice_detail(tmp_path):
    m = _menu(tmp_path)
    sheet = H.sheet_text(m, "zh").plain
    assert "dex 7" in sheet and "/快斩" in sheet and "先手贴近" in sheet
    assert ("@艾琳娜", "@艾琳娜") in H.quick(m) and ("/快斩", "/快斩") in H.quick(m)
    d = H.dice_detail({"total": 37, "vs": 60, "under": True, "passed": True, "label": "侦查", "reason": "找暗门"}, "zh").plain
    assert "侦查" in d and "不超过技能值就成功" in d and "为了 找暗门" in d
    crit = H.dice_detail({"total": 2, "vs": 60, "under": True, "passed": True, "level": "crit", "crit_max": 3}, "en").plain
    assert "3 or lower is a critical" in crit
    assert "Rolled 7" in H.dice_detail({"total": 7}, "en").plain


def test_tui_slash_panel_quick_bar_and_status_sheet(tmp_path):
    from neonrp.tui.app import NeonRPApp
    from neonrp.tui.options_bar import QuickBar

    H.invalidate()
    app = NeonRPApp(root=_install(tmp_path), provider="stub", mode="play")

    async def scenario() -> None:
        async with app.run_test(size=(150, 50)) as pilot:
            await pilot.pause(0.2)
            bar = app.query_one("#quick-bar", QuickBar)
            assert bar.display and ("/快斩", "/快斩") in bar.items
            # 10-24: the words are drawn, not just the buttons — a one-line Button needs Textual's compact variant;
            # Button's own border-top / border-bottom ate the line and the labels never showed (seen in a real terminal)
            btn = bar.query("Button").first()
            assert btn.content_region.height == 1 and "/快斩" in app.export_screenshot()
            rows = app._compute_slash_suggestions("/")
            assert rows[0][1] == "/快斩" and any(c == "/status" for _l, c in rows)
            order = [c for _l, c in rows]
            assert order.index("/status") < order.index("/settings")  # this run's commands before the rest
            assert [c for _l, c in app._compute_slash_suggestions("/快斩 ")][:1] == ["/快斩 艾琳娜"]
            app._update_slash_suggestions("我去 #集")
            assert app._slash_suggestions and app._slash_suggestions[0][1] == "我去 #集市广场"
            app._quick_insert("/快斩")
            app._quick_insert("@艾琳娜")
            assert app.query_one("#message-input").value == "/快斩 @艾琳娜 "
            app._handle_slash_command("/status")
            await pilot.pause(0.2)
            body = str(app.screen.query_one("#status-tab-body").content)
            assert "/快斩" in body and "dex 7" in body

    asyncio.run(scenario())


def _built(tmp_path: Path, tid: str, lang: str) -> Path:
    from _paths import PRODUCT_TEMPLATES

    from neonrp import template as TP
    from neonrp.template import i18n as I

    with I.localized(TP.load(PRODUCT_TEMPLATES / f"{tid}.template"), lang) as t:
        TP.build(t, tmp_path / "run", lang=lang)
    return tmp_path / "run"


def test_the_hints_are_in_the_runs_language_and_names_may_hold_spaces(tmp_path):
    """10-23: skills and people are not always Chinese — an English run lists English skills and names, a name with a
    space still completes (「/Quick S」「@Elena V」「#North G」)."""
    H.invalidate()
    m = H.menu(_built(tmp_path, "stoneford-elena", "en"), ttl=0)
    assert [c for _l, c in H.skill_rows(m, "Quick S", set(), "en")] == ["/Quick Slash"]
    assert "Easier to land" in H.skill_rows(m, "", set(), "en")[0][0]
    row, rest = H.skill_typed(m, "Quick Slash Ele")
    assert row["label"] == "Quick Slash" and [c for _l, c in H.target_rows(m, "/Quick Slash", rest, "en")] == ["/Quick Slash Elena Vale"]
    assert [c for _l, c in H.token_rows(m, "talk to @Elena V", "en")] == ["talk to @Elena Vale"]
    assert [c for _l, c in H.token_rows(m, "walk to #North G", "en")] == ["walk to #North Gate"]
    assert H.token_rows(m, "talk to @Elena Vale about", "en") == []  # the name is done, the line goes on
    assert H.token_rows(m, "mail@host", "en") == []
