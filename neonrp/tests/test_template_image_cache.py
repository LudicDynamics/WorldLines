"""模板图片的取图速度(10-15,chat-fe / ios2:引擎刚起时第一张立绘 ~30 s)。

- 角色立绘 / 小人图(soul.<名>:<sid>)直接在 soul 文件夹里找，不再为一张图建一次整个世界;卡面 / 剧情图只看模板自己
- 图槽表按模板缓存;签名(遍历模板所有文件的 mtime / size)在 SIG_TTL 秒内复用;同一模板同时来 N 个冷请求只建一次
- /api/v1/local/templates/<id>/assets/file 带 ETag + Cache-Control,带回 If-None-Match 得 304"""
from __future__ import annotations

import shutil
import threading
import time
import urllib.error
import urllib.request
from unittest.mock import patch

import pytest

from _paths import PRODUCT_TEMPLATES
from neonrp import template as TP
from neonrp.template import v3


@pytest.fixture
def cold():
    v3._ROWS.clear()
    v3._SIGS.clear()
    yield
    v3._ROWS.clear()
    v3._SIGS.clear()


def _no_build(*a, **k):
    raise AssertionError("a picture must not build the world")


@pytest.mark.parametrize("tid,sid", [("spice-witch", None), ("kagura-island", "hane"), ("stoneford-town", "elena"), ("wuwu", "vera")])
def test_a_portrait_needs_no_world_build(cold, tid, sid):
    t = TP.load(PRODUCT_TEMPLATES / f"{tid}.template")
    sid = sid or next(s["sid"] for s in TP.draw_souls(t, seed="", everyone=True))
    t0 = time.monotonic()
    with patch.object(v3, "_scratch", _no_build):
        p = TP.slot_file(t, f"soul.portrait:{sid}")
        cover = TP.slot_file(t, "card:cover")
    took = time.monotonic() - t0
    assert p is not None and p.is_file() and p.stem == "portrait"
    assert cover is None or cover.is_file()
    assert took < 1.0, f"cold portrait + cover took {took:.2f}s"


def test_fast_path_is_the_slow_paths_answer(cold):
    t = TP.load(PRODUCT_TEMPLATES / "kagura-island.template")
    rows = [r for r in v3.cached_rows(t) if r["cls"] == "soul" and r.get("have")]
    assert rows
    for r in rows:
        assert v3.soul_file_fast(t, r["name"], r["inst"]) == v3.source_file(t, r["slot"]), r["slot"]


def test_signature_is_remembered_and_cold_builds_happen_once(cold, tmp_path):
    shutil.copytree(PRODUCT_TEMPLATES / "spice-witch.template", tmp_path / "spice-witch.template")
    t = TP.load(tmp_path / "spice-witch.template")
    walks, builds = [], []
    real_walk, real_rows = v3._walk_signature, v3.slot_rows
    with (patch.object(v3, "_walk_signature", lambda t: walks.append(1) or real_walk(t)),
          patch.object(v3, "slot_rows", lambda *a, **k: builds.append(1) or real_rows(*a, **k))):
        ths = [threading.Thread(target=v3.cached_rows, args=(t,)) for _ in range(6)]
        for th in ths:
            th.start()
        for th in ths:
            th.join()
        assert len(builds) == 1, "six pictures asked at once: one build"
        v3.cached_rows(t)  # the build itself may outlast SIG_TTL: count from a fresh signature
        n = len(walks)
        for _ in range(20):
            v3.cached_rows(t)
        assert len(walks) == n, "within SIG_TTL the template is not walked again"
        v3._SIGS.clear()
        (tmp_path / "spice-witch.template" / "new.txt").write_text("x", encoding="utf-8")
        v3.cached_rows(t)
        assert len(builds) == 2, "a changed file invalidates the rows"


def test_http_etag_and_cache_control(cold, tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    store = tmp_path / "store"
    shutil.copytree(PRODUCT_TEMPLATES / "wuwu.template", store / "wuwu.template")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(store))
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "studio"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_address[1]}/api/v1/local/templates/wuwu/assets/file?slot=soul.portrait:vera"
        try:
            t0 = time.monotonic()
            with urllib.request.urlopen(url, timeout=60) as r:
                body, etag, cc = r.read(), r.headers["ETag"], r.headers["Cache-Control"]
            assert time.monotonic() - t0 < 3.0 and body[:4] in (b"\x89PNG", b"RIFF") or body[:3] == b"\xff\xd8\xff"
            assert etag and "max-age" in cc
            with pytest.raises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(urllib.request.Request(url, headers={"If-None-Match": etag}), timeout=60)
            assert e.value.code == 304 and e.value.headers["ETag"] == etag
            from neonrp.core import thumbs

            monkeypatch.setattr(thumbs, "HOME", tmp_path / "thumbs")
            with urllib.request.urlopen(url + "&w=128", timeout=60) as r:
                assert r.headers["Content-Type"] == "image/webp" and len(r.read()) < len(body)
        finally:
            server.shutdown()


def test_small_picture_for_avatars(cold, tmp_path, monkeypatch):
    """&w=<px>:卡片 / 头像用的小图(chat-fe 10-15:艾琳娜原图 2.2 MB)。做一次存进缓存,原图变了换新的。"""
    import io

    from PIL import Image

    from neonrp.core import soul_chat, thumbs
    from neonrp.webui import template_routes  # noqa: F401 — the route below

    monkeypatch.setattr(thumbs, "HOME", tmp_path / "thumbs")
    assert thumbs.width("200") == 256 and thumbs.width("5000") == 1024 and thumbs.width("") is None and thumbs.width("x") is None
    t = TP.load(PRODUCT_TEMPLATES / "stoneford-town.template")
    src = TP.slot_file(t, "soul.portrait:elena")
    small = thumbs.thumb(src, 256)
    assert small != src and small.suffix == ".webp" and small.stat().st_size < src.stat().st_size / 4
    with Image.open(small) as im:
        assert im.width == 256
    assert thumbs.thumb(src, 256) == small, "made once"
    assert thumbs.thumb(src, None) == src
    with Image.open(io.BytesIO(small.read_bytes())) as im:
        assert im.format == "WEBP"
    card = soul_chat.soul_card({"tpl": "stoneford-town", "sid": "elena", "sj": {"sid": "elena"}, "t": t}, "zh")
    assert card["avatar_thumb_url"] == card["avatar_url"] + "&w=256"
