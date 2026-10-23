"""The player's run points on their Worldlines account, for the local Hub's 「我的」 (2026-10-21): a settled run's points go
to chronicle (core/chronicle.reward) and on to billing, which pays them only on its own facts (billed calls of that
world during the run). This reads what billing decided and claims a claimable one — the online Hub calls billing itself.

    GET  {billing}/v1/me/run-points        [{ref, world, points_asked, points, status, progress?, reward_id?}]
    GET  {billing}/v1/me/rewards           the claimable ones (kind run_points)
    POST {billing}/v1/me/rewards/<id>/claim

Signed in = ``worldlines_auth.access_token()``. Not signed in / offline / billing down → ``{signed_in, error}``; nothing
here changes the local record (core/player_data keeps its pending rewards as they were)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

BILLING = os.environ.get("WORLDLINES_BILLING_BASE", "https://billing.worldlines.gg").rstrip("/")
TIMEOUT = 8.0


def _call(method: str, path: str, token: str, headers: dict[str, str] | None = None) -> tuple[int, Any]:
    from neonrp.core import worldlines_auth

    req = urllib.request.Request(f"{BILLING}{path}", data=b"{}" if method == "POST" else None, method=method,
                                 headers={**worldlines_auth.headers(), "Authorization": f"Bearer {token}", "Accept": "application/json",
                                          **({"Content-Type": "application/json"} if method == "POST" else {}), **(headers or {})})
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


def _token() -> str | None:
    from neonrp.core import worldlines_auth

    tok = worldlines_auth.access_token()
    return tok if tok and tok != "-" else None


def mine() -> dict[str, Any]:
    """{signed_in, runs, rewards} — or {signed_in, error}."""
    tok = _token()
    if not tok:
        return {"signed_in": False, "runs": [], "rewards": []}
    st, runs = _call("GET", "/v1/me/run-points", tok)
    if st != 200:
        return {"signed_in": st != 401, "error": (runs or {}).get("error") or f"http_{st}", "runs": [], "rewards": []}
    st2, rw = _call("GET", "/v1/me/rewards", tok)
    rewards = [r for r in ((rw or {}).get("rewards") or []) if isinstance(r, dict) and r.get("kind") == "run_points"] if st2 == 200 else []
    return {"signed_in": True, "runs": (runs or {}).get("runs") or [], "rewards": rewards}


def claim(reward_id: str, device: str | None = None) -> tuple[int, Any]:
    tok = _token()
    if not tok:
        return 401, {"error": "not_signed_in"}
    if not (isinstance(reward_id, str) and len(reward_id) == 36 and all(c in "0123456789abcdef-" for c in reward_id.lower())):
        return 400, {"error": "invalid_request"}
    return _call("POST", f"/v1/me/rewards/{reward_id}/claim", tok, {"X-Worldlines-Device": device} if device else None)
