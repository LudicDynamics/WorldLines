"""Worldlines account for the engine: ``ai.worldlines.gg/v1`` is an ordinary OpenAI-compatible endpoint.
Credentials, in order:

1. ``WORLDLINES_API_KEY`` (a PAT ``wl_pat_…`` with ``api:use``) — scripts, CI, a key pasted in settings;
2. a signed-in session from **connect** (like Claude Code / Codex): the browser opens auth.worldlines.gg, the user signs in
   with their own subscription, the loopback PKCE flow hands back tokens, the token manager keeps them fresh (0600 file);
3. nothing → the caller treats it like any provider without a key.

The identity client's login half ships with NeonRP (``neonrp._vendor.worldlines_identity``); an installed
``worldlines-identity`` wins. Sign-in UI: the TUI's /login; ``python -m neonrp.core.worldlines_auth connect`` in a shell.

What signing in is for: the engine is free and plays on any OpenAI-compatible provider the player configures
(their own server included). A Worldlines account adds three things on top: Jev (System One, the fast judge) through
ai.worldlines.gg/v1/systemone, our model relay (the `worldlines` preset), and uploading one's own worlds to the Hub.
Without it — no Jev — the game still plays: judgments fall back to the player's own model, or to none."""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

ISSUER = os.environ.get("WORLDLINES_ISSUER", "https://auth.worldlines.gg")
API_BASE = os.environ.get("WORLDLINES_API_BASE", "https://ai.worldlines.gg/v1")
# X-Worldlines-Product: NeonRP is the platform product `hub` (worldlines-platform products/hub/manifest.json — domain
# neonrp.worldlines.gg, client_id neonrp, chronicle `hub`). Not `local`: that is LivingCanvas's local edition (10-14 D1).
PRODUCT = os.environ.get("WORLDLINES_PRODUCT", "hub")


def store_path() -> Path:
    return Path(os.environ.get("WORLDLINES_IDENTITY_FILE", "~/.worldlines/identity.json")).expanduser()


def is_worldlines(base_url: str | None) -> bool:
    return bool(base_url) and "worldlines.gg" in str(base_url)


def _wl_login() -> Any:
    """The identity client's login module: the installed package if present, else the copy shipped with NeonRP."""
    try:
        from worldlines_identity import login as m  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        from neonrp._vendor.worldlines_identity import login as m
    return m


# 10-17 登录偶尔 timeout:线上 identity 每个接口 0.15–0.45s(东京实测),慢的是网络那一跳。每个请求 10s 超时(原来 15s),
# 网络错误自动再试两次(0.5s · 1.5s 后)—— 但会换掉凭证的请求(授权码换 token、续期)只在「请求根本没送到」时再试(DNS / 拒绝连接):
# 送到了再发一次 = 重放,授权码已经用掉 / 续期令牌已经轮换,identity 会当成重放吊销整个会话。设备码轮询不在这里重试(它自己会接着轮询)。
POST_TIMEOUT = 10.0
RETRY_WAITS = (0.5, 1.5)
_IDEMPOTENT = ("/v1/device/code", "/v1/logout")


def _not_sent(err: BaseException) -> bool:
    import errno
    import socket

    r = getattr(err, "reason", err)
    return isinstance(r, (socket.gaierror, ConnectionRefusedError)) or getattr(r, "errno", None) in (
        errno.ENETUNREACH, errno.EHOSTUNREACH, errno.ENETDOWN)


def post(url: str, body: dict[str, Any], headers: dict[str, str], *, sleep: Any = time.sleep, send: Any = None) -> tuple[int, Any]:
    """The identity client's ``post`` hook (``login`` / ``create_token_manager`` / ``logout``): timeout + the retry rule above.
    Raises OSError when it stays unreachable (the client turns that into ``IdentityError(0, "unreachable")``)."""
    send = send or (lambda u, b, h: _wl_login()._default_post(u, b, h, timeout=POST_TIMEOUT))
    idem = url.rstrip("/").endswith(_IDEMPOTENT)
    polling = (body or {}).get("grant_type") == "urn:ietf:params:oauth:grant-type:device_code"
    for i, wait in enumerate((*RETRY_WAITS, None)):
        try:
            st, data = send(url, body, headers)
        except OSError as err:
            if wait is None or polling or not (idem or _not_sent(err)):
                raise
            sleep(wait)
            continue
        if idem and st in (502, 503, 504) and wait is not None:
            sleep(wait)
            continue
        return st, data
    raise OSError("unreachable")  # pragma: no cover — the loop always returns or raises


