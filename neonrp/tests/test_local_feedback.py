"""「反馈」from the local web page (10-25): the page → engine POST /api/v1/local/feedback → data /v1/feedback/hub with the
engine's session, else a guest token. Against local fakes (data + identity), never the platform."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from neonrp.core import feedback_send
from neonrp.core import worldlines_auth as wa


class _Fake(BaseHTTPRequestHandler):
    log: list = []
    data_status = 201

    def log_message(self, *a):
        pass

    def _send(self, st, body):
        data = json.dumps(body).encode()
        self.send_response(st)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        h = {k.lower(): v for k, v in self.headers.items()}
        type(self).log.append((self.path, h, body))
        if self.path == "/v1/guest":
            return self._send(200, {"access_token": "guest-tok", "expires_in": 900})
        if self.path == "/v1/feedback/hub":
            return self._send(type(self).data_status, {"id": "f1"} if type(self).data_status < 300 else {"error": {"code": "rate_limited"}})
        self._send(404, {})


@pytest.fixture()
def fake(monkeypatch, tmp_path):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    _Fake.log, _Fake.data_status = [], 201
    monkeypatch.setenv("WORLDLINES_DATA_BASE", base)
    monkeypatch.setattr(wa, "ISSUER", base)
    monkeypatch.setenv("WORLDLINES_IDENTITY_FILE", str(tmp_path / "wl" / "identity.json"))
    wa._mgrs.clear()
    yield base
    srv.shutdown()
    srv.server_close()
    wa._mgrs.clear()


def test_body_matches_the_platform_schema():
    b = feedback_send.build("卡住了", template_id="pct-house", save_id="tpl-pct-house-20261025-120000", page="/local#test",
                            errors=["x"] * 9, locale="zh-CN")
    assert set(b) <= {"text", "template", "engine_version", "save_id", "client", "turns", "screenshot"}
    assert b["template"] == {"id": "pct-house"} and b["client"]["mode"] == "local" and b["client"]["locale"] == "zh-CN"
    assert len(b["turns"][0]["errors"]) == 5
    bad = feedback_send.build("", template_id="../x", save_id="a b", locale="zh-Hans-CN-x-toolong")
    assert bad["template"] == {"id": "local"} and "save_id" not in bad and "locale" not in bad["client"] and bad["text"] is None


def test_signed_in_sends_with_the_session(fake, monkeypatch):
    monkeypatch.setenv("WORLDLINES_API_KEY", "wl_pat_test_only")
    st, out = feedback_send.send(feedback_send.build("hi", template_id="t1"))
    assert out == {"ok": True}
    (path, h, body), = _Fake.log
    assert path == "/v1/feedback/hub" and h["authorization"] == "Bearer wl_pat_test_only" and body["text"] == "hi"


def test_not_signed_in_uses_a_guest_token(fake, monkeypatch):
    monkeypatch.delenv("WORLDLINES_API_KEY", raising=False)
    st, out = feedback_send.send(feedback_send.build("hi"))
    assert out["ok"] is True
    assert [p for p, _, _ in _Fake.log] == ["/v1/guest", "/v1/feedback/hub"]
    assert _Fake.log[0][2] == {"client_id": "neonrp"} and len(_Fake.log[0][1]["x-worldlines-device"]) >= 16
    assert _Fake.log[1][1]["authorization"] == "Bearer guest-tok"


def test_a_refusal_is_reported(fake, monkeypatch):
    monkeypatch.setenv("WORLDLINES_API_KEY", "wl_pat_test_only")
    _Fake.data_status = 429
    st, out = feedback_send.send(feedback_send.build("hi"))
    assert st == 429 and out == {"ok": False, "error": "rate_limited"}


def test_local_page_has_the_feedback_button():
    from pathlib import Path

    app = Path(__file__).resolve().parents[1] / "worldlines" / "ui" / "app"
    if not (app / "src" / "feedback.js").is_file():
        pytest.skip("the public repo without the local page")
    js = (app / "src" / "feedback.js").read_text(encoding="utf-8")
    assert "data-fbopen" in js and "/api/v1/local/feedback" in js
    assert "'src/feedback.js'" in (app / "build.mjs").read_text(encoding="utf-8")


def test_route_forwards_and_refuses_other_origins(fake, monkeypatch):
    """The engine route: our own pages only (it sends with the player's account)."""
    from neonrp.webui import launcher_routes as lr

    monkeypatch.setenv("WORLDLINES_API_KEY", "wl_pat_test_only")
    sent: dict = {}
    h = lr.LauncherRoutes.__new__(lr.LauncherRoutes)
    h.path = "/api/v1/local/feedback"
    h._read_json_body = lambda: {"text": "route", "template_id": "t1", "locale": "ja"}
    h._send_json = lambda body, status=200: sent.update(body=body, status=status)
    h.headers = {"Origin": "http://127.0.0.1:8865"}
    assert h._hub_route("POST") is True and sent == {"body": {"ok": True}, "status": 200}
    assert _Fake.log[-1][2]["client"]["locale"] == "ja"
    h.headers = {"Origin": "https://evil.example"}
    n = len(_Fake.log)
    assert h._hub_route("POST") is True and sent["status"] == 403 and len(_Fake.log) == n
