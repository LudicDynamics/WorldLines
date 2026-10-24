"""角色直聊(10-15,chat-fe 的小手机):/api/v1/chat/souls · thread · send · sticker。
只对 standalone 或已带走的角色开放(否则 403);带着角色自己的文档和记忆(带走的 = 那一局的快照,full;没带走 = 模板里的,trial);
聊天记录存在玩家这边;第一次和 standalone 角色聊记 talked(不算获得);表情 wl:<id> / soul:<id>。stub 模型。"""
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
from neonrp.core import player_data, soul_chat
from neonrp.core.llm import LLMTurnResult, Message

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class Fake:
    def __init__(self, raw="嗯,来了。\n[sticker wl:happy]\n[sticker wl:nope]\n今天码头雾大。", error=None):
        self.raw, self.error, self.calls = raw, error, []

    def chat(self, messages, tools=None):
        """The plain chat call — a reply in text lines is not a proposal JSON (chat-fe 10-15: generate() refused it)."""
        self.calls.append((messages[0].content, messages[1].content))
        if self.error:
            return LLMTurnResult(error=self.error)
        return LLMTurnResult(message=Message(role="assistant", content=self.raw), finished=True, usage={"total_tokens": 9})


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = tmp_path / "store"
    for t in ("wuwu", "spice-witch"):
        shutil.copytree(PRODUCT_TEMPLATES / f"{t}.template", s / f"{t}.template")
    vera = s / "wuwu.template" / "world" / "souls" / "vera-si-vera0001"
    (vera / "stickers").mkdir(exist_ok=True)   # the template ships stickers.json (meanings) without pictures
    (vera / "stickers" / "wrench.png").write_bytes(PNG)
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(s))
    return s



def test_names_follow_the_language_and_fall_back_to_english(store):
    """lead 10-23: the phone took the English name for ja / ko although the template's foreign layer has its own;
    a language the template lacks falls back to English, never to Chinese."""
    name = lambda lg: {(r["tpl"], r["sid"]): r["name"] for r in soul_chat.souls(lg)["souls"]}[("wuwu", "vera")]  # noqa: E731
    assert [name(lg) for lg in ("zh", "en", "ja", "ko")] == ["薇拉", "Vera", "ヴェラ", "베라"]
    assert soul_chat.thread("wuwu", "vera", "ja")["soul"]["name"] == "ヴェラ"
    ko = store / "wuwu.template" / "i18n" / "ko"
    shutil.rmtree(ko)   # no Korean layer left: the glossary still has her Korean name; drop that row too
    g = store / "wuwu.template" / "i18n" / "glossary.json"
    if g.is_file():
        d = json.loads(g.read_text(encoding="utf-8"))
        rows = d if isinstance(d, list) else d.get("terms") or d.get("rows") or []
        for r in rows:
            if isinstance(r, dict):
                r.pop("ko", None)
        g.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    assert name("ko") == "Vera"


def test_who_can_be_talked_to(store):
    rows = {(r["tpl"], r["sid"]): r for r in soul_chat.souls("zh")["souls"]}
    assert ("wuwu", "vera") in rows and ("spice-witch", "maestro") in rows
    assert ("spice-witch", "severin") not in rows, "not standalone, not taken, never talked"
    v = rows[("wuwu", "vera")]
    assert v["name"] == "薇拉" and v["standalone"] and not v["obtained"] and v["memory"] == "trial" and v["last"] is None
    assert v["avatar_url"] == "/api/v1/local/templates/wuwu/assets/file?slot=soul.portrait:vera"
    th = soul_chat.thread("wuwu", "vera", "en")
    assert th["access"] == "standalone" and th["soul"]["name"] == "Vera" and "soul:wrench" in [s["id"] for s in th["stickers"]["soul"]]   # beside her own six (10-20)
    assert soul_chat.thread("spice-witch", "severin")["access"] == "locked"
    with pytest.raises(soul_chat.ChatError) as e:
        soul_chat.thread("wuwu", "nobody")
    assert e.value.status == 404


