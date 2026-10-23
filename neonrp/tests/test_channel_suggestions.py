"""`@` / `#` get the same suggestion panel as `/`."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from neonrp.tui.app import NeonRPApp


def _app(root: Path, mode: str = "play") -> NeonRPApp:
    app = NeonRPApp.__new__(NeonRPApp)
    app.root = root
    app.mode = mode
    app.ui_locale = "zh"
    return app


def _world(root: Path):
    for sid, iid, name in (("rowan", "si-1", "罗文"), ("elena", "si-2", "艾琳娜")):
        d = root / "souls" / f"{sid}-{iid}"
        d.mkdir(parents=True)
        (d / "soul.json").write_text(json.dumps({"sid": sid, "name": sid.title(), "name_local": name}), encoding="utf-8")
    pt = MagicMock(souls=[MagicMock(sid="rowan", instance_id="si-1"), MagicMock(sid="elena", instance_id="si-2")])
    return pt


def test_at_lists_world_souls_present_first(tmp_path):
    pt = _world(tmp_path)
    app = _app(tmp_path)
    with patch("neonrp.core.playthrough.read_playthrough", return_value=pt), patch(
        "neonrp.core.light_chat.resolve_room_souls", return_value=[("si-2", tmp_path / "souls" / "elena-si-2", "艾琳娜")]
    ):
        rows = app._compute_channel_suggestions("@")
    assert [c for _, c in rows] == ["@艾琳娜", "@罗文"], "在场的排前面"
    assert "在场" in rows[0][0] and "在场" not in rows[1][0]


def test_at_filters_by_name_or_sid_and_stops_once_addressing(tmp_path):
    pt = _world(tmp_path)
    app = _app(tmp_path)
    with patch("neonrp.core.playthrough.read_playthrough", return_value=pt), patch(
        "neonrp.core.light_chat.resolve_room_souls", return_value=[]
    ):
        assert [c for _, c in app._compute_channel_suggestions("@罗")] == ["@罗文"]
        assert [c for _, c in app._compute_channel_suggestions("@ro")] == ["@罗文"]
        assert [c for _, c in app._compute_channel_suggestions("＠艾")] == ["@艾琳娜"]
        assert app._compute_channel_suggestions("@罗文 你好") == []
        assert app._compute_channel_suggestions("@zzz") == []


def test_hash_shows_its_two_forms_and_nothing_once_typing(tmp_path):
    app = _app(tmp_path)
    rows = app._compute_channel_suggestions("#")
    assert [c for _, c in rows] == ["#", "# "]
    assert app._compute_channel_suggestions("# 大家好") == []


def test_channels_are_play_only(tmp_path):
    _world(tmp_path)
    assert _app(tmp_path, "build")._compute_channel_suggestions("@") == []
    assert _app(tmp_path, "build")._compute_channel_suggestions("#") == []


def test_no_roster_means_no_rows(tmp_path):
    app = _app(tmp_path)
    with patch("neonrp.core.playthrough.read_playthrough", return_value=None):
        assert app._compute_channel_suggestions("@") == []


def test_panel_is_fed_by_channel_rows(tmp_path):
    pt = _world(tmp_path)
    app = _app(tmp_path)
    app._slash_suggestions = []
    app._slash_selected_index = 0
    app._MAX_VISIBLE_SLASH_SUGGESTIONS = 8
    panel = MagicMock()
    app.query_one = MagicMock(return_value=panel)
    with patch("neonrp.core.playthrough.read_playthrough", return_value=pt), patch(
        "neonrp.core.light_chat.resolve_room_souls", return_value=[]
    ):
        app._update_slash_suggestions("@")
    assert sorted(c for _, c in app._slash_suggestions) == ["@罗文", "@艾琳娜"]
    panel.add_class.assert_called_with("visible")
    assert app._get_selected_slash_completion() in ("@罗文", "@艾琳娜")


# ── /open /cast /remove /reset /init 的参数补全 ─────────────────────


def _saves():
    return [{"dir_name": "cat-isle-20260901-000000", "display_name": "猫岛", "mtime_display": "09/01 10:00", "started": True}]


def _worlds():
    return [{"id": "stone-ford", "display_name": "石津镇", "desc": ""}]


def test_open_suggests_saves_and_worlds(tmp_path):
    app = _app(tmp_path)
    with patch("neonrp.worlds.list_saved_games", return_value=_saves()), patch("neonrp.worlds.list_worlds", return_value=_worlds()):
        rows = app._compute_slash_suggestions("/open ")
        assert [c for _, c in rows] == ["/open cat-isle-20260901-000000", "/open stone-ford"]
        assert "存档" in rows[0][0] and "世界" in rows[1][0]
        assert [c for _, c in app._compute_slash_suggestions("/open sto")] == ["/open stone-ford"]
        assert [c for _, c in app._compute_slash_suggestions("/open 猫")] == ["/open cat-isle-20260901-000000"], "按显示名也能搜"


def test_cast_suggests_library_souls_and_marks_present(tmp_path):
    pt = _world(tmp_path)
    app = _app(tmp_path)
    (tmp_path / ".neonrp" / "soul-drafts" / "ghost").mkdir(parents=True)
    with patch("neonrp.core.souls.list_souls", return_value=[{"sid": "rowan", "display_name": "罗文"}, {"sid": "mira", "display_name": "米拉"}]), patch(
        "neonrp.core.playthrough.read_playthrough", return_value=pt
    ), patch("neonrp.core.light_chat.resolve_room_souls", return_value=[]):
        rows = app._compute_slash_suggestions("/cast ")
    labels = dict((c, lab) for lab, c in rows)
    assert set(labels) == {"/cast rowan", "/cast mira", "/cast ghost"}
    assert "已在场" in labels["/cast rowan"] and "已在场" not in labels["/cast mira"]
    assert "草稿" in labels["/cast ghost"]


def test_remove_and_reset_suggest_world_souls(tmp_path):
    pt = _world(tmp_path)
    app = _app(tmp_path)
    with patch("neonrp.core.playthrough.read_playthrough", return_value=pt), patch(
        "neonrp.core.light_chat.resolve_room_souls", return_value=[("si-1", tmp_path / "souls" / "rowan-si-1", "罗文")]
    ):
        rows = app._compute_slash_suggestions("/remove ")
        assert [c for _, c in rows] == ["/remove rowan", "/remove elena"]
        assert "在场" in rows[0][0]
        assert [c for _, c in app._compute_slash_suggestions("/reset el")] == ["/reset elena"]


def test_init_shows_existing_names_as_a_warning(tmp_path):
    app = _app(tmp_path)
    with patch("neonrp.worlds.list_worlds", return_value=_worlds()):
        rows = app._compute_slash_suggestions("/init ")
    assert rows and "已有" in rows[0][0]


def test_argument_rows_are_cached_briefly(tmp_path):
    app = _app(tmp_path)
    calls = []
    with patch("neonrp.worlds.list_saved_games", side_effect=lambda: calls.append(1) or _saves()), patch("neonrp.worlds.list_worlds", return_value=_worlds()):
        app._compute_slash_suggestions("/open ")
        app._compute_slash_suggestions("/open c")
        app._compute_slash_suggestions("/open ca")
    assert len(calls) == 1, "一次扫描,三次按键"


def test_unrelated_commands_get_no_dynamic_rows(tmp_path):
    app = _app(tmp_path)
    assert app._compute_slash_suggestions("/save ") == []


def test_suggestion_notes_follow_the_ui_language(tmp_path):
    """换语言之后 open/cast/init 的 suggestion 还是中文。"""
    app = _app(tmp_path)
    app.ui_locale = "en"
    with patch("neonrp.worlds.list_saved_games", return_value=_saves()), patch("neonrp.worlds.list_worlds", return_value=_worlds()):
        rows = app._compute_slash_suggestions("/open ")
    assert "save" in rows[0][0] and "存档" not in rows[0][0]
    assert "world" in rows[1][0]
    with patch("neonrp.worlds.list_worlds", return_value=_worlds()):
        assert "exists" in app._compute_slash_suggestions("/init ")[0][0]
    assert "who is here" in app._compute_channel_suggestions("#")[0][0]
    app.ui_locale = "ja"
    with patch("neonrp.worlds.list_saved_games", return_value=_saves()), patch("neonrp.worlds.list_worlds", return_value=_worlds()):
        assert "セーブ" in app._compute_slash_suggestions("/open ")[0][0], "换语言后缓存也要跟着换"


# ── 退役命令按前缀出现;内置命令说明跟语言 ────────────────────────


def test_retired_commands_answer_to_a_prefix_but_not_the_bare_slash(tmp_path):
    from neonrp.tui import commands as C

    # sample: /mcp (kept among the retired; /auth itself was deleted)
    assert "mcp" not in C.get_command_suggestions("")
    assert "mcp" in C.get_command_suggestions("mc")
    assert C.command_kind("mcp") == "legacy"
    app = _app(tmp_path)
    app.ui_locale = "en"
    rows = app._format_command_suggestions(["mcp"])
    assert rows[0][1] == "/mcp" and "retired" in rows[0][0] and rows[0][0].startswith("[dim]")


def test_builtin_help_follows_the_ui_language(tmp_path):
    from neonrp.tui import commands as C

    app = _app(tmp_path)
    app.ui_locale = "en"
    rows = dict((c, lab) for lab, c in app._format_command_suggestions(["open", "cast", "init"]))
    assert "save" in rows["/open"] and "存档" not in rows["/open"]
    assert "NEW run" in rows["/init"]
    assert "[world|save]" in C.get_command_args_hint("open", locale="en")
    assert "存档" in C.format_help("zh") and "save" in C.format_help("en")


def test_slash_then_space_does_not_crash(tmp_path):
    """「点 / 然后打一个空格就会死机」— IndexError on parts[0]."""
    import asyncio

    from neonrp.tui.app import SlashCommandSuggester

    app = _app(tmp_path)
    for v in ("/ ", "/  ", "/\t"):
        rows = app._compute_slash_suggestions(v)
        assert rows and rows[0][1].startswith("/")
    sg = SlashCommandSuggester()
    assert asyncio.run(sg.get_suggestion("/ ")) is None
    assert asyncio.run(sg.get_suggestion("/ s")) is not None  # /status · /save · /settings


def test_load_suggests_this_runs_snapshots(tmp_path):
    """「/load 没有 suggestion」。"""
    app = _app(tmp_path)
    snaps = [{"save_id": "save_001", "name": "北门前", "created": "09/11 01:00", "branch": "main", "head_event": 12}, {"save_id": "save_002"}]
    with patch("neonrp.commands.save.list_loadable_save_snapshots", return_value=snaps), patch("neonrp.worlds.list_saved_games", return_value=[]):
        rows = app._compute_slash_suggestions("/load ")
        assert [c for _, c in rows] == ["/load save_001", "/load save_002"]
        assert "北门前" in rows[0][0]
        assert [c for _, c in app._compute_slash_suggestions("/load 002")] == ["/load save_002"]


def test_load_bare_offers_runs_then_snapshots_and_routes_each(tmp_path):
    """「.worldlines 里的 play 无法 load?」— /load 两层都认:
    存档(接着玩)在前,本局快照在后。"""
    from unittest.mock import MagicMock as _M

    app = _app(tmp_path)
    app.push_screen = _M()
    app._cmd_open = _M()
    app.query_one = lambda *a, **k: _M()
    saves = [{"dir_name": "cat-isle-20260901-000000", "display_name": "猫岛", "mtime_display": "09/01", "path": tmp_path / "x"}]
    snaps = [{"save_id": "save_001", "branch": "main", "head_event": 3, "created": "now"}]
    with patch("neonrp.worlds.list_saved_games", return_value=saves), patch("neonrp.commands.save.list_loadable_save_snapshots", return_value=snaps):
        app._cmd_load([])
    screen, cb = app.push_screen.call_args.args[:2]
    values = [v for _, v in screen._options]
    assert values.index("run::cat-isle-20260901-000000") < values.index("snap::save_001")
    cb("run::cat-isle-20260901-000000")
    app._cmd_open.assert_called_once_with(["cat-isle-20260901-000000"])
    with patch("neonrp.worlds.list_saved_games", return_value=saves):
        app._cmd_load(["cat-isle-20260901-000000"])
    assert app._cmd_open.call_count == 2, "/load <存档目录名> = /open <它>"


def test_load_suggestions_list_runs_before_snapshots(tmp_path):
    app = _app(tmp_path)
    saves = [{"dir_name": "cat-isle-20260901-000000", "display_name": "猫岛", "mtime_display": "09/01"}]
    with patch("neonrp.worlds.list_saved_games", return_value=saves), patch(
        "neonrp.commands.save.list_loadable_save_snapshots", return_value=[{"save_id": "save_001"}]
    ):
        rows = app._compute_slash_suggestions("/load ")
    assert [c for _, c in rows] == ["/load cat-isle-20260901-000000", "/load save_001"]
