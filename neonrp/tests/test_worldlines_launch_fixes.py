"""10-13 launch audit (docs/planning/NEONRP-LAUNCH-READINESS-1013.md): three fixes, all offline — no sign-in, no credits.

L1 the `worldlines` preset names a model ai.worldlines.gg actually serves;
L3 a money refusal (429 quota_exceeded / 402 insufficient_credits · claim_required / 403 plan_required) is not retried and
   reaches the player with billing_url, while a plain 429 rate limit keeps retrying;
L2 `/login code` really is the device-code flow (no browser opened on a desktop)."""
from __future__ import annotations

import io
import json
import urllib.error
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import openai
import pytest

from neonrp.core import billing_stop
from neonrp.core.llm import Message
from neonrp.core.llm_errors import BillingError, RetryableError
from neonrp.core.llm_openai import OpenAIAdapter, _classify_openai_error
from _paths import PRODUCT

BILL = "https://billing.worldlines.gg/subscribe?product=local&reason=quota"


def _status_error(cls, status: int, error: dict):
    """A real openai SDK status error, as the client raises it (body = the inner `error` object)."""
    req = httpx.Request("POST", "https://ai.worldlines.gg/v1/chat/completions")
    resp = httpx.Response(status, request=req, json={"error": error})
    return cls(error.get("message", "refused"), response=resp, body=error)


def _quota_429():
    return _status_error(openai.RateLimitError, 429, {"message": "Daily quota exceeded.", "type": "insufficient_quota",
                                                     "code": "quota_exceeded", "billing_url": BILL,
                                                     "quota": {"kind": "chat", "plan": "free"}})


def _rate_429():
    return _status_error(openai.RateLimitError, 429, {"message": "Upstream rate limited.", "type": "rate_limit_error",
                                                     "code": "upstream_rate_limited"})


def _claim_402():
    return _status_error(openai.APIStatusError, 402, {"message": "Claim today's allowance.", "type": "insufficient_quota",
                                                     "code": "insufficient_credits", "reason": "claim_required",
                                                     "kind": "chat", "billing_url": BILL})


@pytest.fixture(autouse=True)
def _fresh_last():
    billing_stop._LAST["stop"] = None
    yield
    billing_stop._LAST["stop"] = None


# ── L1: the relay preset names a model in the relay's catalog ──────────────────────────────────────────────────────


def test_worldlines_preset_model_is_in_the_relay_catalog():
    from neonrp.presets import PRESETS, WORLDLINES_CATALOG_CHAT

    assert PRESETS["worldlines"]["model"] == "deepseek-v4-flash"
    relay = {k: p for k, p in PRESETS.items() if "ai.worldlines.gg" in str(p.get("base_url") or "")}
    assert relay, "the worldlines preset points at ai.worldlines.gg"
    for k, p in relay.items():  # any future preset on the relay must name a served id, or every turn 404s
        assert p["model"] in WORLDLINES_CATALOG_CHAT, (k, p["model"])


def test_relay_catalog_snapshot_has_no_provider_only_ids():
    from neonrp.presets import WORLDLINES_CATALOG_CHAT

    assert "deepseek-v4.1-flash" not in WORLDLINES_CATALOG_CHAT  # DeepSeek's own name; the relay never served it
    assert all(m == m.strip() and m for m in WORLDLINES_CATALOG_CHAT)


# ── L3: money refusals stop, rate limits retry ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("status", "error", "code"),
    [
        (429, {"code": "quota_exceeded", "billing_url": BILL, "quota": {"kind": "chat"}}, "quota_exceeded"),
        (402, {"code": "insufficient_credits", "reason": "insufficient_credits", "billing_url": BILL}, "insufficient_credits"),
        (402, {"code": "insufficient_credits", "reason": "claim_required", "billing_url": BILL}, "claim_required"),
        (402, {"code": "insufficient_credits", "reason": "debt_limit", "billing_url": BILL}, "debt_limit"),
        (403, {"code": "plan_required", "billing_url": BILL}, "plan_required"),
    ],
)
def test_billing_stops_are_recognised(status, error, code):
    stop = billing_stop.from_body(status, {"error": error})
    assert stop is not None and stop.code == code and stop.url == BILL
    back = billing_stop.from_text(f"LLM call failed on turn 1: {stop.error_text()}")  # the marker survives the turn's prefix
    assert back == stop


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (429, {"code": "upstream_rate_limited"}),
        (429, {"code": "concurrency_limit"}),
        (429, {"code": "insufficient_quota", "type": "insufficient_quota"}),  # another provider's own wording: not ours
        (400, {"code": "quota_exceeded"}),
        (500, {"code": "upstream_error"}),
    ],
)
def test_non_billing_errors_are_not_stops(status, error):
    assert billing_stop.from_body(status, {"error": error}) is None


