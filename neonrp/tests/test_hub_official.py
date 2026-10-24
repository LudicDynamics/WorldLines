"""本地 Hub 的官方世界(10-17 · core/template_publish.official_works / fetch_official):本地版只内置灰橡宅 / 石津镇;
没登录 = 本机的 + 线上 Hub 的世界(10-24,点进去到线上 Hub 玩)+ 一张「登录后可获取更多官方世界」;登录后默认区的远端世界进发现页(标「官方」),详情页「获取」;
获取下来的官方世界只能玩(不出复制 / 导出),有新版出「更新」;内置的两个照旧能「复制一份来改」。引擎接口全是假的(tests/hub_official.mjs)。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HUB = ROOT / "worldlines" / "ui" / "app" / "hub"
UI = ROOT / "worldlines" / "ui"


def _remote(wid, title, *, version="1.0", rev=2, installed=None, update=False):
    return {"id": wid, "ref": f"hub/template/{wid}", "title": title, "status": "published", "zone": "reviewed", "official": True,
            "revision": rev, "published_revision": rev, "published_at": "2026-10-17T01:00:00Z", "version": version,
            "installed": installed, "update": update, "cover_url": f"/api/v1/local/hub/cover?id={wid}&rev={rev}",
            "meta": {"source": wid, "version": version, "lang": "zh", "langs": ["zh", "en", "ja", "ko"], "play_contract": "mystery-trpg@1",
                     "ending": "multi", "title": {"zh": title, "en": title + " EN", "ja": title + " JA", "ko": title + " KO"}, "pitch": {"zh": "一句话"}, "cover": "cover.png"}}


def _run(tmp_path, lang="zh", shots=None):
    node = shutil.which("node")
    if not node or not (UI / "node_modules" / "playwright").is_dir():
        pytest.skip("node + worldlines/ui/node_modules/playwright needed")
    page = (HUB / "index.html").read_text(encoding="utf-8").replace(
        "<!--SCRIPT-->", "<script>window.HUB={}</script><script>" + (HUB / "hub.js").read_text(encoding="utf-8") + "</script>")
    (tmp_path / "page.html").write_text(page, encoding="utf-8")
    api = {
        "/api/v1/local/templates": {"templates": [
            {"id": "pct-house", "card": {"title": "灰橡宅", "pitch": "p", "lang": "zh"}, "mode": {"ending": "multi"}, "zone": "reviewed", "forkable": True, "builtin": True},
            {"id": "wuwu", "card": {"title": "乌乌", "pitch": "p", "lang": "zh"}, "mode": {"ending": "multi"}, "zone": "reviewed", "version": "1.0",
             "forkable": False, "official": True, "hub_ref": "hub/template/wuwu", "hub_revision": 1},
            {"id": "mine", "card": {"title": "我自己的", "pitch": "p", "lang": "zh"}, "mode": {"ending": "open"}, "zone": None, "forkable": True}]},
        "/api/v1/local/hub/open": {"works": []},
        # the online Hub's catalog (10-24): listed signed in or not; a world this machine has stays the local one
        "/api/v1/local/hub/remote": {"base": "https://hub.example.test", "templates": [
            {"id": "last-train", "title": {"zh": "末班车"}, "pitch": {"zh": "p"}, "lang": "zh", "zone": "reviewed", "mode": {"ending": "multi"},
             "endings": ["E1", "E2"], "cast": [{"sid": "a", "name": "A", "img": "img/last-train/a.webp"}], "cover": {"src": "img/last-train/cover.webp"}},
            {"id": "pct-house", "title": {"zh": "灰橡宅(线上)"}, "pitch": {"zh": "p"}, "zone": "reviewed", "endings": [], "cast": []}]},
        "official:out": {"signed_in": False, "works": []},
        "official:in": {"signed_in": True, "works": [
            _remote("guixiang", "归乡"),
            _remote("wuwu", "乌乌", version="1.1", installed={"where": "official", "version": "1.0", "revision": 1}, update=True),
            _remote("pct-house", "灰橡宅", installed={"where": "builtin", "version": "0.2", "revision": None})]},
        "POST /api/v1/local/hub/official/fetch": [200, {"ok": True, "id": "guixiang", "message": "已获取,可以开始玩了。"}],
    }
    (tmp_path / "api.json").write_text(json.dumps(api, ensure_ascii=False), encoding="utf-8")
    out = subprocess.run([node, str(ROOT / "tests" / "hub_official.mjs"), str(tmp_path / "page.html"), str(tmp_path / "api.json"),
                          str(UI / "package.json"), lang, *([str(shots)] if shots else [])], capture_output=True, text=True, timeout=180, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_official_worlds_in_the_local_hub(tmp_path):
    shots = os.environ.get("HUB_OFFICIAL_SHOTS")
    r = _run(tmp_path, shots=shots)
    assert r["errs"] == []
    o = r["out"]
    assert sorted(o["cards"]) == ["last-train", "mine", "pct-house", "wuwu"], "signed out: this machine's worlds + the online Hub's"
    assert "登录后可获取更多官方世界" in o["more"] and o["moreBtn"]
    i = r["in"]
    assert "guixiang" in i["cards"] and not i["more"]
    assert "官方" in i["heads"]["guixiang"] and "有新版" in i["heads"]["wuwu"] and "官方" in i["heads"]["pct-house"]
    assert r["remote"] == ["⬇ 获取"], "a default-zone world not on this machine: get it (no report, no copy)"
    assert ["/api/v1/local/hub/official/fetch", {"id": "guixiang", "lang": "zh"}] in r["posts"] and r["afterGet"].endswith("#/t/guixiang")
    c = r["cached"]
    assert c[0].startswith("▶") and "⬆ 更新 到 v1.1" in c and not any("复制" in x for x in c) and not any("下载" in x for x in c)
    assert "只能玩" in r["cachedNote"]
    assert any("复制" in x for x in r["builtin"]), "the two shipped worlds keep 「复制一份来改」"
    h = r["hubOnly"]
    assert h["ctas"] == ["▶ 到 Hub 上玩 ↗"] and h["href"] == "https://hub.example.test/#/t/last-train", "an online-only world plays on the online Hub"


@pytest.mark.parametrize("lang,more,get", [("en", "Sign in to get more official worlds", "⬇ Get"), ("ja", "ログインすると公式の世界をもっと入手できます", "⬇ 入手"),
                                          ("ko", "로그인하면 공식 세계를 더 받을 수 있습니다", "⬇ 받기")])
def test_official_worlds_other_languages(tmp_path, lang, more, get):
    r = _run(tmp_path, lang=lang, shots=os.environ.get("HUB_OFFICIAL_SHOTS"))
    assert r["errs"] == [] and more in r["out"]["more"] and r["remote"] == [get]
