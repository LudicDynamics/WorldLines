"""设置界面里点一个已配置的模型 = 切到它(「点击已经设置好的
模型并不会切换,复用了只管测试的逻辑」)。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from neonrp.tui.settings_flow import SettingsFlow


def _flow(current="qwen", can_switch=True):
    host = MagicMock()
    host._current_model_ref = MagicMock(return_value=current)
    if not can_switch:
        del host._cmd_auth_set_model
    host.locale = "zh"
    host.ui_locale = "zh"
    return SettingsFlow(host=host), host


def _entries():
    return [{"id": "qwen", "provider": "openai", "model": "q"}, {"id": "deepseek", "provider": "openai", "model": "d"}]


def test_root_marks_the_current_model():
    flow, host = _flow("qwen")
    with patch("neonrp.tui.settings_flow.list_configured_entries", return_value=_entries()):
        flow.open_root()
    screen = host.push_screen.call_args.args[0]
    labels = [lab for lab, _ in screen._options]
    assert any(lab.startswith("★ qwen") for lab in labels) and not any(lab.startswith("★ deepseek") for lab in labels)


def test_entry_detail_offers_use_and_switches():
    flow, host = _flow("qwen")
    with patch("neonrp.tui.settings_flow._load_user_config_models", return_value={"deepseek": {"provider": "openai", "model": "d", "api_key": "k"}}):
        flow._open_entry_detail("deepseek")
    screen, cb = host.push_screen.call_args.args[:2]
    values = [v for _, v in screen._options]
    assert "use" in values and values.index("use") < values.index("test"), "「用这个模型」排在测试前面"
    with patch("neonrp.tui.settings_flow.list_configured_entries", return_value=_entries()):
        cb("use")
    host._cmd_auth_set_model.assert_called_once_with(["model", "deepseek"])


def test_launcher_host_has_no_use_action():
    flow, host = _flow(None, can_switch=False)
    with patch("neonrp.tui.settings_flow._load_user_config_models", return_value={"deepseek": {"provider": "openai", "model": "d"}}):
        flow._open_entry_detail("deepseek")
    values = [v for _, v in host.push_screen.call_args.args[0]._options]
    assert "use" not in values
