"""Dashboard second row:「选完 LLM 直接进 build 或 play」.

世界库 = 创作 / 上传 / 一览游玩;角色库 = 对话 / 创作 / 上传 / 一览游玩。
创作 → 起名 → 选模型 → 直接进 build(空白世界的工坊,第一句话是给 agent
的);一览 → 卡片 → 选模型 → 直接进 play(终端),不再问「在哪里玩」,也不再
过分身/带谁进来两屏。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from neonrp.tui.app import TextInputScreen, WorldLinesLauncherApp
from neonrp.tui.card_grid import CardGridScreen, CardItem


@pytest.fixture
def app():
    with patch("neonrp.worlds.list_saved_games", return_value=[]), patch(
        "neonrp.worlds.list_worlds", return_value=[{"id": "stone-ford", "display_name": "石津镇", "desc": "…"}]
    ), patch("neonrp.presets.list_presets", return_value=[{"id": "qwen", "display": "Qwen"}]), patch(
        "neonrp.players.list_players", return_value=[]
    ):
        a = WorldLinesLauncherApp()
    a.locale = "zh"
    a.push_screen = MagicMock()
    a.exit = MagicMock()
    a.notify = MagicMock()
    return a


def _pick_preset(app: WorldLinesLauncherApp, preset_id: str = "qwen") -> None:
    """The preset picker was pushed; answer it."""
    screen, cb = app.push_screen.call_args.args[:2]
    assert screen.__class__.__name__ == "ChoicePickerScreen"
    cb(preset_id)


# ── 创作 ─────────────────────────────────────────────────────────────


def test_create_world_makes_an_empty_shell_then_model_then_lands_in_build(app, tmp_path):
    """「点创建新世界会提示要选……其实就是建立一个空壳然后进入」——
    不问名字,直接建「新世界」,选完模型进工坊。"""
    app._run_menu_action("wl-world-create")
    screen = app.push_screen.call_args.args[0]
    assert not isinstance(screen, TextInputScreen), "不再问名字"
    assert screen.__class__.__name__ == "ChoicePickerScreen", "直接是模型选单"
    assert app._pending_create == ("world", "新世界")
    with patch("neonrp.worlds.create_blank_world", return_value=tmp_path / "新世界-2") as cbw:
        _pick_preset(app)
    cbw.assert_called_once_with("新世界", model_ref="qwen")

    sel = app.launch_selection
    assert sel is not None and sel.mode == "continue"
    assert sel.runtime_mode == "build"
    assert sel.game_path == tmp_path / "新世界-2"
    assert sel.render_surface == "tui"
    assert sel.startup_commands and "新世界" in sel.startup_commands[0]
    assert not sel.startup_commands[0].startswith("/")
    app.exit.assert_called_once()


def test_create_soul_opens_the_characters_own_folder_not_a_world(app, tmp_path):
    """角色构建 = souls/<名字>/ 里开工坊,不是造一个世界。"""
    app._run_menu_action("wl-soul-create")
    got_name = app.push_screen.call_args.args[1]
    got_name("罗文")
    with patch("neonrp.core.souls.create_soul_workshop", return_value=tmp_path / "lib" / "罗文") as csw, patch(
        "neonrp.worlds.create_blank_world", side_effect=AssertionError("must not make a world")
    ):
        _pick_preset(app)
    csw.assert_called_once_with("罗文", model_ref="qwen")
    sel = app.launch_selection
    assert sel.runtime_mode == "build" and sel.game_path == tmp_path / "lib" / "罗文"
    assert "罗文" in sel.startup_commands[0] and "soul-authoring" in sel.startup_commands[0]


def test_create_soul_with_empty_name_does_nothing(app):
    app._run_menu_action("wl-soul-create")
    got_name = app.push_screen.call_args.args[1]
    app.push_screen.reset_mock()
    got_name("   ")
    app.push_screen.assert_not_called()
    assert app._pending_create is None


def test_create_failure_is_reported_not_raised(app):
    app._run_menu_action("wl-world-create")
    with patch("neonrp.worlds.create_blank_world", side_effect=RuntimeError("no template")):
        _pick_preset(app)
    assert app.launch_selection is None
    app.notify.assert_called_once()
    assert "no template" in app.notify.call_args.args[0]
    app.exit.assert_not_called()


# ── 一览游玩 ──────────────────────────────────────────────────────────


def test_browse_worlds_shows_cards_then_model_then_plays_in_tui(app):
    with patch("neonrp.worlds.list_worlds", return_value=[{"id": "stone-ford", "display_name": "石津镇", "desc": "…"}]):
        app._run_menu_action("wl-world-browse")
    screen, picked = app.push_screen.call_args.args[:2]
    assert isinstance(screen, CardGridScreen)
    assert [c.key for c in screen._items] == ["stone-ford"]

    picked("stone-ford")
    assert app._selected_world_id == "stone-ford" and app._direct_surface == "tui"
    _pick_preset(app)
    sel = app.launch_selection
    assert sel is not None and sel.mode == "new"
    assert sel.world_id == "stone-ford"
    assert sel.runtime_mode == "play"
    assert sel.render_surface == "tui"
    assert sel.player_profile is None and sel.bring_in_souls == ()
    # No「在哪里玩」picker and no casting screen were pushed after the model.
    assert app.push_screen.call_count == 2
    app.exit.assert_called_once()


def test_browse_souls_talks_to_the_picked_one(app):
    souls = [{"sid": "rowan", "display_name": "罗文", "version": "1.0", "path": None}]
    with patch("neonrp.core.souls.list_souls", return_value=souls):
        app._run_menu_action("wl-soul-browse")
    screen, picked = app.push_screen.call_args.args[:2]
    assert isinstance(screen, CardGridScreen)
    assert screen._items[0].title == "罗文"
    picked("rowan")
    _pick_preset(app)
    sel = app.launch_selection
    assert sel.world_id == "soul-talk"
    assert sel.bring_in_souls == ("rowan",)
    assert sel.render_surface == "tui" and sel.runtime_mode == "play"


def test_esc_on_cards_goes_home(app):
    with patch("neonrp.worlds.list_worlds", return_value=[]):
        app._run_menu_action("wl-world-browse")
    picked = app.push_screen.call_args.args[1]
    app._focus_menu_button = MagicMock()
    picked(None)
    app._focus_menu_button.assert_called_once()
    assert app.launch_selection is None


def test_esc_on_model_in_a_direct_flow_goes_home_not_to_casting(app):
    with patch("neonrp.worlds.list_worlds", return_value=[{"id": "w", "display_name": "W", "desc": ""}]):
        app._run_menu_action("wl-world-browse")
    app.push_screen.call_args.args[1]("w")
    app._step_choose_player = MagicMock()
    app._focus_menu_button = MagicMock()
    _pick_preset(app, None)
    app._step_choose_player.assert_not_called()
    app._focus_menu_button.assert_called_once()
    assert app._direct_surface is None and app._pending_create is None


def test_direct_state_never_leaks_into_the_next_tile(app):
    app._direct_surface = "tui"
    app._pending_create = ("world", "x")
    app._start_new_flow = MagicMock()
    app._run_menu_action("wl-new")
    assert app._direct_surface is None and app._pending_create is None


def test_world_cards_carry_cover_pictures(app, tmp_path):
    src = tmp_path / "w"
    (src / "assets").mkdir(parents=True)
    (src / "assets" / "cover.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    app._worlds = [{"id": "w", "display_name": "W", "desc": "d"}]
    app._world_source_dir = lambda wid: src
    items = app._world_card_items()
    assert items == [CardItem(key="w", title="W", caption="d", image=src / "assets" / "cover.png")]


def test_world_without_pictures_still_gets_a_card(app):
    app._worlds = [{"id": "w", "display_name": "W", "desc": ""}]
    app._world_source_dir = lambda wid: None
    assert app._world_card_items()[0].image is None


# ── CLI:build 模式的 continue ─────────────────────────────────────────


def test_cli_continue_honours_build_mode_and_the_brief(tmp_path, monkeypatch):
    import neonrp.cli as cli

    run = tmp_path / "w"
    (run / ".neonrp").mkdir(parents=True)
    launched = {}
    monkeypatch.setattr(cli, "_launch_surface", lambda root, surface, **kw: launched.update(root=root, surface=surface, **kw))
    monkeypatch.setattr(cli, "_setup_logging", lambda *_a, **_k: None)
    monkeypatch.setattr("neonrp.presets.build_config_dict", lambda ref: {"llm": {"model_ref": ref}, "models": {ref: {"provider": "openai"}}})
    monkeypatch.setattr("neonrp.core.import_plan.resume_startup_command", lambda *_a: None)
    # The continue path chdirs into the run; let monkeypatch own the cwd so
    # teardown restores the REAL original (a manual restore here once left
    # the suite sitting in a tmp dir and broke 36 relative-path tests).
    monkeypatch.chdir(tmp_path)
    cli._worldlines_continue_game_with_preset(run, "qwen", "tui", runtime_mode="build", startup_commands=["这个世界叫「猫岛」"])
    assert launched["mode"] == "build"
    assert launched["startup_commands"] == ["这个世界叫「猫岛」"]
    assert launched["surface"] == "tui"


def test_cli_continue_default_is_still_play(tmp_path, monkeypatch):
    import neonrp.cli as cli

    run = tmp_path / "w"
    (run / ".neonrp").mkdir(parents=True)
    launched = {}
    monkeypatch.setattr(cli, "_launch_surface", lambda root, surface, **kw: launched.update(root=root, surface=surface, **kw))
    monkeypatch.setattr(cli, "_setup_logging", lambda *_a, **_k: None)
    monkeypatch.setattr("neonrp.presets.build_config_dict", lambda ref: {"llm": {"model_ref": ref}, "models": {ref: {"provider": "openai"}}})
    monkeypatch.setattr("neonrp.core.import_plan.resume_startup_command", lambda *_a: None)
    monkeypatch.chdir(tmp_path)
    cli._worldlines_continue_game_with_preset(run, "qwen", "tui")
    assert launched["mode"] == "play"
    assert launched["startup_commands"] is None


# ── 卡片屏本身 ────────────────────────────────────────────────────────


def test_card_grid_moves_and_picks():
    import asyncio

    from textual.app import App

    class T(App):
        result = "unset"

        def on_mount(self):
            items = [CardItem(key=f"k{i}", title=f"T{i}", caption="c") for i in range(5)]
            self.push_screen(CardGridScreen("t", items, hint="h"), lambda v: setattr(self, "result", v))

    async def run():
        app = T()
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await pilot.press("right", "down")  # +1, +3 → k4
            await pilot.press("enter")
            await pilot.pause()
            return app.result

    assert asyncio.run(run()) == "k4"


def test_card_grid_esc_returns_none():
    import asyncio

    from textual.app import App

    class T(App):
        result = "unset"

        def on_mount(self):
            self.push_screen(CardGridScreen("t", [CardItem(key="a", title="A")]), lambda v: setattr(self, "result", v))

    async def run():
        app = T()
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            return app.result

    assert asyncio.run(run()) is None


# ── 兜底 ─────────────────────────────────────────────────────────────


def test_model_picked_with_no_world_stays_in_the_launcher(app):
    """launcher 退出后 CLI 打「Nothing to launch — launcher
    bug」。不管哪条路把人带到了没有世界的模型选单,都不能带着空选择退出。"""
    app._reset_direct_state()
    app._step_choose_preset(False)
    _pick_preset(app)
    assert app.launch_selection is None
    app.exit.assert_not_called()
    app.notify.assert_called_once()


def test_model_picker_focuses_the_users_default_not_the_first_entry(app):
    app._presets = [{"id": "openai", "display": "OpenAI"}, {"id": "qwen", "display": "Qwen"}]
    app._selected_world_id = "stone-ford"
    with patch("neonrp.presets.default_model_ref", return_value="qwen"):
        app._step_choose_preset(False)
    screen = app.push_screen.call_args.args[0]
    focus = getattr(screen, "_initial_focus", None) or getattr(screen, "initial_focus", None)
    assert focus == "qwen"


def test_model_picker_focus_falls_back_when_default_is_not_listed(app):
    app._presets = [{"id": "openai", "display": "OpenAI"}]
    app._selected_world_id = "stone-ford"
    with patch("neonrp.presets.default_model_ref", return_value="qwen"):
        app._step_choose_preset(False)
    screen = app.push_screen.call_args.args[0]
    focus = getattr(screen, "_initial_focus", None) or getattr(screen, "initial_focus", None)
    assert focus is None


def test_ordinary_new_game_no_longer_asks_where_to_play(app):
    """Not just the direct flows: the classic 新游戏 path also lands in the
    terminal straight after the model (web is a CLI path, not a TUI option)."""
    app._selected_world_id = "stone-ford"
    app._step_choose_preset(False)
    _pick_preset(app)
    sel = app.launch_selection
    assert sel is not None and sel.render_surface == "tui" and sel.world_id == "stone-ford"
    assert app.push_screen.call_count == 1, "模型之后没有第二屏"


def test_mouse_clicking_a_model_row_does_not_wipe_the_create_flow(app, tmp_path):
    """真根因:模型选单的行是 Button,鼠标点它时
    Button.Pressed 冒泡到 launcher 的 on_button_pressed,那里把 _pending_create
    清了,finalize 就成了「还没选世界」/ 以前的「Nothing to launch」。"""
    app._run_menu_action("wl-soul-create")
    app.push_screen.call_args.args[1]("罗文")
    assert app._pending_create == ("soul", "罗文")
    ev = MagicMock()
    ev.button.id = "choice-opt-2"  # a row of the model picker
    app.on_button_pressed(ev)  # bubbles up before the modal handles it
    assert app._pending_create == ("soul", "罗文"), "非首屏按钮不能碰状态"
    with patch("neonrp.worlds.create_blank_world", return_value=tmp_path / "罗文-工坊"):
        _pick_preset(app)
    assert app.launch_selection is not None and app.launch_selection.runtime_mode == "build"
    app.notify.assert_not_called()


def test_mouse_clicking_a_model_row_keeps_the_direct_play_flow(app):
    with patch("neonrp.worlds.list_worlds", return_value=[{"id": "w", "display_name": "W", "desc": ""}]):
        app._run_menu_action("wl-world-browse")
    app.push_screen.call_args.args[1]("w")
    ev = MagicMock()
    ev.button.id = "choice-opt-0"
    app.on_button_pressed(ev)
    assert app._direct_surface == "tui"
    _pick_preset(app)
    assert app.launch_selection is not None and app.launch_selection.world_id == "w"


# ── TODO #9 · 角色工坊的回门 ────────────────────────────────────────


def test_b_on_a_character_card_reopens_its_workshop(app, tmp_path):
    lib = tmp_path / "lib" / "luowen"
    lib.mkdir(parents=True)
    (lib / "soul.json").write_text('{"sid": "luowen", "name": "Luowen"}', encoding="utf-8")
    with patch("neonrp.core.souls.list_souls", return_value=[{"sid": "luowen", "display_name": "罗文", "version": "1.0", "path": lib}]):
        app._run_menu_action("wl-soul-browse")
    picked = app.push_screen.call_args.args[1]
    with patch("neonrp.core.placement.resolve_soul_dir", return_value=lib):
        picked("build::luowen")
    assert app._pending_workshop == (lib, "luowen")
    with patch("neonrp.worlds.seed_run_model", return_value="qwen"):
        _pick_preset(app)
    sel = app.launch_selection
    assert sel is not None and sel.mode == "continue" and sel.runtime_mode == "build"
    assert sel.game_path == lib and "luowen" in sel.startup_commands[0]
    assert (lib / ".neonrp" / "manifest.json").is_file(), "旧工坊补上 manifest"


def test_esc_on_model_clears_a_pending_workshop(app, tmp_path):
    app._pending_workshop = (tmp_path, "x")
    app._selected_world_id = None
    app._step_choose_preset(False)
    app._focus_menu_button = MagicMock()
    _pick_preset(app, None)
    assert app._pending_workshop is None


def test_card_grid_b_returns_a_build_key():
    import asyncio

    from textual.app import App

    class T(App):
        result = "unset"

        def on_mount(self):
            self.push_screen(CardGridScreen("t", [CardItem(key="luowen", title="罗文")]), lambda v: setattr(self, "result", v))

    async def run():
        a = T()
        async with a.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await pilot.press("b")
            await pilot.pause()
            return a.result

    assert asyncio.run(run()) == "build::luowen"
