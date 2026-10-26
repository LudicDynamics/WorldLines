"""One session refresh at a time (10-25: two refreshes at 13:25:24 with the same rotating refresh token → identity took
the second as replay and revoked the session, a long run cut off).

- many threads with a refused (401) token at once → one refresh, all get the new token;
- a caller that read the session before someone else rotated it never sends the old refresh token;
- two processes sharing ~/.worldlines/identity.json refreshing at the same moment → one refresh (the lock file);
- chronicle's flush on a 401 renews through the same function and resends the batch once.
Everything runs against fakes: a temporary session file and a local fake identity — never the real platform."""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from neonrp._vendor.worldlines_identity import login as real_login
from neonrp.core import worldlines_auth as wa


def _jwt(sub: str, n: int) -> str:
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()  # noqa: E731
    return f"{enc({'alg': 'none'})}.{enc({'sub': sub, 'n': n})}.sig"


class _Identity:
    """Rotating refresh tokens; a refresh token used twice = replay → 401 and the session is dead."""

    def __init__(self, delay: float = 0.1) -> None:
        self.calls, self.replays, self.used, self.delay = 0, 0, set(), delay
        self.lock = threading.Lock()

    def refresh(self, rt: str) -> tuple[int, dict]:
        time.sleep(self.delay)  # long enough for parallel callers to pile up
        with self.lock:
            self.calls += 1
            if rt in self.used:
                self.replays += 1
                return 401, {"error": "invalid_grant", "message": "refresh token reuse detected; session revoked"}
            self.used.add(rt)
            n = self.calls
        return 200, {"access_token": _jwt("u1", n), "refresh_token": f"r{n}", "expires_in": 900, "user": {"email": "n@x.test"}}


@pytest.fixture()
def session_file(tmp_path, monkeypatch):
    f = tmp_path / "home" / ".worldlines" / "identity.json"
    f.parent.mkdir(parents=True)
    monkeypatch.setenv("WORLDLINES_IDENTITY_FILE", str(f))
    monkeypatch.delenv("WORLDLINES_API_KEY", raising=False)
    monkeypatch.setattr(wa, "_wl_login", lambda: real_login)
    wa._mgrs.clear()
    wa._lost.clear()
    yield f
    wa._mgrs.clear()
    wa._lost.clear()


def _write(f: Path, access: str, refresh: str = "r0", expires_in: float = 900) -> None:
    f.write_text(json.dumps({"access_token": access, "refresh_token": refresh, "expires_at": time.time() + expires_in}), encoding="utf-8")


@pytest.fixture()
def idp(monkeypatch):
    i = _Identity()

    def send(url, body, headers):
        assert url.endswith("/v1/token/refresh")
        return i.refresh(body["refresh_token"])

    monkeypatch.setattr(wa, "_send", send)
    return i


