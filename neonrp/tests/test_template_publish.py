"""模板发布到 Hub 自由区(niko 10-16 · core/template_publish · worldlines-platform docs/审核与分区-1015.md)。

假的平台(identity 的资源 + storage 的上传 / 公开下载,一个进程,按平台的规则答):
- 发布前本地三项检查 + 封面:密钥(模板和它链接的角色)· lint 无 block · 卡面四语 · 封面;不过 = 一个请求都不发
- 六步:登记 → 租约 → 上传链接 + PUT → complete(meta 带 lint / source)→ publish {zone: open};包 = package.zip + cover
- 作品 id = <模板 id>-<6 位十六进制>;同一模板再发 = 找到自己那件作品(meta.source)、加一个版本
- 平台的 401 / 403 / 409 taken_down / 422 checks_failed 都变成四语人话
- 公开列表(无凭证)· 封面 · 下载到本地(import_package,id 冲突顺延 -2)· 举报 · 撤下 · 申请默认区
- 引擎路由:POST/GET /api/v1/local/templates/<id>/publish · /api/v1/local/hub/{open,cover,mine,fetch,report,unpublish,submit}"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
import urllib.error
import urllib.request
import zipfile
import io
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest

from neonrp import template as TP
from neonrp.core import replay_share, template_publish as tp, worldlines_auth

SRC_TPL = Path(__file__).resolve().parents[1] / "worldlines" / "templates" / "stoneford-market.template"
TOKENS = {"author": "u-author", "reader": "u-reader", "guest": "u-guest"}   # u-guest = an anonymous (guest) account


class Platform:
    """identity /v1/resources* + storage /v1/objects* in memory — the platform's rules for hub:template works."""

    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []
        self.res: dict[str, dict] = {}       # id → {owner, status, zone, revision, title, meta, files, review, takedown}
        self.blobs: dict[str, bytes] = {}    # "<id>/<rev>/<path>"
        self.fail: dict[str, tuple[int, dict]] = {}
        self.reports: list[tuple[str, str, str]] = []
        self.official: set[str] = set()      # identity ID_OFFICIAL_OWNERS (P2): /v1/me official · listings mark them
        self.blocks: dict[str, set[str]] = {}  # reader → owners blocked (identity feat/block-owner 32a8aab)
        self.auto = False                    # P2: an official owner's curated publish is approved at once
        self.p1 = True                       # storage P1: our apps' signed-in (non-guest) tokens get curated packages
        p = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _answer(self, status, body=None, raw: bytes | None = None, ct="application/json"):
                data = raw if raw is not None else json.dumps(body or {}).encode()
                self.send_response(status)
                self.send_header("Content-Type", ct)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _do(self):
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b""
                path, _, qs = self.path.partition("?")
                if path.startswith("/s3/"):   # the signed URLs
                    key = path[4:]
                    if self.command == "PUT":
                        if self.headers.get("x-amz-checksum-sha256") != hashlib.sha256(raw).hexdigest():
                            return self._answer(400, {"error": "BadDigest"})
                        p.blobs[key] = raw
                        p.calls.append(("PUT", path, {}))
                        return self._answer(200)
                    return self._answer(200, raw=p.blobs[key], ct="application/octet-stream") if key in p.blobs else self._answer(404)
                body = json.loads(raw or b"{}")
                p.calls.append((self.command, path, body))
                for suf, ans in p.fail.items():
                    if path.endswith(suf):
                        return self._answer(*ans)
                auth = self.headers.get("Authorization") or ""
                who = next((u for t, u in TOKENS.items() if auth == f"Bearer {t}"), None)
                q = dict(x.split("=", 1) for x in qs.split("&") if "=" in x)
                if path == "/auth/v1/public/resources":
                    reader = next((u for t, u in TOKENS.items() if auth == f"Bearer {t}"), None)
                    rows = [dict(id=i, **{k: v for k, v in r.items() if k not in ("files", "owner")}) for i, r in p.res.items()
                            if r["status"] == "published" and r["zone"] in q.get("zones", "curated").split("%2C") and q.get("client") != "ios"
                            and r["owner"] not in p.blocks.get(reader or "", set())]
                    for row in rows:
                        row["official"] = p.res[row["id"]]["owner"] in p.official
                    return self._answer(200, {"resources": rows})
                m = re.fullmatch(r"/storage/v1/public/objects/hub/template/([^/]+)/download-url", path)
                if m:
                    r = p.res.get(m.group(1))
                    if not r or r["status"] != "published":
                        return self._answer(404, {"error": "not_found"})
                    rev = r["published_revision"]
                    return self._answer(200, {"revision": rev, "files": [
                        {"path": f, "size": len(p.blobs[f"{m.group(1)}/{rev}/{f}"]), "sha256": hashlib.sha256(p.blobs[f"{m.group(1)}/{rev}/{f}"]).hexdigest(),
                         "url": f"{p.base}/s3/{m.group(1)}/{rev}/{f}"} for f in r["files"][rev]]})
                if who is None:
                    return self._answer(401, {"error": "unauthorized"})
                if path == "/auth/v1/me/blocks":
                    return self._answer(200, {"blocks": [{"id": f"blk_{o}", "ref": {"product": "hub", "kind": "template", "id": next((i for i, r in p.res.items() if r["owner"] == o), "")}}
                                                         for o in sorted(p.blocks.get(who, set()))]})
                if path == "/auth/v1/me":
                    return self._answer(200, {"user": {"id": who, "display_name": f"作者{who[2:]}", "anonymous": who == "u-guest", "official": who in p.official}})
                if path == "/auth/v1/resources" and self.command == "GET":
                    return self._answer(200, {"resources": [self._view(i, r) for i, r in p.res.items() if r["owner"] == who]})
                if path == "/auth/v1/resources":
                    r = p.res.get(body["id"])
                    if r and r["owner"] != who:
                        return self._answer(409, {"error": "owned"})
                    if not r:
                        p.res[body["id"]] = {"owner": who, "status": "draft", "zone": None, "revision": 0, "published_revision": None,
                                             "title": body.get("title"), "meta": body.get("meta") or {}, "files": {}, "review": {"state": "none"}, "takedown": None}
                    return self._answer(201 if not r else 200, {"resource": {"id": body["id"]}})
                m = re.fullmatch(r"/(auth|storage)/v1/(resources|objects)/hub/template/([^/]+)/([a-z-]+)(?:/(.+))?", path)
                if not m:
                    return self._answer(404, {})
                rid, act = m.group(3), m.group(4)
                r = p.res.get(rid)
                if act == "block-owner":
                    if not r or r["status"] != "published":
                        return self._answer(404, {"error": "not_found"})
                    if r["owner"] == who:
                        return self._answer(400, {"error": "cannot_block_self"})
                    mine = p.blocks.setdefault(who, set())
                    if self.command == "DELETE":
                        had = r["owner"] in mine
                        mine.discard(r["owner"])
                        return self._answer(200, {"unblocked": had})
                    created = r["owner"] not in mine
                    mine.add(r["owner"])
                    return self._answer(201 if created else 200, {"blocked": True, "created": created, "block": {"id": f"blk_{r['owner']}", "ref": {"id": rid}}})
                if act == "report":
                    if not r or r["status"] != "published" or r["owner"] == who:
                        return self._answer(404, {"error": "not_found"})
                    p.reports.append((rid, who, body.get("reason")))
                    return self._answer(201, {"reported": True, "created": True})
                if act == "download-url" and r and r["status"] == "published" and r["owner"] != who:
                    rev = r["published_revision"]
                    full = r["zone"] == "open" or (r["zone"] == "curated" and p.p1 and who != "u-guest")
                    names = [f for f in r["files"][rev] if full or f.startswith("cover.")]
                    return self._answer(200, {"revision": rev, "published_revision": rev, "zone": r["zone"], **({} if full else {"limited": "zone"}),
                                              "files": [{"path": f, "sha256": hashlib.sha256(p.blobs[f"{rid}/{rev}/{f}"]).hexdigest(),
                                                         "url": f"{p.base}/s3/{rid}/{rev}/{f}"} for f in names]})
                if not r or r["owner"] != who:
                    return self._answer(404, {"error": "not_found"})
                if act == "lease":
                    return self._answer(200 if self.command == "DELETE" else 201, {"lease_id": "wl_lease_x"})
                if act == "upload-url":
                    r["_pending"] = r["revision"] + 1
                    return self._answer(200, {"revision": r["_pending"], "uploads": [
                        {"path": f["path"], "url": f"{p.base}/s3/{rid}/{r['_pending']}/{f['path']}", "method": "PUT",
                         "headers": {"x-amz-checksum-sha256": f["sha256"]}} for f in body["files"]]})
                if act == "complete":
                    rev = r.pop("_pending")
                    r["files"][rev] = sorted(k.split("/", 2)[2] for k in p.blobs if k.startswith(f"{rid}/{rev}/"))
                    r.update(revision=rev, title=body.get("title"), meta=body.get("meta") or {})
                    assert len(json.dumps(r["meta"]).encode()) <= 4096, "identity: meta ≤ 4 KB"
                    return self._answer(200, {"manifest": {"revision": rev}})
                if act == "publish":
                    if r["takedown"]:
                        return self._answer(409, {"error": "taken_down"})
                    if (r["meta"].get("lint") or {}).get("errors"):
                        return self._answer(422, {"error": "checks_failed", "failures": [{"check": "lint", "detail": "lint errors"}]})
                    if r["status"] == "published" and body.get("zone") and body["zone"] != r["zone"]:
                        return self._answer(409, {"error": "published"})
                    zone = body.get("zone") or r["zone"] or "curated"
                    if zone == "curated" and p.auto and who in p.official:
                        r.update(status="published", zone=zone, published_revision=r["revision"], review={"state": "approved"})
                        return self._answer(200, {"resource": self._view(rid, r)})
                    if zone == "curated":
                        r.update(zone=zone, review={"state": "pending"})
                        return self._answer(202, {"review": {"state": "pending"}, "resource": self._view(rid, r)})
                    r.update(status="published", zone=zone, published_revision=r["revision"])
                    return self._answer(200, {"resource": self._view(rid, r)})
                if act == "unpublish":
                    r["status"] = "draft"
                    return self._answer(200, {"resource": self._view(rid, r)})
                if act == "submit":
                    r["review"] = {"state": "pending", "note": None}
                    return self._answer(202, {"review": r["review"], "resource": self._view(rid, r)})
                if act == "withdraw":
                    if r["review"].get("state") != "pending":
                        return self._answer(409, {"error": "not_pending"})
                    r["review"] = {"state": "approved" if r["status"] == "published" else "none"}
                    return self._answer(200, {"resource": self._view(rid, r)})
                return self._answer(404, {})

            def _view(self, rid, r):
                return {"id": rid, "status": r["status"], "zone": r["zone"], "title": r["title"], "meta": r["meta"], "revision": r["revision"],
                        "published_revision": r["published_revision"] if r["status"] == "published" else None,
                        "review": r["review"], "takedown": r["takedown"], "updated_at": f"2026-10-16T00:00:{r['revision']:02d}Z"}

            do_GET = do_POST = do_PUT = do_DELETE = _do

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def steps(self):
        return [p for m, p, _ in self.calls if not p.startswith("/s3/")]


