"""iOS 的创作台(web-create 10-21 · App Store 1.2 用户生成内容):iOS 打开的本地 Hub —— window.HUB = {openZone: false,
createSubmit, createArt, noPayLinks}。社区作品能举报(「已举报」)、能屏蔽作者(发现页不再出现 · 「我的」里能看到、取消)、
页上有联系方式;创作台存好以后提交到默认区(引擎里登录的账号,publish {zone: curated}),生图走引擎代理
/api/v1/local/ai/create/art,额度不足不给外部充值链接;手机一列、不横向溢出。另:引擎代理只放行生图那一个路径。"""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
HUB = ROOT / "worldlines" / "ui" / "app" / "hub"
UI = ROOT / "worldlines" / "ui"

FORM = {"schema": "worldlines.creation-form/1", "template": "stoneford-town", "open": True, "card": ["title", "pitch"],
        "sections": [{"key": "soul", "fields": [{"name": "name", "type": "text", "required": True}, {"name": "persona", "type": "longtext", "required": True}]}],
        "images": [{"for": "card", "name": "cover", "required": True}, {"for": "soul", "name": "portrait"}],
        "reveal": {"required": True, "template": {"zh": "钥匙一直在井里", "en": "The key was in the well all along"}}}


def _page(tmp_path: Path) -> Path:
    js = (HUB / "create-art.js").read_text(encoding="utf-8") + ";\n" + (HUB / "hub.js").read_text(encoding="utf-8")
    hub = '{"openZone":false,"createSubmit":true,"createArt":true,"noPayLinks":true,"app":true}'
    page = (HUB / "index.html").read_text(encoding="utf-8").replace("<!--SCRIPT-->", f"<script>window.HUB={hub}</script><script>{js}</script>")
    (tmp_path / "page.html").write_text(page, encoding="utf-8")
    return tmp_path / "page.html"