def test_send_talks_in_character_and_remembers(store):
    fake = Fake()
    out = soul_chat.send("wuwu", "vera", text="你在吗?", lang="zh", adapter=fake)
    assert [(m["kind"], m.get("text") or m.get("sticker")) for m in out["messages"]] == [
        ("text", "嗯,来了。"), ("sticker", "wl:happy"), ("text", "今天码头雾大。")], "an unknown sticker id is dropped"
    system, user = fake.calls[0]
    assert "薇拉" in system and "wl:happy" in system and "soul:wrench" in system
    soul_md = (store / "wuwu.template" / "world" / "souls" / "vera-si-vera0001" / "soul.md").read_text(encoding="utf-8").strip()
    assert soul_md[:40] in system, "her own folder is what she knows"
    assert "你在吗?" in user
    msgs = soul_chat.thread("wuwu", "vera")["messages"]
    assert [m["from"] for m in msgs] == ["me", "soul", "soul", "soul"] and all(m["id"] and m["at"] for m in msgs)
    soul_chat.send("wuwu", "vera", kind="sticker", sticker="wl:thanks", adapter=fake)
    assert "你在吗?" in fake.calls[1][1] and "嗯,来了。" in fake.calls[1][1], "the thread is her memory of you"
    d = player_data.read()
    assert [(c["world"], c["sid"]) for c in d["talked"]] == [("wuwu", "vera")] and d["characters"] == [], "talked, not gained"
    assert soul_chat.souls()["souls"][[r["sid"] for r in soul_chat.souls()["souls"]].index("vera")]["last"]["from"] == "soul"


def test_locked_busy_and_model_errors(store):
    with pytest.raises(soul_chat.ChatError) as e:
        soul_chat.send("spice-witch", "severin", text="hi", adapter=Fake())
    assert e.value.status == 403
    lock = soul_chat._BUSY.setdefault("wuwu/vera", threading.Lock())
    lock.acquire()
    try:
        with pytest.raises(soul_chat.ChatError) as e:
            soul_chat.send("wuwu", "vera", text="hi", adapter=Fake())
        assert e.value.status == 409
    finally:
        lock.release()
    with pytest.raises(soul_chat.ChatError) as e:
        soul_chat.send("wuwu", "vera", text="hi", adapter=Fake(error="quota"))
    assert e.value.status == 502 and soul_chat.thread("wuwu", "vera")["messages"] == [], "a failed send leaves no message"


def test_a_taken_character_talks_with_the_runs_memory(store, tmp_path):
    from neonrp import template as TP

    run = tmp_path / "run"
    TP.build(TP.load(store / "spice-witch.template"), run)
    sdir = next((run / "souls").glob("maestro-*"))
    sj = json.loads((sdir / "soul.json").read_text(encoding="utf-8"))
    (sdir / "soul.json").write_text(json.dumps({**sj, "take_when": "ending:E01"}, ensure_ascii=False), encoding="utf-8")
    (sdir / "long-term-memo").mkdir(exist_ok=True)
    (sdir / "long-term-memo" / "run.md").write_text("那晚在城门口,她递给我一包藏红花。", encoding="utf-8")
    from neonrp.core.worldmap import soul_dir_iid

    assert player_data.gain(run, soul_dir_iid(sdir), "ending:E01")
    th = soul_chat.thread("spice-witch", "maestro")  # 10-20: severin no longer comes home; maestro does (and is standalone too)
    assert th["access"] == "obtained" and th["memory"] == "full"
    assert (soul_chat.snapshot_dir("spice-witch", "maestro") / "long-term-memo" / "run.md").is_file()
    fake = Fake("记得。")
    soul_chat.send("spice-witch", "maestro", text="还记得城门口吗", adapter=fake)
    assert "藏红花" in fake.calls[0][0], "the memory from that run"
    assert player_data.read()["talked"] == [], "a taken character is not noted as a trial talk"