def _takes_post(fn: Any) -> bool:
    import inspect

    try:
        ps = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    return "post" in ps or any(p.kind is p.VAR_KEYWORD for p in ps.values())


# One token manager per session file, shared by every caller in the process (10-19, iOS: every request 401 after the
# access token expired). Its refresh is single-flight only within one manager: a fresh manager per call let the turn, the
# chat, Jev and the chronicle each refresh with the same rotating refresh token at once — identity takes the second use
# as replay and revokes the whole session, then every refresh is a 4xx and the session file is cleared.
_mgr_lock = threading.Lock()
_mgrs: dict[tuple[str, int], Any] = {}  # (session file, identity client module) → its manager
# A session that was there and is gone because identity refused to refresh it (4xx): "sign in again", not "no model".
_lost: dict[str, float] = {}


def _manager() -> Any | None:
    path = str(store_path())
    try:
        m = _wl_login()
        FileTokenStore, create_token_manager = m.FileTokenStore, m.create_token_manager
    except Exception:  # noqa: BLE001 — never break a turn over the session
        return None
    key = (path, id(m))
    with _mgr_lock:
        mgr = _mgrs.get(key)
        if mgr is None:
            store = FileTokenStore(path)
            mgr = _mgrs[key] = create_token_manager(ISSUER, store.load, store.save,
                                                    **({"post": post} if _takes_post(create_token_manager) else {}))
        return mgr


def _note_refusal(err: BaseException) -> None:
    st = getattr(err, "status", None)
    if isinstance(st, int) and 400 <= st < 500:
        _lost[str(store_path())] = time.time()


def session_expired() -> bool:
    """Signed in before, and identity refused to renew the session (it was revoked or ran out): the player has to sign in
    again. False once a session is back (a new sign-in), and for someone who never signed in."""
    path = str(store_path())
    if path not in _lost:
        return False
    if store_path().exists():
        _lost.pop(path, None)
        return False
    return True


def refresh_now(stale: str | None = None) -> str | None:
    """After a 401 from ai.worldlines.gg: renew the session once and hand back the new access token (None = it cannot be
    renewed: sign in again). ``stale`` = the token that was refused — if the session already moved on (another caller
    refreshed meanwhile), the current token is returned without a second refresh."""
    if os.environ.get("WORLDLINES_API_KEY", "").strip():
        return None  # a PAT is not renewed here
    mgr = _manager()
    if mgr is None:
        return None
    try:
        cur = mgr.access_token()
        if cur and stale and cur != stale:
            return str(cur)
        tok = mgr.access_token(force=True)
        return str(tok) if tok else None
    except Exception as err:  # noqa: BLE001 — a refused / unreachable refresh: not signed in any more (or for now)
        _note_refusal(err)
        return None


