"""创作台各栏的 AI(niko 10-25「所有提示词请都能自动填写」):空栏按表单已有的和世界写草稿,有字的栏改写 / 补全。
只写表单开放的文字栏(id / 选项 / 触发不是文字);一次写多栏;不写盘。平台因为额度拒绝 = credits(带 billing,桌面引导充值),
不是「再试一次」。假模型回放固定输出,不真调 LLM。"""
from __future__ import annotations

import json
import os
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from neonrp import template as TP
from neonrp.core.billing_stop import BillingStop
from neonrp.template import creation_translate as CT, creation_write as CW

TPLS = Path(__file__).resolve().parents[1] / "worldlines" / "templates"
BROKE = BillingStop(code="insufficient_credits", billing_url="https://billing.worldlines.gg/topup?product=hub")


class Replay:
    def __init__(self, reply=None, error=None, raises=None):
        self.reply = reply if isinstance(reply, str) or reply is None else json.dumps(reply, ensure_ascii=False)
        self.error, self.raises, self.asked = error, raises, []

    def generate(self, system, user, tools=None):
        self.asked.append((system, user))
        if self.raises:
            raise self.raises
        return SimpleNamespace(raw_output=self.reply or "", error=self.error)


@pytest.fixture
def desk(tmp_path, monkeypatch):
    ro, mine = tmp_path / "official", tmp_path / "mine"
    for n in ("guixiang", "stoneford-town"):
        shutil.copytree(TPLS / f"{n}.template", ro / f"{n}.template", ignore=shutil.ignore_patterns("__pycache__"))
    mine.mkdir()
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", f"{mine}{os.pathsep}{ro}")
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(mine))
    return mine


def _t(tid):
    return TP.load(TP.discover()[tid])


def test_the_writable_boxes_are_the_forms_text(desk):
    w = CW.writable(_t("stoneford-town"))
    assert w["soul"] == {"name", "persona", "appearance"}, "collect_flag is a flag key, not prose; enums / ids are not text"
    assert w["plot"] == {"title", "stages", "prompt"} and w["clue"] == {"name", "summary"} and w["ending"] == {"title", "text"}
    assert w["rule"] == {"doc"}, "the trigger is 「用一句话说」's"
    assert w["card"] == {"title", "pitch"} and "reveal" not in w, "no reveal box where the form asks none"
    gx = CW.writable(_t("guixiang"))
    assert "soul" not in gx and gx["reveal"] == {"reveal"}, "only what the template opens"


def test_norm_reads_what_each_box_says_now(desk):
    add = {"ending": [{"title": "雾散"}, {"title": "", "text": "门开了。"}], "reveal": "族长藏了钥匙", "plot": [{"stages": ["进村", "开祠堂"]}]}
    got = CW.norm(_t("stoneford-town"), add, {"zh": {"title": "雾夜"}}, [
        {"key": "ending.1.text", "sec": "ending", "name": "text", "i": 1}, {"key": "ending.0.text", "sec": "ending", "name": "text", "i": 0},
        {"key": "reveal", "sec": "reveal", "name": "reveal"}, {"key": "card.zh.title", "sec": "card", "name": "title"},
        {"key": "plot.0.stages", "sec": "plot", "name": "stages"}, {"key": "x", "sec": "ending", "name": "kind"},
        {"key": "y", "sec": "soul", "name": "collect_flag"}, {"key": "ending.1.text", "sec": "ending", "name": "text", "i": 1}], "zh")
    assert got == [{"key": "ending.1.text", "field": "ending.text", "row": 1, "now": "门开了。", "lang": "zh"},
                   {"key": "ending.0.text", "field": "ending.text", "row": 0, "now": "", "lang": "zh"},
                   {"key": "card.zh.title", "field": "card.title", "now": "雾夜", "lang": "zh"},
                   {"key": "plot.0.stages", "field": "plot.stages", "row": 0, "now": "进村、开祠堂", "lang": "zh"}]
    en = CW.norm(_t("stoneford-town"), add, {}, [{"key": "card.en.title", "sec": "card", "name": "title"}, {"key": "reveal", "sec": "soul", "name": "persona"}], "en")
    assert [x["lang"] for x in en] == ["en", "zh"], "the card box in the desk language; a plot box in the work's language"
    with pytest.raises(CT.TranslateError) as e:
        CW.norm(_t("stoneford-town"), [], None, [], "zh")
    assert e.value.code == "bad_body"


