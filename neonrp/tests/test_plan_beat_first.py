"""谈完接清算:商量拍的结果先推给玩家(10-14)。

A planning talk that ends in the switch lands as its own beat (its trace, its engine/beat events) before the Resolve
runs. /events (and the browser's onEvent, the same broadcast) forwards each beat's events the moment they land — the
page shows the talk as one segment while the Resolve is still being written — and does not send them again at
turn_done. A trace whose beat was not announced live is still caught up at the end.
"""
from __future__ import annotations

import queue
from pathlib import Path
from typing import Any

from neonrp.core import topics
from neonrp.core.message_bus import InProcessBus
from neonrp.core.orchestration_trace import TurnTrace, append_turn_trace


class _Session:
    """What WebRuntime._do_turn needs of a session; ``send`` plays a turn whose talk ends in the switch."""

    branch = "main"

    def __init__(self, root: Path, *, announce_resolve: bool = True):
        self.root, self.announce_resolve = root, announce_resolve
        self._bus = InProcessBus()
        self.seen_at_resolve: list[str] = []

    def bus(self):
        return self._bus

    def _land(self, kind: str, text: str, announce: bool) -> None:
        from neonrp.core import beat_events

        tr = TurnTrace(turn_seq=1, player_input="我们去码头")
        tr.apply = {"narration_plain": text, "beat": {"kind": kind, "script": [], "board": {"玩家": "去码头"},
                                                      **({"ended_by": "judge:settled"} if kind == "plan" else {"advanced_by": "judge:settled"})}}
        append_turn_trace(self.root, self.branch, tr)
        if announce:  # session._emit_beats
            evs, _ = beat_events.from_traces([tr.to_dict()], "plan")  # the session is in the plan node already
            for name, data in evs:
                self._bus.publish(topics.ENGINE_BEAT, {"kind": name, **data})

    def send(self, text: str):
        from types import SimpleNamespace

        self._bus.publish(topics.ENGINE_BEAT, {"kind": "node.enter", "node": "plan", "turn": 1})  # _enter_beat
        self._land("plan", "主持:好。\n艾琳娜:「我跟你去。」", True)
        self.seen_at_resolve = list(self.page)  # what the page had when the Resolve began
        self._bus.publish(topics.ENGINE_STREAM, {"kind": "chunk", "text": "雨停了,你们走向码头。"})
        self._land("resolve", "雨停了,你们走向码头。", self.announce_resolve)
        return SimpleNamespace(success=True, error=None, route_decision="plan_loop:resolve", assistant_message="雨停了", timeouts=None)


def _runtime(tmp_path: Path, **kw: Any):
    from neonrp.commands.web import WebRuntime

    rt = WebRuntime(tmp_path, "world-agent")
    s = _Session(tmp_path, **kw)
    rt._session = s
    rt._wire_bus(s)
    rt.positions = lambda: {"kind": "positions"}  # type: ignore[method-assign]
    q = rt.broadcast.register()
    s.page = _Drain(q)
    return rt, s, q


class _Drain:
    """The page's /events stream so far."""

    def __init__(self, q: queue.Queue):
        self.q, self.got = q, []

    def __iter__(self):
        while True:
            try:
                self.got.append(self.q.get_nowait())
            except queue.Empty:
                break
        return iter([e.get("kind") for e in self.got])


def test_the_talk_reaches_the_page_before_the_resolve_is_written(tmp_path):
    rt, s, _q = _runtime(tmp_path)
    rt._do_turn("我们去码头")
    assert s.seen_at_resolve == ["turn_start", "node.enter", "plan.beat"]  # the talk is on the page; the Resolve not yet
    plan = next(e for e in s.page.got if e.get("kind") == "plan.beat")
    assert plan["ended_by"] == "judge:settled" and "我跟你去" in plan["text"]  # the Resolve follows: the page may say so
    kinds = list(s.page)
    assert kinds.count("plan.beat") == 1 and kinds.count("resolve.beat") == 1, kinds  # not again at turn_done
    assert kinds.index("plan.beat") < kinds.index("chunk") < kinds.index("resolve.beat") < kinds.index("turn_done")


def test_a_beat_not_announced_live_is_caught_up_at_the_end(tmp_path):
    rt, s, _q = _runtime(tmp_path, announce_resolve=False)
    rt._do_turn("我们去码头")
    kinds = list(s.page)
    assert kinds.count("plan.beat") == 1 and kinds.count("resolve.beat") == 1, kinds
    assert kinds.index("resolve.beat") < kinds.index("turn_done")
    assert [e["node"] for e in s.page.got if e.get("kind") == "node.enter"] == ["plan", "resolve"]


def test_outside_a_turn_of_this_server_nothing_is_forwarded(tmp_path):
    rt, s, q = _runtime(tmp_path)
    s.bus().publish(topics.ENGINE_BEAT, {"kind": "plan.beat", "turn": 9})
    assert q.empty()
