"""Signing a user in from a local app, and keeping that session fresh.

Mirrors the Node client (``localLogin`` / ``createTokenManager`` in
packages/client-node): the same endpoints, the same single-flight rotation rule.
Standard library only.

    from worldlines_identity import local_login, create_token_manager, FileTokenStore

    store = FileTokenStore("~/.config/myapp/identity.json")   # 0600, outside any world folder
    tm = create_token_manager(issuer="https://auth.worldlines.gg", load=store.load, save=store.save)
    if tm.access_token() is None:
        tm.sign_in(local_login(issuer="https://auth.worldlines.gg"))  # opens the system browser
    headers = {"authorization": f"Bearer {tm.access_token()}"}

Sessions are dicts: ``access_token``, ``refresh_token``, ``expires_at`` (unix
seconds), ``session_id``, ``user``. Tokens never appear in a log line or an exception.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from concurrent.futures import Future
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable, Dict, List, Optional, Tuple

__all__ = [
    "IdentityError",
    "create_pkce",
    "login_url",
    "exchange_code",
    "refresh_tokens",
    "logout",
    "session_from_tokens",
    "local_login",
    "device_login",
    "login",
    "open_billing",
    "can_open_browser",
    "DEVICE_GRANT",
    "TokenManager",
    "create_token_manager",
    "FileTokenStore",
]

# post(url, body: dict, headers: dict) -> (status, parsed JSON or None); raise OSError when unreachable.
Post = Callable[[str, Dict[str, Any], Dict[str, str]], Tuple[int, Any]]


class IdentityError(Exception):
    """An identity-service refusal (``status`` 4xx/5xx) or ``status == 0`` when unreachable."""

    def __init__(self, status: int, code: str, message: Optional[str] = None) -> None:
        super().__init__(message or code)
        self.status = status
        self.code = code


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _default_post(url: str, body: Dict[str, Any], headers: Dict[str, str], timeout: float = 15.0) -> Tuple[int, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"content-type": "application/json", "accept": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:  # noqa: S310 (issuer URL from config)
            status, raw = res.status, res.read()
    except urllib.error.HTTPError as err:
        status, raw = err.code, err.read()
    try:
        return status, json.loads(raw.decode("utf-8")) if raw else None
    except ValueError:
        return status, None


def _post(post: Optional[Post], url: str, body: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Any:
    try:
        status, data = (post or _default_post)(url, body, headers or {})
    except OSError as err:
        raise IdentityError(0, "unreachable", f"identity service unreachable ({type(err).__name__})") from None
    if status < 200 or status >= 300:
        data = data if isinstance(data, dict) else {}
        raise IdentityError(status, data.get("error") or f"http_{status}", data.get("message"))
    return data


def create_pkce() -> Dict[str, str]:
    verifier = _b64url(secrets.token_bytes(32))
    return {"verifier": verifier, "challenge": _b64url(hashlib.sha256(verifier.encode("ascii")).digest()), "method": "S256"}


def login_url(issuer: str, redirect: str, code_challenge: str, provider: Optional[str] = "google", state: Optional[str] = None,
              client_id: Optional[str] = None, scopes: Optional[List[str]] = None, next_url: Optional[str] = None) -> str:
    """URL of /v1/login/start. ``redirect`` must be on the service's allowlist (or loopback) -- or, with
    ``client_id``, on that client's redirect policy. With client_id and no provider, auth shows a provider choice."""
    q: Dict[str, str] = {}
    if client_id:
        q["client_id"] = client_id
        if scopes:
            q["scope"] = " ".join(scopes)
        if next_url:
            q["next"] = next_url
    if provider:
        q["provider"] = provider
    q.update({"redirect": redirect, "code_challenge": code_challenge, "code_challenge_method": "S256"})
    if state:
        q["state"] = state
    return f"{issuer.rstrip('/')}/v1/login/start?{urllib.parse.urlencode(q)}"


def exchange_code(issuer: str, code: str, code_verifier: str, redirect: str, post: Optional[Post] = None) -> Dict[str, Any]:
    """One-time code (from the redirect) + PKCE verifier -> tokens response."""
    body = {"grant_type": "authorization_code", "code": code, "code_verifier": code_verifier, "redirect_uri": redirect}
    return _post(post, f"{issuer.rstrip('/')}/v1/token", body)


