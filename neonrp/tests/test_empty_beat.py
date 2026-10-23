"""A beat in which nobody said anything is a failed turn, not an empty beat (niko 10-18 on the phone: 「输入后没回复」).

归乡: the host's call took the whole 20 s beat and wrote nothing — an empty planning beat landed with only the player's
line; her reply was cut to nothing and 「莲妹:」 stood alone in the narration. 香料魔女: the host came back empty in 1.8 s
— the platform had refused a guest (403 guest_not_allowed) and the turn said nothing about it.
The planning-beat tests need the private layer (requires_private.txt); the engine's own parts run on the open engine."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from neonrp.core import billing_stop
from neonrp.core.llm import LLMTurnResult, Message
from neonrp.core.registry import load_registry
from neonrp.core.stream_lines import stream_chat

_GUEST = {"error": {"message": "Sign in with a Worldlines account to use the API.", "type": "invalid_request_error",
                    "code": "guest_not_allowed"}}


# ── the engine: a guest refusal is a stop the page can act on; an empty reply says why ─────────────────────────────

def test_a_guest_refusal_is_a_sign_in_stop_with_its_own_code():
    stop = billing_stop.from_body(403, _GUEST)
    assert stop is not None and stop.code == "guest_not_allowed" and stop.kind == "guest"
    back = billing_stop.from_text(stop.error_text())  # the marker travels in the turn's error text
    assert back is not None and back.code == "guest_not_allowed" and back.kind == "guest"
    d = stop.to_dict()
    assert all(d["messages"][lg] and "Worldlines" in d["messages"][lg] for lg in ("zh", "en", "ja", "ko"))
    w = billing_stop.from_body(403, {"error": {"code": "guest_world_only"}})
    assert w is not None and w.code == "guest_world_only" and w.kind == "guest"
    assert billing_stop.from_body(401, _GUEST) is None  # only the platform's 403 says it
    assert billing_stop.from_body(403, {"error": {"code": "forbidden"}}) is None


def test_an_empty_reply_carries_why_it_is_empty():
    class _Refused:  # the adapter turns a refused call into a result with an error (llm_openai), not an exception
        def chat(self, messages):
            return LLMTurnResult(error="refused [worldlines-billing:guest_not_allowed kind=guest]", finished=True)

    class _DropsThenRefuses(_Refused):
        def chat_stream(self, messages):
            raise RuntimeError("stream dropped")
            yield  # noqa: unreachable — a generator

    class _Says:
        def chat(self, messages):
            return LLMTurnResult(message=Message(role="assistant", content="<lines>\n好。\n</lines>"), finished=True)

    msgs = [Message(role="user", content="hi")]
    st: dict = {}
    assert stream_chat(_Refused(), msgs, None, state=st)[0] == "" and "guest_not_allowed" in st["error"]
    st = {}
    assert stream_chat(_DropsThenRefuses(), msgs, lambda t: None, state=st)[0] == "" and "guest_not_allowed" in st["error"]
    st = {"error": "old"}
    assert stream_chat(_Says(), msgs, None, state=st)[0] and "error" not in st


# ── the planning beat (private layer) ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def table(tmp_path, monkeypatch):
    from test_conversation import _setup_project
    from test_system_one_turn import _world

    monkeypatch.setenv("NEONRP_TURN_V3", "1")
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    monkeypatch.setenv("NEONRP_PLAN_LOOP", "1")
    monkeypatch.delenv("NEONRP_SYSTEM_ONE", raising=False)
    return _world(_setup_project(tmp_path))


def _send(root, text):
    from neonrp.core.conversation import ConversationSession
    from neonrp.core.orchestration_trace import read_turn_traces

    s = ConversationSession(root, "test-agent", mode="play")
    n0 = len(read_turn_traces(root, "main"))
    res = s.send(text)
    return s, res, read_turn_traces(root, "main")[n0:]


def test_a_host_out_of_time_with_nothing_said_fails_the_turn_instead_of_landing_an_empty_beat(table, monkeypatch):
    from neonrp.core import beat_budget, plan_loop

    def host(root_, system, user):  # the call used the whole beat and wrote nothing (归乡 10-18: 19.8 s of a 20 s beat)
        beat_budget.note("stream.fallback")
        return ""

    monkeypatch.setattr(plan_loop, "_host", host)
    s, res, new = _send(table, "翻开族谱最后一页")
    assert not res.success and "[beat-failed:plan why=timeout]" in (res.error or "")
    assert new == [], "no empty planning beat landed"
    assert not any(m.role == "assistant" and not (m.content or "").strip() for m in s.messages)
    assert res.timeouts and res.timeouts[0]["beat"] == "plan"  # turn_done.timeouts: the page can say the beat ran out
    assert plan_loop.load(table) == {}, "the talk did not move: the line can be sent again"


def test_a_guest_refused_host_fails_the_turn_with_the_sign_in_code(table, monkeypatch):
    from neonrp.commands.web import _billing_payload
    from neonrp.core import turn_v3

    err = billing_stop.from_body(403, _GUEST).error_text()
    monkeypatch.setattr(turn_v3, "_adapter", lambda *a, **k: SimpleNamespace(chat=lambda msgs: LLMTurnResult(error=err, finished=True)))
    monkeypatch.setattr("neonrp.core.light_chat.ask_soul_deliver", lambda *a, **k: {"ok": False, "answer": ""})
    _s, res, new = _send(table, "直接走向城门,自称「来自东方的香料商人」")
    assert not res.success and new == []
    assert "[beat-failed:plan why=error]" in res.error
    b = _billing_payload(res.error)  # what turn_done.billing carries for the page
    assert b and b["code"] == "guest_not_allowed" and b["kind"] == "guest"


def test_a_character_who_said_nothing_gets_no_empty_name_line(table, monkeypatch):
    from neonrp.core import plan_loop

    soul = next(e for e in load_registry(table).of_class("soul") if e.parent == load_registry(table).player_location)
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user:
                        f"<lines>\n她攥着那把香,抬头看你。\n</lines>\n<mic>\n{soul.name}: 你想问哪样?\n</mic>\nnext: wait")
    monkeypatch.setattr("neonrp.core.light_chat.ask_soul_deliver", lambda *a, **k: {"ok": True, "answer": ""})  # cut to nothing
    _s, res, new = _send(table, f"@{soul.name}")
    assert res.success and new
    beat = new[-1]["apply"]["beat"]
    narration = new[-1]["apply"]["narration_plain"]
    assert "她攥着那把香" in narration and f"{soul.name}:" not in narration
    assert not [x for x in beat["script"] if x["role"] == "soul"], json.dumps(beat["script"], ensure_ascii=False)
    assert beat["mic"] == [soul.id]  # she was asked; she just said nothing


# ── 10-19: the talk may use the whole turn · a reply cut by the beat's time is kept · ms to the first chunk ───────────

def test_a_talk_beat_may_use_the_whole_turn_and_carves_the_worlds_share_when_it_resolves():
    import time

    from neonrp.core import beat_budget as bb

    with bb.turn(30.0):
        with bb.beat("plan", bb.talk_seconds(None), reserve=0.0) as b:
            assert b.deadline == pytest.approx(bb._TURN.get().deadline, abs=0.01)  # not 20 s, not 30 − 10
            assert bb.carve(10.0) and bb.remaining() == pytest.approx(bb.turn_remaining() - 10.0, abs=0.01)
        with bb.beat("plan", bb.talk_seconds(None), reserve=0.0):
            bb._TURN.get().deadline = time.monotonic() + 4.0  # the talk used most of the turn
            assert not bb.carve(10.0) and bb.hits()[-1]["where"] == "carve"
    assert bb.carve(10.0)  # no turn budget: nothing to carve


def test_a_stream_cut_by_the_beats_time_keeps_what_it_wrote_and_logs_the_first_chunk():
    from neonrp.core import beat_budget as bb
    from neonrp.core.llm import StreamChunk

    class _Cut:
        def chat(self, messages):
            raise AssertionError("no plain call after a cut stream")

        def chat_stream(self, messages):
            yield StreamChunk(delta="<lines>\n她点点头,说:「跟我来。」\n他")
            bb.current().deadline = 0.0  # the beat's time runs out mid-reply
            yield StreamChunk(error="beat timeout (stream)", finished=True)

    shown: list[str] = []
    st: dict = {}
    with bb.turn(30.0), bb.beat("plan", 20.0):
        text, was_shown = stream_chat(_Cut(), [Message(role="user", content="hi")], shown.append, state=st)
        logged = bb.calls()
    assert "跟我来" in text and was_shown and st["truncated"] and "error" not in st
    assert st["first_ms"] is not None and st["ms"] >= st["first_ms"]
    assert logged and logged[-1]["beat"] == "plan" and logged[-1]["truncated"] and logged[-1]["first_ms"] is not None


def test_the_planning_beat_runs_on_the_whole_turn_not_one_beat(table, monkeypatch):
    from neonrp.core import beat_budget as bb, plan_loop

    seen: dict = {}

    def host(root_, system, user):
        seen.update(left=bb.remaining(), turn=bb.turn_remaining())
        return "<lines>\n铺子里没人。\n</lines>\nnext: wait"

    monkeypatch.setattr(plan_loop, "_host", host)
    _s, res, _new = _send(table, "我四处看看")
    assert res.success and seen["left"] > 25.0 and seen["left"] == pytest.approx(seen["turn"], abs=0.5)


def test_a_host_reply_cut_by_the_beats_time_is_the_beats_words_marked_truncated(table, monkeypatch):
    from neonrp.core import beat_budget as bb, turn_v3
    from neonrp.core.llm import StreamChunk

    class _Cut:
        def chat(self, messages):
            raise AssertionError("no plain call after a cut stream")

        def chat_stream(self, messages):
            yield StreamChunk(delta="<lines>\n族谱最后一页的墨还是湿的,七个名字挤在一起。你凑近")
            bb.current().deadline = 0.0
            yield StreamChunk(error="beat timeout (stream)", finished=True)

    monkeypatch.setattr(turn_v3, "_adapter", lambda *a, **k: _Cut())
    _s, res, new = _send(table, "翻开族谱最后一页")
    assert res.success and new, res.error
    beat = new[-1]["apply"]["beat"]
    assert beat["kind"] == "plan" and beat["truncated"] and "七个名字挤在一起" in new[-1]["apply"]["narration_plain"]
    host = beat["calls"][0]
    assert host["who"] == "host" and host["truncated"] and host["first_ms"] is not None


def test_a_talk_that_settles_too_late_for_the_world_resolves_on_the_next_line(table, monkeypatch):
    import time

    from neonrp.core import beat_budget as bb, plan_loop

    def late(root_, system, user):  # the host took the turn: 4 s are left when it says advance
        bb._TURN.get().deadline = time.monotonic() + 4.0
        return "<lines>\n那就走。\n</lines>\n<board>\n玩家: 出发去主街\n</board>\nnext: advance"

    monkeypatch.setattr(plan_loop, "_host", late)
    _s, res, new = _send(table, "@dm 走吧")
    assert res.success and res.route_decision == "plan_loop:plan"
    beat = new[-1]["apply"]["beat"]
    assert beat["kind"] == "plan" and beat["advance_deferred"] and "那就走" in new[-1]["apply"]["narration_plain"]
    assert plan_loop.load(table)["advance_deferred"] == beat["advance_deferred"]
    _s, res2, new2 = _send(table, "好")
    assert res2.route_decision != "plan_loop:plan"
    assert any((t["apply"].get("beat") or {}).get("advanced_by") == beat["advance_deferred"] for t in new2)
    assert not plan_loop.load(table).get("advance_deferred")
