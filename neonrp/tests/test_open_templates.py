"""`/open` 也认模板(「这 5 个模板是能在 neonrp 能摸到」)。

模板 = 世界 × 角色 × 玩法包 × 剧情 × 合约;从模板开新局走 `template.new_run`,和网页 / launcher 同一条路,
所以 TUI 里开出来的一局带着它的剧情和合约(game/meta/play_contract.json)。模板 id 可能和内置世界同名
(stoneford-elena 两边都有),所以模板用 `tpl:<id>`;不带前缀时世界 / 存档优先。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from neonrp.tui.app import NeonRPApp


class _View:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def write(self, text: str) -> None:
        self.lines.append(text)

    @property
    def text(self) -> str:
        return "".join(self.lines)


@pytest.fixture
def app_view(tmp_path, monkeypatch):
    app = NeonRPApp.__new__(NeonRPApp)
    app.root = tmp_path / "current"
    app.reopen_request = None
    app.ui_locale = "zh"
    view = _View()
    app.push_screen = MagicMock()
    monkeypatch.setattr(NeonRPApp, "query_one", lambda self, *a, **k: view)
    monkeypatch.setattr(NeonRPApp, "exit", lambda self, *a, **k: None)
    monkeypatch.setattr(NeonRPApp, "_current_model_ref", lambda self: None)
    return app, view


def _no_saves_no_worlds():
    return patch("neonrp.worlds.list_saved_games", return_value=[]), patch("neonrp.worlds.list_worlds", return_value=[])


def test_bare_open_lists_the_templates_with_their_contract(app_view):
    app, view = app_view
    a, b = _no_saves_no_worlds()
    with a, b:
        app._cmd_open([])
    text = view.text
    assert "模板" in text
    for tid in ("pct-house", "stoneford-elena", "stoneford-market", "stoneford-three-towns", "werewolf-night-village"):
        assert f"tpl:{tid}" in text, tid
    line = next(x for x in view.lines if "tpl:pct-house" in x)
    assert "沙盒跑团" in line, "模板后面写着它承诺的玩法(合约名,按界面语言)"


def test_picker_offers_templates_and_picking_one_opens_tpl(app_view):
    app, view = app_view
    a, b = _no_saves_no_worlds()
    with a, b:
        app._cmd_open([])
    screen, callback = app.push_screen.call_args.args[:2]
    values = [v for _, v in screen._options]
    assert "template::pct-house" in values
    app._cmd_open = MagicMock()
    callback("template::pct-house")
    app._cmd_open.assert_called_with(["tpl:pct-house"])


def test_open_tpl_builds_a_run_with_its_plots_and_contract(app_view, tmp_path, monkeypatch):
    import neonrp.worlds as W

    monkeypatch.setattr(W, "PLAYS_HOME", tmp_path / "plays")
    app, view = app_view
    a, b = _no_saves_no_worlds()
    with a, b:
        app._cmd_open(["tpl:pct-house"])
    req = app.reopen_request
    assert req is not None, view.text
    run = req.root
    assert run.is_dir() and run.is_relative_to(tmp_path / "plays"), "新局落在存档区,模板源不动"
    assert (run / "game" / "meta" / "play_contract.json").is_file(), "这一局带着模板的合约"
    assert req.mode == "play" and not req.continue_session


def test_same_name_prefers_the_world_and_tpl_prefix_picks_the_template(app_view):
    app, _ = app_view
    with patch("neonrp.worlds.list_saved_games", return_value=[]), patch(
        "neonrp.worlds.list_worlds", return_value=[{"id": "stoneford-elena", "display_name": "石津镇"}]
    ):
        assert app._resolve_openable("stoneford-elena")[0] == "world"
        assert app._resolve_openable("tpl:stoneford-elena")[0] == "template"
        assert app._resolve_openable("pct-house")[0] == "template", "没有同名世界 / 存档时,裸 id 也认模板"
        assert app._resolve_openable("tpl:nope") is None
