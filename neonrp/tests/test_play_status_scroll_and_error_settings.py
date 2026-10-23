"""错误面板只有 重试/跳过,换模型要自己想起
/settings;右上角状态栏没有滚动条与上下按钮。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from neonrp.tui.app import NeonRPApp
from neonrp.tui.portrait import PortraitPanel


@pytest.fixture
def app(tmp_path: Path):
    a = NeonRPApp(root=tmp_path, mode="play")
    a.query_one = MagicMock(return_value=MagicMock())
    return a


def _press(app: NeonRPApp, btn_id: str) -> None:
    ev = MagicMock()
    ev.button.id = btn_id
    app.on_button_pressed(ev)
    ev.stop.assert_called()


def test_error_panel_switch_model_opens_settings(app):
    app._cmd_settings = MagicMock()
    app._send_message = MagicMock()
    _press(app, "agent-error-settings-3")
    app._cmd_settings.assert_called_once()
    app._send_message.assert_not_called()


def test_error_panel_retry_still_resends(app):
    app._cmd_settings = MagicMock()
    app._send_message = MagicMock()
    app._last_user_input = "寻找小夏"
    _press(app, "agent-error-retry-3")
    app._send_message.assert_called_once_with("寻找小夏")
    app._cmd_settings.assert_not_called()


def test_state_buttons_scroll_a_page_each_way(app):
    box = MagicMock()
    box.size.height = 18
    app.query_one = MagicMock(return_value=box)
    _press(app, "btn-state-down")
    assert app.query_one.call_args.args[0] == "#game-state-scroll", "滚的是容器,不是那张 Static 文档"
    box.scroll_relative.assert_called_with(y=16, animate=False)
    _press(app, "btn-state-up")
    box.scroll_relative.assert_called_with(y=-16, animate=False)


def test_state_buttons_survive_a_missing_panel(app):
    app.query_one = MagicMock(side_effect=Exception("not mounted"))
    _press(app, "btn-state-down")  # 不炸


def test_portrait_static_env_disables_the_animation(monkeypatch):
    monkeypatch.delenv("NEONRP_PORTRAIT_STATIC", raising=False)
    assert PortraitPanel._animation_enabled()
    monkeypatch.setenv("NEONRP_PORTRAIT_STATIC", "1")
    assert not PortraitPanel._animation_enabled()
