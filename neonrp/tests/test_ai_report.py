"""举报 AI 内容(App Store 1.2,10-21)—— core/ai_report:POST /api/v1/report/ai → 平台的举报收件箱(data records hub/ai-report,
platform-official 的形状);还没上线(404)→ 游玩反馈收件箱(一条 turn = 被举报的那段)。
本地先记一份;没登录 / 连不上 = 排队,下次补发;页面自己发了 → /done 从队列里拿掉(不发两次)。不连真平台。"""
from __future__ import annotations

import json
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

from _paths import PRODUCT_TEMPLATES
from neonrp.core import ai_report as R


@pytest.fixture(autouse=True)
def _dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NEONRP_REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.delenv("WORLDLINES_REPORT_URL", raising=False)
    monkeypatch.delenv("WORLDLINES_API_KEY", raising=False)


class Post:
    def __init__(self, status: int = 201, records: int | None = None):
        self.status, self.records, self.calls = status, records, []

    def __call__(self, url, body, headers):
        self.calls.append((url, body, headers))
        if url.endswith("/v1/records/hub/ai-report") and self.records is not None:
            return self.records, {}
        return self.status, {}


ALLOWED = {"kind", "reason", "surface", "client", "note", "excerpt", "run_id", "turn", "soul_id", "template_id", "template_version", "lang", "client_version",
           "guest", "msg_id", "report_id"}   # platform feat/ai-report b45c8d7


def _body(**kw):
    return {"reason": "sexual", "excerpt": "她靠近你,说了一句不该说的话。", "surface": "play", "turn": 3, "soul": "chara",
            "template": "pct-house", "run": "tpl-pct-house-abc", "client": {"mode": "browser", "locale": "zh-CN"}, **kw}


def test_a_report_goes_to_the_ai_report_inbox_in_its_shape():
    post = Post()
    out = R.submit(_body(note="太过了"), token="tok", post=post, lang="zh")
    assert out["ok"] and out["sent"] and not out["queued"] and out["message"].startswith("已举报")
    assert len(post.calls) == 1
    url, body, headers = post.calls[0]
    assert url == "https://data.worldlines.gg/v1/records/hub/ai-report" and headers["Authorization"] == "Bearer tok"
    b = body["body"]
    assert b == {"kind": "ai_message", "reason": "sexual", "surface": "play", "client": "web", "note": "太过了", "excerpt": "她靠近你,说了一句不该说的话。",
                 "run_id": "tpl-pct-house-abc", "turn": 3, "soul_id": "chara", "template_id": "pct-house", "lang": "zh-CN", "client_version": b["client_version"],
                 "report_id": out["id"]}
    assert set(b) <= ALLOWED, "only the inbox's fields (anything else is a 422)"
    log = [json.loads(x) for x in (Path(R._dir()) / "ai.jsonl").read_text(encoding="utf-8").splitlines()]
    assert log[-1]["id"] == out["id"] and log[-1]["sent"] and log[-1]["reason"] == "sexual"


def test_every_reason_and_the_message_id_go_as_they_are():
    for reason in R.REASONS:
        post = Post()
        R.submit(_body(reason=reason, note="她才十四岁", surface="phone", msg_id="m3", lang="ja"), token="tok", post=post, lang="ja")
        b = post.calls[0][1]["body"]
        assert b["reason"] == reason and b["note"] == "她才十四岁" and b["msg_id"] == "m3" and b["lang"] == "ja-JP" and b["surface"] == "phone"
        assert set(b) <= ALLOWED


def test_a_body_the_ai_inbox_refuses_still_reaches_the_feedback_inbox():
    post = Post(records=422)
    assert R.submit(_body(), token="tok", post=post)["sent"] and post.calls[-1][0].endswith("/v1/feedback/hub")


def test_until_that_inbox_is_up_it_goes_to_the_feedback_inbox():
    post = Post(records=404)
    out = R.submit(_body(note="太过了"), token="tok", post=post, lang="zh")
    assert out["sent"] and [c[0] for c in post.calls] == ["https://data.worldlines.gg/v1/records/hub/ai-report", "https://data.worldlines.gg/v1/feedback/hub"]
    body = post.calls[1][1]
    assert body["text"].startswith("[report:ai] reason=sexual surface=play soul=chara turn=3") and "太过了" in body["text"]
    assert body["template"] == {"id": "pct-house"} and body["save_id"] == "tpl-pct-house-abc" and body["engine_version"]
    assert body["turns"] == [{"n": 3, "input": "", "output": "", "beats": [{"kind": "dialogue", "speaker": "chara", "text": "她靠近你,说了一句不该说的话。"}], "options": []}]
    assert set(body) <= {"text", "template", "engine_version", "save_id", "client", "turns", "screenshot"}, "only the fields the inbox takes"
    assert set(body["client"]) <= {"mode", "version", "platform", "browser", "device", "locale"}


