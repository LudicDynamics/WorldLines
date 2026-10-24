"""TUI step 1 (10-08): the TUI follows the beats from engine/beat — BeatState keeps the board / dice / changes /
settlement; entering a beat draws a colored band between the beats (planning green · resolving red · a layer amber)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from test_app import _setup_project

from neonrp.tui import beats
from neonrp.tui.app import ConversationView, NeonRPApp


def test_beat_state_follows_the_events():
    st = beats.BeatState()
    assert st.feed({"kind": "node.enter", "node": "plan", "turn": 1}) == "plan"
    st.feed({"kind": "plan.beat", "turn": 1, "board": {"玩家": "撬锁"}, "checks": [{"attr": "DEX"}], "mic": ["艾琳娜"]})
    assert st.board == {"玩家": "撬锁"} and st.checks and st.mic == ["艾琳娜"]
    assert st.feed({"kind": "node.leave", "node": "plan"}) is None
    assert st.feed({"kind": "node.enter", "node": "resolve", "turn": 1}) == "resolve"
    st.feed({"kind": "resolve.beat", "turn": 1})
    st.feed({"kind": "dice", "turn": 1, "request": "dice 1d20+2 vs 12", "answer": "14"})
    st.feed({"kind": "state.changed", "turn": 1, "applied": [{"var": "player.hp", "from": 10, "to": 9}]})
    st.feed({"kind": "run.settled", "turn": 9, "exit": "ending:E01"})
    assert st.checks == [] and st.dice[-1]["answer"] == "14" and st.changes["applied"][0]["to"] == 9
    assert st.settled == {"turn": 9, "exit": "ending:E01"} and st.node == "resolve"
    assert beats.color_of("plan") != beats.color_of("resolve") != beats.color_of("combat")


def test_entering_a_beat_draws_its_band(tmp_path: Path):
    app = NeonRPApp(root=_setup_project(tmp_path), provider="stub")

    async def scenario() -> None:
        async with app.run_test() as pilot:
            view = app.query_one("#conversation-view", ConversationView)
            view.add_assistant_chunk("你和艾琳娜商量怎么撬锁。")
            app._apply_beat_event({"kind": "node.enter", "node": "plan", "turn": 1})
            app._apply_beat_event({"kind": "plan.beat", "turn": 1, "checks": [{"attr": "DEX"}]})
            app._apply_beat_event({"kind": "node.leave", "node": "plan", "turn": 1})
            app._apply_beat_event({"kind": "node.enter", "node": "resolve", "turn": 1})
            app._apply_beat_event({"kind": "node.enter", "node": "combat", "turn": 2})
            await pilot.pause(0.2)
            bands = [str(w.content) for w in view.query(".beat-marker")]
            assert len(bands) == 3 and ("战斗裁判" in bands[2] or "Combat" in bands[2] or "combat" in bands[2])  # the layer's own title
            assert app._beat_state.node == "combat" and app._beat_state.checks == [{"attr": "DEX"}]

    asyncio.run(scenario())


def test_change_and_tool_rows():
    ch = beats.change_text({"applied": [
        {"op": "set", "var": "time.clock", "from": "08:30", "to": "08:32"},
        {"op": "add", "var": "player.hp", "from": 24, "to": 23, "by": "tick:effects"},
        {"op": "new", "class": "carry", "id": "IT004"},
        {"op": "remove", "who": "lantern", "name": "罩灯"},
        {"op": "move_to", "who": "player", "to": "T001/shop_general"},
        {"op": "event", "who": "si-rowan0001", "event": "down"}],
        "created": [{"id": "IT004", "name": "小治疗药水"}],
        "refused": [{"op": {"op": "move_to", "to": "T001/dock"}, "why": "x"}]}).plain
    assert "time" not in ch and "⟳hp 24→23" in ch and "＋ 小治疗药水" in ch and "－ 罩灯" in ch
    assert "➜ shop_general" in ch and "down" in ch and "✕ move_to" in ch
    assert beats.change_text({"applied": [{"op": "set", "var": "time.clock", "from": 1, "to": 2}]}) is None
    assert beats.tool_text({"request": "map", "async": True}).plain.startswith("⇢ map")
    sync = beats.tool_text({"request": "referee 想翻墙", "answer": "可以,要检定"}).plain
    assert sync.startswith("⇄ referee") and "→ 可以" in sync


def test_resolve_rows_appear_under_the_prose(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("NEONRP_SHOW_BEATS", raising=False)
    app = NeonRPApp(root=_setup_project(tmp_path), provider="stub", mode="play")

    async def scenario() -> None:
        async with app.run_test() as pilot:
            view = app.query_one("#conversation-view", ConversationView)
            app._apply_beat_event({"kind": "dice", "turn": 1, "request": "dice 1d20+2 vs 12", "rolls": [14], "total": 16, "vs": 12,
                                   "passed": True, "reason": "撬锁"})
            app._apply_beat_event({"kind": "tool", "turn": 1, "request": "map", "async": True})
            app._apply_beat_event({"kind": "state.changed", "turn": 1, "applied": [{"op": "add", "var": "player.hp", "from": 9, "to": 7}]})
            await pilot.pause(0.2)
            dice = [str(w.content) for w in view.query(".semantic-dice-line")]
            assert dice and "撬锁" in dice[0] and "16" in dice[0]
            assert any("⇢ map" in str(w.content) for w in view.query(".beat-tool"))
            assert any("hp 9→7" in str(w.content) for w in view.query(".beat-changes"))

    asyncio.run(scenario())


def test_options_are_buttons_that_send(tmp_path: Path):
    from neonrp.tui.options_bar import OptionsBar

    app = NeonRPApp(root=_setup_project(tmp_path), provider="stub", mode="play")
    sent: list[str] = []

    async def scenario() -> None:
        async with app.run_test(size=(140, 40)) as pilot:
            app._send_message = lambda text, **kw: sent.append(text)  # type: ignore[method-assign]
            bar = app.query_one("#options-bar", OptionsBar)
            bar.set_options(["去杂货铺问价", "跟艾琳娜商量", "  "])
            await pilot.pause(0.1)
            assert bar.display and len(bar.options) == 2
            await pilot.click("#option-2")
            await pilot.pause(0.1)
            assert sent == ["跟艾琳娜商量"] and not bar.display

    asyncio.run(scenario())


def test_settlement_card():
    t = beats.settlement_text({"exit": {"kind": "ending", "id": "E_VILLAGE"}, "epilogue": "天亮了,村子活了下来。", "cg_unlocked": ["E_VILLAGE"],
                               "deaths": [{"who": "S03", "name": "阿明", "turn": 4}],
                               "accusation": [{"round": 1, "target": "S02", "name": "小梅", "role": "wolf", "votes": [{}, {}]}],
                               "truth_reveal": {"text": "两只狼是小梅和老周。", "roles": [{"id": "S02", "name": "小梅", "role": "wolf", "alive": False}]}},
                              "zh").plain
    for frag in ("✦ 结局", "E_VILLAGE", "天亮了", "解锁 CG", "✝ 死亡  阿明", "指认", "小梅 (wolf)  ×2", "真相", "两只狼", "/settlement"):
        assert frag in t, frag


def test_plan_board_row():
    t = beats.plan_text({"board": {"玩家": "撬锁", "艾琳娜": "按住门框"},
                         "checks": [{"who": "player", "attr": "DEX", "dc": "normal", "adj": "-2(扭伤)", "why": "撬开地窖的锁"}],
                         "mic": [{"who": "艾琳娜"}]}).plain
    assert "▣ 玩家 → 撬锁 · 艾琳娜 → 按住门框" in t and "🎲 player DEX normal -2(扭伤)  撬开地窖的锁" in t and "🎙 → 艾琳娜" in t
    assert beats.plan_text({"board": {}, "checks": [], "mic": []}) is None


def test_panels_drawn_under_the_resolve(tmp_path: Path):
    """[~map] is async: the engine draws it after the write-down into the beat's panels — the TUI puts it on screen."""
    from neonrp.core import beat_events

    tr = {"turn_seq": 2, "apply": {"beat": {"kind": "resolve"}, "narration_plain": "…",
                                   "panels": {"map": {"id": "map", "format": "text", "source": "tool", "text": "── 灰橡宅 ──\n[你的位置] 地窖"}}}}
    evs, _ = beat_events.from_traces([tr], "plan")
    rb = next(d for k, d in evs if k == "resolve.beat")
    assert rb["panels"]["map"]["text"].startswith("── 灰橡宅")
    app = NeonRPApp(root=_setup_project(tmp_path), provider="stub", mode="play")

    async def scenario() -> None:
        async with app.run_test(size=(140, 40)) as pilot:
            app._apply_beat_event({"kind": "resolve.beat", "turn": 2, **{k: v for k, v in rb.items() if k != "turn"}})
            await pilot.pause(0.2)
            view = app.query_one("#conversation-view", ConversationView)
            panels = list(view.query(".beat-panel"))
            assert len(panels) == 1

    asyncio.run(scenario())


