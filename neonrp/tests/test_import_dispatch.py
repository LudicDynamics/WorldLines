"""`/import <文件>` —— 世界与角色合并成一个入口。

用户手里只有「一个文件」。旧设计要他先替我们判断它属于哪一类:世界包走
`/load-world`,角色卡走 `/import sillytavern-card`。合并之后,判断是我们的活。

于是这套测试的重心不是「能不能导入」(那是 `load_world_zip` /
`import_card_to_library` 各自的测试在管),而是**分派对不对** —— 分错类的
代价不是报个错,是把一个世界当角色灌进库里。
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from neonrp.tui.app import NeonRPApp
from neonrp.tui.commands import COMMANDS, parse_command, validate_command


# ── 分类:纯函数,不需要 app ────────────────────────────────────────────

def _write(p: Path, data) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        p.write_bytes(data)
    else:
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def test_zip_is_a_world(tmp_path):
    z = tmp_path / "cat-isle.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("cat-isle/game/meta/game-start.json", "{}")
    assert NeonRPApp._classify_import(z) == "world"


def test_png_is_a_card(tmp_path):
    assert NeonRPApp._classify_import(_write(tmp_path / "hero.png", b"\x89PNG")) == "card"


def test_tavern_json_is_a_card(tmp_path):
    """酒馆卡也可以是 .json —— 靠字段认,不能靠后缀。"""
    card = _write(tmp_path / "hero.json", {"name": "罗文", "description": "铁匠"})
    assert NeonRPApp._classify_import(card) == "card"


def test_v2_spec_card_is_a_card(tmp_path):
    """v2 卡把内容裹在 `data` 里,顶层没有 name。"""
    card = _write(tmp_path / "v2.json", {"spec": "chara_card_v2", "data": {"name": "罗文"}})
    assert NeonRPApp._classify_import(card) == "card"


def test_unrelated_json_is_not_a_card(tmp_path):
    """随手一个配置 JSON 不该被当成角色卡 —— 宁可说认不出,也不要猜错。"""
    cfg = _write(tmp_path / "settings.json", {"provider": "deepseek", "temperature": 0.7})
    assert NeonRPApp._classify_import(cfg) == "unknown"


def test_broken_json_does_not_crash(tmp_path):
    """半截文件(下载中断)只能是「认不出」,不能是异常。"""
    bad = tmp_path / "half.json"
    bad.write_text('{"name": "罗', encoding="utf-8")
    assert NeonRPApp._classify_import(bad) == "unknown"


def test_unknown_suffix_is_unknown(tmp_path):
    assert NeonRPApp._classify_import(_write(tmp_path / "notes.txt", b"hi")) == "unknown"


# ── 路由:一个入口,两条去向 ──────────────────────────────────────────

class _View:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def write(self, text: str) -> None:
        self.lines.append(text)

    @property
    def text(self) -> str:
        return "".join(self.lines)


@pytest.fixture
def app_with_view(tmp_path, monkeypatch):
    app = NeonRPApp.__new__(NeonRPApp)
    app.root = tmp_path
    view = _View()
    monkeypatch.setattr(NeonRPApp, "query_one", lambda self, *a, **k: view)
    return app, view


def test_zip_goes_to_the_world_importer(app_with_view, tmp_path):
    app, view = app_with_view
    z = tmp_path / "w.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("w/x", "")

    with patch("neonrp.core.world_export.load_world_zip") as load_world, patch(
        "neonrp.core.importers.card_to_soul.import_card_to_library"
    ) as load_card:
        load_world.return_value = tmp_path / "worlds" / "w"
        app._cmd_import([str(z)])

    load_world.assert_called_once()
    load_card.assert_not_called(), "世界包不该走角色管线"


def test_card_goes_to_the_soul_importer(app_with_view, tmp_path):
    app, view = app_with_view
    card = _write(tmp_path / "hero.png", b"\x89PNG")

    with patch("neonrp.core.world_export.load_world_zip") as load_world, patch(
        "neonrp.core.importers.card_to_soul.import_card_to_library"
    ) as load_card, patch("neonrp.core.config.load_config"), patch(
        "neonrp.core.config.resolve_provider"
    ), patch("neonrp.core.llm.get_adapter_from_config"):
        load_card.return_value = tmp_path / "souls" / "rowan-sis00001"
        app._cmd_import([str(card)])

    load_card.assert_called_once()
    load_world.assert_not_called(), "角色卡不该走世界管线"


def test_card_import_produces_a_full_soul_not_a_flat_entity(app_with_view, tmp_path):
    """走 `card_to_soul` 而不是老的 `import_sillytavern_card`。

    老路产出的是 `game/character/` 下一个扁平 JSON —— 那不是能独立跑起来的
    角色,迎不进世界。合并入口时顺手把这条纠正了,所以要钉住。
    """
    app, view = app_with_view
    card = _write(tmp_path / "hero.png", b"\x89PNG")
    with patch(
        "neonrp.core.importers.card_to_soul.import_card_to_library"
    ) as load_card, patch("neonrp.core.config.load_config"), patch(
        "neonrp.core.config.resolve_provider"
    ), patch("neonrp.core.llm.get_adapter_from_config"):
        load_card.return_value = tmp_path / "souls" / "rowan-sis00001"
        app._cmd_import([str(card)])

    # 老路是 `import_sillytavern_card`(扁平实体);走对了就该报出 soul id。
    assert "rowan" in view.text
    assert "/cast" in view.text, "导完要告诉他下一步怎么把角色请进世界"


def test_missing_file_says_so(app_with_view):
    app, view = app_with_view
    app._cmd_import(["nope.zip"])
    assert "找不到文件" in view.text


def test_unknown_kind_names_what_we_accept(app_with_view, tmp_path):
    """认不出的时候要说清楚我们认得什么 —— 「未知格式」帮不了任何人。"""
    app, view = app_with_view
    app._cmd_import([str(_write(tmp_path / "a.txt", b"hi"))])
    assert ".zip" in view.text and "PNG" in view.text


def test_bare_import_shows_usage(app_with_view):
    app, view = app_with_view
    app._cmd_import([])
    assert "/import" in view.text


def test_relative_path_resolves_against_the_project(app_with_view, tmp_path):
    """在世界目录里敲 `/import hero.png` 该找得到 —— 不然只能贴绝对路径。"""
    app, view = app_with_view
    _write(tmp_path / "hero.png", b"\x89PNG")
    with patch(
        "neonrp.core.importers.card_to_soul.import_card_to_library"
    ) as load_card, patch("neonrp.core.config.load_config"), patch(
        "neonrp.core.config.resolve_provider"
    ), patch("neonrp.core.llm.get_adapter_from_config"):
        load_card.return_value = tmp_path / "souls" / "x-sis00001"
        app._cmd_import(["hero.png"])
    load_card.assert_called_once()


def test_legacy_subcommand_still_opens(app_with_view, tmp_path):
    """`--import-card` 排出的启动命令仍是 `/import sillytavern-card <文件>`。

    子命令不再露出,但排队里那个老形状不能因此打不开 —— 撤露出和断能力是
    两件事(与 legacy_commands 的归档纪律同一条)。
    """
    app, view = app_with_view
    card = _write(tmp_path / "hero.png", b"\x89PNG")
    with patch(
        "neonrp.core.importers.card_to_soul.import_card_to_library"
    ) as load_card, patch("neonrp.core.config.load_config"), patch(
        "neonrp.core.config.resolve_provider"
    ), patch("neonrp.core.llm.get_adapter_from_config"):
        load_card.return_value = tmp_path / "souls" / "x-sis00001"
        app._cmd_import(["sillytavern-card", str(card)])
    load_card.assert_called_once()


def test_import_failure_is_reported_not_raised(app_with_view, tmp_path):
    """坏包要说人话,不能把 traceback 糊在对话里。"""
    app, view = app_with_view
    z = tmp_path / "broken.zip"
    z.write_bytes(b"not a zip")
    app._cmd_import([str(z)])
    assert "失败" in view.text


# ── 命令面 ────────────────────────────────────────────────────────────

def test_import_is_one_entry_not_two():
    """合并的意思是**一个**入口:子命令不再露出,分派由内容决定。"""
    assert "subcommands" not in COMMANDS["import"]
    assert COMMANDS["import"]["args_hint"] == "<文件>"


def test_import_is_local_not_cli_passthrough():
    """透传给 CLI 就只认得酒馆卡子命令 —— 分派必须在 TUI 这侧。"""
    from neonrp.tui.app import CLI_FORWARD_COMMANDS, LOCAL_SLASH_COMMANDS

    assert "import" in LOCAL_SLASH_COMMANDS
    assert "import" not in CLI_FORWARD_COMMANDS


def test_import_still_validates():
    assert validate_command(parse_command("/import hero.png")) is None
