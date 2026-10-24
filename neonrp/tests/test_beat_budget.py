"""A beat's time budget (core/beat_budget, 10-14: 「一拍 ~10 秒、不超 20 秒,超过直接 timeout」).

Timings are scaled down (a 1 s beat stands for the 20 s default) so the suite stays fast; what is checked is the shape:
a hanging model, a stalled stream and an endless tool loop all end inside the beat (plus the world's settle grace),
the turn lands, and the result carries a ``timeouts`` mark.
"""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from neonrp.core import beat_budget as bb
from neonrp.core.llm import LLMTurnResult, Message, StreamChunk, ToolCall


@pytest.fixture(autouse=True)
def _fast_beats(monkeypatch):
    monkeypatch.setenv("NEONRP_BEAT_TIMEOUT_S", "1.0")
    monkeypatch.setenv("NEONRP_LLM_CALL_TIMEOUT_S", "1.0")
    monkeypatch.setenv("NEONRP_LLM_STALL_S", "0.5")
    monkeypatch.setenv("NEONRP_BEAT_SETTLE_S", "0.4")
    monkeypatch.setenv("NEONRP_TURN_TIMEOUT_S", "1.5")  # 30 s, scaled like the beats (20 s → 1 s)
    monkeypatch.setenv("NEONRP_TURN_WORLD_RESERVE_S", "0.5")  # 10 s


# ── the budget itself ────────────────────────────────────────────────────────

def test_defaults_without_env(monkeypatch):
    for k in ("NEONRP_BEAT_TIMEOUT_S", "NEONRP_LLM_CALL_TIMEOUT_S", "NEONRP_LLM_STALL_S", "NEONRP_BEAT_SETTLE_S",
              "NEONRP_TURN_TIMEOUT_S", "NEONRP_TURN_WORLD_RESERVE_S"):
        monkeypatch.delenv(k, raising=False)
    assert (bb.beat_timeout_s(), bb.call_cap_s(), bb.stall_s(), bb.settle_s()) == (20.0, 20.0, 15.0, 8.0)
    assert (bb.turn_timeout_s(), bb.world_reserve_s()) == (30.0, 10.0)


def test_the_turn_budget_reads_the_engine_config(tmp_path, monkeypatch):
    monkeypatch.delenv("NEONRP_TURN_TIMEOUT_S", raising=False)
    (tmp_path / ".neonrp").mkdir()
    (tmp_path / ".neonrp" / "playthrough.json").write_text(json.dumps({"engine": {"turn": {"turn_timeout_s": 45}}}), encoding="utf-8")
    assert bb.turn_timeout_s(tmp_path) == 45.0
    monkeypatch.setenv("NEONRP_TURN_TIMEOUT_S", "12")  # env first
    assert bb.turn_timeout_s(tmp_path) == 12.0


# ── the whole turn (10-14: 「整回合总上限 30 秒」) ─────────────────────────

def test_beats_share_what_is_left_of_the_turn():
    with bb.turn() as sink:
        with bb.beat("plan"):
            assert 0.9 < bb.remaining() <= 1.0  # the beat's own 1 s: the turn has 1.5
            time.sleep(0.7)
        with bb.beat("souls"):
            assert bb.remaining() <= 0.81  # 1.5 − 0.7: less than a whole beat is left
            time.sleep(0.85)
            assert bb.expired()
            bb.note("llm.call")
    assert sink == [{"beat": "souls", "where": "llm.call", "ms": sink[0]["ms"], "turn": True}]