def test_away_line_is_a_fold_that_opens_and_closes(tmp_path: Path):
    """A character elsewhere shows as a folded 「✓ 罗文 @ 碧石镇」 notice; click opens her whole line
    (from the engine's away event — the prose line is cut at 80), click again folds it."""
    from textual.widgets import Collapsible

    app = NeonRPApp(root=_setup_project(tmp_path), provider="stub", mode="play")
    whole = "公会门口吵吵嚷嚷," + "我挤到委托板前一条条往下看," * 6 + "最后揭下了那张矿道异响的。"

    async def scenario() -> None:
        async with app.run_test(size=(140, 40)) as pilot:
            view = app.query_one("#conversation-view", ConversationView)
            app._apply_beat_event({"kind": "away", "turn": 2, "items": [{"iid": "si-rowan0001", "name": "罗文", "where": "碧石镇", "text": whole}]})
            view.add_assistant_chunk("你点点头。\n\n// 异地 · 罗文 @ 碧石镇:" + whole[:79] + "…\n")
            view.add_assistant_end()
            await pilot.pause(0.3)
            folds = list(view.query(Collapsible))
            assert len(folds) == 1 and folds[0].collapsed and folds[0].title == "✓ 罗文 @ 碧石镇"
            body = folds[0].query_one(".msg-body")
            assert "最后揭下了那张矿道异响的" in str(body.content)  # the whole line, not the 80-character cut
            folds[0].collapsed = False
            await pilot.pause(0.1)
            assert not folds[0].collapsed
            folds[0].collapsed = True
            await pilot.pause(0.1)
            assert folds[0].collapsed

    asyncio.run(scenario())


