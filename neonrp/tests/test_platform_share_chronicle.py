"""回放分享到平台 + chronicle 上报(10-15 lead · sns-platform,worldlines-platform docs/玩家分享SNS-1015.md §4.1)。

假的 platform(auth · storage · sns · chronicle 一个进程):
- POST /api/v1/local/replay/share:登记 → 租约 → 上传链接 + PUT(签名头原样带)→ complete → publish{zone:open} → moments;
  meta.world_ref 第 1、4 步都带;没登录 401、缺权限 403、配额 429;中途失败放回租约
- chronicle:开局 playthrough.ensure + world.open、结局 ending.reached,world_ref = hub/template/<id>;先进本地队列,
  离线 / 没令牌留着补发;unknown_ref 留、其余结果算完;410 清空"""
from __future__ import annotations

import hashlib
import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest

from neonrp.core import chronicle, replay_share, worldlines_auth


def _jwt(**claims) -> str:
    import base64

    b = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJFUzI1NiJ9.{b}.sig"


JWT_A = _jwt(sub="u-a", anon=False, scope="api:use chronicle:write")
JWT_B = _jwt(sub="u-b")
JWT_GUEST = _jwt(sub="g-1", anon=True)


class Platform:
    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []
        self.objects: dict[str, bytes] = {}
        self.fail: dict[str, tuple[int, dict]] = {}   # path suffix → forced answer
        self.chronicle_answer = None
        self.events: list[dict] = []
        self.tokens = {"tok", JWT_A, JWT_B}
        p = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _answer(self, status, body):
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _do(self):
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b""
                path = self.path
                if path.startswith("/s3/"):
                    want = self.headers.get("x-amz-checksum-sha256")
                    if want != hashlib.sha256(raw).hexdigest():
                        return self._answer(400, {"error": "BadDigest"})
                    p.objects[path[4:]] = raw
                    p.calls.append((self.command, path, {}))
                    return self._answer(200, {})
                body = json.loads(raw or b"{}")
                p.calls.append((self.command, path, body))
                if self.headers.get("Authorization") not in {f"Bearer {t}" for t in p.tokens}:
                    return self._answer(401, {"error": "unauthorized"})
                for suf, ans in p.fail.items():
                    if path.endswith(suf):
                        return self._answer(*ans)
                if path == "/chronicle/v1/events:batch":
                    p.events += body["events"]
                    if p.chronicle_answer:
                        return self._answer(*p.chronicle_answer(body))
                    return self._answer(200, {"results": [{"index": i, "status": "created"} for i in range(len(body["events"]))]})
                if path == "/auth/v1/resources":
                    return self._answer(201, {"resource": {"id": body["id"]}})
                if path.endswith("/lease") and self.command == "POST":
                    return self._answer(201, {"lease_id": "L1"})
                if "/lease/" in path and self.command == "DELETE":
                    return self._answer(200, {})
                if path.endswith("/upload-url"):
                    base = f"http://127.0.0.1:{p.port}/s3/"
                    return self._answer(200, {"revision": 1, "uploads": [
                        {"path": f["path"], "url": base + f["path"], "method": "PUT",
                         "headers": {"x-amz-checksum-sha256": f["sha256"]}} for f in body["files"]]})
                if path.endswith("/complete"):
                    return self._answer(200, {"revision": 1})
                if path.endswith("/publish"):
                    return self._answer(200, {"resource": {"status": "published", "zone": body.get("zone")}})
                if path == "/sns/v1/moments":
                    return self._answer(201, {"id": "m1", "url": "https://sns.example/m/m1", "zone": "open", "notice": "web_only"})
                return self._answer(404, {})

            do_GET = do_POST = do_PUT = do_DELETE = _do

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.port}"

    def paths(self):
        return [(m, p) for m, p, _ in self.calls]


@pytest.fixture
def platform(monkeypatch):
    p = Platform()
    monkeypatch.setattr(worldlines_auth, "ISSUER", p.base + "/auth")
    monkeypatch.setattr(replay_share, "STORAGE", p.base + "/storage")
    monkeypatch.setattr(replay_share, "SNS", p.base + "/sns")
    monkeypatch.setattr(chronicle, "BASE", p.base + "/chronicle")
    monkeypatch.setenv("WORLDLINES_API_KEY", "tok")
    yield p
    p.srv.shutdown()