def _run(tmp_path: Path) -> dict:
    node = shutil.which("node")
    if not node or not (UI / "node_modules" / "playwright").is_dir():
        pytest.skip("node + worldlines/ui/node_modules/playwright needed")
    meta = {"title": {"zh": "雾港来信"}, "pitch": {"zh": "一封信"}, "lang": "zh", "cover": "cover.png", "source": "x-mine"}
    api = {
        "/api/v1/local/templates": {"templates": [{"id": "stoneford-town", "card": {"title": "石津镇", "pitch": "p", "lang": "zh"}, "mode": {"ending": "multi"},
                                                   "zone": "reviewed", "official": True, "creation": {"open": True}, "standalone": ["elena"]},
                                                  # 没开放创作的官方模板(pct-house 那样):没有创作入口,「新的创作」里也没有它
                                                  {"id": "pct-house", "card": {"title": "灰橡宅", "pitch": "p", "lang": "zh"}, "mode": {"ending": "multi"},
                                                   "zone": "reviewed", "official": True, "creation": {"open": False}},
                                                  # 获取下来玩的社区作品(别人的):能开局,不能拿来创作
                                                  {"id": "comm-fog-bbbbbb", "card": {"title": "雾夜猎人", "pitch": "p", "lang": "zh"}, "mode": {"ending": "multi"},
                                                   "zone": "reviewed", "hub_ref": "hub/template/comm-fog-bbbbbb", "creation": {"open": True}}]},
        "/api/v1/local/templates/stoneford-town/creation": FORM,
        # 角色名四种写法(ios4 10-23:外语界面下角色页也是中文名)· standalone 让它在「角色」页默认就列出来
        "/api/v1/local/templates/stoneford-town/assets": {"slots": [{"slot": "soul.portrait:elena", "cls": "soul", "name": "portrait", "label": "艾琳娜", "have": False}],
                                                          "names": {"elena": {"zh": "艾琳娜", "en": "Elena Vale", "ja": "エレナ・ヴェイル"}}},   # 没有韩文:退英文
        "/api/v1/local/templates/comm-fog-bbbbbb/creation": {**FORM, "template": "comm-fog-bbbbbb"},
        "/api/v1/local/account": {"signed_in": True},
        "/api/v1/local/hub/official": {"signed_in": True, "works": [
            {"id": "comm-fog-aaaaaa", "ref": "hub/template/comm-fog-aaaaaa", "status": "published", "zone": "reviewed", "official": False, "meta": meta}]},
        "/api/v1/local/templates/stoneford-town-mine/publish": {"checks": {"ok": True, "problems": []}, "signed_in": True},
        "/api/v1/local/ai/create/art": {"allowance": {"cover": {"left": 0}, "world": {"left": 0}}, "free_daily": {"max": 0, "used": 0}, "plan": {"images_left": 0},
                                        "kinds": {"cover": {"credits": 120}, "avatar": {"credits": 90}}},
        "POST /api/v1/local/hub/report": [200, {"ok": True, "message": "收到举报"}],
        "POST /api/v1/local/hub/block": [201, {"ok": True, "created": True}],
        "POST /api/v1/local/hub/unblock": [200, {"ok": True, "unblocked": True}],
        "POST /api/v1/local/templates/stoneford-town/creation/check": [200, {"ok": True, "problems": []}],
        "POST /api/v1/local/templates/stoneford-town/creation/work": [200, {"ok": True, "id": "stoneford-town-mine", "plot": "plots/mine",
                                                                            "slots": [{"slot": "card:cover", "name": "cover", "need": True, "have": True, "row": {"sec": "card", "i": 0}}]}],
        "POST /api/v1/local/ai/create/art": [402, {"error": {"code": "insufficient_credits", "billing_url": "https://billing.worldlines.gg/subscribe"}}],
        "POST /api/v1/local/templates/stoneford-town-mine/publish": [200, {"zone": "reviewed", "status": "draft", "message": "已提交到默认区审核"}],
    }
    (tmp_path / "api.json").write_text(json.dumps(api, ensure_ascii=False), encoding="utf-8")
    shots = tmp_path / "shots"
    shots.mkdir()
    out = subprocess.run([shutil.which("node"), str(ROOT / "tests" / "hub_ios_create.mjs"), str(_page(tmp_path)), str(tmp_path / "api.json"),
                          str(UI / "package.json"), str(shots)], capture_output=True, text=True, timeout=240, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_ios_creation_desk_and_ugc(tmp_path):
    r = _run(tmp_path)
    assert r["errs"] == []
    h = r["cardHint"]   # lead 10-23: the Korean hint said 「中文(는) 꼭 써야 합니다」
    assert "Chinese is required" in h["en"] and "中国語 は必須" in h["ja"] and "중국어는 꼭 써야" in h["ko"] and not any("中文" in v for v in h.values()), h
    assert "举报" in " ".join(r["detailCtas"]) and "屏蔽这个作者" in " ".join(r["detailCtas"])
    assert "rights@worldlines.gg" in r["reportSheet"], "the report sheet carries a contact"
    assert ["/api/v1/local/hub/report", {"id": "comm-fog-aaaaaa", "lang": "zh", "reason": "盗用了别人的角色"}] in r["posts"]
    assert "已举报" in r["afterReport"]
    assert "comm-fog-aaaaaa" not in r["findAfterBlock"] and r["afterBlockUrl"].endswith("#/")
    assert "雾港来信" in r["meBlocked"] and "取消屏蔽" in r["meBlocked"]
    assert "comm-fog-aaaaaa" in r["findAfterUnblock"]
    assert ["/api/v1/local/hub/block", {"id": "comm-fog-aaaaaa", "lang": "zh"}] in r["posts"], "blocked on the account too (identity block-owner)"
    assert ["/api/v1/local/hub/unblock", {"id": "comm-fog-aaaaaa", "lang": "zh"}] in r["posts"]
    assert r["cardFirst"] == "石津镇", "niko 10-23: the desk opens with the template's card filled in, not empty"
    assert r["revealFirst"] == "钥匙一直在井里", "and with the template's own truth"
    assert r["rowDir"] == "column" and r["overflow"] <= 0, "one column on the phone, no sideways scroll"
    assert r["artBtn"] and "积分不够" in r["artErr"]["text"] and r["artErr"]["links"] == 0, "iOS: no outside payment link"
    assert any(g.startswith("/api/v1/local/ai/create/art?") for g in r["gets"]), "the picture service goes through the engine"
    assert "rights@worldlines.gg" in r["submitSheet"] and "创作者协议" in r["submitSheet"]
    assert ["/api/v1/local/templates/stoneford-town-mine/publish", {"zone": "curated", "lang": "zh"}] in r["posts"]
    assert "已提交到默认区审核" in r["submitted"]
    assert "▶ 开局" in r["officialCtas"] and "✎ 在这个模板上创作" in r["officialCtas"], "the app says 开局, not 在浏览器里玩"
    assert "▶ 开局" in r["gotCtas"] and "✎ 在这个模板上创作" not in r["gotCtas"] and "举报" in " ".join(r["gotCtas"]), "someone else's work is played, not built on"
    assert "没有开放给创作者" in r["gotCreate"] and not r["gotForm"], "and the desk itself stays shut on it"
    assert "✎ 在这个模板上创作" not in r["closedCtas"], "a template not open to creators has no desk entry"
    # niko 10-23 真机:进了「我的」以后开不了新的创作 → 「我的作品」里有「新的创作」(开放创作的官方模板)和本机存了没提交的那份
    assert r["meNew"] == "✎ 新的创作" and r["meDrafts"] == ["#/t/stoneford-town/create"], "the saved, unsubmitted work is one tap away"
    # 这个模板已经有一份了:「新的创作」另起一份(<模板>-mine-<6 位>),打开是新的(卡面是模板的,不是上一份的),存的时候带上新 id
    import re
    assert len(r["meNewList"]) == 1 and re.fullmatch(r"#/t/stoneford-town/create\?w=stoneford-town-mine-[0-9a-f]{6}", r["meNewList"][0]), r["meNewList"]
    assert r["fromMe"] == 1 and r["secondCard"] == "石津镇", "a second work starts fresh, not from the first one's draft"
    assert any(p == "/api/v1/local/templates/stoneford-town/creation/work" and re.fullmatch(r"stoneford-town-mine-[0-9a-f]{6}", b.get("id") or "") for p, b in r["posts"]), "saved under its own id"
    assert r["firstAgain"] == "雾夜猎人", "and the first work's draft is still there"
    # 角色列表 · 详情跟界面语言走;缺那种语言退英文,不是中文(lead 10-23)
    assert r["souls"] == {"zh": [["艾琳娜"], "艾琳娜"], "en": [["Elena Vale"], "Elena Vale"], "ja": [["エレナ・ヴェイル"], "エレナ・ヴェイル"],
                          "ko": [["Elena Vale"], "Elena Vale"]}, r["souls"]


class _AI(BaseHTTPRequestHandler):
    seen: list = []

    def log_message(self, *a):
        pass

    def _do(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        _AI.seen.append((self.command, self.path, self.headers.get("Authorization"), body))
        out = json.dumps({"ok": True, "path": self.path}).encode()
        self.send_response(201 if self.command == "POST" else 200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    do_GET = do_POST = _do


def test_engine_ai_proxy_only_the_picture_service(tmp_path, monkeypatch):
    from neonrp.commands.web import make_server
    from neonrp.core import worldlines_auth

    ai = ThreadingHTTPServer(("127.0.0.1", 0), _AI)
    threading.Thread(target=ai.serve_forever, daemon=True).start()
    monkeypatch.setattr(worldlines_auth, "API_BASE", f"http://127.0.0.1:{ai.server_address[1]}/v1")
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "w"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "p"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "s"),
    ):
        srv = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"

        def call(method, path, body=None):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, method=method,
                                         headers={"Content-Type": "application/json", "Authorization": "Bearer page-token"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return r.status, json.loads(r.read() or b"{}")
            except urllib.error.HTTPError as e:
                raw = e.read() or b"{}"
                return e.code, (json.loads(raw) if raw[:1] == b"{" else {})
        try:
            monkeypatch.setenv("WORLDLINES_API_KEY", "-")
            st, b = call("GET", "/api/v1/local/ai/create/art?work_ref=hub/template/x")
            assert st == 401 and b["error"]["code"] == "not_signed_in"
            monkeypatch.setenv("WORLDLINES_API_KEY", "engine-session")
            st, b = call("GET", "/api/v1/local/ai/create/art?work_ref=hub/template/x")
            assert st == 200 and b["path"] == "/v1/create/art?work_ref=hub/template/x"
            st, b = call("POST", "/api/v1/local/ai/create/art", {"kind": "cover"})
            assert st == 201
            assert [(m, a) for m, _, a, _ in _AI.seen] == [("GET", "Bearer engine-session"), ("POST", "Bearer engine-session")], "the engine's session, never the page's"
            assert json.loads(_AI.seen[-1][3]) == {"kind": "cover"}
            st, b = call("POST", "/api/v1/local/ai/create/art", {"description": "x" * 20000})
            assert st == 413 and len(_AI.seen) == 2
            req = urllib.request.Request(base + "/api/v1/local/ai/create/art", data=b"{}", method="POST",
                                         headers={"Content-Type": "application/json", "Origin": "https://evil.example"})
            with pytest.raises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(req, timeout=30)
            assert e.value.code == 403 and len(_AI.seen) == 2, "another site cannot spend the player's credits"
            st, _ = call("POST", "/api/v1/local/ai/chat/completions", {"x": 1})
            assert st != 200 and len(_AI.seen) == 2, "not a general proxy"
        finally:
            srv.shutdown()
            ai.shutdown()
