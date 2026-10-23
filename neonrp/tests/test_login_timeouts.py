"""登录超时 / 重试(niko 10-17:登录偶尔 timeout,退出像卡住)—— 引擎这边:
worldlines_auth.post = identity 客户端的 post 钩子:10s 超时;发码 / 撤销连不上(或 502–504)再试两次;授权码换 token / 续期只在请求没送到时再试
(DNS / 拒绝连接 —— 送到了再发 = 重放);设备码轮询不在这里重试。本地 Hub 的后台浏览器登录:状态 + 错误码 + 取消 + 退出不等网络。"""
from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error

import pytest

from neonrp.core import worldlines_auth as wa
from neonrp.webui import launcher_routes as lr


def _run(url, results, body=None):
    seen, naps = [], []

    def send(u, b, h):
        seen.append(u)
        r = results[min(len(seen) - 1, len(results) - 1)]
        if isinstance(r, BaseException):
            raise r
        return r

    try:
        got = wa.post(url, body or {}, {}, sleep=naps.append, send=send)
    except OSError as e:
        got = e
    return got, len(seen), naps


REFUSED = urllib.error.URLError(ConnectionRefusedError(61, "refused"))
DNS = urllib.error.URLError(socket.gaierror(8, "nodename nor servname"))
TIMEOUT = urllib.error.URLError(TimeoutError("timed out"))


def test_device_code_and_logout_retry_any_network_error():
    for path in ("/v1/device/code", "/v1/logout"):
        got, n, naps = _run(f"https://auth.test{path}", [TIMEOUT, REFUSED, (200, {"ok": 1})])
        assert got == (200, {"ok": 1}) and n == 3 and naps == [0.5, 1.5]
    got, n, _ = _run("https://auth.test/v1/device/code", [(503, {}), (200, {"ok": 1})])
    assert got == (200, {"ok": 1}) and n == 2
    got, n, _ = _run("https://auth.test/v1/device/code", [TIMEOUT])
    assert isinstance(got, OSError) and n == 3, "three tries, then the error goes up (not swallowed)"


def test_code_exchange_and_refresh_retry_only_when_not_sent():
    code = {"grant_type": "authorization_code", "code": "c"}
    got, n, _ = _run("https://auth.test/v1/token", [DNS, REFUSED, (200, {"access_token": "a"})], code)
    assert got == (200, {"access_token": "a"}) and n == 3
    got, n, naps = _run("https://auth.test/v1/token", [TIMEOUT], code)
    assert isinstance(got, OSError) and n == 1 and naps == [], "a request that may have arrived is not sent again (single-use code)"
    got, n, _ = _run("https://auth.test/v1/token/refresh", [TIMEOUT], {"refresh_token": "r"})
    assert isinstance(got, OSError) and n == 1, "rotating refresh token: resending = replay = the session gets revoked"
    got, n, _ = _run("https://auth.test/v1/token", [(503, {})], code)
    assert got == (503, {}) and n == 1, "a 5xx on a code exchange is reported, not retried"


def test_device_polling_is_not_retried_here():
    got, n, naps = _run("https://auth.test/v1/token", [REFUSED], {"grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
    assert isinstance(got, OSError) and n == 1 and naps == []


def test_connect_hands_the_post_hook_to_the_client(monkeypatch, tmp_path):
    monkeypatch.setenv("WORLDLINES_IDENTITY_FILE", str(tmp_path / "id.json"))
    m = wa._wl_login()
    seen = {}

    def login(issuer, **kw):
        seen.update(kw)
        return {"access_token": "a", "refresh_token": "r", "expires_in": 900}

    monkeypatch.setattr(m, "login", login)
    monkeypatch.setattr(wa, "_manager", lambda: None)
    wa.connect(open_browser=False)
    assert seen["post"] is wa.post
    assert wa.POST_TIMEOUT == 10.0


def test_background_disconnect_drops_the_file_first(monkeypatch, tmp_path):
    f = tmp_path / "id.json"
    monkeypatch.setenv("WORLDLINES_IDENTITY_FILE", str(f))
    m = wa._wl_login()
    m.FileTokenStore(str(f)).save({"access_token": "a", "refresh_token": "r", "expires_at": time.time() + 900})
    hit = threading.Event()

    def slow_logout(issuer, access=None, refresh=None, post=None):
        time.sleep(1.0)
        hit.set()

    monkeypatch.setattr(m, "logout", slow_logout)
    t0 = time.time()
    wa.disconnect(background=True)
    assert time.time() - t0 < 0.5 and not f.exists()
    assert hit.wait(3), "the revoke still goes out"


@pytest.fixture
def login_state(monkeypatch):
    monkeypatch.setattr(lr, "_LOGIN", {"state": "idle", "error": None, "code": None, "url": None, "gen": 0})
    return lr._LOGIN


def _until(cond, secs=3.0):
    end = time.time() + secs
    while time.time() < end and not cond():
        time.sleep(0.02)
    return cond()


def test_local_login_error_carries_the_identity_code(monkeypatch, login_state):
    m = wa._wl_login()

    def boom(**kw):
        kw["on_url"]("https://auth.test/v1/login/start?x")
        raise m.IdentityError(408, "login_timeout")

    monkeypatch.setattr(wa, "connect", boom)
    lr._start_login()
    assert _until(lambda: login_state["state"] == "error")
    assert login_state["code"] == "login_timeout" and login_state["url"] is None


def test_local_login_cancel_lets_a_new_one_start(monkeypatch, login_state):
    gate, calls = threading.Event(), []

    def wait(**kw):
        calls.append(1)
        kw["on_url"](f"https://auth.test/{len(calls)}")
        gate.wait(5)

    monkeypatch.setattr(wa, "connect", wait)
    lr._start_login()
    assert _until(lambda: login_state["url"] == "https://auth.test/1")
    lr._start_login()
    assert len(calls) == 1, "one at a time"
    lr._cancel_login()
    assert login_state["state"] == "cancelled" and login_state["url"] is None
    lr._start_login()
    assert _until(lambda: len(calls) == 2) and login_state["state"] == "running"
    gate.set()
    assert _until(lambda: login_state["state"] == "idle"), "the newer one finishing sets the state; the cancelled one does not"
