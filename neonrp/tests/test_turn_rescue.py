"""A line the engine could not finish in time keeps what it wrote (10-25 niko: 超时 / 中断时已经生成的部分直接显示出来,
可以当成这回合的结果;「继续生成」接着写,「重来」回到这一句之前) — core/turn_rescue, core/beat_budget.wrap_up,
core/stream_lines (a broken stream's part is the reply).

No real model: fake adapters stream a few lines and then break, or stall."""
from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace

import pytest
from _paths import PRODUCT_TEMPLATES

from neonrp import template as TP
from neonrp.core import beat_budget as bb
from neonrp.core import turn_rescue, turn_v3
from neonrp.core.llm import LLMTurnResult, Message, StreamChunk
from neonrp.core.orchestration_trace import TurnTrace, append_turn_trace, read_turn_traces
from neonrp.core.registry import load_registry
from neonrp.core.stream_lines import stream_chat
from neonrp.core.turn_v3 import is_timeout_line, trim_cut


# ── a broken stream: what came is the reply ──────────────────────────────────────────────────────────────────────

class _Breaks:
    """Streams ``pieces`` then the connection drops; the plain call after it gives nothing (the provider is gone)."""

    def __init__(self, pieces, plain=""):
        self.pieces, self.plain, self.plain_calls = pieces, plain, 0

    def chat_stream(self, messages):
        for p in self.pieces:
            yield StreamChunk(delta=p)
        raise ConnectionError("stream dropped mid-reply")

    def chat(self, messages):
        self.plain_calls += 1
        return LLMTurnResult(message=Message(role="assistant", content=self.plain), finished=True)


def test_a_stream_that_breaks_keeps_its_part_when_the_plain_call_gives_nothing():
    shown: list[str] = []
    st: dict = {}
    ad = _Breaks(["<lines>\n雨下大了。\n", "你推开门,屋里"])
    with bb.turn(30), bb.beat("world", 20) as b:
        text, was_shown = stream_chat(ad, [Message(role="user", content="x")], shown.append, state=st)
    assert ad.plain_calls == 1  # time was left: the plain call was tried first, as before
    assert "雨下大了。" in text and "你推开门,屋里" in text and was_shown
    assert st.get("truncated") and "error" not in st
    assert "".join(shown).count("雨下大了。") == 1 and "你推开门,屋里" in "".join(shown)  # the cut last line is shown too
    assert any(h["where"] == "stream.cut" and h["beat"] == "world" for h in b.sink)


def test_a_stream_that_breaks_takes_the_plain_answer_when_there_is_one():
    st: dict = {}
    ad = _Breaks(["<lines>\n雨下大了。\n"], plain="<lines>\n雨下大了。门开了。\n</lines>")
    with bb.turn(30), bb.beat("world", 20):
        text, _ = stream_chat(ad, [Message(role="user", content="x")], lambda t: None, state=st)
    assert "门开了" in text and not st.get("truncated")


# ── wrap_up: the page saw the turn stall ─────────────────────────────────────────────────────────────────────────

def test_wrap_up_ends_the_running_beat_and_keeps_the_settle(tmp_path, monkeypatch):
    monkeypatch.setenv("NEONRP_BEAT_SETTLE_S", "3")
    seen: dict = {}
    ready, go = threading.Event(), threading.Event()

    def turn() -> None:
        with bb.turn(30, root=tmp_path) as hits, bb.beat("world", 20):
            ready.set()
            go.wait(5)
            seen["expired"] = bb.expired()
            seen["wrapped"] = bb.wrapped()
            bb.floor(18, "world.floor")  # no share of its own after a wrap-up
            seen["turn_left"] = bb.turn_remaining()
            bb.grant(bb.settle_s(), "world.settle")  # the state transition still gets its call
            seen["after_grant"] = bb.remaining()
        seen["hits"] = list(hits)

    th = threading.Thread(target=turn)
    th.start()
    ready.wait(5)
    assert bb.wrap_up(tmp_path / "other") is False  # another run's turn is not this one
    assert bb.wrap_up(tmp_path) is True
    go.set()
    th.join(5)
    assert seen["expired"] and seen["wrapped"]
    assert 0 < seen["turn_left"] <= 3.0 and 0 < seen["after_grant"] <= 3.0
    assert any(h["where"] == "wrap_up" and h["beat"] == "world" for h in seen["hits"])
    assert bb.wrap_up(tmp_path) is False  # nothing running any more


