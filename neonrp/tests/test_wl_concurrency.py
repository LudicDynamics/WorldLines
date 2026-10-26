"""The account's open-request limit at ai.worldlines.gg (10-25 funnel check: 20 × 429 concurrency_limit in one run — 3 chat
lanes open while 8 System One questions went out in one second; story = 3 open per account, chat and System One together).

- never more than 3 open at once from this engine; System One holds at most one and queues for it;
- a System One question that cannot get a slot in its timeout takes the no-Jev path (no 429);
- a 429 waits ``Retry-After`` before the retry.
Against a local fake ai that refuses a 4th open request like the platform does."""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from neonrp.core import system_one, wl_slots
from neonrp.core import worldlines_auth as wa
from neonrp.core.llm import Message


class _Ai(BaseHTTPRequestHandler):
    lock = threading.Lock()
    open_all = open_s1 = max_all = max_s1 = refused = 0
    delay = 0.3
    first_429: list = []
    log: list = []

    def log_message(self, *a):
        pass

    def _send(self, st, body, headers=None):
        data = json.dumps(body).encode()
        self.send_response(st)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):  # noqa: N802
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        c, s1 = type(self), self.path.endswith("/systemone")
        c.log.append((time.monotonic(), self.path))
        if c.first_429:
            c.first_429.pop()
            return self._send(429, {"error": {"code": "concurrency_limit", "message": "too many"}}, {"Retry-After": "1"})
        with c.lock:
            if c.open_all >= 3:
                c.refused += 1
                busy = True
            else:
                busy = False
                c.open_all += 1
                c.open_s1 += int(s1)
                c.max_all, c.max_s1 = max(c.max_all, c.open_all), max(c.max_s1, c.open_s1)
        if busy:
            return self._send(429, {"error": {"code": "concurrency_limit"}}, {"Retry-After": "1"})
        try:
            time.sleep(c.delay)
        finally:
            with c.lock:
                c.open_all -= 1
                c.open_s1 -= int(s1)
        if s1:
            return self._send(200, {"answers": {"q": {"noul": 0.8}}})
        self._send(200, {"id": "c", "object": "chat.completion", "created": 0, "model": "m",
                         "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}]})


@pytest.fixture()
def ai(monkeypatch):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Ai)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    _Ai.open_all = _Ai.open_s1 = _Ai.max_all = _Ai.max_s1 = _Ai.refused = 0
    _Ai.first_429, _Ai.log, _Ai.delay = [], [], 0.3
    monkeypatch.setenv("WORLDLINES_API_KEY", "wl_pat_test_only")
    monkeypatch.setenv("NEONRP_S1_BACKEND", "proxy")
    monkeypatch.setenv("NEONRP_S1_PROXY_URL", f"{base}/v1/systemone")
    monkeypatch.delenv("WORLDLINES_NONE_API_KEY", raising=False)
    monkeypatch.setattr(wa, "is_worldlines", lambda url: True)
    monkeypatch.setitem(system_one._QUOTA, "until", 0.0)
    system_one._CACHE.clear()
    yield base
    srv.shutdown()
    srv.server_close()


def _adapter(base, retries=0):
    pytest.importorskip("openai")
    from neonrp.core.llm_openai import OpenAIAdapter

    return OpenAIAdapter(model="m", base_url=f"{base}/v1", api_key=None, api_key_env="worldlines_none", max_retries=retries)


def test_slots_unit():
    a = wl_slots.acquire("s1", 0.1)
    assert a is not None
    assert wl_slots.acquire("s1", 0.1) is None  # System One holds one slot at most
    b, c = wl_slots.acquire("chat", 0.1), wl_slots.acquire("chat", 0.1)
    assert wl_slots.in_use() == {"all": 3, "s1": 1}
    t0 = time.monotonic()
    d = wl_slots.acquire("chat", 0.2)  # full: a chat call waits, then goes anyway (no deadlock)
    assert time.monotonic() - t0 >= 0.2 and wl_slots.in_use()["all"] == 3
    for r in (a, a, b, c, d):  # releasing twice is harmless
        r()
    assert wl_slots.in_use() == {"all": 0, "s1": 0}


def test_three_chat_lanes_and_a_burst_of_system_one_stay_under_the_limit(ai):
    errs: list = []

    def chat():
        out = _adapter(ai).chat([Message(role="user", content="hi")])
        if out.error:
            errs.append(out.error)

    def judge(i):
        system_one.ask({"text": f"x{i}"}, {"q": system_one.noul("is it?")}, timeout=3.0, retries=0)

    ts = [threading.Thread(target=chat) for _ in range(3)] + [threading.Thread(target=judge, args=(i,)) for i in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(30)
    assert _Ai.refused == 0, "no 429 concurrency_limit"
    assert _Ai.max_all <= 3 and _Ai.max_s1 <= 1
    assert errs == []
    assert wl_slots.in_use() == {"all": 0, "s1": 0}


def test_system_one_without_a_slot_takes_the_no_jev_path(ai):
    held = [wl_slots.acquire("chat", 0.1) for _ in range(3)]
    try:
        t0 = time.monotonic()
        assert system_one.ask({"text": "y"}, {"q": system_one.noul("is it?")}, timeout=0.5, retries=0) is None
        assert time.monotonic() - t0 < 2.0 and not [p for _, p in _Ai.log if p.endswith("/systemone")]
    finally:
        for r in held:
            r()


def test_chat_429_waits_retry_after(ai):
    _Ai.first_429 = [1]
    t0 = time.monotonic()
    out = _adapter(ai, retries=1).chat([Message(role="user", content="hi")])
    assert out.message.content == "ok"
    assert len(_Ai.log) == 2 and _Ai.log[1][0] - _Ai.log[0][0] >= 1.0
    assert time.monotonic() - t0 >= 1.0


def test_system_one_429_waits_retry_after(ai):
    _Ai.first_429 = [1]
    ans = system_one.ask({"text": "z"}, {"q": system_one.noul("is it?")}, timeout=3.0, retries=1)
    assert ans is not None
    assert len(_Ai.log) == 2 and _Ai.log[1][0] - _Ai.log[0][0] >= 1.0
