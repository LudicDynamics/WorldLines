"""The account's free credits, claimed by the client (10-25 funnel check: a new player's very first System One call came
back 402 ``insufficient_credits`` / ``reason: claim_required`` and they never played again — the newcomer's 500 is not
granted by the server on its own, the client has to ask for it).

    POST {billing}/v1/claims/hub/newcomer        once per account: 201 granted · 200 duplicated · 409 nothing_to_claim
    POST {billing}/v1/claims/hub/daily           today's allowance                · 429 claim_limited   (all four normal)

- after a sign-in (``worldlines_auth.connect``): the newcomer claim, in the background;
- on a 402 ``insufficient_credits`` from ai.worldlines.gg (:func:`recover`): newcomer, and with ``reason: claim_required``
  daily too; when one of them answered 2xx the caller waits :data:`RESEND_AFTER_S` (ai keeps a refusal for 2 s) and
  sends the refused request again — once. Still 402 → the billing stop as before (the player sees the claim / top-up
  page from ``billing_url``). Parallel refusals share one round of claims (single-flight), and a round is not repeated
  within :data:`ROUND_TTL_S`."""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

TIMEOUT = 8.0
RESEND_AFTER_S = 2.0   # ai caches a refusal for 2 s: a resend sooner gets the same 402
ROUND_TTL_S = 30.0
CLAIMABLE = ("insufficient_credits", "claim_required")
_lock = threading.Lock()
_round: dict[str, Any] = {"at": 0.0, "token": None, "granted": False}


def billing_base() -> str:
    return os.environ.get("WORLDLINES_BILLING_BASE", "https://billing.worldlines.gg").rstrip("/")


def _token() -> str | None:
    from neonrp.core import worldlines_auth

    tok = worldlines_auth.access_token()
    return tok if tok and tok != "-" else None


def claim(kind: str, token: str | None = None) -> tuple[int, Any]:
    """POST /v1/claims/hub/<kind> → (status, body); (0, …) offline / nobody signed in. Never raises."""
    from neonrp.core import worldlines_auth

    tok = token or _token()
    if not tok:
        return 0, {"error": "not_signed_in"}
    hdrs = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json", "Accept": "application/json",
            "X-Worldlines-Device": worldlines_auth.device_id()}
    if sys.platform != "emscripten":  # a browser's CORS preflight at billing lets only these through
        hdrs.update(worldlines_auth.headers())
    req = urllib.request.Request(f"{billing_base()}/v1/claims/hub/{kind}", data=b"{}", method="POST", headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 — our own billing
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}
    except (OSError, ValueError) as e:
        return 0, {"error": "offline", "message": str(e)[:200]}


def after_sign_in(*, background: bool = True) -> None:
    """Right after a sign-in: the newcomer claim (a second sign-in gets 200 duplicated / 409 — both fine)."""
    def go() -> None:
        st, body = claim("newcomer")
        logger.info("newcomer claim: %s %s", st, (body or {}).get("error") or (body or {}).get("status") or "")

    if background:
        threading.Thread(target=go, daemon=True, name="worldlines-newcomer-claim").start()
    else:
        go()


def claimable(stop: Any) -> bool:
    """A 402 the client can try to clear by claiming (``insufficient_credits``, or its ``claim_required`` reason)."""
    return getattr(stop, "code", None) in CLAIMABLE


def recover(stop: Any) -> bool:
    """After a claimable 402: claim (newcomer; + daily when today's claim is what is missing). True = something was
    granted (or had been), so the refused request is worth one resend after :data:`RESEND_AFTER_S`."""
    if not claimable(stop):
        return False
    tok = _token()
    if not tok:
        return False
    with _lock:   # parallel refusals (chat lanes + System One) share one round
        if _round["token"] == tok and time.monotonic() - _round["at"] < ROUND_TTL_S:
            return bool(_round["granted"])
        granted = False
        st, _ = claim("newcomer", tok)
        granted |= st in (200, 201)
        if stop.code == "claim_required" or not granted:
            st2, _ = claim("daily", tok)
            granted |= st2 in (200, 201)
        _round.update(at=time.monotonic(), token=tok, granted=granted)
        return granted


def _reset() -> None:
    """Tests."""
    _round.update(at=0.0, token=None, granted=False)
