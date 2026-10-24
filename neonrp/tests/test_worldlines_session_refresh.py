"""Worldlines session renewal (10-19, iOS: every request 401 after the access token expired).

- every caller shares one token manager: an expired session is refreshed ONCE even when many threads ask at the same
  moment (a fresh manager per call refreshed in parallel with the same rotating refresh token = replay → revoked);
- a refused refresh (4xx) clears the session and is remembered as "expired" (sign in again), not "never signed in";
- ai.worldlines.gg answering 401: the adapter renews once and sends the same request again; renewal refused → an
  AuthError that says session_expired (the frontends turn it into a sign-in prompt, not "no model").
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from neonrp._vendor.worldlines_identity import login as real_login
from neonrp.core import worldlines_auth as wa
from neonrp.core.llm import Message
from neonrp.core.llm_errors import AuthError


@pytest.fixture()
def session_file(tmp_path, monkeypatch):
    f = tmp_path / "identity.json"
    monkeypatch.setattr(wa, "store_path", lambda: f)
    monkeypatch.delenv("WORLDLINES_API_KEY", raising=False)
    wa._mgrs.clear()
    wa._lost.clear()
    yield f
    wa._mgrs.clear()
    wa._lost.clear()


def _write(f, access="a0", refresh="r0", expires_in=-10):
    f.write_text(json.dumps({"access_token": access, "refresh_token": refresh, "expires_at": time.time() + expires_in,
                             "user": {"email": "n@x.test"}}), encoding="utf-8")


class _Identity:
    """A fake identity service behind the vendored client's ``post`` hook: rotating refresh tokens, replay = refused."""

    def __init__(self, refuse=False):
        self.calls = 0
        self.used: set[str] = set()
        self.refuse = refuse
        self.lock = threading.Lock()

    def post(self, url, body, headers):
        assert url.endswith("/v1/token/refresh")
        time.sleep(0.05)  # long enough for parallel callers to pile up
        with self.lock:
            self.calls += 1
            rt = body["refresh_token"]
            if self.refuse or rt in self.used:
                return 401, {"error": "invalid_grant"}
            self.used.add(rt)
            n = self.calls
        return 200, {"access_token": f"a{n}", "refresh_token": f"r{n}", "expires_in": 900, "user": {"email": "n@x.test"}}


@pytest.fixture()
def identity(monkeypatch):
    idp = _Identity()
    monkeypatch.setattr(wa, "post", lambda url, body, headers, **kw: idp.post(url, body, headers))
    monkeypatch.setattr(wa, "_wl_login", lambda: real_login)
    return idp


def test_parallel_callers_refresh_once(session_file, identity):
    _write(session_file)
    got: list = []
    ts = [threading.Thread(target=lambda: got.append(wa.access_token())) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(5)
    assert identity.calls == 1  # one refresh, not one per caller (no replay → the session survives)
    assert set(got) == {"a1"}
    assert json.loads(session_file.read_text())["refresh_token"] == "r1"


def test_refused_refresh_is_remembered_as_expired(session_file, identity):
    _write(session_file)
    identity.refuse = True
    assert wa.access_token() is None
    assert not session_file.exists()  # the dead session is cleared
    assert wa.session_expired() is True
    assert wa.status()["expired"] is True
    _write(session_file, expires_in=900)  # signed in again
    assert wa.session_expired() is False


def test_never_signed_in_is_not_expired(session_file):
    assert wa.session_expired() is False


def test_refresh_now_skips_a_second_refresh_when_someone_already_renewed(session_file, identity):
    _write(session_file, access="a0", expires_in=900)
    assert wa.refresh_now("a0") == "a1"  # the refused token is the current one: renew
    assert wa.refresh_now("a0") == "a1"  # already moved on: no second refresh
    assert identity.calls == 1


# ── the adapter: 401 → renew once → same request again ──

class _Api(BaseHTTPRequestHandler):
    good = "a1"
    seen: list = []

    def log_message(self, *a):
        pass

    def do_POST(self):  # noqa: N802
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        tok = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
        _Api.seen.append(tok)
        if tok != _Api.good:
            body, st = {"error": {"message": "invalid_token", "type": "invalid_request_error", "code": "invalid_token"}}, 401
        else:
            body, st = {"id": "c", "object": "chat.completion", "created": 0, "model": "m",
                        "choices": [{"index": 0, "message": {"role": "assistant", "content": "灯亮了"}, "finish_reason": "stop"}]}, 200
        data = json.dumps(body).encode()
        self.send_response(st)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture()
def api(monkeypatch):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Api)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _Api.seen = []
    monkeypatch.setattr(wa, "is_worldlines", lambda base_url: True)
    yield f"http://127.0.0.1:{srv.server_address[1]}/v1"
    srv.shutdown()
    srv.server_close()


def _adapter(url):
    pytest.importorskip("openai")
    from neonrp.core.llm_openai import OpenAIAdapter

    return OpenAIAdapter(model="m", base_url=url, api_key=None, api_key_env="worldlines_none", max_retries=0)


def test_401_renews_once_and_resends(session_file, identity, api, monkeypatch):
    _write(session_file, access="a0", expires_in=900)  # still "valid" locally, but the server refuses it
    monkeypatch.delenv("WORLDLINES_NONE_API_KEY", raising=False)
    out = _adapter(api).chat([Message(role="user", content="hi")])
    assert out.message.content == "灯亮了"
    assert _Api.seen == ["a0", "a1"]
    assert identity.calls == 1


def test_401_with_a_refused_renewal_says_sign_in_again(session_file, identity, api, monkeypatch):
    _write(session_file, access="a0", expires_in=900)
    identity.refuse = True
    monkeypatch.delenv("WORLDLINES_NONE_API_KEY", raising=False)
    out = _adapter(api).chat([Message(role="user", content="hi")])  # chat() answers with the error instead of raising
    assert "session_expired" in str(out.error)
    assert _Api.seen == ["a0"]
    with pytest.raises(AuthError) as e:  # what the retry ladder itself raises
        a = _adapter(api)
        a._wl_token = "a0"
        a._call_with_retry(lambda: (_ for _ in ()).throw(_auth_error()))
    assert "session_expired" in str(e.value)


def _auth_error():
    import httpx
    import openai

    r = httpx.Response(401, request=httpx.Request("POST", "http://x/v1/chat/completions"), json={"error": {"message": "invalid_token"}})
    return openai.AuthenticationError("invalid_token", response=r, body=None)
