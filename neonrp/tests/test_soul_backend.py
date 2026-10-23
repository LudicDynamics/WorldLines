"""Tests for M18 §5 soul-as-external-backend (no LLM)."""

import json
from pathlib import Path

from neonrp.core.soul_backend import (
    InternalLLMBackend,
    StubBackend,
    resolve_soul_backend,
)
from neonrp.core.soul_result import parse_soul_turn_report


class _Soul:
    def __init__(self, sid: str, iid: str) -> None:
        self.sid = sid
        self.instance_id = iid


def _write_soul_json(root: Path, sid: str, iid: str, extra: dict | None = None) -> _Soul:
    d = root / "souls" / f"{sid}-{iid}"
    d.mkdir(parents=True, exist_ok=True)
    body = {"schema_version": 1, "sid": sid, "instance_id": iid, "name": sid}
    body.update(extra or {})
    (d / "soul.json").write_text(json.dumps(body), encoding="utf-8")
    return _Soul(sid, iid)


def test_default_backend_is_internal_llm(tmp_path: Path) -> None:
    soul = _write_soul_json(tmp_path, "elena", "si-e1")  # no backend field
    backend = resolve_soul_backend(tmp_path, soul)
    assert isinstance(backend, InternalLLMBackend)
    assert backend.name == "internal-llm"


def test_stub_backend_selected_from_soul_json(tmp_path: Path) -> None:
    soul = _write_soul_json(tmp_path, "elena", "si-e1", {"backend": "stub"})
    backend = resolve_soul_backend(tmp_path, soul)
    assert isinstance(backend, StubBackend)


def test_unknown_backend_falls_back_to_internal_llm(tmp_path: Path) -> None:
    soul = _write_soul_json(tmp_path, "elena", "si-e1", {"backend": "warpdrive"})
    backend = resolve_soul_backend(tmp_path, soul)
    assert isinstance(backend, InternalLLMBackend)


def test_missing_soul_json_defaults_to_internal_llm(tmp_path: Path) -> None:
    backend = resolve_soul_backend(tmp_path, _Soul("ghost", "si-g1"))
    assert isinstance(backend, InternalLLMBackend)


def test_stub_default_response_parses_as_completed(tmp_path: Path) -> None:
    res = StubBackend().respond(
        root=tmp_path,
        agent_id="soul:elena",
        messages=[],
        mode="agent",
        provider=None,
        max_turns=1,
        run_id="r1",
    )
    assert res.success is True
    report = parse_soul_turn_report(res.assistant_message, success=res.success)
    assert report.state == "completed"


def test_stub_custom_report_drives_speech(tmp_path: Path) -> None:
    canned = {"state": "completed", "speech": "我在这里。", "intended_action": "wave"}
    res = StubBackend(report=canned).respond(
        root=tmp_path,
        agent_id="soul:elena",
        messages=[],
        mode="agent",
        provider=None,
        max_turns=1,
        run_id="r1",
    )
    report = parse_soul_turn_report(res.assistant_message, success=res.success)
    assert report.speech == "我在这里。"
    assert report.intended_action == "wave"


def test_http_backend_round_trip(tmp_path: Path) -> None:
    """M18 §5.3: an external REST service answers the soul request."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    received: dict = {}

    class _H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.update(body)
            out = json.dumps(
                {"assistant_message": '{"state":"completed","confidence":0.5,"urgency":0.1,"speech":"来自外部服务"}'}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

    server = ThreadingHTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/soul"
    try:
        soul = _write_soul_json(
            tmp_path, "elena", "si-e1",
            {"backend": "http", "backend_url": url, "backend_timeout_s": 5},
        )
        backend = resolve_soul_backend(tmp_path, soul)
        assert backend.name == "http"

        class _Msg:
            role = "user"
            content = "场景感知"

        res = backend.respond(
            root=tmp_path, agent_id="soul:elena:si-e1", messages=[_Msg()],
            mode="play", provider=None, max_turns=1, run_id="r1",
        )
        assert res.success is True
        report = parse_soul_turn_report(res.assistant_message)
        assert report.speech == "来自外部服务"
        assert received["agent_id"] == "soul:elena:si-e1"
        assert received["messages"][0]["content"] == "场景感知"
    finally:
        server.shutdown()


def test_http_backend_without_url_falls_back(tmp_path: Path) -> None:
    soul = _write_soul_json(tmp_path, "elena", "si-e1", {"backend": "http"})
    backend = resolve_soul_backend(tmp_path, soul)
    assert isinstance(backend, InternalLLMBackend)
