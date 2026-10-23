"""TODO #3:点角色名进它的 context —— 像 Claude Code team
mode:看它的 RP 进度,或替它 RP。"""

from __future__ import annotations

import asyncio
import json

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from neonrp.core import soul_context as SC
from neonrp.core.playthrough import Playthrough, SoulRef, WorldAgentTeam, WorldRef, write_playthrough
from neonrp.tui.app import CharacterStatusLane, NeonRPApp, ordered_soul_rows


def _world(root: Path) -> Path:
    (root / "game" / "meta").mkdir(parents=True)
    (root / "game" / "meta" / "run_state.json").write_text(json.dumps({"turn_count": 3, "location": {"node": "T004/guild", "node_id": "T004"}}), encoding="utf-8")
    (root / "game" / "towns" / "T004").mkdir(parents=True)
    (root / "game" / "towns" / "T004" / "town_map.json").write_text(json.dumps({"town_id": "T004", "nodes": [{"id": "guild", "name": "公会", "links": []}]}), encoding="utf-8")
    sd = root / "souls" / "luowen-si-luowen0001"
    (sd / "short-term-memo").mkdir(parents=True)
    (sd / "soul.json").write_text(json.dumps({"sid": "luowen", "name": "Luowen", "name_local": "罗文"}, ensure_ascii=False), encoding="utf-8")
    (sd / "soul.md").write_text("沉默寡言的铁匠。", encoding="utf-8")
    (sd / "run_state.json").write_text(json.dumps({"location": "T004/guild", "status": {"hp": 18, "max_hp": 20, "mood": "warm"}, "turn_count": 3}), encoding="utf-8")
    (sd / "short-term-memo" / "current_context.json").write_text(json.dumps({"notes": ["玩家帮我修了炉子"]}, ensure_ascii=False), encoding="utf-8")
    write_playthrough(root, Playthrough(
        schema_version=2, playthrough_id="pt", world=WorldRef(wid="w", instance_id="wi-0000000000ff", version_hash="sha256:x", head_commit=""),
        world_agent_team=WorldAgentTeam(seeded_from="t", agents=[]),
        souls=[SoulRef(sid="luowen", instance_id="si-luowen0001", version_hash="", head_commit="", role="npc")],
        created_at="2026-09-13T00:00:00Z", active_souls=("si-luowen0001",),
    ))
    (root / ".neonrp" / "orchestration").mkdir(parents=True)
    rows = [
        {"turn_seq": 1, "ts": "t1", "player": {"input": "你好"}, "world_location": "T004/guild", "souls": [{"sid": "luowen", "instance_id": "si-luowen0001", "activated": True, "reason": "被叫到名字", "speech": "……嗯。", "tool_calls": 1}]},
        {"turn_seq": 2, "ts": "t2", "player": {"input": "走开"}, "souls": [{"sid": "luowen", "instance_id": "si-luowen0001", "activated": False}]},
        {"turn_seq": 3, "ts": "t3", "player": {"input": "修炉子"}, "souls": [{"sid": "luowen", "instance_id": "si-luowen0001", "activated": True, "reason": "炉子是他的", "speech": "手别乱放。", "tool_calls": 0}]},
    ]
    (root / ".neonrp" / "orchestration" / "main.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return root


def test_build_soul_context_reads_identity_place_memory_and_progress(tmp_path):
    root = _world(tmp_path / "w")
    ctx = SC.build_soul_context(root, "罗文")
    assert ctx["ok"] and ctx["iid"] == "si-luowen0001" and ctx["name"] == "罗文" and ctx["on_stage"]
    assert ctx["location"]["name"] == "公会" and ctx["status"]["mood"] == "warm"
    assert "炉子" in ctx["memory"] and "铁匠" in ctx["persona"]
    assert [r["turn_seq"] for r in ctx["progress"]] == [1, 3], "只列它醒着的回合"
    assert ctx["progress"][-1]["speech"] == "手别乱放。" and ctx["thread"] == []
    assert SC.build_soul_context(root, "nobody")["ok"] is False
    assert SC.build_soul_context(root, "si-luowen0001")["ok"], "iid 也能当 token"


def test_lane_rows_map_back_to_instance_ids():
    snap = {
        "si-b": {"name": "乙", "role": "inactive", "state": "background"},
        "si-a": {"name": "甲", "role": "active", "state": "queued"},
    }
    assert [iid for iid, _ in ordered_soul_rows(snap)] == ["si-a", "si-b"]
    lane = CharacterStatusLane()
    lane._soul_snapshot = snap
    assert lane.iid_at_row(0) is None and lane.iid_at_row(1) == "si-a" and lane.iid_at_row(2) == "si-b" and lane.iid_at_row(3) is None


def test_who_command_routes_to_the_context_screen(tmp_path):
    app = NeonRPApp(mode="play")
    app.query_one = MagicMock(return_value=MagicMock())
    app.open_soul_context = MagicMock()
    app._handle_slash_command("/who 罗文")
    app.open_soul_context.assert_called_once_with("罗文")


def test_who_without_args_offers_the_roster(tmp_path):
    app = NeonRPApp(mode="play")
    app._soul_status_snapshot = {"si-a": {"name": "甲", "role": "active", "state": "queued"}}
    app.query_one = MagicMock(return_value=MagicMock())
    app.push_screen = MagicMock()
    app._cmd_who([])
    picker = app.push_screen.call_args.args[0]
    assert [o[1] for o in picker._options] == ["si-a"]


def test_open_soul_context_pushes_the_screen_and_talk_prefills_input(tmp_path):
    from neonrp.tui.soul_context import SoulContextScreen

    root = _world(tmp_path / "w")
    app = NeonRPApp(mode="play")
    app.root = root
    app.push_screen = MagicMock()
    app.open_soul_context("罗文")
    screen, done = app.push_screen.call_args.args
    assert isinstance(screen, SoulContextScreen) and screen.iid == "si-luowen0001"
    box = MagicMock(value="")
    app.query_one = MagicMock(return_value=box)
    done(("talk", "si-luowen0001"))
    assert box.value == "@罗文 "
    box.focus.assert_called_once()


def test_context_screen_renders_and_acts(tmp_path):
    from textual.app import App

    from neonrp.tui.soul_context import SoulContextScreen

    root = _world(tmp_path / "w")
    ctx = SC.build_soul_context(root, "罗文")
    engaged: list = []

    class T(App):
        result = "unset"

        def on_mount(self):
            self.push_screen(SoulContextScreen(ctx, root=root, locale="zh", on_engaged=engaged.append), lambda v: setattr(self, "result", v))

    async def run():
        a = T()
        async with a.run_test(size=(120, 50)) as pilot:
            await pilot.pause()
            await pilot.pause()
            scr = a.screen
            text = " ".join(str(w.render()) for w in scr.query("Static"))
            with patch("neonrp.core.engage.engage_soul_run", return_value={"ok": True, "name": "罗文", "digest": "罗文把锤子放下了", "intended_action": "看向门口"}):
                scr.engage("放下锤子看门口")
                for _ in range(20):
                    await pilot.pause()
                    if engaged:
                        break
            result_text = str(scr.query_one("#soul-act-result").render())
            await pilot.press("t")
            await pilot.pause()
            return text, result_text, a.result

    text, result_text, result = asyncio.run(run())
    assert "罗文" in text and "公会" in text and "手别乱放" in text and "炉子" in text
    assert engaged and engaged[0]["note"] == "放下锤子看门口"
    assert "锤子放下" in result_text and "看向门口" in result_text
    assert result == ("talk", "si-luowen0001")


def test_context_marks_reachability_and_phone_worlds(tmp_path):
    """TODO #6:@ 对不在场的人 = 打电话 —— 只在世界声明了远程通讯时。"""
    root = _world(tmp_path / "w")
    sd = root / "souls" / "luowen-si-luowen0001"
    (sd / "run_state.json").write_text(json.dumps({"location": "T004/gate", "status": {}, "turn_count": 3}), encoding="utf-8")
    (root / "game" / "towns" / "T004" / "town_map.json").write_text(json.dumps({"town_id": "T004", "nodes": [{"id": "guild", "name": "公会", "links": ["gate"]}, {"id": "gate", "name": "门", "links": ["guild"]}]}), encoding="utf-8")
    ctx = SC.build_soul_context(root, "罗文")
    assert ctx["reachable"] is False and ctx["remote"] is False
    (root / "game" / "meta" / "comms.json").write_text(json.dumps({"remote": True, "medium": "手机"}, ensure_ascii=False), encoding="utf-8")
    ctx = SC.build_soul_context(root, "罗文")
    assert ctx["reachable"] and ctx["remote"] and ctx["medium"] == "手机"


def test_lianyu_template_has_phones():
    from neonrp.templates import __file__ as tpl

    comms = Path(tpl).parent / "lianyu" / "game" / "meta" / "comms.json"
    if not comms.is_file():
        pytest.skip("lianyu is not in this release")
    assert json.loads(comms.read_text(encoding="utf-8"))["remote"] is True


def test_clicking_a_soul_row_opens_that_soul_not_the_next_one():
    """Clicking 罗文 in the TUI lane did nothing, clicking 艾琳娜 opened 罗文 — the lane's border-top is a row
    of its own and the click row was counted from the border."""
    import asyncio

    from textual.app import App, ComposeResult

    from neonrp.tui.app import CharacterStatusLane

    picked: list[str] = []
    lane_snapshot = {"si-a": {"name": "艾琳娜", "role": "active", "state": "completed"},
                     "si-b": {"name": "罗文", "role": "active", "state": "offstage"}}

    class Harness(App):
        CSS = "CharacterStatusLane { height: auto; border-top: solid #1f3a29; padding: 0 1; }"

        def compose(self) -> ComposeResult:
            yield CharacterStatusLane(id="lane")

        def on_character_status_lane_soul_picked(self, message: CharacterStatusLane.SoulPicked) -> None:
            picked.append(message.iid)

    async def run() -> None:
        app = Harness()
        async with app.run_test() as pilot:
            lane = app.query_one("#lane", CharacterStatusLane)
            lane.render_soul_status(lane_snapshot)
            await pilot.pause()
            top = lane.content_region.y - lane.region.y  # rows taken by the border above the content
            await pilot.click("#lane", offset=(4, top + 1))  # the first soul row (row 0 of the content is the title)
            await pilot.click("#lane", offset=(4, top + 2))
            await pilot.pause()

    asyncio.run(run())
    assert picked == [iid for iid, _ in ordered_soul_rows(lane_snapshot)]
