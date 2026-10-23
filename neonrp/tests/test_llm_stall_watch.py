"""The LLM stall watch (「deepseek 理论上 cot 和中断状态我们都能检测到,不能干等」). On 10-13 one call in ten
sat 60–75 s: the provider kept the request open (keep-alives) without producing a token. A streamed call now closes and
resends when no token comes for NEONRP_LLM_FIRST_TOKEN_S (before the first) or NEONRP_LLM_STALL_GAP_S (between), and a
plain chat() is collected from that guarded stream. A local SSE server plays the provider."""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from neonrp.core.llm import Message
from neonrp.core.llm_openai import OpenAIAdapter, StreamStalled


class _Provider(BaseHTTPRequestHandler):
    plan: list[str] = []  # per streamed request, in order: "ok" · "hold" (keep-alives only) · "cut" (two tokens, then keep-alives)
    streamed = 0
    oneshot = 0
    bodies: list[dict] = []

    def log_message(self, *a):  # quiet
        pass

    def _sse(self, obj) -> None:
        self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
        self.wfile.flush()

    def _chunk(self, text: str, finish: str | None = None) -> dict:
        return {"id": "x", "object": "chat.completion.chunk", "created": 0, "model": "m",
                "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": finish}]}

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).bodies.append(body)
        if not body.get("stream"):
            type(self).oneshot += 1
            out = {"id": "x", "object": "chat.completion", "created": 0, "model": "m",
                   "choices": [{"index": 0, "message": {"role": "assistant", "content": "一次性的回答"}, "finish_reason": "stop"}],
                   "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
            data = json.dumps(out).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        mode = type(self).plan[type(self).streamed] if type(self).streamed < len(type(self).plan) else "ok"
        type(self).streamed += 1
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        try:
            if mode == "cut":
                self._sse(self._chunk("半"))
                self._sse(self._chunk("句"))
            if mode in ("hold", "cut"):
                for _ in range(40):  # the provider's keep-alives: bytes, no token
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    time.sleep(0.25)
                return
            for t in ("好", "的"):
                self._sse(self._chunk(t))
            self._sse(self._chunk("", "stop"))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


@pytest.fixture
def provider(monkeypatch):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Provider)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _Provider.plan, _Provider.streamed, _Provider.oneshot, _Provider.bodies = [], 0, 0, []
    monkeypatch.setenv("NEONRP_LLM_FIRST_TOKEN_S", "1.5")
    monkeypatch.setenv("NEONRP_LLM_STALL_GAP_S", "1.0")
    monkeypatch.setenv("NEONRP_LLM_STALL_RETRIES", "1")
    monkeypatch.setenv("NEONRP_LLM_API_KEY", "test")
    yield OpenAIAdapter(model="m", base_url=f"http://127.0.0.1:{srv.server_address[1]}/v1", api_key="test", max_retries=0)
    srv.shutdown()


def _msgs():
    return [Message(role="user", content="hi")]


def test_a_held_request_is_resent_instead_of_waited_out(provider):
    _Provider.plan = ["hold", "ok"]
    t0 = time.monotonic()
    text = "".join(c.delta for c in provider.chat_stream(_msgs()) if c.delta)
    assert text == "好的" and _Provider.streamed == 2
    assert time.monotonic() - t0 < 20, "cut at the first-token limit, not the 60 s read timeout"


def test_a_stream_cut_after_partial_text_raises_so_the_caller_starts_over(provider):
    _Provider.plan = ["cut"]
    seen = []
    with pytest.raises(StreamStalled):
        for c in provider.chat_stream(_msgs()):
            seen.append(c.delta)
    assert "".join(seen) == "半句"


def test_a_plain_chat_is_collected_from_the_guarded_stream(provider):
    _Provider.plan = ["hold", "ok"]
    r = provider.chat(_msgs())
    assert r.message.content == "好的" and _Provider.oneshot == 0 and _Provider.streamed == 2


def test_a_chat_that_stalls_every_time_falls_back_to_one_shot(provider):
    _Provider.plan = ["hold", "hold"]
    t0 = time.monotonic()
    r = provider.chat(_msgs())
    assert r.message.content == "一次性的回答" and _Provider.oneshot == 1
    assert time.monotonic() - t0 < 25  # slack for a loaded machine; the read timeout alone would be 60 s


def test_a_slow_caller_between_chunks_is_not_a_stall(provider):
    """The stream is not read while the caller works on a chunk (a tool answered mid-narration, a busy loop): that wait
    is the caller's, not the provider's — no resend (benchmark 10-15: 868 false mid-stream stalls)."""
    _Provider.plan = ["ok"]
    out = []
    for c in provider.chat_stream(_msgs()):
        if c.delta:
            out.append(c.delta)
            time.sleep(1.6)  # longer than the 1.0 s gap limit
    assert "".join(out) == "好的" and _Provider.streamed == 1


def test_mid_stream_has_no_limit_by_default(provider, monkeypatch):
    """Default: only the wait for the first token is cut; a pause after it is waited out (deepseek resumes)."""
    monkeypatch.delenv("NEONRP_LLM_STALL_GAP_S")
    from neonrp.core.llm_openai import _stall_limits

    assert _stall_limits()[1] == 0


def test_the_callers_thinking_switch_reaches_the_streamed_request(provider, monkeypatch):
    """10-22: the stream is read on its own thread, which did not see the caller's thinking(False) — every streamed call
    outside a beat went out with thinking on (deepseek: 5 of 40 sat 60 s before a token; with it off, none over 2.3 s)."""
    from neonrp.core import llm_openai as L

    monkeypatch.setattr(L, "_think_off", lambda base_url: {} if L._THINK.get() else {"thinking": {"type": "disabled"}})
    _Provider.plan = ["ok", "ok"]
    with L.thinking(False):
        assert "".join(c.delta for c in provider.chat_stream(_msgs()) if c.delta) == "好的"
    assert "".join(c.delta for c in provider.chat_stream(_msgs()) if c.delta) == "好的"
    assert _Provider.bodies[0].get("thinking") == {"type": "disabled"}
    assert "thinking" not in _Provider.bodies[1]
