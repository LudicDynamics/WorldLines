"""ai.worldlines.gg refusing a call for money, not for load (10-13 launch audit, NEONRP-LAUNCH-READINESS-1013 L3).

The platform answers ``429 quota_exceeded`` · ``402 insufficient_credits`` (``reason``: insufficient_credits | claim_required
| debt_limit) · ``403 plan_required`` with an OpenAI-shaped body that carries ``billing_url`` (services/ai docs §3.1, §3.4).
Retrying those only burns a minute; the player has to act (claim today's allowance, top up, subscribe, or switch to their
own key). An ordinary rate limit (``upstream_rate_limited``, ``concurrency_limit``) is *not* a stop and keeps retrying.

A stop travels through the turn as error text with a marker (``[worldlines-billing:<code> kind=… url=…]``), so the TUI,
the web page and the retry ladder all read the same thing without new fields on every result type."""
from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass
from typing import Any

CODES = ("quota_exceeded", "insufficient_credits", "claim_required", "debt_limit", "plan_required")
# not money but the same kind of stop (10-18 niko on the phone: a guest's call refused, the turn came back empty): the
# player has to sign in — ``403 guest_not_allowed`` (this call needs an account) · ``403 guest_world_only`` (a guest plays
# only inside a world). kind = "guest", so a page can offer 「登录后继续」 instead of a top-up.
SIGN_IN_CODES = ("guest_not_allowed", "guest_world_only")
_STATUSES = (402, 403, 429)
_MARK = re.compile(r"\[worldlines-billing:([a-z_]+)(?: kind=([a-z0-9_]+))?(?: url=(\S+?))?\]")

CODES_TEXT_TABLE = "billing_stop"  # src/neonrp/prompts/billing_stop.<lang>.json: one sentence per code + the open hint


def _table(lang: str) -> dict[str, str]:
    from neonrp.prompts import strings

    return strings(CODES_TEXT_TABLE, (lang or "zh")[:2])


def default_url() -> str:
    """Where to send the player when the refusal carried no billing_url (it always should)."""
    return os.environ.get("WORLDLINES_BILLING_URL", "https://billing.worldlines.gg/manage").strip()


@dataclass(frozen=True)
class BillingStop:
    code: str
    kind: str = ""
    billing_url: str = ""

    @property
    def url(self) -> str:
        return self.billing_url or default_url()

    def text(self, lang: str = "zh") -> str:
        t = _table(lang)
        return t.get(self.code) or t["quota_exceeded"]

    def hint(self, lang: str = "zh") -> str:
        return _table(lang)["hint"].format(url=self.url)

    def marker(self) -> str:
        return f"[worldlines-billing:{self.code}" + (f" kind={self.kind}" if self.kind else "") + (f" url={self.billing_url}" if self.billing_url else "") + "]"

    def error_text(self) -> str:
        """The error string a turn carries: a plain sentence (what a log or an old client shows) + the marker."""
        return f"{self.text('en')} {self.marker()}"

    def to_dict(self, lang: str = "zh") -> dict[str, Any]:
        return {"code": self.code, "kind": self.kind, "billing_url": self.url, "message": self.text(lang),
                "messages": {k: self.text(k) for k in ("zh", "en", "ja", "ko")}}


def _error_dict(body: Any) -> dict[str, Any] | None:
    if isinstance(body, (str, bytes)):
        try:
            body = json.loads(body)
        except (TypeError, ValueError):
            return None
    if not isinstance(body, dict):
        return None
    inner = body.get("error")
    return inner if isinstance(inner, dict) else body  # the openai SDK hands over the inner error object


def from_body(status: int | None, body: Any) -> BillingStop | None:
    """A platform money refusal from an HTTP status + body, else None (a rate limit, a bad request, another provider)."""
    if status not in _STATUSES:
        return None
    err = _error_dict(body)
    if not err:
        return None
    code, reason = str(err.get("code") or ""), str(err.get("reason") or "")
    if reason in ("claim_required", "debt_limit", "insufficient_credits"):
        code = reason
    if code in SIGN_IN_CODES and status == 403:
        return BillingStop(code=code, kind="guest")
    if code not in CODES:
        return None
    url = err.get("billing_url")
    url = url if isinstance(url, str) and url.startswith(("https://", "http://127.0.0.1", "http://localhost")) else ""
    quota = err.get("quota") if isinstance(err.get("quota"), dict) else {}
    kind = str(err.get("kind") or quota.get("kind") or "")
    return BillingStop(code=code, kind=re.sub(r"[^a-z0-9_]", "", kind.lower()), billing_url=url)


def from_exception(exc: Any) -> BillingStop | None:
    """An openai SDK ``APIStatusError`` (``status_code`` + ``body``; falls back to the response JSON)."""
    status = getattr(exc, "status_code", None)
    if status not in _STATUSES:
        return None
    stop = from_body(status, getattr(exc, "body", None))
    if stop is None:
        try:
            stop = from_body(status, exc.response.json())
        except Exception:  # noqa: BLE001
            stop = None
    return stop


def from_text(text: Any) -> BillingStop | None:
    """Read the marker back out of a turn's error string."""
    m = _MARK.search(str(text or ""))
    if not m:
        return None
    return BillingStop(code=m.group(1), kind=m.group(2) or "", billing_url=m.group(3) or "")


_LAST: dict[str, BillingStop | None] = {"stop": None}
_LOCK = threading.Lock()


def remember(stop: BillingStop | None) -> BillingStop | None:
    if stop is not None:
        with _LOCK:
            _LAST["stop"] = stop
    return stop


def restore(prev: BillingStop | None) -> None:
    """Put back the stop that was there before a call made off the player's screen (the background write-down): its
    refusal is handled where it happened and is not the player's last stop."""
    with _LOCK:
        _LAST["stop"] = prev


def last() -> BillingStop | None:
    with _LOCK:
        return _LAST["stop"]


def open_page(stop: BillingStop | None = None, *, next_url: str | None = None, open_browser: Any = None,
              on_url: Any = None, headless: bool | None = None) -> str | None:
    """Send the player to billing once (the identity client's ``open_billing``): the last stop's page, else /manage."""
    from neonrp.core import worldlines_auth

    s = stop or last()
    url = s.url if s else default_url()
    return worldlines_auth._wl_login().open_billing({"billing_url": url}, next_url=next_url, open_browser=open_browser,
                                                    on_url=on_url, headless=headless)
