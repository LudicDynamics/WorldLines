"""Hub 创作台「用 AI 填其他语言」e2e(niko 10-25):真引擎(进程内,模型换成假的)+ Hub 页面(index.html + truthquiz.js + hub.js),
一条走完 只写中文 → 点按钮补其他语言(手写的日文标题不动、真相三问补空着的语言)→ 改中文标题 → 存之前自动重写过时的格 →
模型不可用时照原样存。存下来的作品 i18n/<lang>/template.json 里是补好的卡面。
截图:HUB_FILL_SHOTS=<目录>(默认 tmp)。端口 HUB_FILL_PORT(默认 8824;被占就跳过,不打别人的服务)。"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from neonrp.core.billing_stop import BillingStop
from neonrp.template import creation_quiz as CQ, creation_translate as CT
from test_creation_truth_quiz import QS, _Model

ROOT = Path(__file__).resolve().parents[1]
UI, HUB = ROOT / "worldlines" / "ui", ROOT / "worldlines" / "ui" / "app" / "hub"
PORT = int(os.environ.get("HUB_FILL_PORT", "8824"))
BROKE = BillingStop(code="insufficient_credits", billing_url="https://billing.worldlines.gg/topup?product=hub")


def _free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


class Echo:
    """Translate: every asked slot as ``[<lang>] <the first source text>``. Write: ``AI·<field>`` for an empty box,
    ``AI·改写·<text>`` for one with text; a box saying NOCREDIT = the platform refuses for money."""

    def __init__(self):
        self.calls, self.writes = [], []

    def generate(self, system, user, tools=None):
        items = [json.loads(x) for x in user.splitlines() if x.startswith('{"key"')]
        if items and "field" in items[0]:
            self.writes.append(items)
            if any("NOCREDIT" in x["now"] for x in items):
                return SimpleNamespace(error=BROKE.error_text(), raw_output="")
            return SimpleNamespace(error=None, raw_output=json.dumps(
                {x["key"]: f"AI·改写·{x['now']}" if x["now"] else f"AI·{x['field']}" for x in items}, ensure_ascii=False))
        self.calls.append(items)
        return SimpleNamespace(error=None, raw_output=json.dumps(
            {x["key"]: {lg: f"[{lg}] {next(iter(x['from'].values()))}" for lg in x["to"]} for x in items}, ensure_ascii=False))


def test_desk_fills_the_other_languages(tmp_path, monkeypatch):
    node = shutil.which("node")
    if not node or not (UI / "node_modules" / "playwright").is_dir():
        pytest.skip("node + worldlines/ui/node_modules/playwright needed")
    if not _free(PORT):
        pytest.skip(f"port {PORT} is taken — not running against someone else's server")
    ro, mine = tmp_path / "official", tmp_path / "mine"
    shutil.copytree(ROOT / "worldlines" / "templates" / "guixiang.template", ro / "guixiang.template", ignore=shutil.ignore_patterns("__pycache__"))
    mine.mkdir()
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", f"{mine}{os.pathsep}{ro}")
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(mine))
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    browsers = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or str(Path.home() / "Library" / "Caches" / "ms-playwright")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    model = Echo()

    def adapter():
        return model

    real = CT.translate

    def translate(t, fields, targets, **kw):
        if any("NOMODEL" in s for v in (fields or {}).values() for s in v.values()):
            raise CT.TranslateError("no_model")
        return real(t, fields, targets, **kw)

    monkeypatch.setattr(CT, "_adapter", adapter)
    monkeypatch.setattr(CQ, "_adapter", lambda: _Model(json.dumps({"questions": QS}, ensure_ascii=False)))
    monkeypatch.setattr(CT, "translate", translate)
    page = (HUB / "index.html").read_text(encoding="utf-8").replace(
        "<!--SCRIPT-->", "<script>window.HUB={\"mode\":\"auto\"}</script><script>" + (HUB / "truthquiz.js").read_text(encoding="utf-8")
        + "\n" + (HUB / "hub.js").read_text(encoding="utf-8") + "</script>")
    (tmp_path / "page.html").write_text(page, encoding="utf-8")
    shots = Path(os.environ.get("HUB_FILL_SHOTS") or tmp_path / "shots")
    from neonrp.commands.web import make_server

    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "lib" / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "lib" / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "lib" / "studio"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", PORT)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            res = subprocess.run([node, str(ROOT / "tests" / "hub_create_autofill.mjs"), f"http://127.0.0.1:{PORT}", str(tmp_path / "page.html"),
                                  str(UI / "package.json"), str(shots)], capture_output=True, text=True, timeout=700,
                                 env={**os.environ, "PLAYWRIGHT_BROWSERS_PATH": browsers})
        finally:
            server.shutdown()
            server.server_close()
    assert res.returncode == 0, res.stderr[-2000:]
    r = json.loads(res.stdout.strip().splitlines()[-1])
    assert r["errs"] == [], r
    assert "额度" not in r["fillNote"] and "积分" not in r["fillNote"], "no cost next to the button (niko 10-25)"
    # the button: everything not hand-written, from what the author wrote; the hand-written ja title stays
    first = {x["key"]: x for x in model.calls[0]}
    assert first["card.title"]["from"] == {"zh": "井里的钥匙", "ja": "井戸の鍵"} and first["card.title"]["to"] == ["en", "ko"], first
    assert first["card.pitch"]["to"] == ["en", "ja", "ko"]
    assert first["tq.0.q"]["from"] == {k: QS[0]["q"][k] for k in ("zh", "en", "ja")} and first["tq.0.q"]["to"] == ["ko"], "the quiz: only its empty language"
    assert not any(k.startswith("tq.") and k != "tq.0.q" for k in first), "the rest of the quiz is written in all four"
    f = r["filled"]
    assert f["en.title"] == "[en] 井里的钥匙" and f["ko.title"] == "[ko] 井里的钥匙" and f["ja.title"] == "井戸の鍵", f
    assert f["ja.pitch"] == "[ja] 冬至夜,祠堂的钥匙不见了。"
    assert r["tqKo"] == f"[ko] {QS[0]['q']['zh']}"
    assert re.search(r"已填好 \d+ 处", r["fillMsg"]), r["fillMsg"]
    marks = dict(r["marks"])
    assert marks["zh.title"] == "hand" and marks["ja.title"] == "hand" and marks["en.title"] == "ai", marks
    # 「存」: only the slots gone stale (the zh title changed) are rewritten first; the hand-written ja one is not
    assert len(model.calls) == 2, len(model.calls)
    second = {x["key"]: x for x in model.calls[1]}
    assert set(second) == {"card.title"} and second["card.title"]["to"] == ["en", "ko"], second
    assert r["saved"]["en.title"] == "[en] 井里的第二把钥匙" and r["saved"]["ja.title"] == "井戸の鍵"
    assert "没存成" not in r["save"], r["save"]
    w = next(mine.glob("guixiang-mine*"), None)
    assert w, (r["save"], r["save2"])
    en = json.loads((w / "i18n" / "en" / "template.json").read_text(encoding="utf-8"))["card"]
    assert en["title"] == "[en] 井里的第二把钥匙" and en["pitch"] == "[en] 冬至夜,祠堂的钥匙不见了。"
    plot = json.loads((w / "plots" / "mine" / "plot.json").read_text(encoding="utf-8"))
    assert plot["truth_quiz"]["questions"][0]["q"]["ko"] == f"[ko] {QS[0]['q']['zh']}"
    ja = json.loads((w / "i18n" / "ja" / "template.json").read_text(encoding="utf-8"))["card"]
    assert ja["title"] == "井戸の鍵"
    # no model: 「存」 goes on, says so; the other languages keep what they had
    assert "没存成" not in r["save2"] and "没有可用的模型" in r["save2FillMsg"] and "照原样存" in r["save2FillMsg"], r
    assert r["after2"]["en.pitch"] == "[en] 冬至夜,祠堂的钥匙不见了。"
    zh = json.loads((w / "template.json").read_text(encoding="utf-8"))["card"]
    assert zh["pitch"] == "NOMODEL 冬至夜。"
    # 「AI 填空着的栏」: one call, only the empty boxes; the hand-written ending title stays
    w1 = {x["key"]: x for x in model.writes[0]}
    assert set(w1) == {"ending.0.text", "clue.0.name", "clue.0.summary"}, "a blank rule row needs its trigger first: not started for the author"
    assert all(x["now"] == "" for x in w1.values())
    assert r["endText"] == "AI·ending.text" and r["clue"] == "AI·clue.summary" and r["endTitle"] == "开祠堂"
    assert "AI 写好了 3 栏" in r["aiMsg"] and r["aiMarks"] >= 3, r
    # one box's ✦ over the author's text: asked first, then rewritten from it
    assert r["endTitle2"] == "AI·改写·开祠堂" and any("改写这一栏" in d for d in r["dialogs"]), r["dialogs"]
    assert model.writes[1] == [{"key": "ending.0.title", "field": "ending.title", "row": 0, "now": "开祠堂", "lang": "zh"}]
    assert "没存成" not in r["save3"], r["save3"]
    plot = json.loads((w / "plots" / "mine" / "plot.json").read_text(encoding="utf-8"))
    assert "AI·clue.summary" in json.dumps(plot, ensure_ascii=False) and "_ai" not in json.dumps(plot), "AI's text is saved; its marks are not"
    # not enough credits: said, with the top-up; the box keeps the author's text
    assert "额度不够了" in r["broke"] and r["brokeHref"] == BROKE.billing_url and r["revealAfter"] == "NOCREDIT 族长藏了钥匙。", r
    # iOS: the in-app plans page, never an outside payment link
    assert r["iosLinks"] == 0 and r["iosPlans"] == 1, r