def test_the_beats_before_the_world_leave_its_share(monkeypatch):
    # a clock the test moves (10-19: on a loaded box the wall clock made r 0.52 where the budget says 0.7)
    clock = [1000.0]
    monkeypatch.setattr(bb, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    with bb.turn():  # 1.5 s
        clock[0] += 0.4
        with bb.beat("souls", reserve=bb.world_reserve_s()):
            assert bb.remaining() == pytest.approx(1.5 - 0.4 - 0.5)  # the turn's end less the world's share
        with bb.beat("world", reserve=bb.settle_s()):
            r = bb.remaining()
            assert r == pytest.approx(1.5 - 0.4 - 0.4)  # the prose ends settle_s before the turn
            clock[0] += r + 0.02
            bb.grant(bb.settle_s(), "world.settle")  # … and the state transition gets exactly that
            assert bb.remaining() == pytest.approx(0.4 - 0.02) and bb.remaining() == pytest.approx(bb.turn_remaining())


def test_a_grant_never_outlives_the_turn():
    with bb.turn(0.3), bb.beat("world"):
        assert bb.remaining() <= 0.3
        bb.grant(5.0)
        assert bb.remaining() <= 0.3
        with bb.at_least(5.0):
            assert bb.remaining() <= 0.3


def test_a_turn_with_no_time_left_starts_its_beat_over(monkeypatch):
    client = _FakeClient(hang=30.0)
    a = _openai_adapter(client)
    with bb.turn(0.2) as sink:
        time.sleep(0.25)
        with bb.beat("world"):
            res = a.chat([Message(role="user", content="hi")])
    assert res.error and not client.calls  # no call made after the turn ended
    assert sink and sink[0]["turn"] is True


def test_the_turn_off_keeps_the_beats_as_they_were(monkeypatch):
    monkeypatch.setenv("NEONRP_TURN_TIMEOUT_S", "0")
    with bb.turn(), bb.beat("souls", reserve=0.5):
        assert 0.9 < bb.remaining() <= 1.0
        assert bb.turn_remaining() is None


def test_worker_threads_carry_the_turn():
    with bb.turn(), bb.beat("souls"):
        time.sleep(0.6)

        def job(_i: int) -> float | None:
            return bb.turn_remaining()

        with ThreadPoolExecutor(max_workers=2) as ex:
            got = list(ex.map(bb.carry(job), range(2)))
    assert all(r is not None and r <= 0.9 for r in got)


@pytest.mark.parametrize("platform", ["darwin", "ios", "emscripten"])
def test_every_runtime_sizes_its_requests_to_the_turn(monkeypatch, platform):
    """Local (httpx) · iOS (httpx on the device) · the browser (Pyodide: one XHR whose timeout is httpx's read): the
    request a beat makes late in the turn times out when the turn ends, not when a whole beat would."""
    import sys

    import httpx  # noqa: F401 — imported before the clock starts (a cold import takes longer than the scaled turn)

    from neonrp.core.llm_openai import OpenAIAdapter

    monkeypatch.setattr(sys, "platform", platform)
    c = _FakeClient()
    with bb.turn():
        time.sleep(0.9)
        with bb.beat("world"):
            for stream in (False, True):
                t = OpenAIAdapter._beat_client(c, stream=stream).options["timeout"]
                assert t.read <= 0.61 and t.connect <= 0.61, (platform, stream, t)


def test_outside_a_beat_nothing_changes():
    assert bb.remaining() is None and bb.call_timeout() is None and not bb.expired()
    bb.check("x")  # no beat: never raises
    bb.note("x")
    assert bb.hits() == []


def test_beat_deadline_note_and_collect():
    with bb.collect() as sink:
        with bb.beat("souls"):
            assert 0.9 < bb.remaining() <= 1.0
            assert bb.call_timeout() <= 1.0
            time.sleep(1.05)
            assert bb.expired()
            with pytest.raises(bb.BeatTimeout):
                bb.check("llm.call")
            bb.note("llm.call")  # once per beat and place
        assert bb.remaining() is None
    assert [(h["beat"], h["where"]) for h in sink] == [("souls", "llm.call")]


def test_inner_beat_never_outlives_outer():
    with bb.beat("outer", 0.3):
        with bb.beat("inner", 5.0):
            assert bb.remaining() <= 0.3


def test_grant_gives_the_settle_call_time():
    with bb.collect() as sink, bb.beat("world", 0.05):
        time.sleep(0.06)
        assert bb.expired()
        bb.grant(0.4, "world.settle")
        assert not bb.expired() and bb.remaining() > 0.3
    assert sink[0]["where"] == "world.settle"


def test_off_when_zero(monkeypatch):
    monkeypatch.setenv("NEONRP_BEAT_TIMEOUT_S", "0")
    with bb.beat("world") as b:
        assert b is None and bb.remaining() is None


def test_worker_threads_carry_the_beat():
    with bb.collect() as sink, bb.beat("souls"):
        def job(i: int) -> float | None:
            bb.note(f"soul{i}")
            return bb.remaining()

        with ThreadPoolExecutor(max_workers=3) as ex:
            got = list(ex.map(bb.carry(job), range(3)))
    assert all(r is not None and r <= 1.0 for r in got)
    assert sorted(h["where"] for h in sink) == ["soul0", "soul1", "soul2"]


# ── the OpenAI adapter: a model that does not answer for 30 s ─────────────────

class _Completions:
    """chat.completions of a fake OpenAI client: each create waits for the request's own timeout (as httpx would), up
    to ``hang`` seconds, then raises a timeout — the provider that never answers."""

    def __init__(self, owner: "_FakeClient", hang: float, stream_chunks: list[str] | None = None):
        self.owner, self.hang, self.stream_chunks = owner, hang, stream_chunks

    def create(self, **kw):
        import httpx
        import openai

        self.owner.calls.append(kw)
        t = self.owner.timeout
        if kw.get("stream") and self.stream_chunks is not None:
            read = t.read if isinstance(t, httpx.Timeout) else t

            def gen():
                for c in self.stream_chunks:
                    yield SimpleNamespace(usage=None, choices=[SimpleNamespace(
                        delta=SimpleNamespace(content=c, tool_calls=None, reasoning_content=None, reasoning=None), finish_reason=None)])
                time.sleep(min(self.hang, read or self.hang))  # the stall: no next chunk until the read timeout fires
                raise httpx.ReadTimeout("stalled")

            return gen()
        wait = min(self.hang, (t.read if isinstance(t, httpx.Timeout) else t) or self.hang)
        time.sleep(wait)
        raise openai.APITimeoutError(request=httpx.Request("POST", "https://example.invalid/v1/chat/completions"))


class _FakeClient:
    def __init__(self, hang: float = 30.0, stream_chunks: list[str] | None = None, *, _shared=None, timeout=None, max_retries=2):
        self.calls = _shared if _shared is not None else []
        self.timeout, self.max_retries = timeout, max_retries
        self._hang, self._stream_chunks = hang, stream_chunks
        self.chat = SimpleNamespace(completions=_Completions(self, hang, stream_chunks))

    def with_options(self, *, timeout=None, max_retries=None):
        c = _FakeClient(self._hang, self._stream_chunks, _shared=self.calls, timeout=timeout, max_retries=max_retries)
        c.options = {"timeout": timeout, "max_retries": max_retries}
        self.last_options = c.options
        return c


def _openai_adapter(client: _FakeClient):
    from neonrp.core.llm_openai import OpenAIAdapter

    a = OpenAIAdapter(model="m", api_key="k", base_url="https://example.invalid/v1")
    a._client = client
    return a


def test_hanging_model_ends_inside_the_beat():
    client = _FakeClient(hang=30.0)
    a = _openai_adapter(client)
    t0 = time.monotonic()
    with bb.collect() as sink, bb.beat("souls"):
        res = a.chat([Message(role="user", content="hi")])
    took = time.monotonic() - t0
    # one 1 s request timeout, no SDK retries, no ladder retry without time left — read from the request itself (its
    # timeout is what was left of the 1 s beat, and it was made once), not the wall clock: on a loaded box (10-19,
    # load 26) the same single 1 s call took 3.8 s. The wall bound only says it did not wait for the 30 s hang.
    t = client.last_options["timeout"]
    assert (getattr(t, "read", None) or t) <= 1.0 + 1e-6, t
    assert took < 15.0, took
    assert res.error and "beat timeout" in res.error
    assert client.last_options["max_retries"] == 0  # the SDK does not retry on its own inside a beat
    assert len(client.calls) == 1
    assert sink and sink[0]["beat"] == "souls"


def test_expired_beat_makes_no_call():
    client = _FakeClient(hang=30.0)
    a = _openai_adapter(client)
    with bb.beat("world", 0.01):
        time.sleep(0.02)
        res = a.chat([Message(role="user", content="hi")])
    assert res.error and not client.calls


def test_outside_a_beat_the_client_is_untouched():
    from neonrp.core.llm_openai import OpenAIAdapter

    c = _FakeClient()
    assert OpenAIAdapter._beat_client(c, stream=False) is c


def test_stalled_stream_ends_inside_the_beat_without_a_second_whole_call():
    from neonrp.core.stream_lines import stream_chat

    client = _FakeClient(hang=30.0, stream_chunks=["<lines>她抬起头,", "看了你一眼"])
    a = _openai_adapter(client)
    shown: list[str] = []
    t0 = time.monotonic()
    with bb.collect() as sink, bb.beat("souls"):
        text, was_shown = stream_chat(a, [Message(role="user", content="hi")], shown.append)
    took = time.monotonic() - t0
    assert took < 1.6, took
    assert "她抬起头" in text and was_shown  # what came before the stall is kept
    stream_t = client.calls and client.last_options["timeout"]
    assert stream_t.read <= 0.5 + 1e-6  # a stream inside a beat: no chunk for `stall` seconds = stalled
    assert any(h["beat"] == "souls" for h in sink) or took < 1.6


class _StallThenSlowAdapter:
    """chat_stream stalls before any text (as a dropped deepseek stream), chat() would take 30 s."""

    def __init__(self):
        self.plain_calls = 0

    def chat_stream(self, messages, tools=None):
        time.sleep(bb.remaining() or 0)  # stalls until the beat is over
        yield StreamChunk(error="stalled", finished=True)

    def chat(self, messages, tools=None):
        self.plain_calls += 1
        time.sleep(30)
        return LLMTurnResult(message=Message(role="assistant", content="late"))


def test_stream_stall_skips_the_plain_fallback_when_the_beat_is_over():
    from neonrp.core.stream_lines import stream_chat

    a = _StallThenSlowAdapter()
    t0 = time.monotonic()
    with bb.collect() as sink, bb.beat("plan"):
        text, shown = stream_chat(a, [Message(role="user", content="hi")], lambda t: None)
    assert time.monotonic() - t0 < 1.5
    assert text == "" and a.plain_calls == 0
    assert any(h["where"] == "stream.fallback" for h in sink)


# ── the tool loop: a model that calls tools forever ──────────────────────────

def _init_project(root: Path) -> None:
    from neonrp.core.manifest import Manifest
    from neonrp.core.paths import get_manifest_path

    nd = root / ".neonrp"
    (nd / "sessions").mkdir(parents=True, exist_ok=True)
    (nd / "events").mkdir(parents=True, exist_ok=True)
    (root / "game" / "meta").mkdir(parents=True, exist_ok=True)
    (nd / "config.json").write_text(json.dumps({"llm": {"provider": "stub", "max_context_chars": 100000}}), encoding="utf-8")
    m = Manifest()
    m.branches["main"].head_event = -1
    get_manifest_path(root).write_text(json.dumps(m.model_dump(), default=str), encoding="utf-8")
    ad = root / "agents" / "test-agent"
    ad.mkdir(parents=True, exist_ok=True)
    (ad / "agent.json").write_text(json.dumps({"id": "test-agent", "name": "T", "permissions": {
        "read_globs": ["**"], "deny_globs": [], "write_globs": ["**"], "direct_write_globs": []}}), encoding="utf-8")
    (root / "game" / "a.md").write_text("a", encoding="utf-8")
    (root / "game" / "b.md").write_text("b", encoding="utf-8")


class _CycleReadAdapter:
    """Re-reads the same two files round after round (A B A B …, the 09-21 world-agent pattern) and never answers."""

    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        path = "game/a.md" if self.calls % 2 else "game/b.md"
        tc = ToolCall(id=f"r{self.calls}", name="read_file", arguments={"path": path})
        return LLMTurnResult(message=Message(role="assistant", content=f"看一眼 {path}", tool_calls=[tc]), tool_calls=[tc], finished=False)


class _SlowNewToolAdapter:
    """A different tool call every round, each taking 0.3 s: only the beat's clock stops it."""

    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        time.sleep(0.3)
        tc = ToolCall(id=f"r{self.calls}", name="read_file", arguments={"path": "game/a.md", "max_chars": self.calls})
        return LLMTurnResult(message=Message(role="assistant", content=f"第{self.calls}轮", tool_calls=[tc]), tool_calls=[tc], finished=False)


def test_repeated_tool_calls_anywhere_in_the_loop_end_it(tmp_path):
    from neonrp.core.conversation import TOOL_REPEAT_MAX, TOOL_REPEAT_TRIPS, run_conversation_turn

    _init_project(tmp_path)
    a = _CycleReadAdapter()
    with patch("neonrp.core.conversation.get_adapter_from_config", return_value=a):
        res = run_conversation_turn(tmp_path, "test-agent", [Message(role="user", content="x")], max_turns=40)
    assert res.success and res.max_turns_reached  # the clean partial ending, not an error
    assert a.calls <= 2 * TOOL_REPEAT_MAX + TOOL_REPEAT_TRIPS + 1, a.calls  # not 40 rounds
    assert "看一眼" in (res.assistant_message or "")


def test_endless_tool_loop_ends_with_the_beat(tmp_path):
    from neonrp.core.conversation import run_conversation_turn

    _init_project(tmp_path)
    a = _SlowNewToolAdapter()
    t0 = time.monotonic()
    with bb.collect() as sink, bb.beat("souls"):
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=a):
            res = run_conversation_turn(tmp_path, "test-agent", [Message(role="user", content="x")], max_turns=40)
    took = time.monotonic() - t0
    assert took < 1.8, took
    assert res.success and a.calls <= 5
    assert any(h["where"] == "agent_loop" for h in sink)


