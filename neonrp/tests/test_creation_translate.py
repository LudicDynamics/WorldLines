"""创作台「用 AI 填其他语言」(niko 10-25):作者只用一种语言写卡面 / 真相三问,其余语言由引擎里的 agent 写。
桌面决定哪些格是目标(作者手写的格不送);引擎带上模板各语言的卡面和名词表(本地化层可能整个换名字,名字查表不音译),
只回要的那几格;没模型 / 模型乱答是错误码,不是崩溃。假模型回放固定输出,不真调 LLM。"""
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
from neonrp.template import creation_translate as CT

REAL_ADAPTER = CT._adapter   # conftest makes the desk's translate model-less by default; this test checks the real lookup

TPLS = Path(__file__).resolve().parents[1] / "worldlines" / "templates"


class Replay:
    def __init__(self, reply):
        self.reply, self.asked = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False), []

    def generate(self, system, user, tools=None):
        self.asked.append((system, user))
        return SimpleNamespace(raw_output=self.reply, error=None)


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


def test_norm_keeps_only_what_has_a_source_and_is_not_written():
    src, want = CT.norm({"card.title": {"zh": " 井里的钥匙 ", "en": ""}, "card.pitch": {"zh": "  "}, "x": "not an object"},
                        {"card.title": ["en", "ja", "zh", "fr"], "card.pitch": ["en"], "x": ["en"], "ghost": ["en"]})
    assert src == {"card.title": {"zh": "井里的钥匙"}}
    assert want == {"card.title": ["en", "ja"]}, "the written language is not a target, nor an unknown one; no source = no target"
    with pytest.raises(CT.TranslateError) as e:
        CT.norm([], {})
    assert e.value.code == "bad_body"
    with pytest.raises(CT.TranslateError) as e:
        CT.norm({"a": {"zh": "字" * (CT.MAX_CHARS + 1)}}, {"a": ["en"]})
    assert e.value.code == "too_long"


def test_translate_writes_only_the_asked_slots_with_the_world_in_view(desk):
    m = Replay("好的:\n" + json.dumps({"card.title": {"en": "The Key in the Well", "ja": "井戸の鍵", "zh": "改掉作者的", "ko": ""},
                                       "card.pitch": {"en": "Rowley, the night before the solstice."},
                                       "tq.0.q": {"ko": "누가 열쇠를 숨겼나?"}, "extra": {"en": "x"}}, ensure_ascii=False))
    res = CT.translate(_t("guixiang"), {"card.title": {"zh": "井里的钥匙"}, "card.pitch": {"zh": "冬至前夜,罗屋村。"}, "tq.0.q": {"zh": "谁藏了钥匙?"}},
                       {"card.title": ["en", "ja", "ko"], "card.pitch": ["en"], "tq.0.q": ["ko"]}, lang="zh", adapter=m)
    assert res["fields"] == {"card.title": {"en": "The Key in the Well", "ja": "井戸の鍵"}, "card.pitch": {"en": "Rowley, the night before the solstice."},
                             "tq.0.q": {"ko": "누가 열쇠를 숨겼나?"}}, "never the author's own language, never a key not asked for"
    assert res["ok"] and res["missing"] == [["card.title", "ko"]]
    system, user = m.asked[0]
    assert "名词表" in system and "不加注释" in system, "the desk's language decides the prompt's"
    assert "黒沢集落" in user and "Rowley" in user and "罗屋村" in user, "the glossary: each language's own name for a place"
    assert "冬至前夜" in user, "the template's card per language (its setting and tone)"
    assert '{"key": "card.title", "from": {"zh": "井里的钥匙"}, "to": ["en", "ja", "ko"]}' in user


def test_nothing_to_write_asks_no_model(desk):
    m = Replay("{}")
    assert CT.translate(_t("guixiang"), {"card.title": {"zh": "a", "en": "b"}}, {"card.title": ["en"]}, adapter=m) == {"ok": True, "fields": {}, "missing": []}
    assert m.asked == []


def test_a_model_out_of_shape_or_missing_is_an_error(desk, monkeypatch):
    t = _t("stoneford-town")
    job = ({"card.title": {"en": "Stoneford"}}, {"card.title": ["zh"]})
    with pytest.raises(CT.TranslateError) as e:
        CT.translate(t, *job, adapter=Replay("sorry, I cannot"))
    assert e.value.code == "model"
    with pytest.raises(CT.TranslateError) as e:
        CT.translate(t, *job, adapter=SimpleNamespace(generate=lambda s, u: SimpleNamespace(raw_output="", error="timeout")))
    assert e.value.code == "model"
    from neonrp.core.llm_stub import StubAdapter

    monkeypatch.setattr(CT, "_adapter", REAL_ADAPTER)
    with patch("neonrp.core.hub_publish.adapter_for_preset", return_value=StubAdapter()), pytest.raises(CT.TranslateError) as e:
        CT.translate(t, *job)
    assert e.value.code == "no_model"


def test_every_language_has_the_prompt():
    from neonrp import prompts

    for lg in prompts.LANGS:
        S = prompts.strings("creation_translate", lg)
        assert set(S) == {"system", "user"}
        u = S["user"].format(setting="S", terms="T", items="I")
        assert "S" in u and "T" in u and "I" in u and '{"<key>": {"<lang>": "…"}}' in u


def test_translate_route(desk, tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    m = Replay({"card.title": {"en": "Stoneford, mine"}})
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
            path = "/api/v1/local/templates/stoneford-town/creation/translate"
            st, b = call(path, {"fields": {"card.title": {"zh": "石津镇,我的"}}, "targets": {"card.title": ["en"]}, "lang": "zh"})
            assert st == 200 and b == {"ok": True, "fields": {"card.title": {"en": "Stoneford, mine"}}, "missing": []}, b
            assert not (desk / "stoneford-town-mine").exists(), "translate never writes"
            st, b = call(path, {"fields": "x", "targets": {}})
            assert st == 400 and b["error"] == "bad_body"
            m.reply = "no json"
            st, b = call(path, {"fields": {"card.title": {"zh": "石津镇"}}, "targets": {"card.title": ["en"]}})
            assert st == 502 and b["error"] == "model"
            with patch("neonrp.template.creation_translate._adapter", side_effect=CT.TranslateError("no_model")):
                st, b = call(path, {"fields": {"card.title": {"zh": "石津镇"}}, "targets": {"card.title": ["en"]}})
            assert st == 503 and b["error"] == "no_model"
            st, b = call("/api/v1/local/templates/nope/creation/translate", {"fields": {}, "targets": {}})
            assert st == 404
        finally:
            server.shutdown()
