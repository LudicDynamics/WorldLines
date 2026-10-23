"""任务 B3:游玩行动登记成 `/` 命令,和我们的工具命令用
颜色分开 —— play 绿 / build 红。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from neonrp.tui import commands as C
from neonrp.tui.app import NeonRPApp


@pytest.fixture(autouse=True)
def _clean_registry():
    C.clear_world_actions()
    yield
    C.clear_world_actions()


def _world(root: Path, actions) -> Path:
    (root / "game" / "meta").mkdir(parents=True, exist_ok=True)
    (root / "game" / "meta" / "actions.json").write_text(json.dumps({"actions": actions}, ensure_ascii=False), encoding="utf-8")
    return root


GOOD = [
    {"name": "go", "help": "走到某个地点", "args_hint": "<地点>", "prompt": "我走向{args}。"},
    {"name": "look", "help": "环顾四周", "prompt": "我环顾四周。"},
]


def test_load_reads_valid_entries_and_drops_bad_ones(tmp_path):
    root = _world(tmp_path, GOOD + [
        {"name": "open", "prompt": "x"},            # collides with a built-in → dropped
        {"name": "validate", "prompt": "x"},        # retired command → dropped
        {"name": "bad name", "prompt": "x"},        # not a slash token
        {"name": "noprompt"},                        # nothing to send
        "junk",
    ])
    acts = C.load_world_actions(root)
    assert sorted(acts) == ["go", "look"]
    assert acts["go"]["kind"] == "play" and acts["go"]["args_hint"] == "<地点>"


def test_missing_file_is_empty(tmp_path):
    assert C.load_world_actions(tmp_path) == {}


def test_registered_actions_join_suggestions_validation_and_help(tmp_path):
    C.register_world_actions(C.load_world_actions(_world(tmp_path, GOOD)))
    assert "go" in C.get_command_suggestions("") and C.get_command_suggestions("go") == ["go"]
    assert C.validate_command(C.parse_command("/go 北门")) is None
    assert C.command_kind("go") == "play" and C.command_kind("open") == "tool"
    help_text = C.format_help()
    assert "── 行动 · play ──" in help_text and "[green]/go[/]" in help_text
    assert "── 工具 · tools ──" in help_text


def test_render_prompt_fills_args_or_appends():
    C.register_world_actions({"go": {"prompt": "我走向{args}。"}, "look": {"prompt": "我环顾四周。"}})
    assert C.render_action_prompt("go", ["北门"]) == "我走向北门。"
    assert C.render_action_prompt("look", []) == "我环顾四周。"
    assert C.render_action_prompt("look", ["仔细"]) == "我环顾四周。 仔细"


def test_a_world_cannot_shadow_a_builtin():
    C.register_world_actions({"open": {"prompt": "x"}, "go": {"prompt": "y"}})
    assert "open" not in C.WORLD_ACTIONS and "go" in C.WORLD_ACTIONS


# ── app side ──────────────────────────────────────────────────────────


class _View:
    def __init__(self):
        self.lines = []

    def write(self, t):
        self.lines.append(t)

    def add_user_message(self, *_a, **_k):  # the command echo; not under test
        pass

    @property
    def text(self):
        return "".join(self.lines)


def _app(root: Path, mode: str = "play"):
    app = NeonRPApp.__new__(NeonRPApp)
    app.root = root
    app.mode = mode
    app.ui_locale = "zh"
    view = _View()
    app.query_one = lambda *a, **k: view
    app._apply_mode = MagicMock(side_effect=lambda m: setattr(app, "mode", m))
    app._submit_user_text = MagicMock()
    return app, view


def test_app_registers_the_worlds_actions_at_construction(tmp_path):
    _world(tmp_path, GOOD)
    NeonRPApp(root=tmp_path, mode="play")
    assert "go" in C.WORLD_ACTIONS


def test_running_an_action_sends_the_players_words(tmp_path):
    C.register_world_actions(C.load_world_actions(_world(tmp_path, GOOD)))
    app, view = _app(tmp_path, "play")
    app._handle_slash_command("/go 北门")
    app._submit_user_text.assert_called_once_with("我走向北门。")
    app._apply_mode.assert_not_called()
    assert "/go" in view.text


def test_action_from_build_switches_to_play_first(tmp_path):
    C.register_world_actions(C.load_world_actions(_world(tmp_path, GOOD)))
    app, view = _app(tmp_path, "build")
    app._handle_slash_command("/look")
    app._apply_mode.assert_called_once_with("play")
    app._submit_user_text.assert_called_once_with("我环顾四周。")
    assert "游玩行动" in view.text


def test_suggestions_colour_play_and_tool_differently(tmp_path):
    from neonrp.tui.app import mode_accent

    C.register_world_actions(C.load_world_actions(_world(tmp_path, GOOD)))
    app, _ = _app(tmp_path, "play")
    rows = dict(app._format_command_suggestions(["go", "open"]))
    go = next(k for k, v in rows.items() if v == "/go")
    op = next(k for k, v in rows.items() if v == "/open")
    assert f"[{mode_accent('play')}]/go" in go and "行动" in go
    assert f"[{mode_accent('build')}]/open" in op
    assert mode_accent("play") != mode_accent("build")


def test_blank_template_ships_default_actions():
    from neonrp.templates import __file__ as tpl

    path = Path(tpl).parent / "white-blank" / "game" / "meta" / "actions.json"
    acts = C.load_world_actions(path.parents[2])
    assert {"go", "talk", "look"} <= set(acts)