def test_parallel_401s_refresh_once(session_file, idp):
    a0 = _jwt("u1", 0)
    _write(session_file, a0)
    got: list = []
    ts = [threading.Thread(target=lambda: got.append(wa.refresh_now(a0))) for _ in range(12)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(10)
    assert idp.calls == 1 and idp.replays == 0
    assert len(got) == 12 and set(got) == {_jwt("u1", 1)}
    assert json.loads(session_file.read_text())["refresh_token"] == "r1"


def test_expiring_session_parallel_callers_refresh_once(session_file, idp):
    _write(session_file, _jwt("u1", 0), expires_in=30)  # < 60 s left: the first caller renews, the rest wait for it
    got: list = []
    ts = [threading.Thread(target=lambda: got.append(wa.access_token())) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(10)
    assert idp.calls == 1 and set(got) == {_jwt("u1", 1)}


def test_forced_manager_refreshes_in_parallel_send_once(session_file, idp):
    """The iOS shell renews through the shared manager (wl_host: mgr.access_token(force=True)) — still one refresh."""
    _write(session_file, _jwt("u1", 0))
    mgr = wa._manager()
    got: list = []
    ts = [threading.Thread(target=lambda: got.append(mgr.access_token(force=True))) for _ in range(10)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(10)
    assert idp.calls == 1 and idp.replays == 0 and set(got) == {_jwt("u1", 1)}


def test_ios_client_names(monkeypatch):
    from neonrp.core import chronicle

    monkeypatch.setenv("WORLDLINES_CLIENT", "ios")
    assert wa.client_header() == {"X-Worldlines-Client": "ios"} and chronicle.client() == "app"
    monkeypatch.setenv("WORLDLINES_CLIENT", "app")
    assert wa.client_header() == {"X-Worldlines-Client": "ios"} and chronicle.client() == "app"


def test_a_session_with_time_left_is_not_refreshed(session_file, idp):
    _write(session_file, _jwt("u1", 0), expires_in=120)
    assert wa.access_token() == _jwt("u1", 0)
    assert idp.calls == 0


def test_a_stale_refresh_token_is_never_sent_again(session_file, idp):
    _write(session_file, _jwt("u1", 5), refresh="r5")  # another process already rotated r0 → r5
    st, data = wa.post(f"{wa.ISSUER}/v1/token/refresh", {"refresh_token": "r0"}, {})
    assert st == 200 and data["access_token"] == _jwt("u1", 5) and data["refresh_token"] == "r5"
    assert idp.calls == 0


def test_a_stale_refresh_token_near_expiry_renews_from_the_current_one(session_file, idp):
    _write(session_file, _jwt("u1", 5), refresh="r5", expires_in=10)
    st, data = wa.post(f"{wa.ISSUER}/v1/token/refresh", {"refresh_token": "r0"}, {})
    assert st == 200 and idp.used == {"r5"} and idp.replays == 0


class _FakeAuth(BaseHTTPRequestHandler):
    idp: _Identity

    def log_message(self, *a):
        pass

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        st, out = self.idp.refresh(body.get("refresh_token", "")) if self.path == "/v1/token/refresh" else (404, {})
        data = json.dumps(out).encode()
        self.send_response(st)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


_CHILD = """
import sys, time
from neonrp.core import worldlines_auth as wa
start = float(sys.argv[1])
while time.time() < start:
    time.sleep(0.005)
print(wa.refresh_now(sys.argv[2]) or "none", flush=True)
"""


def test_two_processes_refresh_once(session_file, tmp_path):
    """Engine + Launcher (or the desktop app, or the local Hub) on one machine, both told 401 at the same moment."""
    _FakeAuth.idp = idp = _Identity(delay=0.3)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _FakeAuth)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        a0 = _jwt("u1", 0)
        _write(session_file, a0)
        env = {**os.environ, "WORLDLINES_IDENTITY_FILE": str(session_file), "HOME": str(tmp_path / "home"),
               "WORLDLINES_ISSUER": f"http://127.0.0.1:{srv.server_address[1]}"}
        env.pop("WORLDLINES_API_KEY", None)
        start = time.time() + 2.0  # both are up and waiting before either asks
        procs = [subprocess.Popen([sys.executable, "-c", _CHILD, str(start), a0], env=env, stdout=subprocess.PIPE, text=True)
                 for _ in range(3)]
        outs = [p.communicate(timeout=60)[0].strip() for p in procs]
    finally:
        srv.shutdown()
        srv.server_close()
    assert idp.calls == 1 and idp.replays == 0, (idp.calls, outs)
    assert set(outs) == {_jwt("u1", 1)}
    assert json.loads(session_file.read_text())["refresh_token"] == "r1"


def test_chronicle_flush_renews_on_401_and_resends_once(session_file, idp, monkeypatch, tmp_path):
    from neonrp.core import chronicle

    monkeypatch.setattr(chronicle, "SPOOL", tmp_path / "spool.jsonl")
    monkeypatch.delenv("NEONRP_CHRONICLE", raising=False)
    a0 = _jwt("u1", 0)
    _write(session_file, a0)
    seen: list = []

    def post(body, token):
        seen.append(token)
        return (401, {}) if token == a0 else (200, {"results": [{"index": 0, "code": "created"}]})

    monkeypatch.setattr(chronicle, "_post", post)
    chronicle.emit({"type": "world.open", "world_ref": "builtin:x", "open_id": "o1", "client": "local"}, send=False)
    out = chronicle.flush()
    assert seen == [a0, _jwt("u1", 1)] and idp.calls == 1
    assert out["sent"] == 1 and chronicle.pending() == []


def test_chronicle_flush_keeps_the_batch_when_renewal_is_refused(session_file, monkeypatch, tmp_path):
    from neonrp.core import chronicle

    monkeypatch.setattr(chronicle, "SPOOL", tmp_path / "spool.jsonl")
    monkeypatch.delenv("NEONRP_CHRONICLE", raising=False)
    monkeypatch.setattr(wa, "_send", lambda url, body, headers: (401, {"error": "invalid_grant"}))
    a0 = _jwt("u1", 0)
    _write(session_file, a0)
    seen: list = []
    monkeypatch.setattr(chronicle, "_post", lambda body, token: (seen.append(token), (401, {}))[1])
    chronicle.emit({"type": "world.open", "world_ref": "builtin:x", "open_id": "o1", "client": "local"}, send=False)
    out = chronicle.flush()
    assert seen == [a0]  # no loop: one try, a refused renewal, the batch waits for the next sign-in
    assert out["kept"] == 1
