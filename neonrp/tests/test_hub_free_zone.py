"""Hub 的自由区(10-16 · core/template_publish):hub.js 运行时拉公开列表进发现页;远端作品详情 =「下载到本地玩」+「举报」;
已经下载过的(同 id 的本机模板)并到本机那一项上、标自由区;「我的作品」按默认区 / 自由区分两栏,带状态和驳回 / 下架理由;
iOS(window.HUB.openZone === false)整个不拉、不显示。引擎接口全部是假的(tests/hub_free_zone.mjs)。

两个区两个地址(10-16):本地 /hub.html#/ ⇄ #/free/…;线上 / ⇄ /free/(同一份页面 + <base href="../">,tests/hub_free_web.mjs);
顶上的「默认区 ⇄ 自由区」开关跳到另一个地址,直达 / 刷新落在那一区;线上自由区作品(niko 10-26)主按钮 =「下载到本地玩」(本地是完整体验),
次按钮 =「在浏览器里玩」(弹窗:额度默认 + 自己的 key,play/?ref=hub/template/<id>);默认区(官方世界)不出世界包下载,也不出「在本地玩」
(只在浏览器里玩),弹窗里没有自己的 key(只用 Worldlines 额度)。"""
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


def _work(wid, title, *, zone="open", status="published", review=None, takedown=None, source=None):
    return {"id": wid, "ref": f"hub/template/{wid}", "title": title, "status": status, "zone": zone, "revision": 2, "published_revision": 2,
            "published_at": "2026-10-16T01:00:00Z", "review": review, "takedown": takedown, "source": source,
            "meta": {"source": source or wid, "version": "1.0", "lang": "zh", "langs": ["zh", "en", "ja", "ko"], "play_contract": "open-adventure@1",
                     "ending": "open", "title": {"zh": title, "en": title + " EN"}, "pitch": {"zh": "一句话"}, "cast": ["艾琳娜"], "cover": "cover.png"},
            "cover_url": f"/api/v1/local/hub/cover?id={wid}&rev=2"}