def test_billing_url_must_be_a_web_page():
    stop = billing_stop.from_body(429, {"error": {"code": "quota_exceeded", "billing_url": "javascript:alert(1)"}})
    assert stop is not None and stop.billing_url == "" and stop.url.startswith("https://billing.worldlines.gg/")


def test_classify_quota_and_claim_as_billing_error_rate_limit_stays_retryable():
    q = _classify_openai_error(_quota_429())
    assert isinstance(q, BillingError) and not q.retryable and q.stop.code == "quota_exceeded" and q.stop.kind == "chat"
    c = _classify_openai_error(_claim_402())
    assert isinstance(c, BillingError) and c.stop.code == "claim_required"
    r = _classify_openai_error(_rate_429())
    assert isinstance(r, RetryableError) and r.status_code == 429
    assert billing_stop.last().code == "claim_required"  # the last stop is kept for `/login billing`


def _adapter(max_retries=3):
    a = OpenAIAdapter(api_key="test-key", max_retries=max_retries)
    a._client = MagicMock()
    return a


@patch("neonrp.core.llm_openai.time.sleep")
def test_chat_quota_is_not_retried_and_carries_billing_url(mock_sleep):
    a = _adapter()
    a._client.chat.completions.create.side_effect = _quota_429()
    res = a.chat([Message(role="user", content="hi")])
    assert not res.success and res.retryable is False
    assert a._client.chat.completions.create.call_count == 1 and mock_sleep.call_count == 0
    stop = billing_stop.from_text(res.error)
    assert stop is not None and stop.code == "quota_exceeded" and stop.url == BILL


@patch("neonrp.core.llm_openai.time.sleep")
def test_chat_plain_rate_limit_still_retries(mock_sleep):
    a = _adapter(max_retries=2)
    a._client.chat.completions.create.side_effect = _rate_429()
    res = a.chat([Message(role="user", content="hi")])
    assert not res.success and res.retryable is True
    assert a._client.chat.completions.create.call_count == 3 and mock_sleep.call_count == 2
    assert billing_stop.from_text(res.error) is None


@patch("neonrp.core.llm_openai.time.sleep")
def test_chat_stream_claim_required_is_not_retried(mock_sleep):
    a = _adapter()
    a._client.chat.completions.create.side_effect = _claim_402()
    chunks = list(a.chat_stream([Message(role="user", content="hi")]))
    err = [c for c in chunks if getattr(c, "error", None)]
    assert err and err[-1].retryable is False and billing_stop.from_text(err[-1].error).code == "claim_required"
    assert a._client.chat.completions.create.call_count == 1 and mock_sleep.call_count == 0


def test_turn_retry_ladder_skips_billing_stops():
    from neonrp.core.conversation import _looks_retryable_error_text

    stop = billing_stop.BillingStop("quota_exceeded", "chat", BILL)
    assert _looks_retryable_error_text(f"LLM call failed on turn 2: {stop.error_text()} (HTTP 429)") is False
    assert _looks_retryable_error_text("Error code: 429 - rate limit") is True  # an ordinary rate limit still retries


def test_relay_client_turns_off_the_sdk_own_429_retries(monkeypatch):
    from neonrp.core import worldlines_auth

    seen = {}

    class FakeOpenAI:
        def __init__(self, **kw):
            seen.update(kw)

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(worldlines_auth, "access_token", lambda: "tok")
    a = OpenAIAdapter(model="deepseek-v4-flash", base_url="https://ai.worldlines.gg/v1", api_key_env="WORLDLINES_API_KEY")
    a._get_client()
    assert seen["max_retries"] == 0 and seen["api_key"] == "tok"
    b = OpenAIAdapter(model="x", base_url="https://api.deepseek.com/v1", api_key="k")
    seen.clear()
    b._get_client()
    # other providers too (10-14 beat budget, 292778ff): one retry ladder, ours — the SDK's own 2 retries × 60 s read
    # timeout under it made one stalled call take 189 s; quota 429 / 402 are still never retried by our ladder (above)
    assert seen["max_retries"] == 0