# ── snapshot: 重来 / a failed line go back to before the line ─────────────────────────────────────────────────────

def test_restore_puts_the_run_back_and_leaves_pictures_alone(tmp_path):
    root = tmp_path / "run"
    (root / "game" / "player").mkdir(parents=True)
    (root / "assets").mkdir()
    (root / "game" / "player" / "state.json").write_text('{"gold": 10}', encoding="utf-8")
    (root / ".neonrp" / "sessions").mkdir(parents=True)
    (root / ".neonrp" / "sessions" / "main.jsonl").write_text('{"role": "user", "content": "a"}\n', encoding="utf-8")
    assert turn_rescue.capture(root, "开门", branch="main")
    (root / "game" / "player" / "state.json").write_text('{"gold": 3}', encoding="utf-8")
    (root / "game" / "player" / "new.json").write_text("{}", encoding="utf-8")
    with open(root / ".neonrp" / "sessions" / "main.jsonl", "a", encoding="utf-8") as f:
        f.write('{"role": "user", "content": "开门"}\n')
    (root / "assets" / "scene.png").write_bytes(b"png")
    assert turn_rescue.restore(root)
    assert json.loads((root / "game" / "player" / "state.json").read_text(encoding="utf-8")) == {"gold": 10}
    assert not (root / "game" / "player" / "new.json").exists()
    assert (root / ".neonrp" / "sessions" / "main.jsonl").read_text(encoding="utf-8").count("\n") == 1
    assert (root / "assets" / "scene.png").exists()  # pictures are not part of a line's state
    assert turn_rescue.state(root)["text"] == "开门"
    turn_rescue.forget(root)


def test_grow_replaces_the_cut_prose_in_place():
    assert turn_rescue.grow("// 骰子\n\n雨下大了。你推", "雨下大了。你推", "雨下大了。你推开门。") == "// 骰子\n\n雨下大了。你推开门。"
    assert turn_rescue.grow("", "", "门开了。") == "门开了。"


# ── the world's beat cut, then continued ─────────────────────────────────────────────────────────────────────────

class _World:
    """The narrator streams (and may break); every plain call is a write-down answer, in order."""

    base_url = "https://example.invalid/v1"  # no thinking switch: one write-down call

    def __init__(self, streams, writes):
        self.streams, self.writes = list(streams), list(writes)
        self.plain: list[str] = []

    def chat_stream(self, messages):
        pieces, breaks = self.streams.pop(0)
        for p in pieces:
            yield StreamChunk(delta=p)
        if breaks:
            raise ConnectionError("stream dropped mid-reply")
        yield StreamChunk(finished=True)

    def chat(self, messages, tools=None):
        user = str(messages[-1].content or "")
        self.plain.append(user)
        if not self.writes:
            return SimpleNamespace(message=SimpleNamespace(content=""), usage={})
        return SimpleNamespace(message=SimpleNamespace(content=self.writes.pop(0)), usage={})


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("NEONRP_V3_SOLVE", "narrate")
    monkeypatch.setenv("NEONRP_TRANSITION_THINKING", "0")
    root = tmp_path / "w"
    TP.build(PRODUCT_TEMPLATES / "stoneford-elena.template", root)
    yield root
    turn_v3.ADAPTER_FACTORY = None
    turn_rescue.forget(root)


