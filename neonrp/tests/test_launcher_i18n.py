"""Regression: the WorldLines launcher must re-localize EVERY label when
the UI locale changes — not just the handful of buttons the old
``_relabel_launcher`` touched.

On a Japanese system (``LANG=ja_JP``) the launcher resolves its locale to
``ja`` at construction. When the user then picks another language, the
section titles (``menu.section_*``) and the import / upload / soul-talk
buttons used to stay frozen in Japanese because ``_relabel_launcher``
never updated them. This test pins the full relabel surface.
"""

from __future__ import annotations

from textual.widgets import Button, Static

from neonrp.tui.app import WorldLinesLauncherApp
from neonrp.tui.i18n import get_message


class _FakeWidget:
    """Captures whatever label/text gets written, keyed by selector."""

    def __init__(self, selector: str, sink: dict[str, str]) -> None:
        object.__setattr__(self, "_selector", selector)
        object.__setattr__(self, "_sink", sink)

    def update(self, value: str) -> None:  # Static path
        self._sink[self._selector] = str(value)

    def __setattr__(self, name: str, value: object) -> None:  # Button.label path
        if name == "label":
            self._sink[self._selector] = str(value)
        else:
            object.__setattr__(self, name, value)


def _relabel_capture(locale: str) -> dict[str, str]:
    app = WorldLinesLauncherApp()
    app.locale = locale
    app._saved_games = []  # deterministic continue-button branch
    captured: dict[str, str] = {}
    app.query_one = lambda selector, kind=None: _FakeWidget(selector, captured)  # type: ignore[assignment]
    app._relabel_launcher()
    return captured


def test_relabel_localizes_every_row() -> None:
    """仪表盘回来了:分区标题与每一格都要跟着语言走。"""
    cap = _relabel_capture("zh")

    assert cap["#wl-new"] == get_message("zh", "menu.new")
    assert cap["#wl-settings"] == get_message("zh", "menu.settings")
    assert cap["#wl-exit"] == get_message("zh", "menu.exit")
    assert cap["#wl-soul-talk"] == get_message("zh", "menu.soul_talk")
    assert cap["#wl-soul-browse"] == get_message("zh", "menu.soul_browse")
    assert cap["#wl-world-create"] == get_message("zh", "menu.world_create")
    assert cap["#wl-title-continue"] == get_message("zh", "menu.section_continue")
    assert cap["#wl-title-world"].startswith(get_message("zh", "menu.section_world_lib"))
    assert cap["#wl-continue"].startswith(get_message("zh", "menu.continue")) or cap[
        "#wl-continue"
    ] == get_message("zh", "menu.continue_empty")


def test_relabel_leaves_no_stale_japanese_when_switching_to_zh() -> None:
    cap = _relabel_capture("zh")
    # Every captured label must be the zh string — never the JP fallback
    # that a ja-system construction would have produced.
    joined = "".join(cap.values())
    for jp_fragment in ("続き", "物語", "キャラクター", "ロア", "ソウル"):
        assert jp_fragment not in joined, f"stale Japanese {jp_fragment!r} survived relabel: {cap}"


def test_relabel_covers_every_menu_widget() -> None:
    """Completeness guard: the relabel must touch every titled/buttoned
    widget in the dashboard, so adding one without wiring relabel fails here.
    """
    cap = _relabel_capture("en")
    expected = {"#worldlines-header", "#worldlines-hint"}
    expected |= {f"#{i}" for i in WorldLinesLauncherApp._menu_button_ids()}
    expected |= {"#wl-title-continue", "#wl-title-new", "#wl-title-world", "#wl-title-char"}
    missing = expected - set(cap)
    assert not missing, f"_relabel_launcher did not touch: {sorted(missing)}"
    # 反向守卫:创建两格仍退役,relabel 不该去碰它们。
    stale = {k for k in cap if "new-character" in k or "new-world" in k}
    assert not stale, f"_relabel_launcher still touches removed widgets: {sorted(stale)}"
