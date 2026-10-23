"""TUI step 2a (10-08): the right status column — 玩家 / Agent toggle; hp bar · down / stable / dead · effects with
their countdown · carried items, drawn field by field (not Markdown)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from test_app import _setup_project
from test_engine_v3 import _install

from neonrp.core import sdk
from neonrp.core.registry import load_registry
from neonrp.packs.rpg import character_state as cs
from neonrp.tui import status_side as S


def test_collect_and_render_conditions(tmp_path):
    root = _install(tmp_path)
    sdk.apply(root, [{"op": "new", "class": "status", "name": "中毒", "props": {"turns": 3, "rule": "每次结算 player.hp -1"}}],
              load_registry(root), turn=1)
    cs.write(root, "si-elena0001", hp=0, down=1, stable=1)
    cs.write(root, "si-rowan0001", hp=0, dead=1)
    d = S.collect(root)
    p = d["player"]
    assert p["hp"] == 24 and p["effects"][0]["name"] == "中毒" and p["effects"][0]["turns"] == 3 and p["items"]
    by = {a["name"]: a for a in d["agents"]}
    assert by["艾琳娜"]["here"] and by["艾琳娜"]["down"] and by["艾琳娜"]["stable"]
    assert by["罗文"]["dead"] and by["罗文"]["where"] == "碧石镇"
    pt = S.render_player("zh", p).plain
    assert "◆ 中毒" in pt and "⏳3" in pt and "随身物品" in pt and "HP" in pt
    at = S.render_agents("zh", d["agents"], {"si-elena0001": {"state": "running"}}).plain
    assert "稳住了" in at and "阵亡" in at and "✎" in at
    assert at.index("艾琳娜") < at.index("罗文")  # who is here comes first


def test_toggle_switches_views(tmp_path: Path):
    from neonrp.tui.app import NeonRPApp

    root = _setup_project(tmp_path)
    app = NeonRPApp(root=root, provider="stub", mode="play")

    async def scenario() -> None:
        async with app.run_test(size=(140, 40)) as pilot:
            side = app.query_one("#status-side", S.StatusSide)
            assert side.display  # play mode shows the column
            side.data = {"player": {"name": "旅人", "hp": 5, "max_hp": 10, "effects": [], "items": []},
                         "agents": [{"id": "a", "name": "艾琳娜", "here": True, "hp": 3, "max_hp": 8}]}
            side.show("player")
            body = app.query_one("#status-body")
            assert "旅人" in str(body.content)
            await pilot.click("#status-tab-agents")
            await pilot.pause(0.1)
            assert side.view == "agents" and "艾琳娜" in str(body.content)
            await pilot.click("#status-tab-player")
            await pilot.pause(0.1)
            assert side.view == "player"

    asyncio.run(scenario())


def test_judge_line_follows_the_account():
    off = S.judge_line("zh", {"backend": "off", "signed_in": False}).plain
    assert "没有判断器" in off and "/login" in off
    proxy = S.judge_line("zh", {"backend": "proxy", "signed_in": True}).plain
    assert "Worldlines 账号" in proxy and "/login" not in proxy
    assert "额度" in S.judge_line("zh", {"backend": "quota", "signed_in": True}).plain
    p = S.render_player("en", {"name": "x", "judge": {"backend": "off", "signed_in": False}}).plain
    assert "no judge" in p and "/login turns Jev on" in p


def test_status_account_command(tmp_path: Path, monkeypatch):
    from neonrp.tui.app import NeonRPApp

    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    monkeypatch.setattr(S, "judge_matters", lambda root: True)  # 10-15: the judge line only shows while a planning node runs
    app = NeonRPApp(root=_setup_project(tmp_path), provider="stub", mode="play")

    async def scenario() -> None:
        async with app.run_test() as pilot:
            app._handle_slash_command("/status account")
            await pilot.pause(0.1)
            out = str(app.screen.query_one("#status-tab-body").content)  # 10-23: the usage tab of the /status screen
            assert "⚖" in out and "/login" in out

    asyncio.run(scenario())


def test_login_while_signed_in_signs_in_again(tmp_path: Path, monkeypatch):
    """10-23: /login no longer needs /login out first — signed in, it runs the sign-in again (switch account)."""
    from neonrp.core import worldlines_auth as wa
    from neonrp.tui.app import NeonRPApp

    calls: list[dict] = []
    monkeypatch.setattr(wa, "status", lambda: {"signed_in": True, "source": "session"})
    monkeypatch.setattr(wa, "connect", lambda **kw: calls.append(kw) or {})
    app = NeonRPApp(root=_setup_project(tmp_path), provider="stub", mode="play")

    async def scenario() -> None:
        async with app.run_test() as pilot:
            app._cmd_login([])
            for _ in range(40):
                await pilot.pause(0.05)
                if calls:
                    break
            assert len(calls) == 1

    asyncio.run(scenario())


def test_status_is_a_screen_of_tabs(tmp_path: Path, monkeypatch):
    """10-23: /status opens one screen — the player, each character, then usage (account · contract · board · dice ·
    ending · tokens); ← / → go round, /status account lands on usage, Esc closes."""
    from neonrp.tui.app import NeonRPApp
    from neonrp.tui.status_screen import StatusScreen

    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    app = NeonRPApp(root=_install(tmp_path), provider="stub", mode="play")

    async def scenario() -> None:
        async with app.run_test(size=(140, 40)) as pilot:
            app._handle_slash_command("/status")
            await pilot.pause(0.2)
            scr = app.screen
            assert isinstance(scr, StatusScreen) and scr.key == "player"
            keys = [k for k, _ in scr.tabs]
            assert keys[-1] == "usage" and any(k.startswith("soul:") for k in keys)
            await pilot.press("left")
            assert scr.key == "usage"
            body = str(app.screen.query_one("#status-tab-body").content)
            assert "/login" in body
            await pilot.press("right")
            await pilot.press("right")
            assert scr.key == keys[1] and keys[1].startswith("soul:")
            app._handle_slash_command("/status account")
            await pilot.pause(0.1)
            assert app.screen is scr and scr.key == "usage"
            await pilot.press("escape")
            await pilot.pause(0.1)
            assert not isinstance(app.screen, StatusScreen)

    asyncio.run(scenario())