# ── a whole turn: every model call hangs ─────────────────────────────────────

class _HangAdapter:
    """Every call waits as long as its request would be allowed to (the beat's call timeout), then fails like an HTTP
    timeout — a provider that does not answer for 30 s."""

    def __init__(self):
        self.calls = 0
        self.lock = threading.Lock()

    def _wait(self):
        with self.lock:
            self.calls += 1
        t = bb.call_timeout()
        time.sleep(min(30.0, t if t is not None else 30.0))
        bb.note("llm.call")

    def chat(self, messages, tools=None):
        self._wait()
        return LLMTurnResult(error="beat timeout (llm.call)", finished=True)

    def chat_stream(self, messages, tools=None):
        self._wait()
        yield StreamChunk(error="beat timeout (llm.call)", finished=True)


def _build(tmp_path: Path, tpl_id: str) -> Path:
    from neonrp import template

    tpl = Path(__file__).resolve().parents[1] / "worldlines" / "templates" / f"{tpl_id}.template"
    if not tpl.is_dir():
        pytest.skip(f"no template {tpl_id}")
    root = tmp_path / "run"
    template.build(template.load(tpl), root)
    nr = root / ".neonrp"
    nr.mkdir(exist_ok=True)
    if not (nr / "manifest.json").exists():
        from neonrp.core.manifest import Manifest

        m = Manifest()
        m.branches["main"].head_event = -1
        (nr / "manifest.json").write_text(json.dumps(m.model_dump(), default=str), encoding="utf-8")
    (nr / "config.json").write_text(json.dumps({"llm": {"provider": "stub", "model": "stub-model"}}), encoding="utf-8")
    return root