def _resolve(root, fake, monkeypatch, shown):
    """The world's beat as v3_resolve runs it: the prose streams to the screen, inside the turn's budget."""
    monkeypatch.setattr(turn_v3, "ADAPTER_FACTORY", lambda root_, provider: fake)
    turn_v3.STREAM.update(on_text=shown.append, on_event=None, shown=False)
    try:
        with bb.turn(30, root=root) as hits, bb.beat("world", 20, root=root, reserve=0):
            out = turn_v3.solve_turn(root, user_text="推门进去", provider=None, turn=1, soul_reports=[])
    finally:
        turn_v3.STREAM.update(on_text=None, on_event=None, shown=False)
    return out, list(hits)


def test_a_cut_beat_lands_its_prose_and_continues_from_where_it_stopped(world, monkeypatch):
    root = world
    gold = load_registry(root).variables["player.gold"].value
    fake = _World(
        streams=[(["<lines>\n雨下大了。\n", "你推开门,屋里一股"], True),  # breaks mid-line
                 (["<lines>\n你推开门,屋里一股潮气。\n", "炉子还温着。\n</lines>\n[options 坐下烤火|喊一声]"], False)],
        writes=["", f"<vars>\nplayer.gold = {gold - 2}\n</vars>", f"<vars>\nplayer.gold = {gold - 5}\n</vars>"])
    # ("" = the plain call after the broken stream gave nothing)
    shown: list[str] = []
    turn_rescue.capture(root, "推门进去")
    out, hits = _resolve(root, fake, monkeypatch, shown)
    assert out["narration"] == "雨下大了。"  # the half sentence it broke in does not land (10-25 S[20] 「才把罩」)
    assert load_registry(root).variables["player.gold"].value == gold - 2  # the cut prose landed with its own write-down
    assert turn_rescue.cut_of(hits)  # the page is told it was cut
    # the turn's record and the session's reply, as the conversation writes them
    tr = TurnTrace(turn_seq=1, player_input="推门进去")
    tr.apply = {"narration_plain": out["narration"], "annotated": out["annotated"], "applied": [], "options": []}
    append_turn_trace(root, "main", tr)
    from neonrp.core.session import append_message

    append_message(root, "main", Message(role="user", content="推门进去"))
    append_message(root, "main", Message(role="assistant", content=out["narration"]))
    st = turn_rescue.after_turn(root, success=True, timeouts=hits)
    assert st["cut"] and st["continue"] and st["redo"] and st["text"] == "推门进去"

    more: list[str] = []
    msgs = [Message(role="assistant", content=out["narration"])]
    got = turn_rescue.continue_turn(root, on_text=more.append, messages=msgs)
    assert got["ok"], got
    assert got["text"].startswith("你推开门,屋里一股潮气。") and "炉子还温着" in got["text"]
    assert got["narration"].count("雨下大了。") == 1 and got["narration"].count("你推开门") == 1  # not repeated
    assert got["options"] == ["坐下烤火", "喊一声"] and not got["cut"]
    assert "炉子还温着" in "".join(more) and "雨下大了" not in "".join(more)  # only the new part streams
    # the continuation's own write-down landed on top (no tick): its lines are the continuation only
    assert load_registry(root).variables["player.gold"].value == gold - 5
    assert "炉子还温着" in fake.plain[-1] and "雨下大了" not in fake.plain[-1].split("炉子还温着")[0][-200:]
    rec = read_turn_traces(root, "main")[-1]
    assert rec["apply"]["narration_plain"] == got["narration"] and rec["apply"]["continued"] == 1
    assert rec["apply"]["options"] == ["坐下烤火", "喊一声"]
    from neonrp.core.session import read_session_messages

    assert read_session_messages(root, "main")[-1].content == got["narration"]
    assert msgs[-1].content == got["narration"]
    assert not turn_rescue.state(root)["continue"]  # finished: nothing more to continue

    # 重来: back to before the line — the state, the record and the log
    assert turn_rescue.restore(root)
    assert load_registry(root).variables["player.gold"].value == gold
    assert read_turn_traces(root, "main") == []
    assert all(m.content != "推门进去" for m in read_session_messages(root, "main"))


