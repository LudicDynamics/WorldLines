"""A new account's free credits (10-25 funnel check: the first System One call of a new player came back 402
insufficient_credits / claim_required, they never came back — the newcomer's 500 is claimed by the client).

- sign-in → POST billing /v1/claims/hub/newcomer (with the device id), in the background;
- a 402 insufficient_credits from ai → newcomer (+ daily on claim_required) → ≥ 2 s later the same request once more;
- still 402 → the billing stop (the player is shown the claim / top-up page); nothing granted → no resend;
- System One (the proxy) does the same.
All against a local fake platform — never billing / ai.worldlines.gg."""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from neonrp.core import system_one, wl_claims
from neonrp.core import worldlines_auth as wa
from neonrp.core.llm import Message

REFUSE = {"error": {"code": "insufficient_credits", "reason": "claim_required", "wallet": "worldlines", "type": "billing_error",
                    "message": "claim today's credits", "billing_url": "https://billing.example.test/claim?product=hub"}}


class _Platform(BaseHTTPRequestHandler):
    log: list = []
    claims: dict = {}            # kind → status
    refuse_until_claimed = True
    refuse_always = False
    granted = False

    def log_message(self, *a):
        pass

    def _send(self, st, body):
        data = json.dumps(body).encode()
        self.send_response(st)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):  # noqa: N802
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        cls = type(self)
        cls.log.append((time.monotonic(), self.path, dict(self.headers)))
        if self.path.startswith("/v1/claims/hub/"):
            kind = self.path.rsplit("/", 1)[-1]
            st = cls.claims.get(kind, 409)
            if st in (200, 201):
                cls.granted = True
            return self._send(st, {"status": "granted"} if st == 201 else {"error": "nothing_to_claim"})
        refused = cls.refuse_always or (cls.refuse_until_claimed and not cls.granted)
        if refused:
            return self._send(402, REFUSE)
        if self.path.endswith("/systemone"):
            return self._send(200, {"answers": {"q": {"noul": 0.9}}, "usage": {}})
        return self._send(200, {"id": "c", "object": "chat.completion", "created": 0, "model": "m",
                                "choices": [{"index": 0, "message": {"role": "assistant", "content": "开场"}, "finish_reason": "stop"}]})


@pytest.fixture()
def platform(monkeypatch, tmp_path):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Platform)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    _Platform.log, _Platform.claims, _Platform.granted = [], {"newcomer": 201, "daily": 201}, False
    _Platform.refuse_until_claimed, _Platform.refuse_always = True, False
    monkeypatch.setenv("WORLDLINES_BILLING_BASE", base)
    monkeypatch.setenv("WORLDLINES_API_KEY", "wl_pat_test_only")
    monkeypatch.setenv("WORLDLINES_IDENTITY_FILE", str(tmp_path / "wl" / "identity.json"))
    monkeypatch.setattr(wa, "is_worldlines", lambda base_url: True)
    wl_claims._reset()
    yield base
    srv.shutdown()
    srv.server_close()
    wl_claims._reset()


def _paths():
    return [p for _, p, _ in _Platform.log]


def _adapter(base):
    pytest.importorskip("openai")
    from neonrp.core.llm_openai import OpenAIAdapter

    return OpenAIAdapter(model="m", base_url=f"{base}/v1", api_key=None, api_key_env="worldlines_none", max_retries=0)


def test_sign_in_claims_the_newcomer_credits(platform, monkeypatch):
    m = wa._wl_login()
    monkeypatch.setattr(m, "login", lambda issuer, **kw: {"access_token": "a", "refresh_token": "r", "expires_in": 900})
    monkeypatch.setattr(wa, "_manager", lambda: None)
    wa.connect(open_browser=False)
    for _ in range(100):
        if _paths():
            break
        time.sleep(0.02)
    assert _paths() == ["/v1/claims/hub/newcomer"]
    h = {k.lower(): v for k, v in _Platform.log[0][2].items()}
    assert h["authorization"] == "Bearer wl_pat_test_only" and len(h["x-worldlines-device"]) >= 16
    assert wa.device_id() == h["x-worldlines-device"]  # the same install keeps its id


def test_402_claims_then_resends_once_after_two_seconds(platform, monkeypatch):
    monkeypatch.delenv("WORLDLINES_NONE_API_KEY", raising=False)
    out = _adapter(platform).chat([Message(role="user", content="hi")])
    assert out.message.content == "开场"
    assert _paths() == ["/v1/chat/completions", "/v1/claims/hub/newcomer", "/v1/claims/hub/daily", "/v1/chat/completions"]
    t_first, t_again = _Platform.log[0][0], _Platform.log[3][0]
    assert t_again - t_first >= 2.0  # ai keeps a refusal for 2 s


def test_still_402_after_the_resend_is_the_billing_stop(platform, monkeypatch):
    monkeypatch.delenv("WORLDLINES_NONE_API_KEY", raising=False)
    _Platform.refuse_always = True
    out = _adapter(platform).chat([Message(role="user", content="hi")])
    assert "worldlines-billing:claim_required" in str(out.error)
    assert "billing.example.test/claim" in str(out.error)  # the page the player is sent to
    assert _paths().count("/v1/chat/completions") == 2  # one resend, no loop


def test_nothing_granted_means_no_resend(platform, monkeypatch):
    monkeypatch.delenv("WORLDLINES_NONE_API_KEY", raising=False)
    _Platform.claims = {"newcomer": 409, "daily": 429}  # already had both: nothing_to_claim / claim_limited
    out = _adapter(platform).chat([Message(role="user", content="hi")])
    assert "worldlines-billing:claim_required" in str(out.error)
    assert _paths() == ["/v1/chat/completions", "/v1/claims/hub/newcomer", "/v1/claims/hub/daily"]


def test_parallel_refusals_share_one_round_of_claims(platform, monkeypatch):
    monkeypatch.delenv("WORLDLINES_NONE_API_KEY", raising=False)
    outs: list = []
    ts = [threading.Thread(target=lambda: outs.append(_adapter(platform).chat([Message(role="user", content="hi")]))) for _ in range(3)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(20)
    assert [o.message.content for o in outs] == ["开场"] * 3
    assert _paths().count("/v1/claims/hub/newcomer") == 1 and _paths().count("/v1/claims/hub/daily") == 1


def test_system_one_claims_and_asks_again(platform, monkeypatch):
    monkeypatch.setenv("NEONRP_S1_BACKEND", "proxy")
    monkeypatch.setenv("NEONRP_S1_PROXY_URL", f"{platform}/v1/systemone")
    monkeypatch.setitem(system_one._QUOTA, "until", 0.0)
    system_one._CACHE.clear()
    ans = system_one.ask({"text": "x"}, {"q": system_one.noul("is it?")}, timeout=3.0)
    assert ans is not None and ans["q"].value == pytest.approx(0.9)
    assert _paths() == ["/v1/systemone", "/v1/claims/hub/newcomer", "/v1/claims/hub/daily", "/v1/systemone"]
    assert _Platform.log[3][0] - _Platform.log[0][0] >= 2.0
    assert not system_one.quota_blocked()