def test_open_page_uses_the_vendored_open_billing():
    opened, printed = [], []
    billing_stop.remember(billing_stop.BillingStop("insufficient_credits", "chat", BILL))
    url = billing_stop.open_page(next_url="http://127.0.0.1:8906/", open_browser=opened.append, on_url=printed.append, headless=False)
    assert url and url.startswith(BILL) and "next=" in url
    assert opened == [url] and printed == [url]
    assert billing_stop.open_page(on_url=printed.append, headless=True) and len(opened) == 1  # headless: printed only


def test_stop_messages_cover_four_languages():
    for code in billing_stop.CODES:
        s = billing_stop.BillingStop(code)
        for lang in ("zh", "en", "ja", "ko"):
            assert s.text(lang) and s.url in s.hint(lang) and "/login billing" in s.hint(lang)


def test_web_turn_payload_carries_billing():
    from neonrp.commands.web import _billing_payload

    stop = billing_stop.BillingStop("claim_required", "chat", BILL)
    b = _billing_payload(f"LLM call failed on turn 1: {stop.error_text()}")
    assert b["code"] == "claim_required" and b["billing_url"] == BILL and b["message"] and set(b["messages"]) == {"zh", "en", "ja", "ko"}
    assert _billing_payload("Connection reset") is None and _billing_payload(None) is None


def test_web_page_handles_the_billing_payload():
    from pathlib import Path

    js = (PRODUCT / "ui/app/real/engine.js").read_text(encoding="utf-8")
    assert "m.billing" in js and "billingStop(" in js and "billing_url" in js


def test_tui_shows_the_stop_instead_of_a_retry_callout():
    from neonrp.tui.app import NeonRPApp

    writes, callouts = [], []
    view = SimpleNamespace(write=writes.append, add_agent_error=lambda *a: callouts.append(a),
                           fail_open_tool_indicators=lambda *a: None, flush_pending_execution_details=lambda: None)
    host = SimpleNamespace(query_one=lambda *a: view, _set_main_input_enabled=lambda v: None, _clear_run_status=lambda: None,
                           _refresh_status=lambda: None, _emit_bridge_event=lambda *a, **k: None, verbose=False,
                           _account_lang=lambda: "zh", _stream_started=True)
    stop = billing_stop.BillingStop("quota_exceeded", "chat", BILL)
    result = SimpleNamespace(success=False, error=f"LLM call failed on turn 1: {stop.error_text()}", run_id="r", assistant_speaker="")
    NeonRPApp._handle_result(host, result)
    text = "".join(writes)
    assert not callouts and stop.text("zh") in text and BILL in text and "/login billing" in text

    writes.clear()
    NeonRPApp._handle_result(host, SimpleNamespace(success=False, error="Connection reset", run_id="r", assistant_speaker=""))
    assert callouts and not writes  # any other failure keeps the Retry / Skip callout


def test_jev_wallet_refusal_takes_the_no_jev_path(monkeypatch):
    from neonrp.core import system_one as s1

    body = json.dumps({"error": {"code": "insufficient_credits", "reason": "claim_required", "kind": "systemone",
                                 "billing_url": BILL, "message": "x" * 400}}).encode()  # longer than the 300-char log tail

    def refuse(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 402, "Payment Required", {}, io.BytesIO(body))

    monkeypatch.setattr(s1, "endpoint", lambda: ("https://ai.worldlines.gg/v1/systemone", "tok"))
    monkeypatch.setattr(s1.urllib.request, "urlopen", refuse)
    with pytest.raises(s1.QuotaExceeded):
        s1._post_jev({"t": 1}, {"q": s1.noul("ok?")}, model="jev-latest", timeout=1)
    assert billing_stop.last().code == "claim_required" and billing_stop.last().url == BILL


# ── L2: /login code is the device-code flow ───────────────────────────────────────────────────────────────────────


def test_connect_device_passes_device_and_opens_no_browser(tmp_path, monkeypatch):
    from neonrp.core import worldlines_auth as wa

    calls = {}
    real = wa._wl_login()

    def fake_login(issuer, **kw):
        calls.update(kw)
        return {"access_token": "a", "refresh_token": "r", "expires_in": 900}

    fake = SimpleNamespace(login=fake_login, session_from_tokens=real.session_from_tokens, FileTokenStore=real.FileTokenStore)
    monkeypatch.setattr(wa, "_wl_login", lambda: fake)
    monkeypatch.setattr(wa, "_manager", lambda: None)
    monkeypatch.setenv("WORLDLINES_IDENTITY_FILE", str(tmp_path / "identity.json"))
    monkeypatch.delenv("WORLDLINES_API_KEY", raising=False)
    with patch("webbrowser.open") as wb:
        st = wa.connect(open_browser=True, device=True)
    assert calls["device"] is True and calls["open_browser"] is None and wb.call_count == 0
    assert st["signed_in"]
    wa.connect()  # the default leaves the choice to login()
    assert calls["device"] is None and calls["open_browser"] is not None