def test_http_routes(store, tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "studio"),
        patch.object(soul_chat, "_adapter", lambda rt=None: Fake("在呢。")),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def get(p):
            with urllib.request.urlopen(base + p, timeout=60) as r:
                return r.read()

        def post(p, b):
            req = urllib.request.Request(base + p, data=json.dumps(b).encode(), method="POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        try:
            assert any(r["sid"] == "vera" for r in json.loads(get("/api/v1/chat/souls?lang=zh"))["souls"])
            assert json.loads(get("/api/v1/chat/thread?tpl=wuwu&sid=vera"))["access"] == "standalone"
            assert get("/api/v1/chat/sticker?tpl=wuwu&sid=vera&id=wrench") == PNG
            out = post("/api/v1/chat/send", {"tpl": "wuwu", "sid": "vera", "kind": "text", "text": "嗨", "lang": "zh"})
            assert out["messages"][0]["text"] == "在呢。"
            g = post("/api/v1/chat/greet", {"tpl": "spice-witch", "sid": "maestro", "lang": "zh"})
            assert g["messages"][0]["greeting"] and post("/api/v1/chat/greet", {"tpl": "spice-witch", "sid": "maestro"}) == {"messages": []}
            with pytest.raises(urllib.error.HTTPError) as e:
                post("/api/v1/chat/send", {"tpl": "spice-witch", "sid": "severin", "text": "嗨"})
            assert e.value.code == 403 and "error" in json.loads(e.value.read())
        finally:
            server.shutdown()


def _twin(store, tid, zone):
    twin = store / f"{tid}.template"
    shutil.copytree(store / "wuwu.template", twin)
    tj = json.loads((twin / "template.json").read_text(encoding="utf-8"))
    (twin / "template.json").write_text(json.dumps({**tj, "id": tid, "zone": zone}, ensure_ascii=False), encoding="utf-8")


def test_one_row_per_character_and_where_she_is_from(store):
    _twin(store, "a-wuwu", "open")  # sorts before wuwu, but is not the listed official world
    _twin(store, "b-wuwu", "open")
    veras = [r for r in soul_chat.souls("zh")["souls"] if r["sid"] == "vera"]
    assert [r["tpl"] for r in veras] == ["wuwu"], "none touched: the officially listed world's copy only"
    assert veras[0]["world"] and veras[0]["world"] == soul_chat.thread("wuwu", "vera", "zh")["soul"]["world"]
    soul_chat.send("b-wuwu", "vera", text="嗨", adapter=Fake("嗯。"))
    assert [r["tpl"] for r in soul_chat.souls("zh")["souls"] if r["sid"] == "vera"] == ["b-wuwu"], \
        "the copy you have a thread with is the one listed"


def test_real_adapter_shape_plain_text_reply(store):
    """The OpenAI adapter as a real model answers it — plain text lines, no proposal JSON (chat-fe 10-15: 502)."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from neonrp.core.llm_openai import OpenAIAdapter

    a = OpenAIAdapter(model="m", api_key="k")
    a._client = MagicMock()
    a._client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="来了来了\n[sticker wl:hello]", tool_calls=None))],
        usage=None)
    out = soul_chat.send("wuwu", "vera", text="在吗", adapter=a)
    assert [(m["kind"], m.get("text") or m.get("sticker")) for m in out["messages"]] == [("text", "来了来了"), ("sticker", "wl:hello")]
    roles = [m["role"] for m in a._client.chat.completions.create.call_args.kwargs["messages"]]
    assert roles == ["system", "user"]


GREET = "<greeting>\n你来啦。\n今天码头雾大。\n</greeting>\n<suggest>\n1. 雾有多大?\n- 你在忙什么\n「给我讲讲灯塔」\n第四句不要\n</suggest>"


def test_greet_writes_her_opening_line_once(store):
    """The first time (10-17): an empty thread gets her opening line in her voice + three suggested replies, kept in the
    thread; opening it again writes nothing new; once you have talked she does not greet again."""
    fake = Fake(GREET)
    out = soul_chat.greet("wuwu", "vera", lang="zh", adapter=fake)
    assert [m["text"] for m in out["messages"]] == ["你来啦。", "今天码头雾大。"] and all(m["greeting"] and m["from"] == "soul" for m in out["messages"])
    assert out["messages"][-1]["suggest"] == ["雾有多大?", "你在忙什么", "给我讲讲灯塔"], "three, numbering / quotes stripped"
    system, user = fake.calls[0]
    assert "薇拉" in system and "<greeting>" in user and "<suggest>" in user
    assert [m["text"] for m in soul_chat.thread("wuwu", "vera")["messages"]] == ["你来啦。", "今天码头雾大。"]
    assert soul_chat.greet("wuwu", "vera", lang="zh", adapter=fake) == {"messages": []} and len(fake.calls) == 1, "written once"
    for lg in ("en", "ja", "ko"):
        assert "<greeting>" in soul_chat._T(lg)["greet"] and "{name}" in soul_chat._T(lg)["greet"]


def test_greet_her_authors_line_no_model_and_locked(store):
    sj = store / "wuwu.template" / "world" / "souls" / "vera-si-vera0001" / "soul.json"
    d = json.loads(sj.read_text(encoding="utf-8"))
    with pytest.raises(soul_chat.ChatError) as e:
        soul_chat.greet("wuwu", "vera", adapter=Fake(error="no model configured — pick one in settings (/auth) first"))
    assert e.value.status == 502 and "no model configured" in str(e.value) and soul_chat.thread("wuwu", "vera")["messages"] == [], "nothing kept: next open tries again"
    sj.write_text(json.dumps({**d, "greeting_i18n": {"zh": "灯还亮着。", "en": "The lamp's still lit."}}, ensure_ascii=False), encoding="utf-8")
    fake = Fake(GREET)
    out = soul_chat.greet("wuwu", "vera", lang="en", adapter=fake)
    assert [m["text"] for m in out["messages"]] == ["The lamp's still lit."] and not fake.calls, "her author's line: no model call"
    with pytest.raises(soul_chat.ChatError) as e:
        soul_chat.greet("spice-witch", "severin", adapter=Fake(GREET))
    assert e.value.status == 403
