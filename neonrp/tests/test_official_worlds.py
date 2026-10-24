"""官方世界走账号(10-17):本地版只内置灰橡宅 / 石津镇,其他官方世界由官方账号「发布为官方」进默认区,
登录的本地玩家在 Hub 里获取到官方缓存(NEONRP_OFFICIAL_DIR)—— 只能玩,不能导出 / 复制。

假平台 = test_template_publish.Platform(identity /v1/me official · 公开列表标 official · curated 自动通过(P2)·
storage 给我们 app 的非游客 token 放行 curated 包(P1))。"""
from __future__ import annotations

import io
import json
import shutil
import zipfile

import pytest

from neonrp import template as TP
from neonrp.core import template_publish as tp
from neonrp.template import author
from neonrp.template.package import ExportRefused, export_template

from _paths import PRODUCT_TEMPLATES
from test_template_publish import platform  # noqa: F401 — the fake platform fixture

SRC_TPL = PRODUCT_TEMPLATES / "stoneford-market.template"   # a publishable template to start from (dev repo only)


@pytest.fixture
def desk(tmp_path, monkeypatch):
    """The official account's local creation desk: one publishable template ``of-test`` in its store + an official cache."""
    root = tmp_path / "store"
    d = root / "of-test.template"
    shutil.copytree(SRC_TPL, d, ignore=shutil.ignore_patterns("__pycache__"))
    j = json.loads((d / "template.json").read_text(encoding="utf-8"))
    j.update(id="of-test", version="1.0")
    (d / "template.json").write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(root))
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(root))
    monkeypatch.setenv("NEONRP_OFFICIAL_DIR", str(tmp_path / "official"))
    monkeypatch.delenv("NEONRP_OFFICIAL_PUBLISH", raising=False)
    return d


def _t():
    return TP.load(TP.discover()["of-test"])


def _bump(d, v):
    j = json.loads((d / "template.json").read_text(encoding="utf-8"))
    j["version"] = v
    (d / "template.json").write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")


def test_only_the_official_account(desk, platform):
    with pytest.raises(tp.PublishError) as e:
        tp.publish_official(_t(), lang="zh")
    assert (e.value.status, e.value.code) == (403, "official_only") and "官方账号" in str(e.value)
    assert not [c for c in platform.calls if c[0] == "POST"], "nothing registered"
    assert tp.status(_t(), lang="zh")["official"] is False
    platform.official.add("u-author")
    assert tp.status(_t(), lang="zh")["official"] is True


def test_publish_official_own_id_curated_versions(desk, platform):
    platform.official.add("u-author")
    out = tp.publish_official(_t(), lang="zh")   # before P2: waits for review in the console
    assert (out["id"], out["ref"], out["zone"], out["status"], out["revision"]) == ("of-test", "hub/template/of-test", "reviewed", "pending", 1)
    assert "批准" in out["message"]
    body = {(m, p): b for m, p, b in platform.calls}
    assert body[("POST", "/auth/v1/resources/hub/template/of-test/publish")] == {"zone": "curated"}
    meta = body[("POST", "/storage/v1/objects/hub/template/of-test/complete")]["meta"]
    assert meta["official"] is True and meta["version"] == "1.0" and meta["source"] == "of-test"
    z = zipfile.ZipFile(io.BytesIO(platform.blobs["of-test/1/package.zip"]))
    assert json.loads(z.read("of-test.template/template.json"))["zone"] == "reviewed"
    assert "zone" not in json.loads((desk / "template.json").read_text(encoding="utf-8")), "the source folder is not touched"
    # the same version again: refused before anything goes up
    platform.calls.clear()
    with pytest.raises(tp.PublishError) as e:
        tp.publish_official(_t(), lang="en")
    assert (e.value.status, e.value.code) == (409, "official_version") and "1.1" in str(e.value)
    assert not [c for c in platform.calls if c[0] == "POST"]
    # P2 on: an official owner's curated publish is live at once — a new revision under the same id
    platform.auto = True
    _bump(desk, "1.1")
    out = tp.publish_official(_t(), lang="zh")
    assert (out["id"], out["status"], out["revision"], out["updated"]) == ("of-test", "published", 2, True) and "已发布为官方" in out["message"]


def test_official_id_taken(desk, platform, monkeypatch):
    platform.official.add("u-author")
    platform.res["of-test"] = {"owner": "u-reader", "status": "draft", "zone": None, "revision": 0, "published_revision": None,
                               "title": "x", "meta": {}, "files": {}, "review": {"state": "none"}, "takedown": None}
    with pytest.raises(tp.PublishError) as e:
        tp.publish_official(_t(), lang="ja")
    assert (e.value.status, e.value.code) == (409, "official_id_taken") and "of-test" in str(e.value)


def _live(desk, platform):
    platform.official.add("u-author")
    platform.auto = True
    tp.publish_official(_t(), lang="zh")
    shutil.rmtree(desk)   # the player's machine: not the author's store


def test_signed_out_sees_nothing(desk, platform, monkeypatch):
    _live(desk, platform)
    monkeypatch.setenv("WORLDLINES_API_KEY", "-")
    assert tp.official_works(lang="zh") == {"signed_in": False, "works": []}