def test_a_beat_cut_before_it_wrote_anything_continues_from_nothing(world, monkeypatch):
    root = world
    fake = _World(streams=[([], True), (["<lines>\n夜里很静。\n</lines>"], False)], writes=["", "", "<vars>\n</vars>"])
    turn_rescue.capture(root, "等着")
    monkeypatch.setattr(turn_v3, "ADAPTER_FACTORY", lambda root_, provider: fake)
    turn_v3.STREAM.update(on_text=lambda t: None, on_event=None, shown=False)
    try:
        with bb.turn(30, root=root) as hits, bb.beat("world", 20, root=root, reserve=0):
            bb.wrap_up(root, grace=2.0)  # the page asked to wrap up before the prose started
            out = turn_v3.solve_turn(root, user_text="等着", provider=None, turn=1, soul_reports=[])
    finally:
        turn_v3.STREAM.update(on_text=None, on_event=None, shown=False)
    assert turn_rescue.cut_of(list(hits))
    tr = TurnTrace(turn_seq=1, player_input="等着")
    tr.apply = {"narration_plain": out["narration"], "annotated": out["annotated"], "applied": [], "options": []}
    append_turn_trace(root, "main", tr)
    assert turn_rescue.after_turn(root, success=True, timeouts=list(hits))["continue"]
    msgs = [Message(role="assistant", content=out["narration"])]  # the beat's short line (nothing was written)
    got = turn_rescue.continue_turn(root, on_text=lambda t: None, messages=msgs)
    assert got["ok"] and got["narration"] == "夜里很静。" and got["replaced_last"]  # the short line on screen goes
    assert msgs[-1].content == "夜里很静。"


def test_nothing_to_continue_without_a_cut(world, monkeypatch):
    root = world
    fake = _World(streams=[(["<lines>\n门开了。\n</lines>"], False)], writes=["<vars>\n</vars>"])
    turn_rescue.capture(root, "开门")
    _out, hits = _resolve(root, fake, monkeypatch, [])
    st = turn_rescue.after_turn(root, success=True, timeouts=hits)
    assert not st["cut"] and not st["continue"] and st["redo"]
    assert turn_rescue.continue_turn(root)["ok"] is False


# ── real-run shapes (10-25 niko's two runs) ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("cut, kept", [
    ("矮门在身后重新锁上。罗文往前走了二十来步,蹲下摸了摸地面,才把罩", "矮门在身后重新锁上。"),  # S[20]
    ("夜见:「书签是读者写给我的一行字。」「有人用过。", "夜见:「书签是读者写给我的一行字。」"),  # an unclosed line goes whole
    ("第一行。\n没有一句写完的半行", "第一行。"),
    ("He stopped. Then he said \"wait", "He stopped."),
    ("她低声说:「别走」", "她低声说:「别走」"),  # already whole
    ("完整一句。", "完整一句。"),
])
def test_trim_cut_ends_on_a_whole_sentence(cut, kept):
    assert trim_cut(cut) == kept


def test_the_timeout_line_is_known_in_every_language():
    from neonrp import prompts

    for lg in ("zh", "en", "ja", "ko"):
        assert is_timeout_line(prompts.strings("turn_v3", lg)["beat_timeout"])
    assert not is_timeout_line("门开了。")


def test_an_ask_whose_answer_stalls_keeps_the_prose_and_its_place(world, monkeypatch):
    """S[37]: the prose (308 characters, a new cave, [ask 罗文]) streamed; the continuation after her answer stalled and
    the beat ran out → the player read 「这一拍超时了」 while the move into the cave landed. Now the prose stays."""
    root = world
    fake = _World(
        streams=[(["<lines>\n你侧身挤进石缝,走了二十来步,缝忽然松开。\n", "灯照亮一间不大的石室。\n[ask 艾琳娜]\n</lines>"], False),
                 ([], True)],  # the continuation: nothing, the connection gone
        writes=["", "<vars>\n</vars>"])
    asked: list[str] = []

    def ask(who, text):
        asked.append(who)
        bb.wrap_up(root, grace=3.0)  # her answer took the rest of the beat
        return {"ok": True, "text": "「好地方。」"}

    monkeypatch.setattr(turn_v3, "ADAPTER_FACTORY", lambda root_, provider: fake)
    turn_v3.STREAM.update(on_text=lambda t: None, on_event=None, shown=False)
    try:
        with bb.turn(30, root=root) as hits, bb.beat("world", 20, root=root, reserve=0):
            out = turn_v3.solve_turn(root, user_text="往前走", provider=None, turn=1, soul_reports=[], ask_soul=ask)
    finally:
        turn_v3.STREAM.update(on_text=None, on_event=None, shown=False)
    assert asked == ["si-elena0001"]
    assert "灯照亮一间不大的石室。" in out["narration"] and not is_timeout_line(out["narration"])
    assert any(h["beat"] == "world" for h in hits)