def refresh_tokens(issuer: str, refresh_token: str, post: Optional[Post] = None) -> Dict[str, Any]:
    """Refresh (rotating: the old refresh token is dead after this call)."""
    return _post(post, f"{issuer.rstrip('/')}/v1/token/refresh", {"refresh_token": refresh_token})


def logout(issuer: str, access_token: Optional[str] = None, refresh_token: Optional[str] = None, post: Optional[Post] = None) -> Any:
    headers = {"authorization": f"Bearer {access_token}"} if access_token else {}
    return _post(post, f"{issuer.rstrip('/')}/v1/logout", {"refresh_token": refresh_token} if refresh_token else {}, headers)


def session_from_tokens(t: Dict[str, Any], now: Optional[float] = None) -> Dict[str, Any]:
    """tokens response -> a storable session (absolute expiry, unix seconds)."""
    now = time.time() if now is None else now
    return {
        "access_token": t["access_token"],
        "refresh_token": t["refresh_token"],
        "expires_at": now + float(t["expires_in"]),
        "session_id": t.get("session_id"),
        "user": t.get("user"),
    }


_DONE_PAGE = {
    True: "Signed in. You can close this tab. / 登录完成，可以关闭此页。",
    False: "Sign-in failed. Please try again. / 登录失败，请重试。",
}