def _run(root: Path, tpl: str | None = "wuwu") -> Path:
    (root / ".neonrp" / "orchestration").mkdir(parents=True)
    (root / ".neonrp" / "config.json").write_text(json.dumps({"api_key": "sk-" + "x" * 32}), encoding="utf-8")
    (root / "game" / "meta").mkdir(parents=True)
    if tpl:
        (root / "game" / "meta" / "template.json").write_text(json.dumps({"id": tpl, "pack": "pct", "card": {"title": "雾港"}}), encoding="utf-8")
    (root / "story.md").write_text("# 实录\n\n## T0 · 码头\n\n雾很大。\n\n## T1 · 灯塔\n\n灯灭了。\n", encoding="utf-8")
    (root / "feed.jsonl").write_text('{"turn_seq": 0}\n{"turn_seq": 1}\n', encoding="utf-8")
    (root / ".neonrp" / "orchestration" / "main.jsonl").write_text('{"turn_seq": 0}\n', encoding="utf-8")
    (root / "cover.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    return root


# ── replay share ─────────────────────────────────────────────────────────────

def test_share_runs_the_six_steps(platform, tmp_path):
    run = _run(tmp_path / "tpl-wuwu-20261015-101010")
    out = replay_share.share(run, text="雾港这一局", lang="zh")
    rid = out["replay_id"]
    ref = f"hub/replay/{rid}"
    assert out["ref"] == ref and out["world_ref"] == "hub/template/wuwu"
    assert out["moment_url"] == "https://sns.example/m/m1" and out["notice"] == "web_only" and out["published"] == "published"
    steps = [p for m, p in platform.paths() if not p.startswith("/s3/")]
    assert steps == ["/auth/v1/resources", f"/auth/v1/resources/{ref}/lease", f"/storage/v1/objects/{ref}/upload-url",
                     f"/storage/v1/objects/{ref}/complete", f"/auth/v1/resources/{ref}/publish", "/sns/v1/moments"]
    body = {p: b for _, p, b in platform.calls}
    reg = body["/auth/v1/resources"]
    assert reg["product"] == "hub" and reg["kind"] == "replay" and reg["id"] == rid and reg["meta"]["world_ref"] == "hub/template/wuwu"
    assert body[f"/storage/v1/objects/{ref}/complete"]["meta"]["world_ref"] == "hub/template/wuwu", "world_ref again at complete"
    assert body[f"/storage/v1/objects/{ref}/complete"]["leaseId"] == "L1"
    assert body[f"/auth/v1/resources/{ref}/publish"] == {"zone": "open"}
    assert body["/sns/v1/moments"] == {"text": "雾港这一局", "attachments": [{"type": "replay", "ref": ref}], "lang": "zh-CN"}
    assert set(platform.objects) == {"replay.json", "timeline.json", "story.md", "feed.jsonl", "cover.png"}, "原始回合轨迹不上传"
    assert json.loads(platform.objects["replay.json"])["world_ref"] == "hub/template/wuwu"
    assert not any(b"sk-" in v for v in platform.objects.values()), "the bundle whitelist: no config"
    import re

    assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", rid)


def test_share_errors(platform, tmp_path, monkeypatch):
    run = _run(tmp_path / "tpl-wuwu-20261015-101010")
    old = _run(tmp_path / "stoneford-elena-20260911-101010", tpl=None)
    replay_share.share(old)
    reg = next(b for _, p, b in platform.calls if p == "/auth/v1/resources")
    assert "world_ref" not in reg["meta"], "not from a template: no address"
    platform.calls.clear()
    platform.fail["/upload-url"] = (500, {"error": "boom"})
    with pytest.raises(replay_share.ShareError) as e:
        replay_share.share(run)
    assert e.value.status == 502 and ("DELETE", next(p for m, p in platform.paths() if m == "DELETE")) in platform.paths()
    assert any(m == "DELETE" and "/lease/L1" in p for m, p in platform.paths()), "the lease is given back"
    platform.fail = {"/v1/resources": (429, {"error": "quota_count_exceeded"})}
    with pytest.raises(replay_share.ShareError) as e:
        replay_share.share(run)
    assert (e.value.status, e.value.code) == (429, "quota_count_exceeded")
    platform.fail = {"/v1/moments": (403, {"error": "insufficient_scope"})}   # signed in without sns:share (before identity 0016)
    out = replay_share.share(run, lang="zh")
    assert out["moment_error"] == "sns_share_unavailable" and out["moment_url"] is None and out["published"] == "published", \
        "the replay is up; only the post is missing"
    assert "还没开放" in out["message"]
    platform.fail = {}
    monkeypatch.setenv("WORLDLINES_API_KEY", JWT_A)   # a session whose scope has no sns:share: the post is not even tried
    platform.calls.clear()
    out = replay_share.share(run, lang="en")
    assert out["moment_error"] == "sns_share_unavailable" and "not open" in out["message"]
    assert "/sns/v1/moments" not in [p for _, p in platform.paths()] and f"/auth/v1/resources/{out['ref']}/publish" in [p for _, p in platform.paths()]
    monkeypatch.setenv("WORLDLINES_API_KEY", "tok")
    platform.fail = {"/lease": (403, {"error": "insufficient_scope"})}
    with pytest.raises(replay_share.ShareError) as e:
        replay_share.share(run)
    assert e.value.status == 403 and "sign in again" in str(e.value)
    monkeypatch.setenv("WORLDLINES_API_KEY", "-")
    with pytest.raises(replay_share.ShareError) as e:
        replay_share.share(run)
    assert (e.value.status, e.value.code) == (401, "not_signed_in")
    monkeypatch.setenv("WORLDLINES_API_KEY", "other")
    with pytest.raises(replay_share.ShareError) as e:
        replay_share.share(run)
    assert e.value.status == 401


def test_share_route(platform, tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    plays = tmp_path / "plays"
    _run(plays / "tpl-wuwu-20261015-101010")
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", plays),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "studio"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_address[1]}/api/v1/local/replay/share"

        def post(b):
            req = urllib.request.Request(url, data=json.dumps(b).encode(), method="POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        try:
            assert post({"session_id": "tpl-wuwu-20261015-101010", "text": "hi"})["world_ref"] == "hub/template/wuwu"
            for b, code in (({"session_id": "nope"}, 404), ({"session_id": "../x"}, 400)):
                with pytest.raises(urllib.error.HTTPError) as e:
                    post(b)
                assert e.value.code == code and "error" in json.loads(e.value.read())
        finally:
            server.shutdown()


# ── chronicle ────────────────────────────────────────────────────────────────

def test_chronicle_spools_then_sends(platform, tmp_path, monkeypatch):
    run = _run(tmp_path / "tpl-wuwu-20261015-101010")
    monkeypatch.setenv("WORLDLINES_API_KEY", JWT_A)
    monkeypatch.setattr(chronicle, "BASE", "http://127.0.0.1:9")   # offline: everything waits, bound to account A
    chronicle.opened(run)
    chronicle.ending(run, {"id": "E01", "title": "潮退"})
    chronicle._wait()
    q = chronicle.pending()
    assert [e["type"] for e in q] == ["playthrough.ensure", "world.open", "playthrough.ensure", "ending.reached"]
    assert {e["_uid"] for e in q} == {"u-a"}
    assert q[0]["world_ref"] == q[1]["world_ref"] == "hub/template/wuwu" and q[0]["save_id"] == run.name
    assert q[0]["meta"] == {"template_id": "wuwu", "pack": "pct", "world_title": "雾港"} and q[1]["client"] == "local"
    assert q[3]["ending_id"] == "E01" and q[3]["title"] == "潮退" and q[3]["occurred_at"]
    monkeypatch.setattr(chronicle, "BASE", platform.base + "/chronicle")
    monkeypatch.setenv("WORLDLINES_API_KEY", JWT_B)   # someone else signs in on this machine: A's games are not theirs
    assert chronicle.flush()["sent"] == 0 and platform.events == [] and len(chronicle.pending()) == 4
    monkeypatch.setenv("WORLDLINES_API_KEY", JWT_A)
    assert chronicle.flush() == {"sent": 4, "kept": 0, "dropped": 0}
    assert [e["type"] for e in platform.events] == [e["type"] for e in q] and chronicle.pending() == []
    assert not any(k.startswith("_") for e in platform.events for k in e), "the account tag stays local"
    assert next(b for _, p, b in platform.calls if p == "/chronicle/v1/events:batch")["product"] == "hub"


def test_chronicle_keeps_nothing_for_guests_or_nobody(platform, tmp_path, monkeypatch):
    run = _run(tmp_path / "tpl-wuwu-20261015-101010")
    for tok in ("-", JWT_GUEST):   # nobody signed in (the browser's "-") · a guest: chronicle takes neither
        monkeypatch.setenv("WORLDLINES_API_KEY", tok)
        chronicle.opened(run)
        chronicle.ending(run, {"id": "E01"})
        chronicle._wait()
        assert chronicle.pending() == [] and platform.events == []
    monkeypatch.setenv("WORLDLINES_API_KEY", JWT_A)   # signing in later does not bring the guest's games along
    chronicle.flush()
    assert platform.events == []


def test_chronicle_offline_unknown_ref_and_gone(platform, tmp_path, monkeypatch):
    run = _run(tmp_path / "tpl-wuwu-20261015-101010")
    monkeypatch.setenv("WORLDLINES_API_KEY", JWT_A)
    monkeypatch.setattr(chronicle, "BASE", "http://127.0.0.1:9")   # offline
    chronicle.emit({"type": "world.open", "world_ref": "hub/template/wuwu", "open_id": "o1", "client": "local"}, send=False)
    assert chronicle.flush()["kept"] == 1 and len(chronicle.pending()) == 1
    monkeypatch.setattr(chronicle, "BASE", platform.base + "/chronicle")
    platform.chronicle_answer = lambda body: (200, {"results": [
        {"index": i, "status": "rejected", "code": "unknown_ref"} if e["type"] == "ending.reached" else {"index": i, "status": "created"}
        for i, e in enumerate(body["events"])]})
    chronicle.ending(run, {"id": "E02"})   # its background flush sends the old one along
    chronicle._wait()
    chronicle.flush()
    assert [e["type"] for e in platform.events].count("world.open") == 1 and [e["type"] for e in chronicle.pending()] == ["ending.reached"], \
        "unknown_ref waits for the next time"
    platform.chronicle_answer = lambda body: (410, {"error": "account_deleted"})
    assert chronicle.flush()["dropped"] == 1 and chronicle.pending() == []
    monkeypatch.setenv("NEONRP_CHRONICLE", "off")
    chronicle.emit({"type": "world.open", "world_ref": "x", "open_id": "o2"})
    assert chronicle.pending() == []


def test_chronicle_world_ref_without_template(tmp_path):
    run = _run(tmp_path / "stoneford-elena-20260911-101010", tpl=None)
    assert chronicle.world_ref(run) == "local:stoneford-elena"


def test_bind_tells_chronicle(tmp_path, monkeypatch):
    import shutil

    from _paths import PRODUCT_TEMPLATES
    from neonrp.commands.web import make_server

    store = tmp_path / "store"
    shutil.copytree(PRODUCT_TEMPLATES / "wuwu.template", store / "wuwu.template")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(store))
    monkeypatch.setenv("WORLDLINES_API_KEY", JWT_A)
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "studio"),
        patch("neonrp.commands.web.WebRuntime.gateway_start", lambda self: {"sid": "local", "root": self.root.name}),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        req = urllib.request.Request(f"http://127.0.0.1:{server.server_address[1]}/api/v1/play/session",
                                     data=json.dumps({"slug": "tpl--wuwu", "output_lang": "zh"}).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                r.read()
        finally:
            server.shutdown()
    chronicle._wait()
    q = chronicle.pending()
    assert [e["type"] for e in q][:2] == ["playthrough.ensure", "world.open"] and q[0]["world_ref"] == "hub/template/wuwu"
    assert q[0]["save_id"] == next((tmp_path / "plays").iterdir()).name


def test_signing_in_mid_run_reports_from_then_on_only(platform, tmp_path, monkeypatch):
    """lead 10-15:登录前那一局,登录那一刻起的事件照常报,之前的不补。"""
    run = _run(tmp_path / "tpl-wuwu-20261015-101010")
    monkeypatch.setenv("WORLDLINES_API_KEY", JWT_GUEST)
    chronicle.opened(run)   # played as a guest: nothing kept
    chronicle._wait()
    monkeypatch.setenv("WORLDLINES_API_KEY", JWT_A)
    chronicle.ending(run, {"id": "E01"})
    chronicle._wait()
    chronicle.flush()
    assert [e["type"] for e in platform.events] == ["playthrough.ensure", "ending.reached"], "no world.open from the guest time"


def test_spool_forgets_old_and_too_many(monkeypatch):
    monkeypatch.setenv("WORLDLINES_API_KEY", JWT_B)
    monkeypatch.setattr(chronicle, "SPOOL_MAX", 3)
    chronicle.emit({"type": "world.open", "world_ref": "a", "open_id": "old", "occurred_at": "2020-01-01T00:00:00+00:00"}, send=False)
    assert chronicle.pending() == [], "older than SPOOL_DAYS: gone"
    for i in range(5):
        chronicle.emit({"type": "world.open", "world_ref": "a", "open_id": f"o{i}"}, send=False)
    assert [e["open_id"] for e in chronicle.pending()] == ["o2", "o3", "o4"], "first in, first out"


# ── sign-in scopes ───────────────────────────────────────────────────────────

LIVE_NEONRP_SCOPES = {"profile:read", "api:use", "resources:read", "resources:write", "storage:read", "storage:write",
                      "chronicle:read", "chronicle:write", "data:read", "data:write"}   # worldlines-platform main, identity 0004


def test_login_asks_everything_then_retries_without_sns_share(monkeypatch, tmp_path):
    """Live identity does not allow sns:share for neonrp yet (ios2 10-15: 400 invalid_scope): ask all, on invalid_scope
    once more without it; anything else is not retried."""
    from neonrp._vendor.worldlines_identity.login import IdentityError

    assert set(worldlines_auth.FALLBACK_SCOPES) <= LIVE_NEONRP_SCOPES and set(worldlines_auth.PROD_SCOPES) == LIVE_NEONRP_SCOPES
    assert worldlines_auth.SCOPES == worldlines_auth.FALLBACK_SCOPES + ("sns:share",)
    assert {"data:read", "data:write"} <= set(worldlines_auth.FALLBACK_SCOPES), "the fallback keeps data:* (10-25: 403 on the collection)"
    asked = []

    class WL:
        @staticmethod
        def login(issuer, client_id, scopes, **k):
            asked.append(tuple(scopes))
            if "sns:share" in scopes:
                raise IdentityError(400, "invalid_scope")
            return {"access_token": "a", "expires_at": 9e9}

        class FileTokenStore:
            def __init__(self, path):
                self.path = path

            def save(self, s):
                Path(self.path).write_text(json.dumps(s), encoding="utf-8")

    monkeypatch.setattr(worldlines_auth, "_wl_login", lambda: WL)
    worldlines_auth.connect(open_browser=False)
    assert asked == [worldlines_auth.SCOPES, worldlines_auth.FALLBACK_SCOPES]

    def refuse(issuer, client_id, scopes, **k):
        asked.append(tuple(scopes))
        raise IdentityError(400, "access_denied")

    monkeypatch.setattr(WL, "login", staticmethod(refuse))
    asked.clear()
    with pytest.raises(IdentityError):
        worldlines_auth.connect(open_browser=False)
    assert asked == [worldlines_auth.SCOPES], "only invalid_scope is retried"
    from _paths import PRODUCT_TEMPLATES

    hub = PRODUCT_TEMPLATES.parent / "ui" / "app" / "hub" / "hub.js"
    if not hub.is_file():
        return   # the public repo without the Hub front end
    import re

    js = hub.read_text(encoding="utf-8")
    base = set(re.findall(r"'([a-z]+:[a-z]+)'", next(x for x in js.splitlines() if "const BASE_SCOPES" in x)))
    assert base | {"data:read", "data:write"} == set(worldlines_auth.FALLBACK_SCOPES) and "[...BASE_SCOPES, 'data:read', 'data:write', 'sns:share']" in js
    assert "const FALLBACK_SCOPES = [...BASE_SCOPES, 'data:read', 'data:write'].join(' ')" in js
    assert "err === 'invalid_scope' && p && !p.fallback" in js and "startLogin(p.provider, true, p.back)" in js
