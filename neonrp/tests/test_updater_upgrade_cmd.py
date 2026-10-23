"""Regression: uv 安装的升级命令必须打破收据钉版。

桌面壳引导装引擎用 `uv tool install --force worldlines==<壳版本>`,收据里
留下 ==pin;`uv tool upgrade` 尊重这个约束 → 永远无操作。用户每次启动被
问"更新到 x?",答应了也停在原版本(0.3.1 死循环,Windows 实测)。
`install --force` 重新解析最新并改写收据。
"""

from neonrp.core import updater


def test_uv_upgrade_command_breaks_receipt_pin(monkeypatch):
    monkeypatch.setattr(updater, "_install_manager", lambda: "uv")
    monkeypatch.setattr(updater, "_find_uv_binary", lambda: "/fake/uv")
    cmd = updater.build_upgrade_command("worldlines")
    assert cmd == ["/fake/uv", "tool", "install", "--force", "worldlines"]
    assert "upgrade" not in cmd


def test_unknown_layout_falls_back_to_uv_force_install(monkeypatch):
    monkeypatch.setattr(updater, "_install_manager", lambda: "unknown")
    monkeypatch.setattr(updater, "_find_uv_binary", lambda: "/fake/uv")
    cmd = updater.build_upgrade_command("worldlines")
    assert cmd == ["/fake/uv", "tool", "install", "--force", "worldlines"]
