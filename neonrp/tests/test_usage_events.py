"""Usage events for the console (docs/planning/USAGE-DATA-CONTRACT-1025.md) + X-Worldlines-Client on platform requests +
chronicle play records cleaned to what chronicle accepts. Against a local fake chronicle — never the platform."""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from neonrp.core import chronicle, usage
from neonrp.core import worldlines_auth as wa


class _Chronicle(BaseHTTPRequestHandler):
    log: list = []
    status = 202
    headers_out: dict = {}

    def log_message(self, *a):
        pass

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        c = type(self)
        c.log.append(({k.lower(): v for k, v in self.headers.items()}, body))
        data = json.dumps({"accepted": len(body.get("events") or []), "rejected": 0, "errors": []}).encode()
        self.send_response(c.status)
        for k, v in c.headers_out.items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if c.status != 204:
            self.wfile.write(data)


@pytest.fixture()
def fake(monkeypatch, tmp_path):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Chronicle)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _Chronicle.log, _Chronicle.status, _Chronicle.headers_out = [], 202, {}
    monkeypatch.setenv("WORLDLINES_USAGE_BASE", f"http://127.0.0.1:{srv.server_address[1]}")
    monkeypatch.setenv("WORLDLINES_IDENTITY_FILE", str(tmp_path / "wl" / "identity.json"))
    monkeypatch.setenv("NEONRP_USAGE", "on")
    monkeypatch.setenv("NEONRP_LOCALE", "zh")
    for k in ("WORLDLINES_USAGE_SESSION", "WORLDLINES_USAGE_OPENED", "WORLDLINES_CLIENT", "WORLDLINES_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(usage, "_schedule", lambda now=False: None)  # the test flushes by hand
    wa._mgrs.clear()
    usage._reset()
    yield srv
    usage._reset()
    srv.shutdown()
    srv.server_close()


def _events():
    return [e for _, b in _Chronicle.log for e in b["events"]]


def test_a_normal_visit(fake):
    usage.app_open()
    usage.lobby_view()
    usage.world_enter("hub/template/pct-house", resumed=False)
    for t in range(1, 8):
        usage.turn("hub/template/pct-house", t, "hall")
        usage.turn("hub/template/pct-house", t, "hall")  # a second apply in the same turn is not another turn
    usage.ending("hub/template/pct-house", "true_end")
    usage.leave()
    assert usage.flush(force=True)["sent"] > 0
    names = [(e["name"], e.get("props", {}).get("n")) for e in _events()]
    assert names == [("app_open", None), ("lobby_view", None), ("world_enter", None), ("first_turn", None), ("session_turn", 1),
                     ("session_turn", 2), ("session_turn", 3), ("session_turn", 6), ("ending_reached", None), ("world_leave", None)]
    ev = {e["name"]: e for e in _events()}
    assert ev["world_enter"]["props"] == {"resumed": False, "tracked": True} and ev["world_enter"]["world_id"] == "hub/template/pct-house"
    assert ev["world_leave"]["props"] == {"turns": 7, "place": "hall"}
    assert ev["ending_reached"]["props"] == {"ending": "true_end"}
    h, body = _Chronicle.log[0]
    assert set(body) <= {"product", "session_id", "app_version", "locale", "src", "client", "events"}
    assert body["product"] == "hub" and body["locale"] == "zh" and 16 <= len(body["session_id"]) <= 64
    assert h["x-worldlines-client"] == "local" and "authorization" not in h  # nobody signed in: anonymous
    assert usage.pending() == []


def test_band_starts():
    assert [n for n in range(1, 1200) if usage.is_band_start(n)] == [1, 2, 3, 6, 11, 21, 51, 101, 201, 501, 1001]


def test_a_guest_token_goes_along_and_ios_says_ios(fake, monkeypatch):
    monkeypatch.setenv("WORLDLINES_API_KEY", "guest-token-from-the-page")
    monkeypatch.setenv("WORLDLINES_CLIENT", "app")  # the iOS shell's old name
    usage.lobby_view()
    usage.flush(force=True)
    h, _ = _Chronicle.log[0]
    assert h["authorization"] == "Bearer guest-token-from-the-page" and h["x-worldlines-client"] == "ios"


def test_a_browser_tab_session_is_kept(fake, monkeypatch):
    monkeypatch.setenv("WORLDLINES_USAGE_SESSION", "TabSession_0123456789")
    usage.world_enter("builtin:x")
    usage.flush(force=True)
    assert [e["name"] for e in _events()] == ["app_open", "world_enter"]  # the page had not said app_open yet
    assert _Chronicle.log[0][1]["session_id"] == "TabSession_0123456789"
    usage._reset()
    _Chronicle.log.clear()
    monkeypatch.setenv("WORLDLINES_USAGE_OPENED", "1")
    usage.world_enter("builtin:x")
    usage.flush(force=True)
    assert [e["name"] for e in _events()] == ["world_enter"]


def test_retry_after_drop_and_off(fake, monkeypatch):
    usage.lobby_view()
    _Chronicle.status, _Chronicle.headers_out = 429, {"Retry-After": "120"}
    assert usage.flush(force=True)["kept"] == 2  # app_open + lobby_view wait
    n = len(_Chronicle.log)
    assert usage.flush()["kept"] == 2 and len(_Chronicle.log) == n, "not before Retry-After"
    _Chronicle.status, _Chronicle.headers_out = 400, {}
    assert usage.flush(force=True)["dropped"] == 2 and usage.pending() == []
    _Chronicle.status = 204
    usage.lobby_view()
    assert usage.flush(force=True)["sent"] == 1
    usage.set_enabled(False)
    usage.lobby_view()
    assert usage.pending() == [] and not usage.enabled()
    usage.set_enabled(True)
    monkeypatch.setenv("NEONRP_USAGE", "off")
    usage.lobby_view()
    assert usage.pending() == []


def test_no_text_in_props(fake):
    usage.emit("lobby_view", props={"note": "a whole sentence the player typed", "n": 3, "ok": True, "big": 10**9})
    assert usage.pending()[-1]["ev"]["props"] == {"n": 3, "ok": True}


def test_client_header_on_platform_requests(monkeypatch):
    monkeypatch.delenv("WORLDLINES_CLIENT", raising=False)
    assert wa.headers()["X-Worldlines-Client"] == "local" and wa.client_header() == {"X-Worldlines-Client": "local"}
    monkeypatch.setattr(sys, "platform", "emscripten")  # the browser engine: CORS lets it through to chronicle / ai only
    assert "X-Worldlines-Client" not in wa.headers() and wa.client_header() == {"X-Worldlines-Client": "web"}
    monkeypatch.setattr(sys, "platform", "darwin")
    seen = {}
    wa.post("https://auth.test/v1/logout", {}, {}, send=lambda u, b, h: (seen.update(h), (200, {}))[1])
    assert seen["X-Worldlines-Client"] == "local"


def test_chronicle_records_are_cleaned():
    c = chronicle.clean({"type": "playthrough.ensure", "save_id": "tpl-my world_1", "world_ref": "local:My World!",
                         "meta": {"template_id": "pct-house", "pack": "rpg+economy", "template_version": "1.0 beta", "world_title": "灰橡宅\n" + "x" * 300}})
    assert c["save_id"] == "tpl-my-world_1"
    assert c["world_ref"] == "local:My-World-"
    assert c["meta"] == {"template_id": "pct-house", "world_title": ("灰橡宅 " + "x" * 300)[:200]}
    r = chronicle.clean({"type": "settlement.reward", "save_id": "s", "ref": "settlement:Pct House:tpl-pct_house-1/x", "source": "settlement:quiz",
                         "points": 12.0, "score": -1, "total": "3"})
    assert r["ref"] == "settlement:pct-house:tpl-pct_house-1-x" and r["points"] == 12 and r["score"] == 0 and r["total"] == 3
    e = chronicle.clean({"type": "ending.reached", "save_id": "s", "ending_id": "true end", "kind": "Good Ending", "title": "t"})
    assert e["ending_id"] == "true-end" and e["kind"] == "good_ending"
    assert "kind" not in chronicle.clean({"type": "ending.reached", "save_id": "s", "ending_id": "e", "kind": "大结局"})


def test_route_lobby_view_and_switch(fake, monkeypatch):
    from neonrp.webui import launcher_routes as lr

    sent: dict = {}
    h = lr.LauncherRoutes.__new__(lr.LauncherRoutes)
    h.path, h.headers = "/api/v1/local/usage", {"Origin": "http://127.0.0.1:8865"}
    h._send_json = lambda body, status=200: sent.update(body=body, status=status)
    h._read_json_body = lambda: {"name": "lobby_view"}
    assert h._hub_route("POST") and sent["body"] == {"ok": True, "usage_data": True}
    assert [r["ev"]["name"] for r in usage.pending()] == ["app_open", "lobby_view"]
    h._read_json_body = lambda: {"name": "world_enter"}
    assert h._hub_route("POST") and sent["status"] == 400, "a page asks for lobby_view only"
    h._read_json_body = lambda: {"usage_data": False}
    assert h._hub_route("POST") and sent["body"]["usage_data"] is False and usage.pending() == []
    h.headers = {"Origin": "https://evil.example"}
    h._read_json_body = lambda: {"usage_data": True}
    assert h._hub_route("POST") and sent["status"] == 403 and not usage.enabled()


def test_failures_are_silent_and_leave_play_records_alone(fake, monkeypatch):
    """Before the platform has /v1/events (404), or offline: nothing raises, events wait, chronicle's spool is untouched."""
    _Chronicle.status = 404
    usage.lobby_view()
    assert usage.flush(force=True)["kept"] == 2
    monkeypatch.setenv("WORLDLINES_USAGE_BASE", "http://127.0.0.1:9")
    usage.world_enter("builtin:x")
    usage.turn("builtin:x", 1, "hall")
    assert usage.flush(force=True)["sent"] == 0 and len(usage.pending()) == 5
    assert usage._spool() != chronicle.SPOOL and not chronicle.SPOOL.exists()
