"""「反馈」from the local web page (10-25 funnel check: the PyPI engine and its local page had no way to report a problem —
only iOS and the neonrp site's footer did). The page asks the engine; the engine posts to the platform's play feedback:

    POST {data}/v1/feedback/hub   {text, template: {id}, engine_version, save_id?, client: {mode: local, …}, turns: [...]}

with the engine's Worldlines session, else a guest token (identity ``POST /v1/guest {client_id}`` + this install's device
id — data takes guest feedback). The page never holds a token. ``turns`` carries one note row (the page, recent errors) —
never the save, never a key; data masks secrets again on its side."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any

TIMEOUT = 10.0
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_LOCALE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8}){0,3}$")
_VER = re.compile(r"[^A-Za-z0-9._+-]")


def data_base() -> str:
    return os.environ.get("WORLDLINES_DATA_BASE", "https://data.worldlines.gg").rstrip("/")


def _post(url: str, body: dict[str, Any], headers: dict[str, str]) -> tuple[int, Any]:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "Accept": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 — our own platform
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}
    except (OSError, ValueError) as e:
        return 0, {"error": "offline", "message": str(e)[:200]}


def guest_token() -> str | None:
    from neonrp.core import worldlines_auth as wa

    st, b = _post(f"{wa.ISSUER.rstrip('/')}/v1/guest", {"client_id": wa.CLIENT_ID},
                  {"X-Worldlines-Device": wa.device_id(), **wa.headers()})
    tok = (b or {}).get("access_token") if 200 <= st < 300 and isinstance(b, dict) else None
    return str(tok) if tok else None


def _engine_version() -> str:
    try:
        from neonrp import __version__ as v
    except Exception:  # noqa: BLE001
        v = "local"
    return _VER.sub("", str(v))[:40] or "local"


def build(text: Any, *, template_id: Any = None, save_id: Any = None, page: Any = None, errors: Any = None,
          locale: Any = None) -> dict[str, Any]:
    tid = str(template_id or "")
    loc = str(locale or "")
    errs = [str(e)[:300] for e in (errors if isinstance(errors, list) else [])][-5:]
    body: dict[str, Any] = {
        "text": str(text or "")[:1000] or None,
        "template": {"id": tid if _ID.match(tid) else "local"},
        "engine_version": _engine_version(),
        "client": {"mode": "local", "platform": sys.platform[:80], **({"locale": loc} if _LOCALE.match(loc) else {})},
        "turns": [{"n": 0, "kind": "bug", "page": str(page or "")[:300], "errors": errs}],
    }
    if save_id and _ID.match(str(save_id)):
        body["save_id"] = str(save_id)
    return body


def send(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """→ (status, {ok, error?}). 0 = offline."""
    from neonrp.core import worldlines_auth as wa

    tok = wa.access_token()
    if not tok or tok == "-":
        tok = guest_token()
    hdrs = {**wa.headers(), **({"Authorization": f"Bearer {tok}"} if tok else {})}
    st, out = _post(f"{data_base()}/v1/feedback/hub", body, hdrs)
    if st == 401 and tok:  # an access token that ran out: the shared renewal, once
        fresh = wa.refresh_now(tok)
        if fresh:
            st, out = _post(f"{data_base()}/v1/feedback/hub", body, {**hdrs, "Authorization": f"Bearer {fresh}"})
    ok = 200 <= st < 300
    err = (out or {}).get("error") if isinstance(out, dict) else None
    return st, {"ok": ok, **({} if ok else {"error": (err.get("code") if isinstance(err, dict) else err) or f"http_{st}"})}
