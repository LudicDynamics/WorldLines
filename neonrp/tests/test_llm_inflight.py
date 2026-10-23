"""core/llm_inflight (iOS 10-18: a stream that went quiet across an app suspension is cut instead of hanging to its
read timeout). A local fake OpenAI endpoint sends one chunk and then nothing: the stream is registered while it runs,
quiet_since() names it, abort() shuts its socket down and the adapter's stream ends at once with an error chunk."""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from neonrp.core import llm_inflight
from neonrp.core.llm import Message
from neonrp.core.llm_openai import OpenAIAdapter

pytest.importorskip("openai")


class _Hang(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if not body.get("stream"):  # the adapter's plain-call fallback after a broken stream: answer at once
            data = json.dumps({"id": "c2", "object": "chat.completion", "created": 0, "model": "m",
                               "choices": [{"index": 0, "message": {"role": "assistant", "content": "灯"}, "finish_reason": "stop"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")  # like the real endpoint: a cut stream is an error, not an end
        self.end_headers()
        chunk = {"id": "c1", "object": "chat.completion.chunk", "created": 0, "model": "m",
                 "choices": [{"index": 0, "delta": {"content": "雾"}, "finish_reason": None}]}
        data = f"data: {json.dumps(chunk)}\n\n".encode()
        self.wfile.write(b"%x\r\n%s\r\n" % (len(data), data))
        self.wfile.flush()
        time.sleep(30)  # the connection stays open and silent (the model side of a suspended phone)


@pytest.fixture()
def hang_url():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Hang)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/v1"
    srv.shutdown()
    srv.server_close()


def test_quiet_stream_is_found_and_cut(hang_url):
    a = OpenAIAdapter(model="m", base_url=hang_url, api_key="k", max_retries=0)
    out: list = []
    done = threading.Event()

    def run():
        for c in a.chat_stream([Message(role="user", content="hi")]):
            out.append(c)
        done.set()

    before = set(llm_inflight._calls)  # other tests' streams may still be open: look only at this one
    threading.Thread(target=run, daemon=True).start()
    assert _until(lambda: out)  # the first chunk came: the stream is open and registered
    mine = set(llm_inflight._calls) - before
    assert len(mine) == 1
    mark = time.time()
    time.sleep(0.3)
    quiet = [k for k in llm_inflight.quiet_since(mark) if k in mine]
    assert quiet == list(mine)
    t = time.time()
    assert llm_inflight.abort(quiet) == 1
    assert done.wait(5), "the stream did not end after abort"
    assert time.time() - t < 3
    assert out[0].delta == "雾"
    assert out[-1].finished and out[-1].error  # cut mid-body: the stream ends as a failed call (the caller's fallback runs)
    assert not (set(llm_inflight._calls) & mine)  # unregistered when the stream ended


def test_live_stream_is_not_quiet():
    tok = llm_inflight.begin()
    try:
        mark = time.time()
        llm_inflight.touch(tok)
        assert llm_inflight.quiet_since(mark) == []
        assert llm_inflight.quiet_since(mark + 10) == [tok]
    finally:
        llm_inflight.end(tok)


def _until(cond, secs=5.0):
    end = time.time() + secs
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False