def test_list_fetch_play_update(desk, platform, monkeypatch, tmp_path):
    _live(desk, platform)
    monkeypatch.setenv("WORLDLINES_API_KEY", "reader")   # a player signed in on the local edition
    d = tp.official_works(lang="zh")
    w = next(x for x in d["works"] if x["id"] == "of-test")
    assert d["signed_in"] and w["official"] and w["version"] == "1.0" and w["installed"] is None and not w["update"]
    out = tp.fetch_official("of-test", lang="zh")
    assert out["id"] == "of-test" and out["revision"] == 1 and not out["updated"] and "已获取" in out["message"]
    cache = tmp_path / "official" / "of-test.template"
    t = TP.load(TP.discover()["of-test"])
    assert t.dir == cache and t.official and t.zone == "reviewed" and t.data["hub_revision"] == 1
    assert not author.writable(t) and not TP.can_fork(t) and t.meta()["forkable"] is False
    with pytest.raises(ExportRefused):
        export_template(t)
    assert TP.new_run(cache).is_dir(), "it plays"
    w = next(x for x in tp.official_works(lang="zh")["works"] if x["id"] == "of-test")
    assert w["installed"]["where"] == "official" and w["installed"]["revision"] == 1 and not w["update"]
    # a new official revision: the list says update; fetching swaps the copy whole, same id (no -2)
    monkeypatch.setenv("WORLDLINES_API_KEY", "author")
    shutil.copytree(SRC_TPL, desk, ignore=shutil.ignore_patterns("__pycache__"))
    j = json.loads((desk / "template.json").read_text(encoding="utf-8"))
    j.update(id="of-test", version="1.1")
    j["card"]["title"] = "新版标题"
    (desk / "template.json").write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")
    tp.publish_official(_t(), lang="zh")
    shutil.rmtree(desk)
    monkeypatch.setenv("WORLDLINES_API_KEY", "reader")
    w = next(x for x in tp.official_works(lang="zh")["works"] if x["id"] == "of-test")
    assert w["update"] and w["version"] == "1.1"
    out = tp.fetch_official("of-test", lang="en")
    assert out["updated"] and out["revision"] == 2 and "Updated" in out["message"]
    assert TP.load(cache).card["title"] == "新版标题" and not list((tmp_path / "official").glob(".of-test*"))
    assert sorted(p.name for p in (tmp_path / "official").iterdir()) == ["of-test.template"]


def test_guest_and_no_p1_are_refused(desk, platform, monkeypatch):
    _live(desk, platform)
    monkeypatch.setenv("WORLDLINES_API_KEY", "guest")
    with pytest.raises(tp.PublishError) as e:
        tp.fetch_official("of-test", lang="zh")
    assert (e.value.status, e.value.code) == (403, "official_locked")
    monkeypatch.setenv("WORLDLINES_API_KEY", "reader")
    platform.p1 = False   # storage before P1: covers only
    with pytest.raises(tp.PublishError) as e:
        tp.fetch_official("of-test", lang="ko")
    assert e.value.code == "official_locked" and "로그인" in str(e.value)


def test_free_zone_list_has_no_official_worlds(desk, platform, monkeypatch):
    _live(desk, platform)
    monkeypatch.setenv("WORLDLINES_API_KEY", "reader")
    assert [w["id"] for w in tp.open_works(lang="zh")] == []


def test_routes(desk, platform, monkeypatch, tmp_path):
    import threading
    import urllib.error
    import urllib.request
    from unittest.mock import patch

    from neonrp.commands.web import make_server

    platform.official.add("u-author")
    platform.auto = True
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
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                raw = e.read() or b"{}"
                return e.code, (json.loads(raw) if raw[:1] == b"{" else {})
        try:
            st, b = call("GET", "/api/v1/local/templates/of-test/publish?lang=zh")
            assert st == 200 and b["official"] is True
            st, b = call("POST", "/api/v1/local/templates/of-test/publish", {"official": True, "lang": "zh"})
            assert st == 200 and b["ref"] == "hub/template/of-test" and b["status"] == "published", b
            shutil.rmtree(desk)
            monkeypatch.setenv("WORLDLINES_API_KEY", "reader")
            st, b = call("GET", "/api/v1/local/hub/official?lang=zh")
            w = next(x for x in b["works"] if x["id"] == "of-test")
            assert st == 200 and b["signed_in"] and w["official"] and w["cover_url"].startswith("/api/v1/local/hub/cover?id=of-test")
            st, b = call("POST", "/api/v1/local/hub/official/fetch", {"id": "of-test", "lang": "zh"})
            assert st == 200 and b["ok"], b
            st, b = call("GET", "/api/v1/local/templates")
            row = next(x for x in b["templates"] if x["id"] == "of-test")
            assert row["official"] and row["forkable"] is False
            st, b = call("POST", "/api/v1/local/templates/of-test/fork", {"id": "of-mine", "lang": "ja"})
            assert st == 403 and b["error"] == "not_forkable" and "コピー" in b["message"]
            st, b = call("GET", "/api/v1/local/templates/of-test/export")
            assert st == 403
        finally:
            server.shutdown()