def test_not_signed_in_is_kept_and_sent_later_once():
    out = R.submit(_body(), token="", lang="en")
    assert out["ok"] and not out["sent"] and out["queued"] and out["why"] == "not_signed_in" and out["message"].startswith("Report saved")
    assert out["body"]["record"]["body"]["reason"] == "sexual" and out["body"]["feedback"]["text"].startswith("[report:ai]"), "the page may send it itself"
    post = Post()
    assert R.flush(token="tok", post=post) == 1 and len(post.calls) == 1
    assert R.flush(token="tok", post=post) == 0, "sent once"
    # the page sent one itself: off the queue
    other = R.submit(_body(reason="hate"), token="", lang="ja")
    assert other["message"].startswith("報告を保存")
    assert R.done(other["id"]) and R.flush(token="tok", post=post) == 0


def test_a_body_the_inbox_refuses_is_not_retried():
    out = R.submit(_body(), token="tok", post=Post(422))
    assert not out["sent"] and not out["queued"] and out["why"] == "rejected:422"


def test_bad_requests():
    with pytest.raises(ValueError, match="bad_reason"):
        R.build(_body(reason="boring"))
    with pytest.raises(ValueError, match="no_excerpt"):
        R.build(_body(excerpt="  "))
    built = R.build(_body(surface="phone", template="", run="", turn=None, msg_id="m-12", excerpt="x" * 5000))["body"]
    b = built["feedback"]
    assert b["template"]["id"] == "chat" and "save_id" not in b and len(b["turns"][0]["beats"][0]["text"]) == R.MAX_EXCERPT == 500
    assert "msg=m-12" in b["text"]
    r = built["record"]["body"]
    assert r["template_id"] == "chat" and r["msg_id"] == "m-12" and r["report_id"].startswith("ai-") and "turn" not in r and len(r["excerpt"]) == 500 and set(r) <= ALLOWED


def test_four_languages():
    for lang, head in {"zh": "已举报", "en": "Reported", "ja": "報告しました", "ko": "신고했어요"}.items():
        assert R.submit(_body(), token="t", post=Post(), lang=lang)["message"].startswith(head)
        t = R._T(lang)
        assert {"sent", "queued", "bad_reason", "no_excerpt"} <= set(t)


def test_http_route(tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    store = tmp_path / "store"
    shutil.copytree(PRODUCT_TEMPLATES / "pct-house.template", store / "pct-house.template")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(store))
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    post = Post()
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "studio"),
        patch("neonrp.commands.web.WebRuntime.gateway_start", lambda self: {"sid": "local", "root": self.root.name}),
        patch("neonrp.core.worldlines_auth.access_token", lambda: "tok"),
        patch.object(R, "_send", lambda pb, token, post=None: (post_call(pb), (True, ""))[1]),
    ):
        sent: list = []

        def post_call(pb):
            sent.append(pb)

        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def call(path, body):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return r.status, json.loads(r.read() or b"{}")
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read() or b"{}")
        try:
            st, out = call("/api/v1/report/ai", {"reason": "violence", "excerpt": "一段话", "surface": "phone", "soul": "vera", "lang": "ko"})
            assert st == 200 and out["sent"] and out["message"].startswith("신고")
            call("/api/v1/play/session", {"slug": "tpl--pct-house", "output_lang": "zh"})
            st, out = call("/api/v1/report/ai", {"reason": "other", "excerpt": "雾从巷口漫上来", "turn": 0})
            assert st == 200 and out["sent"] and out["message"].startswith("已举报")
            assert sent[-1]["record"]["body"]["template_id"] == "pct-house" and sent[-1]["record"]["body"]["run_id"], "the bound run fills in run + template"
            st, out = call("/api/v1/report/ai", {"reason": "nope", "excerpt": "x"})
            assert st == 400 and out["error"] == "bad_reason" and out["message"] == "请选一个举报理由。"
        finally:
            server.shutdown()
