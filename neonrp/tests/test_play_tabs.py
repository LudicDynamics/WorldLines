"""任务 A1: the play stage has three tabs — 对话 / 文生图 /
地图. A tab swaps the whole content block; the transcript and the input line
are never re-mounted, only shown or hidden; build mode is untouched."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from neonrp.tui.app import NeonRPApp


def _world(tmp_path: Path) -> Path:
    root = tmp_path / "w"
    (root / "game" / "meta").mkdir(parents=True)
    (root / "game" / "meta" / "run_state.json").write_text(json.dumps({"turn_count": 1}), encoding="utf-8")
    (root / "game" / "world").mkdir()
    (root / "game" / "world" / "world_map.json").write_text(
        json.dumps({"name": "w", "nodes": [{"id": "a", "name": "A", "pos": [0, 0], "links": ["b"]}, {"id": "b", "name": "B", "pos": [3, 2]}]}),
        encoding="utf-8",
    )
    return root


def _shown(app: NeonRPApp, wid: str) -> bool:
    return bool(app.query_one(wid).display)


def test_tabs_swap_the_play_content_and_keep_the_transcript(tmp_path):
    root = _world(tmp_path)

    async def go():
        app = NeonRPApp(root=root, mode="play")
        async with app.run_test(size=(120, 44)) as pilot:
            await pilot.pause()
            view = app.query_one("#conversation-view")
            assert _shown(app, "#play-tab-chat") and not _shown(app, "#play-tab-image") and not _shown(app, "#play-tab-map")
            assert _shown(app, "#conversation-view") and _shown(app, "#input-area")
            assert app.query_one("#tab-chat").has_class("active")

            await pilot.click("#tab-map")
            await pilot.pause()
            assert _shown(app, "#play-tab-map") and not _shown(app, "#play-tab-chat") and not _shown(app, "#play-tab-image")
            assert not _shown(app, "#conversation-view"), "the transcript belongs to the 对话 tab"
            assert _shown(app, "#input-area"), "you can keep typing on every tab"
            assert app.query_one("#tab-map").has_class("active") and not app.query_one("#tab-chat").has_class("active")

            await pilot.click("#tab-image")
            await pilot.pause()
            assert _shown(app, "#play-tab-image") and not _shown(app, "#play-tab-map")
            assert _shown(app, "#scene-panel")
            assert not _shown(app, "#conversation-view")

            await pilot.click("#tab-chat")
            await pilot.pause()
            assert _shown(app, "#play-tab-chat") and _shown(app, "#conversation-view")
            assert app.query_one("#conversation-view") is view, "never re-mounted"
            assert not _shown(app, "#scene-panel")

    asyncio.run(go())


def test_build_mode_layout_is_untouched(tmp_path):
    root = _world(tmp_path)

    async def go():
        app = NeonRPApp(root=root, mode="build")
        async with app.run_test(size=(120, 44)) as pilot:
            await pilot.pause()
            assert not _shown(app, "#play-stage")
            assert _shown(app, "#build-stage") and _shown(app, "#conversation-view")
            # A tab press while building changes nothing visible.
            app._set_play_tab("map")
            await pilot.pause()
            assert not _shown(app, "#play-stage") and _shown(app, "#conversation-view")

    asyncio.run(go())


def test_leaving_play_on_the_map_tab_brings_the_transcript_back(tmp_path):
    root = _world(tmp_path)

    async def go():
        app = NeonRPApp(root=root, mode="play")
        async with app.run_test(size=(120, 44)) as pilot:
            await pilot.pause()
            await pilot.click("#tab-map")
            await pilot.pause()
            assert not _shown(app, "#conversation-view")
            app._apply_mode("build")
            await pilot.pause()
            assert _shown(app, "#conversation-view") and not _shown(app, "#play-stage")
            app._apply_mode("play")
            await pilot.pause()
            assert _shown(app, "#play-tab-map") and not _shown(app, "#conversation-view"), "the open tab is remembered"

    asyncio.run(go())


def test_tab_labels_follow_the_locale(tmp_path):
    root = _world(tmp_path)

    async def go():
        app = NeonRPApp(root=root, mode="play")
        async with app.run_test(size=(120, 44)) as pilot:
            await pilot.pause()
            app.ui_locale = "zh"
            app._relabel_play_controls()
            await pilot.pause()
            assert "地图" in str(app.query_one("#tab-map").label)
            assert "上一级" in str(app.query_one("#btn-map-up").label)

    asyncio.run(go())