def _stored_access() -> str | None:
    try:
        s = json.loads(store_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    tok = s.get("access_token") if isinstance(s, dict) else None
    exp = float(s.get("expires_at") or 0) if isinstance(s, dict) else 0
    if tok and (not exp or exp > time.time() + 30):
        return str(tok)
    return None


def access_token() -> str | None:
    """A bearer for ai.worldlines.gg, or None. Never raises."""
    pat = os.environ.get("WORLDLINES_API_KEY", "").strip()
    if pat:
        return pat
    mgr = _manager()
    if mgr is not None:
        try:
            tok = mgr.access_token()
            if tok:
                return str(tok)
        except Exception as err:  # noqa: BLE001 — an expired / revoked session is "not signed in"
            _note_refusal(err)
    return _stored_access()


def headers() -> dict[str, str]:
    return {"X-Worldlines-Product": PRODUCT}


# X-Worldlines-World (2026-10-21): which world the model calls are for — the bound run's template id (ai records it on
# api.usage.world_id; billing pays a run's settlement points only on billed calls of that world during the run, never
# on what the client says). One run is bound at a time (the web engine / the browser engine); None = not a template run.
_WORLD: dict[str, str | None] = {"id": None}
_WORLD_ID_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def set_world(world_id: str | None) -> None:
    _WORLD["id"] = world_id if world_id and _WORLD_ID_OK.match(str(world_id)) else None


def world_header() -> dict[str, str]:
    return {"X-Worldlines-World": str(_WORLD["id"])} if _WORLD["id"] else {}


def bills_run(root: Any) -> bool:
    """This run's model goes through the Worldlines account (ai.worldlines.gg / the browser engine's ``web`` model on the
    page's token) — not the player's own key. Only such runs can have their points paid (billing sees the calls)."""
    try:
        from neonrp.core.config import load_config, resolve_provider

        p = resolve_provider(load_config(Path(root)), None, None)
    except Exception:  # noqa: BLE001 — a run whose config does not load bills nothing we know of
        return False
    return is_worldlines(p.base_url) or (p.api_key_env or "") == "WORLDLINES_API_KEY"


def status() -> dict[str, Any]:
    src = "env" if os.environ.get("WORLDLINES_API_KEY", "").strip() else ("session" if store_path().exists() else None)
    signed = bool(access_token())
    return {"signed_in": signed, "expired": not signed and session_expired(), "source": src, "issuer": ISSUER, "api": API_BASE,
            "store": str(store_path())}


_ENT: dict[str, Any] = {}  # {"at": epoch, "token": the access token it was read with, "value": the answer}


def entitlements(ttl: float = 60.0) -> dict[str, Any] | None:
    """What the signed-in account may use right now — billing's ``GET /v1/me/entitlements`` (``{plan, tier, limits, …}``;
    ``tier`` is reckoned from the live subscription: free · story · vivid). Cached ``ttl`` seconds per session. None =
    not signed in, or the platform did not answer (the caller decides what that means)."""
    import urllib.error
    import urllib.request

    tok = access_token()
    if not tok:
        return None
    now = time.time()
    if _ENT.get("token") == tok and now - float(_ENT.get("at") or 0) < ttl:
        return _ENT.get("value")
    base = os.environ.get("WORLDLINES_BILLING_BASE", "https://billing.worldlines.gg").rstrip("/")
    req = urllib.request.Request(f"{base}/v1/me/entitlements", headers={"authorization": f"Bearer {tok}", "accept": "application/json", **headers()})
    try:
        with urllib.request.urlopen(req, timeout=POST_TIMEOUT) as r:  # noqa: S310 — our own platform URL
            value = json.loads(r.read().decode("utf-8") or "{}")
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return None
    value = value if isinstance(value, dict) else None
    _ENT.update(at=now, token=tok, value=value)
    return value


CLIENT_ID = os.environ.get("WORLDLINES_CLIENT_ID", "neonrp")  # the app registered in identity (connect page shows it)
# 10-15: sharing a replay registers + uploads it as the player's own work and posts it (core/replay_share), and what
# was played is told to chronicle (core/chronicle) — a session from before this asks the player to sign in again.
# One scope the identity does not let the `neonrp` app ask for fails the whole sign-in (invalid_scope): the full set is
# asked first, and on invalid_scope once more without `sns:share` (it arrives with identity 0016; ios2 does the same).
# PROD_SCOPES = what live identity allows today (worldlines-platform main, migrations 0004 / 0006).
PROD_SCOPES = ("profile:read", "api:use", "resources:read", "resources:write", "storage:read", "storage:write", "chronicle:read",
               "chronicle:write", "data:read", "data:write")
FALLBACK_SCOPES = ("profile:read", "api:use", "resources:write", "storage:write", "chronicle:write")
SCOPES = FALLBACK_SCOPES + ("data:read", "data:write", "sns:share")  # data:*: the collection on the account (core/collection_sync, 10-18)


def connect(provider: str = "google", *, open_browser: bool = True, on_url: Any = None, on_code: Any = None,
            device: bool | None = None) -> dict[str, Any]:
    """Sign in through the browser and keep the session. Prefers the identity client's ``login()`` (auth.worldlines.gg
    /connect: app id + scopes + PKCE, short-code fallback when no browser); falls back to ``local_login`` (loopback
    PKCE, same token shape). Needs ``worldlines-identity``.

    ``device=True`` (TUI ``/login code``) is the short-code flow even on a desktop: no browser is opened here, the UI
    shows the code (``on_code``) and the player opens the page wherever they like. ``None`` = let ``login()`` decide."""
    _wl = _wl_login()
    if device:
        open_browser = False
    opener = None
    if open_browser:
        import webbrowser

        opener = webbrowser.open
    if hasattr(_wl, "login"):  # the /connect flow (identity 10-01 design); the UI shows the URL / the short code
        extra = {"post": post} if _takes_post(_wl.login) else {}

        def go(scopes: tuple[str, ...]) -> Any:
            return _wl.login(ISSUER, client_id=CLIENT_ID, scopes=list(scopes), device=device, open_browser=opener,
                             on_url=on_url, on_code=on_code, **extra)

        try:
            tokens = go(SCOPES)
        except Exception as exc:  # noqa: BLE001 — only invalid_scope is retried; anything else is the caller's
            if getattr(exc, "code", None) != "invalid_scope":
                raise
            tokens = go(FALLBACK_SCOPES)
    else:
        tokens = _wl.local_login(ISSUER, provider=provider, open_browser=opener, on_url=on_url or (lambda u: print(f"在浏览器里打开:{u}")),
                               **({"post": post} if _takes_post(_wl.local_login) else {}))
    session = _wl.session_from_tokens(tokens) if "expires_in" in (tokens or {}) else dict(tokens or {})
    _wl.FileTokenStore(str(store_path())).save(session)
    return status()


ABOUT = {
    "zh": ("引擎免费:在设置里接上你自己的模型服务(任何兼容 OpenAI 接口的服务,也可以是你自己的服务器)就能玩。\n"
           "登录 Worldlines 账号多三样:Jev 判断器(角色判断与校验更快更稳)、我们的模型中转(模型选 worldlines,用账号额度)、把自己的世界上传到 Hub。\n"
           "不登录、没有 Jev 也能玩:判断会改用你自己的模型来答,或者不用判断器。"),
    "en": ("The engine is free: connect your own model provider in settings (any OpenAI-compatible endpoint, your own server included) and play.\n"
           "A Worldlines account adds three things: Jev, the fast judge (quicker, steadier character judgments and checks); our model relay (pick the worldlines model, uses your account's quota); and uploading your own worlds to the Hub.\n"
           "No account, no Jev — you can still play: judgments fall back to your own model, or to none."),
    "ja": ("エンジンは無料:設定で自分のモデルサービス(OpenAI 互換ならどれでも。自分のサーバーでも)をつなげば遊べる。\n"
           "Worldlines アカウントでログインすると三つ増える:Jev 判定器(キャラの判断と検証が速く安定)、こちらのモデル中継(モデルに worldlines を選び、アカウントの枠を使う)、自分の世界を Hub にアップロード。\n"
           "ログインしなくても、Jev がなくても遊べる:判定は自分のモデルが答えるか、判定器なしになる。"),
}


def about(lang: str = "zh") -> str:
    return ABOUT.get(lang) or ABOUT["en"]


def disconnect(*, background: bool = False) -> None:
    """Sign out: revoke the session at identity, then drop the session file. ``background=True`` (the Hub's / the iOS app's
    「退出」, 10-17): the file goes first and the revoke runs on its own thread — signing out never waits on the network
    (a revoke that never arrives leaves a session that expires by itself)."""
    if background:
        _wl = _wl_login()
        s = _wl.FileTokenStore(str(store_path())).load()
        try:
            store_path().unlink()
        except OSError:
            pass
        if s:
            import threading

            def revoke() -> None:
                try:
                    _wl.logout(ISSUER, s.get("access_token"), s.get("refresh_token"), **({"post": post} if _takes_post(_wl.logout) else {}))
                except Exception:  # noqa: BLE001
                    pass

            threading.Thread(target=revoke, daemon=True, name="worldlines-logout").start()
        return
    mgr = _manager()
    if mgr is not None:
        try:
            mgr.sign_out()
        except Exception:  # noqa: BLE001
            pass
    try:
        store_path().unlink()
    except OSError:
        pass


if __name__ == "__main__":  # python -m neonrp.core.worldlines_auth connect|status|disconnect
    import sys

    cmd = (sys.argv[1:] or ["status"])[0]
    if cmd == "connect":
        print(json.dumps(connect(), ensure_ascii=False, indent=2))
    elif cmd == "disconnect":
        disconnect()
        print(json.dumps(status(), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(status(), ensure_ascii=False, indent=2))