def local_login(
    issuer: str,
    provider: Optional[str] = None,
    open_browser: Optional[Callable[[str], Any]] = None,
    host: str = "127.0.0.1",
    port: int = 0,
    path: str = "/callback",
    timeout_s: float = 300.0,
    post: Optional[Post] = None,
    on_url: Optional[Callable[[str], Any]] = None,
    client_id: Optional[str] = None,
    scopes: Optional[List[str]] = None,
    next_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Loopback login for local apps: listen on 127.0.0.1:<port> (random by default),
    open the browser at /v1/login/start with redirect=http://127.0.0.1:<port><path>,
    wait for ?code, exchange it at /v1/token (PKCE). Blocks; returns the tokens response.
    The listener closes after one valid callback or on timeout (IdentityError 408 login_timeout).
    ``open_browser`` defaults to the system browser (``webbrowser.open``) unless only ``on_url`` is given."""
    if open_browser is None and on_url is None:
        open_browser = webbrowser.open
    if provider is None and not client_id:
        provider = "google"  # without a client: today's behaviour
    pkce = create_pkce()
    state = _b64url(secrets.token_bytes(16))
    result: "Future[Dict[str, Any]]" = Future()
    redirect_box: Dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:  # the query holds a one-time code: never log it
            pass

        def do_GET(self) -> None:  # noqa: N802
            u = urllib.parse.urlsplit(self.path)
            if u.path != path:
                self.send_response(404)
                self.end_headers()
                return
            q = dict(urllib.parse.parse_qsl(u.query))
            ok, value, err = False, None, None
            if not secrets.compare_digest(q.get("state", ""), state):
                err = IdentityError(400, "state_mismatch")
            elif not q.get("code"):
                err = IdentityError(400, q.get("error") or "no_code")
            else:
                try:
                    value, ok = exchange_code(issuer, q["code"], pkce["verifier"], redirect_box["url"], post=post), True
                except IdentityError as e:
                    err = e
            nxt = q.get("next") if ok else None
            if nxt and nxt.startswith(("https://", "http://")):  # checked by the identity service
                self.send_response(302)
                self.send_header("location", nxt)
                self.send_header("cache-control", "no-store")
                self.end_headers()
                if not result.done():
                    result.set_result(value)
                return
            page = f'<!doctype html><meta charset="utf-8"><title>Worldlines</title><body style="font:16px system-ui;text-align:center;padding-top:20vh">{_DONE_PAGE[ok]}</body>'.encode()
            self.send_response(200 if ok else 400)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("cache-control", "no-store")
            self.send_header("content-length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
            if not result.done():
                result.set_result(value) if ok else result.set_exception(err)  # type: ignore[arg-type]

    server = HTTPServer((host, port), Handler)
    server.timeout = 0.2
    redirect_box["url"] = f"http://{host}:{server.server_address[1]}{path}"
    url = login_url(issuer, redirect_box["url"], pkce["challenge"], provider=provider, state=state, client_id=client_id, scopes=scopes, next_url=next_url)

    def serve() -> None:
        while not result.done():
            server.handle_request()

    t = threading.Thread(target=serve, name="worldlines-local-login", daemon=True)
    t.start()
    try:
        if on_url:
            on_url(url)
        if open_browser:
            try:
                threading.Thread(target=open_browser, args=(url,), daemon=True).start()
            except Exception:  # noqa: BLE001 (a browser that fails to open still leaves on_url / manual copy)
                pass
        try:
            return result.result(timeout=timeout_s)
        except TimeoutError:
            raise IdentityError(408, "login_timeout") from None
        except Exception as e:  # concurrent.futures.TimeoutError is not TimeoutError before 3.11
            if type(e).__name__ == "TimeoutError":
                raise IdentityError(408, "login_timeout") from None
            raise
    finally:
        if not result.done():
            result.cancel()
        t.join(timeout=2)
        server.server_close()


DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"


def can_open_browser() -> bool:
    """Is there (probably) a browser? Not over SSH, nor on Linux without a display."""
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return False
    if sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    return True


def _eprint(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


def device_login(issuer: str, client_id: str, scopes: Optional[List[str]] = None, next_url: Optional[str] = None,
                 on_code: Optional[Callable[[Dict[str, Any]], Any]] = None, post: Optional[Post] = None,
                 sleep: Callable[[float], Any] = time.sleep, now: Callable[[], float] = time.time) -> Dict[str, Any]:
    """Device code flow (RFC 8628): show "open <url> and enter ABCD-EFGH", poll /v1/token until the user
    approves. Honours interval / slow_down; raises IdentityError (access_denied, expired_token, ...)."""
    base = issuer.rstrip("/")
    body: Dict[str, Any] = {"client_id": client_id}
    if scopes:
        body["scope"] = " ".join(scopes)
    if next_url:
        body["next"] = next_url
    code = _post(post, f"{base}/v1/device/code", body)
    show = {k: code[k] for k in ("user_code", "verification_uri", "verification_uri_complete", "expires_in")}
    if on_code:
        on_code(show)
    else:
        _eprint(f"To sign in, open {code['verification_uri']} and enter the code {code['user_code']}\n  (or open {code['verification_uri_complete']})")
    deadline = now() + float(code["expires_in"])
    interval = max(1.0, float(code.get("interval") or 5))
    while True:
        sleep(interval)
        if now() > deadline:
            raise IdentityError(400, "expired_token")
        try:
            return _post(post, f"{base}/v1/token", {"grant_type": DEVICE_GRANT, "device_code": code["device_code"], "client_id": client_id})
        except IdentityError as err:
            if err.code in ("authorization_pending", "unreachable"):
                continue
            if err.code == "slow_down":
                interval += 5
                continue
            raise


def login(issuer: str, client_id: str, scopes: Optional[List[str]] = None, device: Optional[bool] = None,
          next_url: Optional[str] = None, token_manager: "Optional[TokenManager]" = None,
          open_browser: Optional[Callable[[str], Any]] = None, on_url: Optional[Callable[[str], Any]] = None,
          on_code: Optional[Callable[[Dict[str, Any]], Any]] = None, post: Optional[Post] = None,
          timeout_s: float = 300.0, sleep: Callable[[float], Any] = time.sleep) -> Dict[str, Any]:
    """App sign-in like Claude Code / Codex: the system browser opens auth.worldlines.gg, the user signs in
    and approves (consent), the tokens come back over loopback. The device code flow is used when
    ``device=True`` or there is no browser. With ``token_manager`` the tokens go straight into it."""
    use_device = device if device is not None else not (open_browser or can_open_browser())
    if use_device:
        tokens = device_login(issuer, client_id, scopes=scopes, next_url=next_url, on_code=on_code, post=post, sleep=sleep)
    else:
        tokens = local_login(issuer, open_browser=open_browser or webbrowser.open,
                             on_url=on_url or (lambda u: _eprint(f"Opening your browser to sign in. If it does not open, visit:\n  {u}")),
                             timeout_s=timeout_s, post=post, client_id=client_id, scopes=scopes, next_url=next_url)
    if token_manager is not None:
        token_manager.sign_in(tokens)
    return tokens


def open_billing(error: Any, next_url: Optional[str] = None, open_browser: Optional[Callable[[str], Any]] = None,
                 on_url: Optional[Callable[[str], Any]] = None, headless: Optional[bool] = None) -> Optional[str]:
    """ai.worldlines.gg answers "no subscription / quota used up" (e.g. 429 quota_exceeded) with a body
    carrying ``billing_url``. Send the user there once -- no retry loop: open the browser (or only print
    the URL when headless) at billing_url + next=<your return>. ``error`` = that body (dict) or an object
    with ``.body``. Returns the URL, or None when there was none."""
    body = error if isinstance(error, dict) else getattr(error, "body", None)
    raw = body.get("billing_url") if isinstance(body, dict) else None
    if not isinstance(raw, str):
        return None
    u = urllib.parse.urlsplit(raw)
    if not (u.scheme == "https" or (u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost"))):
        return None
    if next_url:
        q = [(k, v) for k, v in urllib.parse.parse_qsl(u.query, keep_blank_values=True) if k != "next"] + [("next", next_url)]
        raw = urllib.parse.urlunsplit((u.scheme, u.netloc, u.path, urllib.parse.urlencode(q), u.fragment))
    no_browser = headless if headless is not None else not (open_browser or can_open_browser())
    (on_url or (lambda x: _eprint(f"Open this page to manage your plan: {x}" if no_browser else f"Opening billing: {x}")))(raw)
    if not no_browser:
        try:
            (open_browser or webbrowser.open)(raw)
        except Exception:  # noqa: BLE001 (the printed URL still works)
            pass
    return raw


class TokenManager:
    """Keep one session fresh. ``load()`` / ``save(session_or_None)`` persist it (e.g.
    FileTokenStore). Refreshes are single-flight across threads: rotating refresh tokens
    mean two parallel refreshes with the same token would look like replay and revoke the
    session. A 4xx on refresh means the session is dead: it is cleared (sign in again)."""

    def __init__(self, issuer: str, load: Callable[[], Optional[Dict[str, Any]]], save: Callable[[Optional[Dict[str, Any]]], Any],
                 post: Optional[Post] = None, now: Callable[[], float] = time.time, slack_s: float = 60.0) -> None:
        self.issuer = issuer
        self._load, self._save, self._post, self._now, self.slack_s = load, save, post, now, slack_s
        self._lock = threading.Lock()
        self._inflight: "Optional[Future[Dict[str, Any]]]" = None

    def _refresh(self, current: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            fut, mine = self._inflight, False
            if fut is None:
                fut = self._inflight = Future()
                mine = True
        if not mine:
            return fut.result()
        try:
            nxt = session_from_tokens(refresh_tokens(self.issuer, current["refresh_token"], post=self._post), self._now())
            self._save(nxt)
            fut.set_result(nxt)
        except BaseException as err:
            if isinstance(err, IdentityError) and 400 <= err.status < 500:
                self._save(None)
            fut.set_exception(err)
        finally:
            with self._lock:
                self._inflight = None
        return fut.result()

    def access_token(self, force: bool = False) -> Optional[str]:
        """A valid access token (refreshing first when near expiry), or None when signed out."""
        s = self._load()
        if not s:
            return None
        if not force and s["expires_at"] - self.slack_s > self._now():
            return s["access_token"]
        return self._refresh(s)["access_token"]

    def sign_in(self, tokens: Dict[str, Any]) -> None:
        self._save(session_from_tokens(tokens, self._now()))

    def sign_out(self) -> None:
        s = self._load()
        if s:
            try:
                logout(self.issuer, s.get("access_token"), s.get("refresh_token"), post=self._post)
            except IdentityError:
                pass
        self._save(None)


def create_token_manager(issuer: str, load: Callable[[], Optional[Dict[str, Any]]], save: Callable[[Optional[Dict[str, Any]]], Any],
                         post: Optional[Post] = None, now: Callable[[], float] = time.time, slack_s: float = 60.0) -> TokenManager:
    return TokenManager(issuer, load, save, post=post, now=now, slack_s=slack_s)


class FileTokenStore:
    """A session in one JSON file, mode 0600 (directory created 0700). Writes are atomic
    (temp file + rename), so a crash never leaves half a token. Keep it OUTSIDE any folder
    that gets shared, synced or uploaded (e.g. not inside a world directory)."""

    def __init__(self, path: str) -> None:
        self.path = os.path.abspath(os.path.expanduser(path))

    def load(self) -> Optional[Dict[str, Any]]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return None
        except ValueError:
            return None
        return data if isinstance(data, dict) and data.get("refresh_token") else None

    def save(self, session: Optional[Dict[str, Any]]) -> None:
        if session is None:
            try:
                os.remove(self.path)
            except FileNotFoundError:
                pass
            return
        d = os.path.dirname(self.path)
        os.makedirs(d, mode=0o700, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".identity-", dir=d)
        try:
            os.fchmod(fd, 0o600) if hasattr(os, "fchmod") else None
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(session, f)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
