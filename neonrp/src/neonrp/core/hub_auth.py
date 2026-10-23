"""Hub token management with browser-based OAuth login.

The Hub API at ``api.worldlines.gg`` requires a Bearer token obtained from
``worldlines.gg/account``. This module stores the token locally at
``~/.worldlines/hub_token`` and provides a browser-based login flow: it
starts a local HTTP server, opens the browser to the Hub account page, and
waits for the token to arrive via a localhost redirect (no copy-paste).
"""

from __future__ import annotations

import json
import logging
import os
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

HUB_TOKEN_FILE = Path.home() / ".worldlines" / "hub_token"
# The page where a logged-in user sees their API token / can create one.
HUB_ACCOUNT_URL = "https://hub.worldlines.gg/account"
HUB_API_URL_DEFAULT = "https://api.worldlines.gg"
CALLBACK_TIMEOUT_S = 120  # how long the local server waits for the redirect


def get_hub_token() -> str | None:
    """Return the stored Hub token, or ``None`` if not logged in.

    Checks, in order: ``HUB_API_TOKEN`` env var, ``~/.worldlines/hub_token``.
    """
    env_token = os.environ.get("HUB_API_TOKEN", "").strip()
    if env_token:
        return env_token
    # 10-02: the Worldlines account session (TUI /login) is the one sign-in — uploads ride it too; an old hub_token still works
    try:
        from neonrp.core import worldlines_auth

        if worldlines_auth.store_path().exists() or os.environ.get("WORLDLINES_API_KEY"):
            tok = worldlines_auth.access_token()
            if tok:
                return tok
    except Exception:  # noqa: BLE001
        pass
    try:
        if HUB_TOKEN_FILE.is_file():
            data = json.loads(HUB_TOKEN_FILE.read_text(encoding="utf-8"))
            token = str(data.get("token", "")).strip()
            if token:
                return token
    except (OSError, ValueError, KeyError):
        pass
    return None


def save_hub_token(token: str) -> None:
    """Persist a Hub token to ``~/.worldlines/hub_token`` (mode 0600)."""
    HUB_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"token": token.strip()}, indent=2, ensure_ascii=False)
    HUB_TOKEN_FILE.write_text(payload + "\n", encoding="utf-8")
    # Restrictive permissions — the token is a secret.
    try:
        os.chmod(HUB_TOKEN_FILE, 0o600)
    except OSError:
        pass


def clear_hub_token() -> None:
    """Remove the stored token (logout)."""
    try:
        HUB_TOKEN_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def hub_browser_login(callback_port: int = 0) -> str | None:
    """Open the browser to the Hub account page and wait for a localhost
    redirect carrying the token. Returns the token string, or ``None`` if
    the user closed the browser / the callback timed out.

    If the Hub site does not yet support ``?callback=``, this still opens
    the account page — the user can copy the token and the caller can fall
    back to a manual-entry prompt.

    ``callback_port=0`` picks a random available port.
    """
    import socket

    # Pick a port
    if callback_port == 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            callback_port = s.getsockname()[1]

    result: dict[str, Any] = {"token": None}

    class _CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            token = (params.get("token") or [None])[0]
            if not token:
                token = (params.get("hub_token") or [None])[0]
            if token:
                result["token"] = token.strip()
                self._respond(200, "OK — you may close this window.")
            elif parsed.path == "/callback" or parsed.path.startswith("/callback"):
                # No token param — still close gracefully.
                self._respond(200, "No token received. You may close this window.")
            else:
                self._respond(200, "Listening for Hub login redirect...")

        def _respond(self, code: int, body: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        def log_message(self, fmt, *args) -> None:  # noqa: N802
            logger.debug("hub-auth server: %s", fmt % args)

    server = HTTPServer(("127.0.0.1", callback_port), _CallbackHandler)
    server.timeout = 1  # check result[] every second
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    callback_url = f"http://localhost:{callback_port}/callback"
    account_url = f"{HUB_ACCOUNT_URL}?callback={callback_url}"
    webbrowser.open(account_url)

    # Wait for the redirect or timeout
    waited = 0
    while result["token"] is None and waited < CALLBACK_TIMEOUT_S:
        import time
        time.sleep(0.25)
        waited += 0.25

    server.shutdown()
    thread.join(timeout=2)

    token: str | None = result["token"]
    if token:
        save_hub_token(token)
    return token
