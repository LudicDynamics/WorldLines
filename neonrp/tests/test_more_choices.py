"""「再给几个选项」(10-15):POST /api/v1/play/engine/choices {n?, avoid?} → {lang, options, by: "more"}。
只读(不写回合记录、不动 state)· 本局语言 · 只用玩家看得到的东西 · 忙时 409 · 每次记进 trace 的旁路文件。stub,不调真模型。"""
from __future__ import annotations

import hashlib
import json
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

from _paths import PRODUCT_TEMPLATES
from neonrp import template as TP
from neonrp.core import more_choices as MC
from neonrp.core.llm import LLMResponse
from neonrp.core.output_lang import write_output_lang


class FakeAdapter:
    def __init__(self, raw: str = "", error: str | None = None):
        self.raw, self.error, self.calls = raw, error, []

    def generate(self, system, user, tools=None):
        self.calls.append((system, user))
        return LLMResponse(proposal_text=None if self.error else self.raw, raw_output=self.raw, usage={"total_tokens": 42}, error=self.error)


def _run(tmp_path: Path, name: str = "kagura-island", lang: str | None = None) -> Path:
    dest = tmp_path / f"run-{lang or 'src'}"
    TP.build(TP.load(PRODUCT_TEMPLATES / f"{name}.template"), dest)
    if lang:
        write_output_lang(dest, lang)
    return dest


def _state_hash(root: Path) -> str:
    h = hashlib.sha1()
    for p in sorted((root / "game").rglob("*.json")):
        h.update(p.read_bytes())
    return h.hexdigest()


def test_more_options_from_what_the_player_sees(tmp_path):
    root = _run(tmp_path)
    before = _state_hash(root)
    fake = FakeAdapter("1. 看看海面\n- 问羽记得什么\n看看海面\n环顾四周\n「沿着砂滩走一走」\n捡起漂流木\n多余的一条")
    out = MC.more_choices(root, n=3, avoid=["环顾四周"], adapter=fake)
    assert out == {"lang": "zh", "options": ["看看海面", "问羽记得什么", "沿着砂滩走一走"], "by": "more"}
    system, user = fake.calls[0]
    assert "3" in user and "环顾四周" in user and "羽" in user, "the place / people the player sees, and what to avoid"
    assert "卡卡尔是悠人的妹妹" not in user and "灵魂设定" not in user, "nothing only the host may know"
    assert _state_hash(root) == before, "the world does not move"
    assert not (root / ".neonrp" / "orchestration" / "main.jsonl").exists() or "choices" not in (root / ".neonrp" / "orchestration" / "main.jsonl").read_text(encoding="utf-8")
    side = [json.loads(x) for x in (root / ".neonrp" / "orchestration" / "main.side.jsonl").read_text(encoding="utf-8").splitlines()]
    assert side[-1]["kind"] == "choices" and side[-1]["options"] == out["options"] and side[-1]["usage"] == {"total_tokens": 42}


def test_the_runs_language_and_a_model_error(tmp_path):
    root = _run(tmp_path, lang="en")
    fake = FakeAdapter("Look at the sea\nAsk Hane what she remembers")
    out = MC.more_choices(root, n=9, adapter=fake)
    assert out["lang"] == "en" and out["options"] == ["Look at the sea", "Ask Hane what she remembers"]
    assert fake.calls[0][0].startswith("You help a tabletop player")
    bad = MC.more_choices(root, adapter=FakeAdapter(error="quota"))
    assert bad["options"] == [] and bad["error"] == "quota"


def test_http_route_and_busy(tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    store = tmp_path / "store"
    shutil.copytree(PRODUCT_TEMPLATES / "pct-house.template", store / "pct-house.template")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(store))
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "studio"),
        patch("neonrp.commands.web.WebRuntime.gateway_start", lambda self: {"sid": "local", "root": self.root.name}),
        patch.object(MC, "_adapter", lambda root: FakeAdapter("推开书房的门\n问温妮那晚的事")),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def post(path, body):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read() or b"{}")
        try:
            post("/api/v1/play/session", {"slug": "tpl--pct-house", "output_lang": "zh"})
            out = post("/api/v1/play/engine/choices", {"n": 2, "avoid": []})
            assert out["options"] == ["推开书房的门", "问温妮那晚的事"] and out["by"] == "more"
            assert server.runtime._busy.acquire(blocking=False)
            try:
                with pytest.raises(urllib.error.HTTPError) as e:
                    post("/api/v1/play/engine/choices", {})
                assert e.value.code == 409
            finally:
                server.runtime._busy.release()
        finally:
            server.shutdown()