def _run(tmp_path, *, open_zone=True):
    node = shutil.which("node")
    if not node or not (UI / "node_modules" / "playwright").is_dir():
        pytest.skip("node + worldlines/ui/node_modules/playwright needed")
    page = (HUB / "index.html").read_text(encoding="utf-8").replace(
        "<!--SCRIPT-->", "<script>window.HUB={}</script><script>" + (HUB / "hub.js").read_text(encoding="utf-8") + "</script>")
    (tmp_path / "page.html").write_text(page, encoding="utf-8")
    api = {
        "/api/v1/local/templates": {"templates": [
            {"id": "mine-local", "card": {"title": "本机的世界", "pitch": "p", "lang": "zh"}, "mode": {"ending": "open"}, "zone": None},
            {"id": "official", "card": {"title": "官方世界", "pitch": "p", "lang": "zh"}, "mode": {"ending": "multi"}, "zone": "reviewed"}]},
        "/api/v1/local/hub/open": {"works": [_work("remote-abc123", "别人的作品"), _work("mine-local", "本机的世界")]},
        "/api/v1/local/hub/mine": {"works": [
            _work("w-pub-aaaaaa", "公开中的", source="a"),
            _work("w-down-bbbbbb", "被下架的", status="draft", takedown={"by": "admin", "reason": "侵权图"}),
            _work("w-rej-cccccc", "被驳回的", review={"state": "rejected", "note": "缺结局 CG"}),
            _work("w-def-dddddd", "默认区的", zone="reviewed")]},
        "POST /api/v1/local/hub/report": [401, {"error": "not_signed_in", "message": "还没登录 Worldlines 账号:先登录,再发布。"}],
        "POST /api/v1/local/hub/fetch": [200, {"ok": True, "id": "remote-abc123", "message": "已下载到本地"}],
        "POST /api/v1/local/hub/submit": [200, {"ok": True, "message": "已申请"}],
    }
    (tmp_path / "api.json").write_text(json.dumps(api, ensure_ascii=False), encoding="utf-8")
    out = subprocess.run([node, str(ROOT / "tests" / "hub_free_zone.mjs"), str(tmp_path / "page.html"), str(tmp_path / "api.json"),
                          str(UI / "package.json"), "1" if open_zone else "0"], capture_output=True, text=True, timeout=180, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_free_zone_in_the_local_hub(tmp_path):
    r = _run(tmp_path)
    assert r["errs"] == []
    assert sorted(r["openCards"]) == ["mine-local", "official", "remote-abc123"], "the free zone page: this machine's worlds + the platform's works"
    assert r["mineCards"] == ["official"], "this machine's own (bundled · made · kept) in its 「本机」 section; a downloaded free work is a free work"
    assert sorted(r["defaultCards"]) == sorted(r["openCards"]), "local: #/ is the free zone page too (no local default zone)"
    assert ["默认区 ↗", "https://neonrp.worldlines.gg/"] in r["defLinks"], "the default zone is the online Hub"
    rm = r["remote"]
    assert rm["ctas"] == ["⬇ 下载到本地玩", "举报", "屏蔽这个作者"] and "hub/template/remote-abc123" in rm["tag"]
    assert rm["cover"] == "/api/v1/local/hub/cover?id=remote-abc123&rev=2"
    assert "还没登录" in r["reportMsg"], "not signed in: the engine's sentence + a sign-in button"
    assert ["/api/v1/local/hub/report", {"id": "remote-abc123", "lang": "zh", "reason": "侵权"}] in r["posts"]
    assert ["/api/v1/local/hub/fetch", {"id": "remote-abc123", "lang": "zh"}] in r["posts"]
    assert r["localOpen"]["report"] and "自由区" in r["localOpen"]["note"]
    assert "⎘ 复制到我的工作台" in r["localOpen"]["ctas"] and "✎ 在这个模板上创作" in r["localOpen"]["ctas"], "the free zone keeps fork / create"
    assert {"⎘ 复制到我的工作台", "✎ 在这个模板上创作"} <= set(r["officialLocal"]), "this machine's worlds (本机) keep fork / create"
    w = {x["text"].split(" ")[0]: x for x in r["works"]}
    assert w["公开中的"]["chips"] == ["公开中"] and w["公开中的"]["unpub"] and w["公开中的"]["apply"]
    assert w["被下架的"]["chips"] == ["被下架"] and "侵权图" in w["被下架的"]["text"] and not w["被下架的"]["unpub"]
    assert w["被驳回的"]["chips"] == ["公开中", "被驳回"] and "缺结局 CG" in w["被驳回的"]["text"]
    # 默认区公开的就是通过审核的那一版(identity:curated 只有 approved 的才公开)→「已通过」;自由区的照旧「公开中」(web-create 10-18)
    assert w["默认区的"]["chips"] == ["已通过"] and not w["默认区的"]["apply"], "already in the default zone"
    assert ["/api/v1/local/hub/submit", {"id": "w-pub-aaaaaa", "lang": "zh"}] in r["posts"]


def test_ios_never_pulls_the_free_zone(tmp_path):
    r = _run(tmp_path, open_zone=False)
    assert r["errs"] == [] and not r["zoneBtn"]
    assert "/api/v1/local/hub/open" not in r["gets"]
    assert "remote-abc123" not in r["defaultCards"]


def _web(tmp_path, *, ios=False, shots=os.environ.get("WL_ZONE_KEY_SHOTS", "")):
    node = shutil.which("node")
    if not node or not (UI / "node_modules" / "playwright").is_dir():
        pytest.skip("node + worldlines/ui/node_modules/playwright needed")
    w = _work("w-free-abc123", "别人的作品")
    w.pop("cover_url")
    api = {
        "/catalog.json": {"templates": [{"id": "official", "title": {"zh": "官方世界"}, "pitch": {"zh": "p"}, "lang": "zh", "tags": {}, "endings": [],
                                         "cast": [], "zone": "reviewed", "download": {"src": "dl/official.template.zip", "bytes": 1000},
                                         "browser": {"ok": True, "bytes": 1000}}]},
        "/v1/public/resources": {"resources": [{**w, "status": "published"}]},
        "/v1/public/objects/hub/template/w-free-abc123/download-url": {"files": [{"path": "cover.png", "url": "https://s3.test/cover.png"}]},
    }
    (tmp_path / "web.json").write_text(json.dumps(api, ensure_ascii=False), encoding="utf-8")
    out = subprocess.run([node, str(ROOT / "tests" / "hub_free_web.mjs"), str(HUB / "index.html"), str(HUB / "hub.js"), str(tmp_path / "web.json"),
                          str(UI / "package.json"), *(["ios"] if ios else [])], capture_output=True, text=True, timeout=180, check=True,
                         env={**os.environ, **({"HUB_SHOTS": shots} if shots else {})})
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_two_addresses_on_the_web(tmp_path):
    r = _web(tmp_path)
    assert r["errs"] == []
    assert r["root"]["cards"] == ["official"] and r["root"]["toggle"] == [["默认区", "./#/", "on"], ["自由区", "free/#/", ""]]
    assert "下载世界包" not in " ".join(r["officialCtas"]), "the default zone gives no package download"
    assert "在本地玩" not in " ".join(r["officialCtas"]), "the default zone plays in the browser only"
    f = r["free"]
    assert f["url"] == "http://hub.test/free/#/" and f["cards"] == ["w-free-abc123"] and f["toggleOn"] == "自由区"
    assert f["hrefs"] == ["free/#/t/w-free-abc123"], "a free work's detail lives under /free/"
    d = r["freeDetail"]
    assert d["url"] == "http://hub.test/free/#/t/w-free-abc123" and d["cover"] == "https://s3.test/cover.png"
    assert [c[0] for c in d["ctas"]][:2] == ["⬇ 下载到本地玩", "▶ 在浏览器里玩"], "free zone: take it home first, the browser second"
    assert "p" in d["ctas"][0][2].split() and "p" not in d["ctas"][1][2].split(), "download-to-play-locally is the primary button"
    lo = r["freeLocalSheet"]["text"]
    assert "本地版是完整体验" in lo and "浏览器版之后再开" not in lo, "the local sheet no longer says the browser is unavailable"
    ws = r["freeWebSheet"]
    play = [h for _, h, _ in ws["links"] if h.startswith("play/?")]
    assert play and all(h.startswith("play/?ref=hub%2Ftemplate%2Fw-free-abc123&") for h in play), play
    own = [x for x in ws["links"] if x[0] == "用自己的 key(不扣额度)"]
    assert own and "own=1" in own[0][1] and "p" not in own[0][2].split(), "free zone: own key is offered, credits stay the default"
    assert "key 只存在这个浏览器里,只发给你填的地址" in ws["text"]
    os_ = r["officialSheet"]
    assert "自己的 key" not in os_["text"] and not any("own=1" in h for _, h, _ in os_["links"]), "default zone: credits only, no own key"
    assert any(h.startswith("play/?tpl=official&") for _, h, _ in os_["links"])
    assert r["back"]["url"] == "http://hub.test/#/" and r["back"]["cards"] == ["official"]


def test_local_free_zone_address(tmp_path):
    r = _run(tmp_path)
    assert r["landing"] == "#/free/", "hub.html opened without a hash lands in the free zone"
    assert sorted(r["openHrefs"]) == ["#/free/t/mine-local", "#/free/t/official", "#/free/t/remote-abc123"], "local: #/free/… is the free zone, details under it"
    assert r["toggle"] == [["https://neonrp.worldlines.gg/", ""], ["#/free/", "on"]]


def test_ios_web_has_no_free_zone(tmp_path):
    r = _web(tmp_path, ios=True)
    assert r["errs"] == [] and r["root"]["toggle"] == [] and r["root"]["cards"] == ["official"]
    # iOS 只显示默认区(c0b2b1fe 起会问默认区的社区作品):公开列表只许 zones=curated&client=ios,从不问自由区
    from urllib.parse import parse_qs, urlparse

    asked = [parse_qs(urlparse(x).query) for x in r["seen"] if x.startswith("/v1/public/resources")]
    assert asked and all(q.get("zones") == ["curated"] and q.get("client") == ["ios"] for q in asked), r["seen"]
    assert not any("open" in ",".join(q.get("zones", [])) for q in asked), "iOS never asks for the free zone"
