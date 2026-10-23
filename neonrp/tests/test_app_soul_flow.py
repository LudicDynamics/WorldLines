"""Tests for the M16 launcher soul restore + soul-create flow.

Covers the re-enabled `wl-new-character` / `wl-soul-download` launcher
entries and the soul-create intent chain. Mirrors the launcher test
style in ``test_app.py``: construct ``WorldLinesLauncherApp`` with the
disk-listing functions patched out so no real ``~/.worldlines`` access
happens.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

# Import the submodule so `neonrp.core.souls` is resolvable as a patch
# target (app.py imports it lazily inside __init__/_step_choose_player).
import neonrp.core.souls  # noqa: F401
from neonrp.tui.app import WorldLinesLauncherApp


def _make_launcher() -> WorldLinesLauncherApp:
    """Build a launcher with all disk-listing side effects stubbed."""
    with patch("neonrp.worlds.list_saved_games", return_value=[]), patch(
        "neonrp.worlds.list_worlds", return_value=[]
    ), patch("neonrp.presets.list_presets", return_value=[]), patch(
        "neonrp.players.list_players", return_value=[]
    ), patch(
        "neonrp.core.souls.migrate_players_to_souls", return_value=[]
    ):
        app = WorldLinesLauncherApp()
    # Pin the UI locale so locale-dependent assertions (e.g.
    # list_souls(locale="en")) stay deterministic regardless of the
    # developer's ambient ~/.neonrp ui.language.
    app.locale = "en"
    return app


class TestLauncherSoulEntries:
    def test_launcher_imports_and_constructs(self) -> None:
        app = _make_launcher()
        assert isinstance(app, WorldLinesLauncherApp)
        assert app._custom_soul_intent is None

    def test_init_calls_migrate_players_to_souls(self) -> None:
        """Migration must run once (idempotently) on launcher init."""
        with patch("neonrp.worlds.list_saved_games", return_value=[]), patch(
            "neonrp.worlds.list_worlds", return_value=[]
        ), patch("neonrp.presets.list_presets", return_value=[]), patch(
            "neonrp.players.list_players", return_value=[]
        ), patch(
            "neonrp.core.souls.migrate_players_to_souls", return_value=[]
        ) as mig:
            WorldLinesLauncherApp()
        mig.assert_called_once_with()

class TestChoosePlayerSoulBacked:
    def test_choose_player_calls_list_souls(self) -> None:
        app = _make_launcher()
        app.push_screen = MagicMock()
        with patch(
            "neonrp.core.souls.list_souls", return_value=[]
        ) as list_souls:
            app._step_choose_player()
        list_souls.assert_called_once_with(locale="en")
        app.push_screen.assert_called_once()

    def test_choose_player_passes_souls_to_casting_screen(self) -> None:
        # The casting ② screen receives the soul library; it renders each
        # soul's display_name in both the avatar (RadioSet) and bring-in
        # (SelectionList) columns.
        from neonrp.tui.app import CastingScreen

        app = _make_launcher()
        app.push_screen = MagicMock()
        souls = [
            {
                "sid": "elena",
                "name": "Elena Voss",
                "name_local": "艾莲娜",
                "display_name": "Elena Voss (艾莲娜)",
                "dir_name": "elena-20260515-100000",
                "path": Path("/tmp/elena-20260515-100000"),
            }
        ]
        with patch("neonrp.core.souls.list_souls", return_value=souls):
            app._step_choose_player()

        screen = app.push_screen.call_args.args[0]
        assert isinstance(screen, CastingScreen)
        assert [s["display_name"] for s in screen._souls] == ["Elena Voss (艾莲娜)"]

    def test_choose_player_opens_casting_screen(self) -> None:
        # The player step now opens the casting ② screen: avatar (分身) +
        # bring-in NPCs on one screen. Creating a character is a library
        # action (jump), no longer an entry inside the player picker.
        from neonrp.tui.app import CastingScreen

        app = _make_launcher()
        app.push_screen = MagicMock()
        with patch("neonrp.core.souls.list_souls", return_value=[]):
            app._step_choose_player()
        screen = app.push_screen.call_args.args[0]
        assert isinstance(screen, CastingScreen)


class TestDashboardMenu:
    """首屏是仪表盘,但创建两格没回来。

    08-31 砍成四行时创建管线一并退役(裁决①);仪表盘回来只回盘面:
    PLAY 行 + 世界库/角色库两象限 + 设置/退出条。每一格都是「选世界」列表里
    同一个方法的快捷键,没有第二套实现。
    """

    def test_menu_is_the_dashboard(self) -> None:
        ids = WorldLinesLauncherApp._menu_button_ids()
        assert ids[:3] == ["wl-resume", "wl-continue", "wl-new"], "⚡ 接着上次是第一格,PLAY 行在最前"
        assert ids[-2:] == ["wl-settings", "wl-exit"], "设置/退出条在最后"
        # 世界库 创作/上传/一览游玩;角色库 对话/创作/上传/一览游玩
        assert ids[3:6] == ["wl-world-create", "wl-upload-world", "wl-world-browse"]
        assert ids[6:10] == ["wl-soul-talk", "wl-soul-create", "wl-upload-soul", "wl-soul-browse"]
        for moved in ("wl-import-world", "wl-hub-download", "wl-manage-world", "wl-import-soul", "wl-soul-download", "wl-manage-char"):
            assert moved not in ids, f"{moved} 留在「新游戏」列表里,不占首屏"

    def test_creation_entries_stay_gone(self) -> None:
        ids = WorldLinesLauncherApp._menu_button_ids()
        for gone in ("wl-new-character", "wl-new-world"):
            assert gone not in ids

    def test_every_tile_has_an_action_and_vice_versa(self) -> None:
        app = _make_launcher()
        assert set(app._menu_actions()) == set(WorldLinesLauncherApp._menu_button_ids())
        for btn_id, action in app._menu_actions().items():
            assert callable(action), btn_id

    def test_click_and_enter_share_one_dispatch(self) -> None:
        app = _make_launcher()
        app._start_soul_browse_flow = MagicMock()
        app._pending_card_import = object()
        app._run_menu_action("wl-soul-browse")
        app._start_soul_browse_flow.assert_called_once()
        assert app._pending_card_import is None, "任何首屏动作都清掉残留的卡片导入"

        app._start_hub_upload_flow = MagicMock()
        app._run_menu_action("wl-upload-soul")
        app._start_hub_upload_flow.assert_called_once_with("souls")

    def test_unknown_button_is_ignored(self) -> None:
        app = _make_launcher()
        app._run_menu_action("wl-nope")  # 不炸

    def test_library_actions_are_still_reachable(self) -> None:
        """仪表盘与「选世界」列表调的是同一批方法。"""
        for method in (
            "_step_world_import_prompt",
            "_step_hub_download_prompt",
            "_start_hub_upload_flow",
            "_step_manage_worlds",
            "_start_soul_talk_flow",
            "_step_character_import_prompt",
            "_step_manage_souls",
        ):
            assert callable(getattr(WorldLinesLauncherApp, method, None)), method

    def test_relabel_touches_titles_and_tiles(self) -> None:
        app = _make_launcher()
        app.query_one = MagicMock(return_value=MagicMock())
        app._relabel_launcher()
        resolved = {c.args[0] for c in app.query_one.call_args_list}
        assert "#wl-continue" in resolved
        assert "#wl-title-world" in resolved and "#wl-title-char" in resolved
        assert "#wl-soul-talk" in resolved and "#wl-world-browse" in resolved and "#wl-soul-create" in resolved
        assert "#wl-new-character" not in resolved


class TestQuickResume:
    """⚡ 第一格:一键进最近的存档,不经过存档/模型/界面三个选单
    (「不用 launcher 点这么多的入口,变成第一个选项」)。"""

    def _app(self, saves, presets=("qwen", "deepseek")):
        app = _make_launcher()
        app._presets = [{"id": p, "display": p} for p in presets]
        app.exit = MagicMock()
        app._step_choose_preset = MagicMock()
        app._start_new_flow = MagicMock()
        return app

    def test_newest_save_with_its_last_model_launches_in_tui(self, tmp_path) -> None:
        saves = [{"dir_name": "cat-20260909", "display_name": "猫岛", "path": tmp_path / "cat"}]
        app = self._app(saves)
        with patch("neonrp.worlds.list_saved_games", return_value=saves), patch(
            "neonrp.cli.read_worldlines_last_preset", return_value="qwen"
        ):
            app._quick_resume()
        sel = app.launch_selection
        assert sel is not None and sel.mode == "continue"
        assert sel.game_path == tmp_path / "cat"
        assert sel.preset_id == "qwen"
        assert sel.render_surface == "tui"
        assert sel.runtime_mode == "play"
        app.exit.assert_called_once()
        app._step_choose_preset.assert_not_called()

    def test_no_last_model_uses_the_user_default(self, tmp_path) -> None:
        saves = [{"dir_name": "cat-20260909", "display_name": "猫岛", "path": tmp_path / "cat"}]
        app = self._app(saves)
        with patch("neonrp.worlds.list_saved_games", return_value=saves), patch(
            "neonrp.cli.read_worldlines_last_preset", return_value=None
        ), patch("neonrp.presets.default_model_ref", return_value="deepseek"):
            app._quick_resume()
        assert app.launch_selection.preset_id == "deepseek"

    def test_unknown_model_falls_back_to_the_picker_not_a_guess(self, tmp_path) -> None:
        saves = [{"dir_name": "cat-20260909", "display_name": "猫岛", "path": tmp_path / "cat"}]
        app = self._app(saves)
        with patch("neonrp.worlds.list_saved_games", return_value=saves), patch(
            "neonrp.cli.read_worldlines_last_preset", return_value="gone"
        ), patch("neonrp.presets.default_model_ref", return_value=None):
            app._quick_resume()
        assert app.launch_selection is None
        app._step_choose_preset.assert_called_once_with(True)
        assert app._selected_game == tmp_path / "cat"

    def test_no_saves_goes_to_new_game(self) -> None:
        app = self._app([])
        with patch("neonrp.worlds.list_saved_games", return_value=[]):
            app._quick_resume()
        app._start_new_flow.assert_called_once()
        assert app.launch_selection is None

    def test_resume_label_names_the_save(self) -> None:
        app = _make_launcher()
        app.locale = "zh"
        app._saved_games = [{"dir_name": "cat-20260909", "display_name": "猫岛"}]
        assert "猫岛" in app._resume_label()
        app._saved_games = []
        assert "存档" in app._resume_label()

    def test_the_tui_never_offers_the_browser(self) -> None:
        """web 保留路径(`worldlines web`),但 TUI 里不推荐
        不显示 —— 没有「在哪里玩」,也没有 `_play_surface_options`。"""
        assert not hasattr(WorldLinesLauncherApp, "_play_surface_options")