def test_mode_layer_tag_in_the_place_header(tmp_path: Path):
    """Entering a mode layer puts a standing ⚔ tag (the layer's own title) after the place; the beats clear it."""
    from test_engine_v3 import _install

    from neonrp.tui.location_header import LocationHeader

    app = NeonRPApp(root=_install(tmp_path), provider="stub", mode="play")

    async def scenario() -> None:
        async with app.run_test(size=(140, 40)) as pilot:
            header = app.query_one("#location-header", LocationHeader)
            app._apply_beat_event({"kind": "node.enter", "node": "combat", "turn": 3})
            await pilot.pause(0.1)
            assert "⚔" in str(header.content) and header._mode  # 战斗裁判 / Combat referee
            app._apply_beat_event({"kind": "node.leave", "node": "combat", "turn": 4})
            app._apply_beat_event({"kind": "node.enter", "node": "resolve", "turn": 4})
            await pilot.pause(0.1)
            assert "⚔" not in str(header.content) and not header._mode

    asyncio.run(scenario())


def test_picked_up_item_is_a_card(tmp_path: Path):
    """Items are drawn field by field, not as Markdown — a new item in the bag gets its own card."""
    from test_engine_v3 import _install

    from neonrp.core import sdk
    from neonrp.core.registry import load_registry

    root = _install(tmp_path)
    res = sdk.apply(root, [{"op": "new", "class": "carry", "name": "小治疗药水", "props": {"qty": 2, "effect": "回复 1d6 hp", "kind": "药水"}}],
                    load_registry(root), turn=1)
    created = [dict(c) for c in res.created]
    assert created and created[0]["class"] == "carry"
    app = NeonRPApp(root=root, provider="stub", mode="play")

    async def scenario() -> None:
        async with app.run_test(size=(140, 40)) as pilot:
            app._apply_beat_event({"kind": "state.changed", "turn": 1, "applied": [], "created": created, "refused": []})
            await pilot.pause(0.2)
            view = app.query_one("#conversation-view", ConversationView)
            cards = list(view.query(".beat-item"))
            assert len(cards) == 1
            panel = cards[0].content if hasattr(cards[0], "content") else None
            body = str(getattr(panel, "renderable", panel))
            assert "小治疗药水" in body and "×2" in body and "回复 1d6 hp" in body and "药水" in body

    asyncio.run(scenario())



def test_the_first_planning_beat_says_who_judges_when_jev_is_off(tmp_path: Path, monkeypatch):
    """10-24: no Jev, no account — say so once, low-key: the run's own model judges (or 「定」 / @dm), /login turns Jev on."""
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    app = NeonRPApp(root=_setup_project(tmp_path), provider="stub")

    async def scenario() -> None:
        async with app.run_test() as pilot:
            view = app.query_one("#conversation-view", ConversationView)
            app._apply_beat_event({"kind": "plan.beat", "turn": 1})
            app._apply_beat_event({"kind": "plan.beat", "turn": 2})
            await pilot.pause(0.2)
            rows = [str(w.content) for w in view.query(".beat-judge-hint")]
            assert len(rows) == 1 and "/login" in rows[0]

    asyncio.run(scenario())