@pytest.fixture
def platform(monkeypatch):
    p = Platform()
    monkeypatch.setattr(worldlines_auth, "ISSUER", p.base + "/auth")
    monkeypatch.setattr(replay_share, "STORAGE", p.base + "/storage")
    monkeypatch.setenv("WORLDLINES_API_KEY", "author")
    tp._COVER_CACHE.clear()
    yield p
    p.srv.shutdown()


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A writable template store holding one publishable template (a copy of stoneford-market as ``fz-test``)."""
    root = tmp_path / "store"
    d = root / "fz-test.template"
    shutil.copytree(SRC_TPL, d, ignore=shutil.ignore_patterns("__pycache__"))
    j = json.loads((d / "template.json").read_text(encoding="utf-8"))
    j["id"] = "fz-test"
    (d / "template.json").write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(root))
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(root))
    return d


def _t():
    return TP.load(TP.discover()["fz-test"])


# ── the checks ───────────────────────────────────────────────────────────────

def test_preflight_secret_langs_cover(store, platform):
    assert tp.preflight(_t()) == []
    (store / "notes.md").write_text("api_key = " + "sk-" + "a" * 32 + "\n", encoding="utf-8")
    ko = store / "i18n" / "ko" / "template.json"
    kj = json.loads(ko.read_text(encoding="utf-8"))
    kj["card"].pop("pitch")
    ko.write_text(json.dumps(kj, ensure_ascii=False), encoding="utf-8")
    j = json.loads((store / "template.json").read_text(encoding="utf-8"))
    j["card"]["cover"] = "assets/nope.png"
    (store / "template.json").write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")
    probs = tp.preflight(_t(), lang="en")
    codes = [p["code"] for p in probs]
    assert {"secret", "langs", "cover"} <= set(codes), probs   # (the lint has its own say about the cover too)
    by = {p["code"]: p for p in probs}
    assert "fz-test/notes.md:1" in by["secret"]["message"] and by["langs"]["langs"] == ["ko"]
    platform.calls.clear()
    with pytest.raises(tp.PublishError) as e:
        tp.publish(_t(), lang="ja")
    assert (e.value.status, e.value.code) == (422, "checks_failed") and "公開前のチェック" in str(e.value)
    assert [p["code"] for p in e.value.extra["problems"]] == codes
    assert platform.calls == [], "nothing goes up before the checks pass"


def test_preflight_lint_blocks(store, platform):
    lint = {"publishable": False, "problems": [{"level": "block", "code": "meta.card", "where": "card.title", "message": "needs a title"}]}
    probs = tp.preflight(_t(), lang="zh", lint=lint)
    assert probs[0]["code"] == "lint" and "1 个" in probs[0]["message"] and probs[0]["items"][0]["code"] == "meta.card"


# ── publish ──────────────────────────────────────────────────────────────────

def test_publish_six_steps_then_a_new_revision(store, platform):
    out = tp.publish(_t(), lang="zh")
    wid, ref = out["id"], out["ref"]
    assert re.fullmatch(r"fz-test-[0-9a-f]{6}", wid) and ref == f"hub/template/{wid}"
    assert (out["zone"], out["status"], out["revision"], out["updated"]) == ("open", "published", 1, False)
    assert "自由区" in out["message"]
    assert platform.steps() == ["/auth/v1/resources", "/auth/v1/me", "/auth/v1/resources", f"/auth/v1/resources/{ref}/lease",
                                f"/storage/v1/objects/{ref}/upload-url", f"/storage/v1/objects/{ref}/complete",
                                f"/auth/v1/resources/{ref}/publish"], "mine (GET) → me (the author's name) → register → lease → upload → complete → publish"
    body = {(m, p): b for m, p, b in platform.calls}
    assert body[("POST", f"/auth/v1/resources/{ref}/publish")] == {"zone": "open"}
    meta = body[("POST", f"/storage/v1/objects/{ref}/complete")]["meta"]
    assert meta["author"] == "作者author", "the web Hub labels community works with the author's name"
    assert meta["source"] == "fz-test" and meta["lint"]["errors"] == 0 and meta["cover"] == "cover.png" and meta["package"] == "package.zip"
    assert set(meta["title"]) == {"zh", "en", "ja", "ko"} and set(meta["pitch"]) == {"zh", "en", "ja", "ko"}
    assert len(json.dumps(meta, ensure_ascii=False).encode()) <= 4096
    up = {k.split("/", 2)[2] for k in platform.blobs}
    assert up == {"package.zip", "cover.png"}
    z = zipfile.ZipFile(io.BytesIO(platform.blobs[f"{wid}/1/package.zip"]))
    assert json.loads(z.read("pack.json"))["id"] == "fz-test" and "fz-test.template/template.json" in z.namelist()
    assert any(n.startswith("_builtin/stoneford-elena/") for n in z.namelist()), "a built-in world rides along for the browser engine"
    # the same template again: the author's work is found by meta.source, one more revision, same id
    platform.calls.clear()
    again = tp.publish(_t(), lang="en")
    assert again["id"] == wid and again["revision"] == 2 and again["updated"] is True
    st = tp.status(_t(), lang="zh")
    assert st["checks"]["ok"] and st["signed_in"] and st["work"]["id"] == wid and st["work"]["zone"] == "open"


def test_publish_errors_in_the_authors_language(store, platform, monkeypatch):
    monkeypatch.setenv("WORLDLINES_API_KEY", "-")
    with pytest.raises(tp.PublishError) as e:
        tp.publish(_t(), lang="ko")
    assert (e.value.status, e.value.code) == (401, "not_signed_in") and "로그인" in str(e.value)
    monkeypatch.setenv("WORLDLINES_API_KEY", "author")
    platform.fail = {"/lease": (403, {"error": "insufficient_scope"})}
    with pytest.raises(tp.PublishError) as e:
        tp.publish(_t(), lang="zh")
    assert (e.value.status, e.value.code) == (403, "insufficient_scope") and "重新登录" in str(e.value)
    platform.fail = {"/publish": (422, {"error": "checks_failed", "failures": [{"check": "secret", "detail": "api_key in meta"}]})}
    with pytest.raises(tp.PublishError) as e:
        tp.publish(_t(), lang="en")
    assert e.value.status == 422 and e.value.extra["problems"] == [{"code": "platform.secret", "message": "api_key in meta"}]
    platform.fail = {"/upload-url": (500, {})}
    platform.calls.clear()
    with pytest.raises(tp.PublishError) as e:
        tp.publish(_t(), lang="zh")
    assert e.value.status == 502 and any(m == "DELETE" and "/lease/" in p for m, p, _ in platform.calls), "the lease is given back"
    platform.fail = {}
    wid = tp.publish(_t())["id"]
    platform.res[wid]["takedown"] = {"by": "admin", "reason": "侵权"}
    with pytest.raises(tp.PublishError) as e:
        tp.publish(_t(), lang="zh")
    assert (e.value.status, e.value.code) == (409, "taken_down")
    assert tp.mine()[0]["takedown"]["reason"] == "侵权", "the author sees why"


def test_a_work_moved_to_the_default_zone_goes_to_review(store, platform):
    wid = tp.publish(_t())["id"]
    platform.res[wid]["zone"] = "curated"   # an admin moved it
    out = tp.publish(_t(), lang="zh")
    assert out["zone"] == "reviewed" and out["review"]["state"] == "pending" and "审核" in out["message"]
    assert [b for m, p, b in platform.calls if p.endswith("/publish")][-1] == {}, "no zone asked: a published work keeps its zone"


# ── the free zone: list · cover · fetch · report · unpublish · submit ───────

def test_open_list_fetch_report_unpublish(store, platform, monkeypatch, tmp_path):
    wid = tp.publish(_t())["id"]
    ws = tp.open_works()
    assert [w["id"] for w in ws] == [wid] and ws[0]["zone"] == "open" and ws[0]["meta"]["source"] == "fz-test"
    assert tp.open_works(client="ios") == [], "iOS never gets the free zone"
    data, ct = tp.cover(wid)
    assert ct == "image/jpeg" and data == (store / "assets" / "cover.png").read_bytes(), "typed by its bytes (this .png is a JPEG)"
    # a reader downloads it: lands under the work id, marked as a free-zone work; again → -2
    monkeypatch.setenv("WORLDLINES_API_KEY", "reader")
    got = tp.fetch(wid, lang="ja")
    assert got["id"] == wid and "ダウンロード" in got["message"]
    tj = json.loads((store.parent / f"{wid}.template" / "template.json").read_text(encoding="utf-8"))
    assert tj["zone"] == "open" and tj["hub_ref"] == f"hub/template/{wid}" and TP.load(TP.discover()[wid]).zone == "open"
    assert tp.fetch(wid)["id"] == f"{wid}-2"
    assert tp.report(wid, "  泄露了密钥 ", lang="zh")["ok"] and platform.reports == [(wid, "u-reader", "泄露了密钥")]
    with pytest.raises(tp.PublishError) as e:
        tp.report(wid, " ")
    assert e.value.code == "no_reason"
    monkeypatch.setenv("WORLDLINES_API_KEY", "author")
    with pytest.raises(tp.PublishError) as e:
        tp.report(wid, "self")
    assert e.value.status == 404
    assert tp.submit(wid, lang="zh")["review"]["state"] == "pending"
    assert tp.unpublish(wid, lang="en")["work"]["status"] == "draft"
    assert tp.open_works() == []
    with pytest.raises(tp.PublishError) as e:
        tp.fetch(wid)
    assert e.value.status == 404
    with pytest.raises(tp.PublishError) as e:
        tp.unpublish("../x")
    assert e.value.code == "bad_id"


# ── over HTTP ────────────────────────────────────────────────────────────────

def test_routes(store, platform, monkeypatch, tmp_path):
    from neonrp.commands.web import make_server

    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "studio"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def call(method, path, b=None):
            req = urllib.request.Request(base + path, data=json.dumps(b).encode() if b is not None else None, method=method,
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    raw = r.read()
                    return r.status, (json.loads(raw) if r.headers.get_content_type() == "application/json" else raw)
            except urllib.error.HTTPError as e:
                raw = e.read() or b"{}"
                return e.code, (json.loads(raw) if raw[:1] == b"{" else {})
        try:
            st, b = call("GET", "/api/v1/local/templates/fz-test/publish?lang=en")
            assert st == 200 and b["checks"]["ok"] and b["work"] is None and b["signed_in"]
            st, b = call("POST", "/api/v1/local/templates/fz-test/publish", {"lang": "zh"})
            assert st == 200 and b["zone"] == "open", b
            wid = b["id"]
            st, b = call("GET", "/api/v1/local/templates/fz-test/publish")
            assert b["work"]["id"] == wid and b["work"]["status"] == "published"
            st, b = call("GET", "/api/v1/local/hub/open")
            assert [w["id"] for w in b["works"]] == [wid] and b["works"][0]["cover_url"].startswith(f"/api/v1/local/hub/cover?id={wid}")
            assert b["works"][0]["local"] is None
            st, img = call("GET", b["works"][0]["cover_url"])
            assert st == 200 and img == (store / "assets" / "cover.png").read_bytes()
            st, b = call("GET", "/api/v1/local/hub/mine?lang=ja")
            assert st == 200 and b["works"][0]["id"] == wid
            st, b = call("POST", "/api/v1/local/hub/fetch", {"id": wid, "lang": "en"})
            assert st == 200 and b["id"] == wid
            st, b = call("GET", "/api/v1/local/hub/open")
            assert b["works"][0]["local"] == wid, "downloaded: the Hub plays it locally"
            monkeypatch.setenv("WORLDLINES_API_KEY", "reader")
            st, b = call("POST", "/api/v1/local/hub/report", {"id": wid, "reason": "x", "lang": "ko"})
            assert st == 200 and b["ok"]
            monkeypatch.setenv("WORLDLINES_API_KEY", "author")
            st, b = call("POST", "/api/v1/local/hub/submit", {"id": wid})
            assert st == 200 and b["review"]["state"] == "pending"
            st, b = call("POST", "/api/v1/local/hub/unpublish", {"id": wid, "lang": "zh"})
            assert st == 200 and "撤下" in b["message"]
            st, b = call("POST", "/api/v1/local/templates/nope/publish", {})
            assert st == 404
            monkeypatch.setenv("WORLDLINES_API_KEY", "-")
            st, b = call("POST", "/api/v1/local/templates/fz-test/publish", {"lang": "en"})
            assert st == 401 and b["error"] == "not_signed_in" and "sign in" in b["message"]
            st, b = call("GET", "/api/v1/local/account")
            assert st == 200 and b["signed_in"] is False and b["login"] == "idle"
        finally:
            server.shutdown()