def test_write_drafts_and_rewrites_in_one_call(desk):
    m = Replay("好:" + json.dumps({"soul.0.persona": "镇上的守夜人,话少,只信自己的灯。", "ending.0.text": "雾散了,灯还亮着。", "extra": "x"}, ensure_ascii=False))
    add = {"soul": [{"name": "阿白", "persona": "守夜人"}], "ending": [{"title": "灯不灭", "kind": "true"}]}
    res = CW.write(_t("stoneford-town"), add, [{"key": "soul.0.persona", "sec": "soul", "name": "persona"},
                                               {"key": "ending.0.text", "sec": "ending", "name": "text"},
                                               {"key": "rule.0.doc", "sec": "rule", "name": "doc"}], lang="zh", adapter=m)
    assert res == {"ok": True, "fields": {"soul.0.persona": "镇上的守夜人,话少,只信自己的灯。", "ending.0.text": "雾散了,灯还亮着。"},
                   "missing": ["rule.0.doc"]}
    system, user = m.asked[0]
    assert "空的" in system and "改写" in system and "不提 AI" in system
    assert '"now": "守夜人"' in user and '"now": ""' in user, "a box with text is rewritten, an empty one drafted"
    assert "阿白" in user and "灯不灭" in user, "what the form already says"
    assert "角色设定" in user and "结局" in user and "外貌" not in user, "the guide: only the asked boxes"
    world = json.loads(user.split("\n")[1])
    assert world["places"] and world["characters"] and world["title"], "the world's own names and card"


def test_nothing_writable_asks_no_model(desk):
    m = Replay("{}")
    assert CW.write(_t("guixiang"), {}, [{"key": "a", "sec": "soul", "name": "persona"}], adapter=m) == {"ok": True, "fields": {}, "missing": []}
    assert m.asked == []


def test_a_money_refusal_is_credits_not_a_retry(desk):
    t, box = _t("guixiang"), [{"key": "reveal", "sec": "reveal", "name": "reveal"}]
    for m in (Replay(error=BROKE.error_text()), Replay(raises=RuntimeError(BROKE.error_text()))):
        with pytest.raises(CT.TranslateError) as e:
            CW.write(t, {}, box, adapter=m)
        assert e.value.code == "credits" and e.value.extra["billing"]["billing_url"] == BROKE.billing_url
    with pytest.raises(CT.TranslateError) as e:
        CW.write(t, {}, box, adapter=Replay(error=BillingStop(code="guest_not_allowed", kind="guest").error_text()))
    assert e.value.code == "sign_in"
    with pytest.raises(CT.TranslateError) as e:   # the translator shares the call
        CT.translate(t, {"a": {"zh": "字"}}, {"a": ["en"]}, adapter=Replay(error=BROKE.error_text()))
    assert e.value.code == "credits"
    with pytest.raises(CT.TranslateError) as e:
        CW.write(t, {}, box, adapter=Replay("not json"))
    assert e.value.code == "model"


def test_every_language_has_the_prompt():
    from neonrp import prompts

    zh = prompts.strings("creation_write", "zh")
    for lg in prompts.LANGS:
        S = prompts.strings("creation_write", lg)
        assert set(S) == {"system", "user", "fields"} and set(S["fields"]) == set(zh["fields"])
        assert '{"<key>": "…"}' in S["user"].format(world="w", draft="d", guide="g", items="i")


def test_write_route(desk, tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    m = Replay({"reveal": "族长藏了钥匙。"})
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "lib" / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "lib" / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "lib" / "studio"),
        patch("neonrp.template.creation_translate._adapter", return_value=m),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def call(path, b):
            req = urllib.request.Request(base + path, data=json.dumps(b).encode(), method="POST", headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return r.status, json.loads(r.read() or b"{}")
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read() or b"{}")
        try:
            path, box = "/api/v1/local/templates/guixiang/creation/write", [{"key": "reveal", "sec": "reveal", "name": "reveal"}]
            st, b = call(path, {"addition": {}, "targets": box, "lang": "zh"})
            assert st == 200 and b == {"ok": True, "fields": {"reveal": "族长藏了钥匙。"}, "missing": []}, b
            assert not list(desk.iterdir()), "write never writes to disk"
            m.reply, m.error = "", BROKE.error_text()
            st, b = call(path, {"addition": {}, "targets": box})
            assert st == 402 and b["error"] == "credits" and b["billing"]["billing_url"] == BROKE.billing_url, b
            st, b = call(path, {"addition": [], "targets": box})
            assert st == 400 and b["error"] == "bad_body"
        finally:
            server.shutdown()