def test_a_beat_that_wrote_nothing_lands_no_change(world, monkeypatch):
    """Nothing written in time: the short notice, and no write-down — a change nobody can read about does not land."""
    root = world
    gold = load_registry(root).variables["player.gold"].value
    fake = _World(streams=[([], True)], writes=["", f"<vars>\nplayer.gold = {gold - 7}\n</vars>"])
    monkeypatch.setattr(turn_v3, "ADAPTER_FACTORY", lambda root_, provider: fake)
    turn_v3.STREAM.update(on_text=lambda t: None, on_event=None, shown=False)
    try:
        with bb.turn(30, root=root), bb.beat("world", 20, root=root, reserve=0):
            bb.wrap_up(root, grace=2.0)
            out = turn_v3.solve_turn(root, user_text="等着", provider=None, turn=1, soul_reports=[])
    finally:
        turn_v3.STREAM.update(on_text=None, on_event=None, shown=False)
    assert is_timeout_line(out["narration"])
    assert load_registry(root).variables["player.gold"].value == gold
    assert not any("player.gold" in p for p in fake.plain)  # no write-down was asked


# ── a talk cut by time (10-25 niko: 商量拍时间过长时,已经生成的内容不要浪费了) ────────────────────────────────────────

def test_a_cut_talk_with_no_world_beat_after_it_is_continued_as_talk(tmp_path):
    root = tmp_path / "run"
    (root / "game").mkdir(parents=True)
    turn_rescue.capture(root, "我们先进镇")
    st = turn_rescue.after_turn(root, success=True, timeouts=[{"beat": "plan", "where": "stream.cut", "chars": 40}])
    assert st["continue"] and st["resume"] == "talk" and st["cut"][0]["beat"] == "plan"
    # settled with no time left for the world's beat (beat_budget.carve → plan.advance): that is a cut talk too
    st = turn_rescue.after_turn(root, success=True, timeouts=[{"beat": "plan", "where": "plan.advance"}])
    assert st["resume"] == "talk"
    # played on and failed (the talk said nothing): the line stays cut, still to be continued
    st = turn_rescue.after_turn(root, success=False, timeouts=[], resumed=True)
    assert st["resume"] == "talk" and st["continued"] == 0
    st = turn_rescue.after_turn(root, success=True, timeouts=[], resumed=True)
    assert not st["continue"] and st["continued"] == 1
    turn_rescue.forget(root)


def test_a_talk_cut_before_a_world_beat_that_finished_is_not_continued(tmp_path):
    root = tmp_path / "run"
    (root / "game").mkdir(parents=True)
    turn_rescue.capture(root, "开门")
    turn_rescue.offer(root, narration="门开了。")  # the world's beat ran and finished
    st = turn_rescue.after_turn(root, success=True, timeouts=[{"beat": "plan", "where": "stream.cut"}])
    assert not st["continue"] and st["resume"] is None and st["cut"]  # marked, nothing to go on with
    turn_rescue.forget(root)


def test_resuming_talk_is_only_inside_its_block():
    assert turn_rescue.resuming() is None
    with turn_rescue.resuming_talk("进镇"):
        assert turn_rescue.resuming() == "进镇"
    assert turn_rescue.resuming() is None