def test_vendored_login_device_true_never_starts_loopback_or_browser(monkeypatch):
    from neonrp._vendor.worldlines_identity import login as m

    monkeypatch.setattr(m, "can_open_browser", lambda: True)  # a desktop with a browser
    monkeypatch.setattr(m, "local_login", lambda *a, **k: pytest.fail("loopback flow started"))
    posts, codes = [], []

    def post(url, body, headers):
        posts.append(url)
        if url.endswith("/v1/device/code"):
            return 200, {"device_code": "dc", "user_code": "ABCD-EFGH", "verification_uri": "https://auth.worldlines.gg/device",
                         "verification_uri_complete": "https://auth.worldlines.gg/device?code=ABCD-EFGH", "expires_in": 600, "interval": 1}
        return 200, {"access_token": "a", "refresh_token": "r", "expires_in": 900}

    tokens = m.login("https://auth.worldlines.gg", client_id="neonrp", scopes=["api:use"], device=True,
                     open_browser=None, on_code=codes.append, post=post, sleep=lambda s: None)
    assert tokens["access_token"] == "a" and codes and codes[0]["user_code"] == "ABCD-EFGH"
    assert posts[0].endswith("/v1/device/code") and posts[-1].endswith("/v1/token")


def test_tui_login_code_asks_for_the_device_flow(monkeypatch):
    from neonrp.core import worldlines_auth as wa
    from neonrp.tui.app import NeonRPApp

    seen = []
    monkeypatch.setattr(wa, "status", lambda: {"signed_in": False})
    monkeypatch.setattr(wa, "connect", lambda **kw: seen.append(kw) or {"signed_in": True})
    view = SimpleNamespace(write=lambda *a: None)
    host = SimpleNamespace(query_one=lambda *a: view, _t=lambda k: k, _account_lang=lambda: "zh",
                           call_from_thread=lambda f, *a: f(*a), run_worker=lambda fn, **k: fn())
    NeonRPApp._cmd_login(host, ["code"])
    NeonRPApp._cmd_login(host, [])
    assert seen[0]["device"] is True and seen[0]["open_browser"] is False
    assert seen[1]["device"] is None and seen[1]["open_browser"] is True


# ── D1 (10-14): NeonRP bills as the platform product `hub`, never LivingCanvas's `local` alias ────────────────────


def test_product_header_is_hub(monkeypatch):
    import importlib

    from neonrp.core import worldlines_auth as wa

    monkeypatch.delenv("WORLDLINES_PRODUCT", raising=False)
    monkeypatch.delenv("WORLDLINES_CLIENT", raising=False)
    wa = importlib.reload(wa)
    try:
        # funnel 10-25: native requests also say which client sent them (X-Worldlines-Client: local on a desktop)
        assert wa.PRODUCT == "hub" and wa.headers() == {"X-Worldlines-Product": "hub", "X-Worldlines-Client": "local"}
    finally:
        importlib.reload(wa)


def test_jev_proxy_call_sends_product_hub(monkeypatch):
    from neonrp.core import system_one as s1

    sent = {}

    class Resp(io.BytesIO):
        headers = {"x-request-id": "req_1"}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def capture(req, timeout=None):
        sent.update({k.lower(): v for k, v in req.header_items()})
        return Resp(b'{"answers": {}}')

    monkeypatch.delenv("WORLDLINES_CLIENT", raising=False)
    monkeypatch.setattr(s1, "endpoint", lambda: ("https://ai.worldlines.gg/v1/systemone", "tok"))
    monkeypatch.setattr(s1.urllib.request, "urlopen", capture)
    s1._post_jev({"t": 1}, {"q": s1.noul("ok?")}, model="jev-latest", timeout=1)
    # the product is never LivingCanvas's `local` alias; `local` is only the client name (funnel 10-25)
    assert sent["x-worldlines-product"] == "hub" and sent["x-worldlines-client"] == "local"
