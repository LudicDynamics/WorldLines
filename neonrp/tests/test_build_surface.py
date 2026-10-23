"""M31 · build 模式的配套界面 —— 文件树 + 文档阅读器。

play 和 build 应该是**两个看得见的地方**:play 的家具
回答「世界现在什么样」(立绘/场景图/状态栏),build 的家具回答「世界由
什么构成」(可折叠文件树 + 文档阅读器)。只读——修改回 agent 对话框做。

这里钉三件:噪音必须被挡在树外(否则树会教会你别看它)、阅读器按文件
类型渲染且坏文件要看得见、以及 `/mode` 真的会换家具而不是只换一个词。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from neonrp.tui.app import NeonRPApp
from neonrp.tui.build_surface import BuildStage, DocReader, WorldTree


class TestTreeHidesPlumbing:
    """树里不该出现机器账本。

    一棵会展开 `__pycache__` 和 commit blob 的树,会教会你「这棵树是噪音」,
    然后你就再也不看它了 —— 那它存在的意义就没了。
    """

    def test_engine_bookkeeping_is_hidden(self, tmp_path: Path) -> None:
        tree = WorldTree(str(tmp_path))
        paths = [
            tmp_path / ".neonrp",
            tmp_path / "__pycache__",
            tmp_path / ".git",
            tmp_path / "game",
            tmp_path / "souls",
        ]
        kept = {p.name for p in tree.filter_paths(paths)}
        assert kept == {"game", "souls"}

    def test_folders_sort_before_files(self, tmp_path: Path) -> None:
        (tmp_path / "game").mkdir()
        (tmp_path / "a.md").write_text("x", encoding="utf-8")
        tree = WorldTree(str(tmp_path))
        order = [p.name for p in tree.filter_paths([tmp_path / "a.md", tmp_path / "game"])]
        assert order == ["game", "a.md"]


class TestDocReader:
    """阅读器要按文件的样子渲染,而不是一律糊成文本。"""

    def _reader(self) -> DocReader:
        reader = DocReader()
        # 未挂载:把渲染出口换成 mock,只检查它挑了哪条路。
        reader._as_markdown = MagicMock()  # type: ignore[method-assign]
        reader._as_text = MagicMock()  # type: ignore[method-assign]
        reader._as_rich = MagicMock()  # type: ignore[method-assign]
        return reader

    def test_markdown_renders_as_markdown(self, tmp_path: Path) -> None:
        f = tmp_path / "soul.md"
        f.write_text("# 罗文\n\n沉默寡言。\n", encoding="utf-8")
        reader = self._reader()

        reader.show_path(f)

        reader._as_markdown.assert_called_once()

    def test_json_goes_through_the_house_renderer(self, tmp_path: Path) -> None:
        f = tmp_path / "e.json"
        f.write_text(json.dumps({"id": "x", "kind": "location"}), encoding="utf-8")
        reader = self._reader()

        reader.show_path(f)

        reader._as_rich.assert_called_once()

    def test_broken_json_is_shown_raw_not_swallowed(self, tmp_path: Path) -> None:
        """坏 JSON 正是你最想看见的东西,不该被藏起来。"""
        f = tmp_path / "bad.json"
        f.write_text("{not json", encoding="utf-8")
        reader = self._reader()

        reader.show_path(f)

        reader._as_text.assert_called_once()
        assert "not json" in reader._as_text.call_args.args[1]

    def test_binary_gets_one_line_not_a_screenful(self, tmp_path: Path) -> None:
        f = tmp_path / "cover.png"
        f.write_bytes(b"\x89PNG\x00\x01\x02")
        reader = self._reader()

        reader.show_path(f)

        reader._as_text.assert_called_once()
        assert "二进制" in reader._as_text.call_args.args[1]

    def test_huge_file_is_summarised(self, tmp_path: Path) -> None:
        f = tmp_path / "big.md"
        f.write_text("x" * 300_000, encoding="utf-8")
        reader = self._reader()

        reader.show_path(f)

        assert "过大" in reader._as_text.call_args.args[1]

    def test_missing_file_does_not_raise(self, tmp_path: Path) -> None:
        reader = self._reader()
        reader.show_path(tmp_path / "nope.md")  # 不抛
        reader._as_text.assert_called_once()

    def test_reader_scrolls(self) -> None:
        """够不着文档底部的阅读器不算阅读器。"""
        assert DocReader().is_scrollable


class TestModeSwapsTheFurniture:
    """`/mode` 要换的是地方,不只是状态栏上的一个词。"""

    def _app(self, tmp_path: Path, mode: str) -> tuple[NeonRPApp, dict]:
        app = NeonRPApp(root=tmp_path, mode=mode)  # type: ignore[arg-type]
        shown: dict[str, object] = {}

        def _fake_query(selector, *_a, **_k):
            # 同一个选择器必须返回同一个替身:`_apply_mode_chrome` 会对
            # #build-stage 查两次(翻显隐、设根),每次给新对象就看不到状态了。
            return shown.setdefault(selector, MagicMock())

        app.query_one = MagicMock(side_effect=_fake_query)  # type: ignore[method-assign]
        return app, shown

    def test_build_shows_the_tree_and_hides_the_stage(self, tmp_path: Path) -> None:
        app, shown = self._app(tmp_path, "play")

        app._apply_mode_chrome("build")

        assert shown["#build-stage"].display is True
        assert shown["#play-stage"].display is False
        assert shown["#character-status-lane"].display is False

    def test_play_shows_the_stage_and_hides_the_tree(self, tmp_path: Path) -> None:
        app, shown = self._app(tmp_path, "build")

        app._apply_mode_chrome("play")

        assert shown["#play-stage"].display is True
        # 10-08: the characters live in the right status column now (Agent view); the old lane stays hidden
        assert shown["#character-status-lane"].display is False
        assert shown["#status-side"].display is True
        assert shown["#build-stage"].display is False

    def test_portrait_is_hidden_through_its_own_switch(self, tmp_path: Path) -> None:
        """PortraitPanel 每次重绘都会把自己设回可见,所以只翻 display 会被推翻;
        它自己的 set_hidden() 才是能粘住的开关。"""
        app, shown = self._app(tmp_path, "play")

        app._apply_mode_chrome("build")

        shown["#portrait-panel"].set_hidden.assert_called_once_with(True)

    def test_switching_survives_an_unmounted_app(self, tmp_path: Path) -> None:
        """切模式绝不能因为某个面板不在就失败。"""
        app = NeonRPApp(root=tmp_path, mode="build")
        app._apply_mode_chrome("play")  # 未挂载,不抛

    def test_mode_switch_drives_the_chrome(self, tmp_path: Path) -> None:
        """完整路径:_apply_mode 应当把家具一起搬过去。"""
        app, shown = self._app(tmp_path, "build")
        app.session = None
        app._apply_mode_chrome = MagicMock()  # type: ignore[method-assign]

        app._apply_mode("play")

        app._apply_mode_chrome.assert_called_once_with("play")


def test_build_stage_points_the_tree_at_this_world(tmp_path: Path) -> None:
    stage = BuildStage()
    tree = MagicMock()
    stage.query_one = MagicMock(return_value=tree)  # type: ignore[method-assign]

    stage.set_root(tmp_path)

    assert tree.path == str(tmp_path)