@pytest.mark.timeout(120)
def test_a_turn_with_a_hanging_model_lands_with_a_timeout_mark(tmp_path, monkeypatch):
    monkeypatch.setenv("NEONRP_PRIVATE", "off")
    monkeypatch.setenv("NEONRP_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    root = _build(tmp_path, "pct-house")
    from neonrp.core import light_chat, turn_v3
    from neonrp.core.conversation import ConversationSession

    hang = _HangAdapter()
    monkeypatch.setattr(turn_v3, "_adapter", lambda *a, **k: hang)
    monkeypatch.setattr(light_chat, "_adapter", lambda *a, **k: hang)
    s = ConversationSession(root, "world-agent", mode="play")
    with patch("neonrp.core.conversation.get_adapter_from_config", return_value=hang):
        s.send("开始游戏")
        t0 = time.monotonic()
        res = s.send("我四处看看,问问管家这三天发生了什么")
    took = time.monotonic() - t0
    # souls beat (1 s) + world beat (1 s) + settle grace (0.4 s) + engine work; 30 s per call without the budget
    assert took < 6.0, took
    assert res.success, res.error
    assert res.timeouts, "the result says which beat ran out of time"
    assert {h["beat"] for h in res.timeouts} & {"world", "souls"}
    assert (res.assistant_message or "").strip()  # never an empty reply: the short line when nothing was written


@pytest.mark.timeout(120)
def test_a_whole_turn_on_a_hanging_model_ends_inside_the_turn_budget(tmp_path, monkeypatch):
    """10-14: the whole turn ≤ 30 s (here 1.5 s), each beat ≤ 20 s (here 1 s). Without the turn budget the
    characters' beat (1 s) + the world's (1 s) + its settle (0.4 s) = 2.4 s of model waiting; with it every beat of the
    turn — its settle grant included — ends by the turn's deadline, and the world's beat keeps its settle share.
    Checked on the deadlines themselves (wall time on a loaded CI box is not the budget's to keep)."""
    monkeypatch.setenv("NEONRP_PRIVATE", "off")
    monkeypatch.setenv("NEONRP_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    root = _build(tmp_path, "pct-house")
    from neonrp.core import light_chat, turn_v3
    from neonrp.core.conversation import ConversationSession

    hang = _HangAdapter()
    monkeypatch.setattr(turn_v3, "_adapter", lambda *a, **k: hang)
    monkeypatch.setattr(light_chat, "_adapter", lambda *a, **k: hang)
    s = ConversationSession(root, "world-agent", mode="play")
    seen: list[dict] = []
    real_beat = bb.beat

    from contextlib import contextmanager

    @contextmanager
    def watched(name, seconds=None, **kw):
        with real_beat(name, seconds, **kw) as b:
            start = b.deadline if b is not None else None
            yield b
            t = bb._TURN.get()
            seen.append({"beat": name, "start": start, "end": b.deadline if b is not None else None,
                         "turn": t.deadline if t is not None else None, "turn_t0": t.t0 if t is not None else None})

    with patch("neonrp.core.conversation.get_adapter_from_config", return_value=hang):
        s.send("开始游戏")
        monkeypatch.setattr(bb, "beat", watched)
        res = s.send("我四处看看,问问管家这三天发生了什么")
    assert res.success and (res.assistant_message or "").strip()
    beats = [x for x in seen if x["turn"] is not None]
    assert {x["beat"] for x in beats} >= {"souls", "world"}, seen
    for x in beats:
        assert x["end"] <= x["turn"] + 1e-6, x  # no beat (nor the world's settle grant) outlives the turn
        # 10-19: the world's beat may push the turn by its floor; 10-21: the write-down after the prose by its own (half the turn)
        assert x["turn"] - x["turn_t0"] <= 1.5 + 0.6 * 1.5 + 0.5 * 1.5 + 0.01
    souls = next(x for x in beats if x["beat"] == "souls")
    world = next(x for x in beats if x["beat"] == "world")
    assert souls["start"] <= souls["turn"] - 0.5 + 1e-6  # the characters leave the world its share
    assert world["start"] <= world["turn"] - 0.4 + 1e-6  # the world's prose leaves its settle
    assert res.timeouts


@pytest.mark.timeout(60)
def test_a_planning_beat_that_never_converges_ends_inside_its_beat(tmp_path, monkeypatch):
    """A node-kind plugin running a host↔character talk loop (the planning beat's shape) on a model that hangs: the
    beat ends at its deadline and the reply is the short line, not silence."""
    monkeypatch.setenv("NEONRP_PRIVATE", "off")
    monkeypatch.setenv("NEONRP_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    root = _build(tmp_path, "pct-house")
    from neonrp.core import node_kinds
    from neonrp.core.conversation import ConversationSession, ConversationTurnResult
    from neonrp.core.stream_lines import stream_chat

    hang = _HangAdapter()

    class TalkLoop:
        kind = "plan"

        def active(self, root, user_text):
            return True

        def graph(self):
            return {"nodes": {"plan": {"kind": "loop", "title": "plan"}}, "edges": [], "start": "plan"}

        def take_turn(self, session, *, user_text, trace, run_id, on_chunk):
            said = []
            for _ in range(8):  # host → character → host … (the real loop caps rounds, not time)
                t, _shown = stream_chat(hang, [Message(role="user", content=user_text)], lambda x: None)
                if not t:
                    break
                said.append(t)
            return ConversationTurnResult(success=True, run_id=run_id, assistant_message="\n".join(said))

    # stand in for the planning beat only for this test: with the private layer loaded its own "plan" is in the
    # registry (and hidden while NEONRP_PRIVATE=off) — put it back afterwards, or every later test runs without it
    monkeypatch.setitem(node_kinds._REG, "plan", TalkLoop())
    monkeypatch.setattr(node_kinds, "_PRIVATE_KINDS", node_kinds._PRIVATE_KINDS - {"plan"})
    s = ConversationSession(root, "world-agent", mode="play")
    t0 = time.monotonic()
    res = s.send("@温妮 你先去书房看看")
    took = time.monotonic() - t0
    assert took < 3.0, took
    assert res.success and res.timeouts and res.timeouts[0]["beat"] == "plan"
    assert (res.assistant_message or "").strip()


def test_the_sdk_never_retries_under_our_ladder():
    """One retry ladder: the SDK's own 2 retries under our 3 made a stalled call wait 3 × 60 s (10-13 bench: a 189 s
    state transition right after 「Retryable error (attempt 1/3): Request timed out」)."""
    from neonrp.core.llm_openai import OpenAIAdapter

    with patch("openai.OpenAI") as cls:
        OpenAIAdapter(model="m", api_key="k", base_url="https://api.deepseek.com/v1")._get_client()
    assert cls.call_args.kwargs["max_retries"] == 0


def test_in_the_browser_a_stream_request_gets_the_whole_beat(monkeypatch):
    """Pyodide's transport is one synchronous XHR (no chunks): the stall limit would be a whole-reply limit there."""
    import sys

    from neonrp.core.llm_openai import OpenAIAdapter

    c = _FakeClient()
    with bb.beat("world"):
        assert OpenAIAdapter._beat_client(c, stream=True).options["timeout"].read <= 0.5 + 1e-6
        monkeypatch.setattr(sys, "platform", "emscripten")
        assert OpenAIAdapter._beat_client(c, stream=True).options["timeout"].read > 0.9
