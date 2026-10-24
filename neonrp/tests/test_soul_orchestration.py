"""角色编排图(10-16,角色编排台 S1):worldlines.orchestration/1 + subject: soul。默认图 = 10-15 的小手机行为;
图从角色自己的文件夹 / 模板覆盖(只改这个世界)叠出来;小手机按图的 chat 节点回话(历史条数 · 文档 · 表情工具 · 气泡数);
targets 声明适配的 soul / world 规范版本,lint 校验;角色列表三类(角色库独立 · standalone · takeable)+ 角色库角色能聊;
写回:角色库写角色文件夹,世界里的角色写模板覆盖,内置模板只读;新图照读旧记忆。stub 模型。"""
from __future__ import annotations

import json
import shutil
import threading
import urllib.error
import urllib.request
from unittest.mock import patch

import pytest

from _paths import PRODUCT_TEMPLATES
from neonrp.core import player_data, soul_chat
from neonrp.core import soul_orchestration as SO
from neonrp.core.llm import LLMTurnResult, Message
from test_engine_v3 import fake_adapter  # noqa: F401 — the v3 turn's fake model (a fixture)


class Fake:
    def __init__(self, raw="嗯。\n[sticker wl:happy]\n第二句。\n第三句。"):
        self.raw, self.calls = raw, []

    def chat(self, messages, tools=None):
        self.calls.append((messages[0].content, messages[1].content))
        return LLMTurnResult(message=Message(role="assistant", content=self.raw), finished=True, usage={})


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = tmp_path / "store"
    for t in ("wuwu", "spice-witch"):
        shutil.copytree(PRODUCT_TEMPLATES / f"{t}.template", s / f"{t}.template")
    # 10-20 made Severin stay in his world (takeable: false); these tests use him as the takeable, not-standalone kind
    for sj in (s / "spice-witch.template").rglob("severin-*/soul.json"):
        d = json.loads(sj.read_text(encoding="utf-8"))
        d["takeable"] = True
        sj.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(s))
    return s


@pytest.fixture
def lib():
    """A character in the library that no world links (① 独立角色)."""
    import neonrp.core.souls as _souls

    d = _souls.SOUL_HOME / "awu"
    (d / "long-term-memo").mkdir(parents=True)
    (d / "soul.json").write_text(json.dumps({"schema_version": 1, "sid": "awu", "name": "Awu", "name_local": "阿雾"}, ensure_ascii=False), encoding="utf-8")
    (d / "soul.md").write_text("码头卖鱼的姑娘,说话很冲。", encoding="utf-8")
    (d / "long-term-memo" / "old.md").write_text("去年冬天你帮她修过船。", encoding="utf-8")
    return d


def test_default_graph_is_the_phone_as_it_was():
    g = SO.default_graph()
    assert g["schema"] == "worldlines.orchestration/1" and g["subject"] == "soul" and g["targets"] == {"soul_spec": 1, "world_spec": 1}
    n = SO.chat_node(g)
    assert n["id"] == "chat" and n["tools"] == ["sticker"] and n["history"] == soul_chat.HISTORY and n["doc_cap"] == soul_chat.DOC_CAP
    assert tuple(n["docs"]) == soul_chat.DOC_FILES and n["max_bubbles"] == 5
    assert SO.lint(g) == []


def test_lint_versions_kinds_tools_edges():
    g = SO.default_graph()
    codes = lambda x: {(r["level"], r["code"]) for r in SO.lint(x)}  # noqa: E731
    assert ("block", "orch.spec_mismatch") in codes({**g, "targets": {"soul_spec": SO.SOUL_SPEC + 1}}), "a graph for a newer spec is refused"
    assert ("warn", "orch.spec_mismatch") in {(r["level"], r["code"]) for r in SO.lint(g, soul_spec=0)}, "the soul folder is older"
    bad = {**g, "nodes": {**g["nodes"], "x": {"kind": "dance"}, "t": {"kind": "tick", "tools": ["image.generate", "nope"]}, "r": {"kind": "reflect"}},
           "edges": [*g["edges"], {"id": "e", "from": "chat", "to": "gone", "on": {"weather": "rain"}}]}
    c = codes(bad)
    assert {("block", "orch.node_kind"), ("block", "orch.edge"), ("warn", "orch.on_unknown"), ("warn", "orch.tool_unknown"), ("warn", "orch.node_off")} <= c, c
    assert ("warn", "orch.tool_off") in codes({**g, "nodes": {"chat": {**g["nodes"]["chat"], "tools": ["sticker", "image.generate"]}}})
    assert ("warn", "orch.no_chat") in codes({**g, "nodes": {"chat": {"kind": "tick"}}, "edges": []})
    with pytest.raises(ValueError):
        SO.check(bad)


def test_the_phone_answers_the_way_its_graph_says(store):
    folder = store / "wuwu.template" / "world" / "souls" / "vera-si-vera0001"
    soul_chat.send("wuwu", "vera", text="一", adapter=Fake())
    (folder / "agents").mkdir(exist_ok=True)
    (folder / "agents" / "orchestration.json").write_text(json.dumps(
        {"nodes": {"chat": {"tools": [], "history": 0, "max_bubbles": 2, "docs": ["soul.md"]}}}), encoding="utf-8")
    fake = Fake()
    out = soul_chat.send("wuwu", "vera", text="二", adapter=fake)
    assert [m["kind"] for m in out["messages"]] == ["text", "text"], "no sticker tool → stickers dropped; at most 2 bubbles"
    system, user = fake.calls[0]
    assert "wl:happy" not in system and "## soul.md" in system and "## persona" not in system
    assert "一" not in user, "history 0: the thread is not shown"
    assert soul_chat.thread("wuwu", "vera")["stickers"]["soul"] == []
    assert len(soul_chat.thread("wuwu", "vera")["messages"]) == (1 + 4) + (1 + 2), "the old thread is kept: a new graph loses nothing"


def test_template_override_is_this_world_only_and_beats_the_folder(store):
    t = store / "wuwu.template"
    (t / "prompts" / "souls" / "vera").mkdir(parents=True)
    (t / "prompts" / "souls" / "vera" / "orchestration.json").write_text(json.dumps({"nodes": {"chat": {"max_bubbles": 1}}}), encoding="utf-8")
    out = soul_chat.send("wuwu", "vera", text="hi", adapter=Fake())
    assert len(out["messages"]) == 1
    b = SO.bench("tpl:wuwu/vera")
    assert [x["scope"] for x in b["layers"]] == ["soul", "template"] and b["layers"][1]["exists"]
    assert SO.chat_node(b["base"])["max_bubbles"] == 5 and SO.chat_node(b["graph"])["max_bubbles"] == 1


def test_a_taken_character_follows_the_source_graph_with_its_snapshot_memory(store, tmp_path):
    from neonrp import template as TP
    from neonrp.core.worldmap import soul_dir_iid

    run = tmp_path / "run"
    TP.build(TP.load(store / "spice-witch.template"), run)
    sdir = next((run / "souls").glob("severin-*"))
    (sdir / "long-term-memo").mkdir(exist_ok=True)
    (sdir / "long-term-memo" / "run.md").write_text("那晚在城门口,她递给我一包藏红花。", encoding="utf-8")
    assert player_data.gain(run, soul_dir_iid(sdir), "companion_at_ending")
    t = store / "spice-witch.template"
    (t / "prompts" / "souls" / "severin").mkdir(parents=True)
    (t / "prompts" / "souls" / "severin" / "orchestration.json").write_text(json.dumps({"nodes": {"chat": {"max_bubbles": 1}}}), encoding="utf-8")
    fake = Fake()
    out = soul_chat.send("spice-witch", "severin", text="还记得吗", adapter=fake)
    assert len(out["messages"]) == 1, "the graph edited after he was taken reaches him"
    assert "藏红花" in fake.calls[0][0], "and his memory is still the run's"


def test_catalog_three_kinds_and_library_chat(store, lib):
    rows = {r["ref"]: r for r in SO.catalog("zh")["souls"]}
    assert rows["lib:awu"]["kinds"] == ["library", "independent"] and rows["lib:awu"]["chat"] == "library" and rows["lib:awu"]["edit"]["to"] == "library"
    assert rows["tpl:wuwu/vera"]["kinds"] == ["standalone", "takeable"] and rows["tpl:wuwu/vera"]["chat"] == "standalone"
    assert rows["tpl:spice-witch/severin"]["kinds"] == ["takeable"] and rows["tpl:spice-witch/severin"]["chat"] == "locked"
    assert rows["tpl:wuwu/vera"]["edit"] == {"to": "template", "id": "wuwu", "writable": False}
    fake = Fake("在呢。")
    out = soul_chat.send("lib:awu", "", text="船还好吗", adapter=fake)
    assert out["messages"][0]["text"] == "在呢。" and "修过船" in fake.calls[0][0], "a library character talks from its own folder"
    th = soul_chat.thread("lib:awu", "")
    assert th["access"] == "library" and th["memory"] == "full" and [m["from"] for m in th["messages"]] == ["me", "soul"]
    assert th["soul"]["avatar_url"] == "/api/v1/local/souls/awu/portrait" and th["soul"]["world"] == ""
    assert player_data.read()["talked"] == [] and player_data.read()["characters"] == [], "talking with your own is neither"
    listed = {(r["tpl"], r["sid"]): r for r in soul_chat.souls("zh")["souls"]}
    assert listed[("lib:awu", "awu")]["library"] and listed[("lib:awu", "awu")]["last"]["text"] == "在呢。"


def test_save_writes_where_it_belongs(store, lib, monkeypatch):
    g = SO.default_graph()
    g["nodes"]["chat"]["max_bubbles"] = 3
    out = SO.save("lib:awu", g)
    # stored as a patch: only the fields that differ from the default (author.graph_patch, 10-18 2e202bd7 — the engine's
    # own fields keep flowing in); read back it merges over the default
    assert out["to"] == "library" and json.loads((lib / "agents" / "orchestration.json").read_text(encoding="utf-8")) == {"nodes": {"chat": {"max_bubbles": 3}}}
    assert SO.chat_node(SO.bench("lib:awu")["graph"])["max_bubbles"] == 3
    with pytest.raises(PermissionError):
        SO.save("tpl:wuwu/vera", g)  # built in: read-only
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(store))
    out = SO.save("tpl:wuwu/vera", g)
    p = store / "wuwu.template" / "prompts" / "souls" / "vera" / "orchestration.json"
    assert out["to"] == "template" and p.is_file() and SO.chat_node(out["graph"])["max_bubbles"] == 3
    assert not (store / "wuwu.template" / "world" / "souls" / "vera-si-vera0001" / "agents" / "orchestration.json").is_file(), "the world's soul folder is not touched"
    SO.save("tpl:wuwu/vera", SO.bench("tpl:wuwu/vera")["base"])
    assert json.loads(p.read_text(encoding="utf-8")) == {}, "back to what it gets without one = an empty patch"
    with pytest.raises(ValueError):
        SO.save("lib:awu", {"nodes": {"chat": {"kind": "dance"}}, "edges": [], "start": "chat"})


def test_http_bench_and_chat_by_ref(store, lib, tmp_path, monkeypatch):
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
                return json.loads(r.read())

        def post(p, b):
            req = urllib.request.Request(base + p, data=json.dumps(b).encode(), method="POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        try:
            assert any(r["ref"] == "lib:awu" for r in get("/api/v1/souls/catalog?lang=zh")["souls"])
            b = get("/api/v1/souls/orchestration?ref=tpl%3Awuwu%2Fvera")
            assert b["graph"]["subject"] == "soul" and b["lint"] == [] and "chat" in b["hooks"]["node_kinds"]
            assert post("/api/v1/souls/orchestration/lint", {"graph": {"nodes": {"a": {"kind": "dance"}}, "edges": [], "start": "a"}})["lint"]
            with pytest.raises(urllib.error.HTTPError) as e:
                post("/api/v1/souls/orchestration", {"ref": "tpl:wuwu/vera", "graph": SO.default_graph()})
            assert e.value.code == 403
            assert post("/api/v1/souls/orchestration", {"ref": "lib:awu", "graph": SO.default_graph()})["to"] == "library"
            assert get("/api/v1/chat/thread?ref=lib%3Aawu")["access"] == "library"
            assert post("/api/v1/chat/send", {"ref": "lib:awu", "text": "嗨"})["messages"][0]["text"] == "在呢。"
            assert get("/api/v1/chat/tick?ref=lib%3Aawu")["why"] == "no_tick_node"
            assert post("/api/v1/chat/tick/settings", {"ref": "lib:awu", "on": True})["on"] is True
            assert post("/api/v1/chat/tick", {"ref": "lib:awu", "catchup": True})["ran"] is False
            assert get("/api/v1/souls/ambient?ref=tpl%3Awuwu%2Fvera")["world"]["source"] == "replicated"
            monkeypatch.setenv("WORLDLINES_PRODUCT", "hub")
            with pytest.raises(urllib.error.HTTPError) as e:
                get("/api/v1/souls/catalog")
            assert e.value.code == 404, "no bench in the browser engine"
        finally:
            server.shutdown()


# ── 简单世界观(S3):复刻 · 自动生成 · 写回 ──

def test_ambient_replicated_from_its_world_without_secrets(store):
    from neonrp.core import soul_ambient as SA

    c = soul_chat.resolve("wuwu", "vera")
    w = SA.read(c, "zh")
    assert w["source"] == "replicated" and w["schema"] == "worldlines.soul-ambient/1" and w["clock"] == "real"
    assert w["places"][0]["id"] == "office" and w["places"][0]["name"] == "港务所", "home = where she stands in the world"
    assert 1 < len(w["places"]) <= SA.MAX_PLACES and [r["at"] for r in w["routine"]] == list(SA.SLOTS)
    truth = (store / "wuwu.template" / "world" / "game" / "lore" / "gm-truth.md").read_text(encoding="utf-8").strip().splitlines()[-1][:20]
    assert truth not in json.dumps(w, ensure_ascii=False), "never the GM's truth"
    assert SA.read(soul_chat.resolve("spice-witch", "severin"), "zh")["source"] == "replicated"


def test_ambient_generated_for_a_library_character_and_saved(store, lib, monkeypatch):
    from neonrp.core import soul_ambient as SA

    c = soul_chat.resolve("lib:awu", "")
    assert SA.read(c) is None, "a library character has none until one is made"
    fake = Fake('好的:{"setting": "海边小镇", "places": [{"id": "stall", "name": "鱼摊", "summary": "码头边"}, {"name": "家"}], '
                '"routine": [{"at": "morning", "place": "stall", "doing": "卖鱼"}, {"at": "noon", "place": "stall"}], "people": [{"name": "老莫", "line": "邻居"}]}')
    w = SA.generate(c, "zh", adapter=fake)
    assert w["source"] == "generated" and w["places"][0]["id"] == "stall" and len(w["routine"]) == 1 and "修过船" in fake.calls[0][1]
    SA.save(c, w)
    assert SA.read(c)["setting"] == "海边小镇" and (lib / "ambient" / "world.json").is_file()
    with pytest.raises(ValueError):
        SA.generate(c, "zh", adapter=Fake("没有 JSON"))
    with pytest.raises(PermissionError):
        SA.save(soul_chat.resolve("wuwu", "vera"), w)
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(store))
    SA.save(soul_chat.resolve("wuwu", "vera"), {**w, "setting": "雾港"})
    assert (store / "wuwu.template" / "prompts" / "souls" / "vera" / "ambient" / "world.json").is_file()
    assert SA.read(soul_chat.resolve("wuwu", "vera"))["setting"] == "雾港", "the template's override wins over replicating"


# ── tick(S4):前台自由行动,默认关;只 tick 自己的(角色库 / 已获得);一次 = 一次模型调用 → 写进它自己的记忆 ──

def _tick_graph():
    g = SO.default_graph()
    g["nodes"]["tick"] = {"kind": "tick", "title": "tick", "tools": ["memo.write"]}
    g["edges"].append({"id": "chat>tick:clock", "from": "chat", "to": "tick", "on": {"tick": "clock"}})
    return g


def test_tick_off_by_default_owned_only_and_needs_a_tick_node(store, lib):
    from neonrp.core import soul_tick as T

    awu = soul_chat.resolve("lib:awu", "")
    assert T.status(awu)["why"] == "no_tick_node" and not T.status(awu)["can"]
    SO.save("lib:awu", _tick_graph())
    assert T.status(awu)["can"] and T.status(awu)["why"] == "off", "off by default: it spends the player's credits"
    assert T.run(awu, adapter=Fake())["why"] == "off"
    assert T.status(soul_chat.resolve("wuwu", "vera"))["why"] == "trial", "a character only tried out never ticks"
    assert T.status(soul_chat.resolve("spice-witch", "severin"))["why"] == "locked"


def test_tick_lands_in_its_own_memory_and_may_text_the_player(store, lib):
    from neonrp.core import soul_tick as T

    SO.save("lib:awu", _tick_graph())
    awu = soul_chat.resolve("lib:awu", "")
    (lib / "ambient").mkdir()
    (lib / "ambient" / "world.json").write_text(json.dumps({"setting": "海边小镇", "places": [{"id": "stall", "name": "鱼摊"}],
        "routine": [{"at": s, "place": "stall", "doing": "卖鱼"} for s in ("morning", "afternoon", "evening", "night")]}, ensure_ascii=False), encoding="utf-8")
    T.set_on(awu, True)
    fake = Fake('{"did": "我把今早的鱼摆上了摊。", "mood": "精神", "message": "今天的鱼很新鲜,要不要来看看?"}')
    out = T.run(awu, adapter=fake, catchup=True, now=1_800_000_000)
    assert out["ran"] and out["did"] == "我把今早的鱼摆上了摊。" and out["message"]["origin"] == "tick"
    system, ctx = fake.calls[0]
    assert "Awu" in system or "阿雾" in system
    assert "海边小镇" in ctx and "卖鱼" in ctx and "修过船" in ctx and "while the player was away" in ctx
    assert "我把今早的鱼摆上了摊。" in (lib / "trajectory" / "action_log.md").read_text(encoding="utf-8")
    ev = json.loads((lib / "short-term-memo" / "recent_events.json").read_text(encoding="utf-8"))["events"][-1]
    assert ev["by"] == "soul.tick" and ev["my_reaction"] == "精神"
    assert soul_chat.thread("lib:awu", "")["messages"][-1]["text"] == "今天的鱼很新鲜,要不要来看看?"
    assert T.run(awu, adapter=fake, now=1_800_000_000 + 60)["why"] == "wait", "one tick per interval"
    for k in range(1, 3):
        T.run(awu, adapter=fake, now=1_800_000_000 + k * (T.INTERVAL_MIN * 60 + 1))
    msgs = [m for m in soul_chat.thread("lib:awu", "")["messages"] if m.get("origin") == "tick"]
    assert len(msgs) == T.PROACTIVE_DAILY, "at most two messages a day on its own"
    assert T.run(awu, adapter=Fake("胡言乱语"), now=1_800_000_000 + 9 * T.INTERVAL_MIN * 60)["why"] == "model", "a bad answer lands nothing"


def test_tick_for_a_gained_character_writes_the_snapshot_not_the_template(store, tmp_path, monkeypatch):
    from neonrp import template as TP
    from neonrp.core import soul_tick as T
    from neonrp.core.worldmap import soul_dir_iid

    run = tmp_path / "run"
    TP.build(TP.load(store / "spice-witch.template"), run)
    assert player_data.gain(run, soul_dir_iid(next((run / "souls").glob("severin-*"))), "companion_at_ending")
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(store))
    SO.save("tpl:spice-witch/severin", _tick_graph())
    c = soul_chat.resolve("spice-witch", "severin")
    T.set_on(c, True)
    assert T.run(c, adapter=Fake('{"did": "我去集市转了一圈。", "mood": "", "message": ""}'))["ran"]
    assert "集市" in (soul_chat.snapshot_dir("spice-witch", "severin") / "trajectory" / "action_log.md").read_text(encoding="utf-8")
    tdir = store / "spice-witch.template" / "world" / "souls" / "severin-si-severin1" / "trajectory" / "action_log.md"
    assert not tdir.is_file() or "集市" not in tdir.read_text(encoding="utf-8"), "the template's folder is never written"


# ── 专属表情(S5):图 + 含义(stickers/stickers.json 四语 + 什么时候发)· 生图只留接口 ──

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def test_stickers_with_meanings_reach_the_picker_and_the_model(store, lib):
    out = SO.sticker_put("lib:awu", "fish", PNG)
    assert [s["id"] for s in out["stickers"]] == ["fish"] and out["writable"]
    SO.sticker_meta_set("lib:awu", "fish", {"zh": "举起一条鱼", "en": "holds up a fish", "xx": "no"}, "炫耀今天的货")
    meta = json.loads((lib / "stickers" / "stickers.json").read_text(encoding="utf-8"))
    assert meta == {"fish": {"label": {"zh": "举起一条鱼", "en": "holds up a fish"}, "when": "炫耀今天的货"}}
    th = soul_chat.thread("lib:awu", "", "en")
    assert th["stickers"]["soul"][0]["label"] == "holds up a fish" and th["stickers"]["soul"][0]["when"] == "炫耀今天的货"
    fake = Fake("看!\n[sticker soul:fish]")
    out = soul_chat.send("lib:awu", "", text="今天有什么", lang="zh", adapter=fake)
    assert "soul:fish(举起一条鱼 · 炫耀今天的货)" in fake.calls[0][0] and out["messages"][-1]["sticker"] == "soul:fish"
    assert soul_chat.sticker_file("lib:awu", "awu", "fish").read_bytes() == PNG
    with pytest.raises(ValueError):
        SO.sticker_put("lib:awu", "Bad Id", PNG)
    with pytest.raises(ValueError):
        SO.sticker_put("lib:awu", "jpg", b"\xff\xd8\xff")
    with pytest.raises(PermissionError):
        SO.sticker_put("tpl:wuwu/vera", "x", PNG)   # built in: read-only
    assert SO.sticker_remove("lib:awu", "fish")["stickers"] == []


def test_a_gained_character_gets_stickers_added_after_it_was_taken(store, tmp_path, monkeypatch):
    from neonrp import template as TP
    from neonrp.core.worldmap import soul_dir_iid

    run = tmp_path / "run"
    TP.build(TP.load(store / "spice-witch.template"), run)
    assert player_data.gain(run, soul_dir_iid(next((run / "souls").glob("severin-*"))), "companion_at_ending")
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(store))
    SO.sticker_put("tpl:spice-witch/severin", "bow", PNG)
    # 10-20: a taken character's stickers are the player's — the author's new one waits in the update's diff
    assert [s["id"] for s in soul_chat.thread("spice-witch", "severin")["stickers"]["soul"]] == []
    from neonrp.core import soul_update

    d = soul_update.diff("spice-witch", "severin")
    assert [(it["file"], it["op"], it["default"]) for it in d["items"] if it["file"].startswith("stickers/")] == [("stickers/bow.png", "add", "theirs")]
    soul_update.apply("spice-witch", "severin", token=d["token"], all_="defaults")
    assert [s["id"] for s in soul_chat.thread("spice-witch", "severin")["stickers"]["soul"]] == ["soul:bow"], "taken in: now the player's too"


def test_image_lines_are_an_interface_only(store):
    out = soul_chat.send("wuwu", "vera", text="拍张照?", adapter=Fake("好啊。\n[~image 码头的雾]\n[image 灯塔]\n你看。"))
    assert [m["text"] for m in out["messages"]] == ["好啊。", "你看。"], "image.generate is not live: its lines never show as text"


# ── 工作台去 mock 第 3 批(10-17):tick 参数从节点读 · idle 触发 · reflect · describe 只含引擎跑的 · in_world 真实设置 ──

class Seq(Fake):
    """Answers in turn (a tick, then a reflect …); the last one repeats."""

    def __init__(self, *raws):
        super().__init__(raws[0])
        self.raws = list(raws)

    def chat(self, messages, tools=None):
        self.raw = self.raws.pop(0) if len(self.raws) > 1 else self.raws[0]
        return super().chat(messages, tools)


DID = '{"did": "我补了渔网。", "mood": "平静", "message": "在吗?"}'


def _tick_with(**fields):
    g = _tick_graph()
    g["nodes"]["tick"].update(fields)
    return g


def test_tick_fields_come_from_the_node(store, lib):
    from neonrp.core import soul_tick as T

    SO.save("lib:awu", _tick_with(interval_min=1, daily_max=3, proactive_daily=1, prompt="你是{name}。现在是{slot}。只回 JSON {\"did\": \"…\"}"))
    awu = soul_chat.resolve("lib:awu", "")
    T.set_on(awu, True)
    st = T.status(awu)
    assert (st["interval_min"], st["daily_max"], st["proactive_daily"], st["trigger"]) == (1, 3, 1, "clock")
    t0 = 1_800_000_000
    fake = Fake(DID)
    assert T.run(awu, adapter=fake, now=t0)["ran"]
    assert fake.calls[0][0].startswith("你是Awu。") or fake.calls[0][0].startswith("你是阿雾。"), "the node's prompt, filled in"
    assert "{slot}" not in fake.calls[0][0] and '{"did"' in fake.calls[0][0], "placeholders filled, the JSON shape kept"
    assert T.status(awu, now=t0 + 30)["why"] == "wait"
    assert T.status(awu, now=t0 + 61)["due"], "interval_min 1: due a minute later"
    assert T.run(awu, adapter=fake, now=t0 + 61)["ran"] and T.run(awu, adapter=fake, now=t0 + 122)["ran"]
    assert T.status(awu, now=t0 + 183)["why"] == "daily_max", "daily_max 3"
    assert len([m for m in soul_chat.thread("lib:awu", "")["messages"] if m.get("origin") == "tick"]) == 1, "proactive_daily 1"
    on = json.loads((lib / "agents" / "orchestration.json").read_text(encoding="utf-8"))["nodes"]["tick"]
    assert on["interval_min"] == 1 and on["prompt"].startswith("你是")


def test_tick_field_ranges_are_linted():
    codes = lambda g: {(r["level"], r["code"]) for r in SO.lint(g)}  # noqa: E731
    assert ("block", "orch.param_range") in codes(_tick_with(interval_min=0))
    assert ("block", "orch.param_range") in codes(_tick_with(daily_max="9"))
    assert ("block", "orch.param_range") in codes(_tick_with(prompt="x" * (SO.PROMPT_MAX + 1)))
    g = _tick_graph()
    g["edges"].append({"id": "idle", "from": "chat", "to": "tick", "on": {"idle": "soon"}})
    assert ("block", "orch.param_range") in codes(g)
    g["edges"][-1]["on"] = {"idle": 5}
    assert not [r for r in SO.lint(g) if r["level"] == "block"]
    g["edges"][-1]["to"] = "chat"
    assert ("warn", "orch.on_target") in codes(g), "idle only starts a tick node"
    assert SO.node_params({"interval_min": 0, "daily_max": 5}, "tick") == {**SO.NODE_KINDS["tick"]["params"], "daily_max": 5}, "out of range = the default"


def test_idle_ticks_once_per_quiet_stretch(store, lib):
    import time as _t

    from neonrp.core import soul_tick as T

    g = SO.default_graph()
    g["nodes"]["tick"] = {"kind": "tick", "title": "tick", "tools": ["memo.write"], "interval_min": 1}
    g["edges"].append({"id": "chat>tick:idle", "from": "chat", "to": "tick", "on": {"idle": 5}})
    SO.save("lib:awu", g)
    awu = soul_chat.resolve("lib:awu", "")
    T.set_on(awu, True)
    soul_chat._append("lib:awu", "awu", [{"from": "me", "kind": "text", "text": "在吗"}])
    now = _t.time()
    st = T.status(awu, now=now + 60)
    assert st["trigger"] == "idle" and st["idle_min"] == 5 and st["why"] == "idle_wait" and 0 < st["wait_s"] <= 240
    assert T.run(awu, adapter=Fake(DID), now=now + 60)["why"] == "idle_wait"
    assert T.run(awu, adapter=Fake(DID), now=now + 5 * 60 + 2)["ran"], "five quiet minutes: it ticks"
    assert T.status(awu, now=now + 30 * 60)["why"] == "idle_done", "once per quiet stretch, however long"
    back = soul_chat._append("lib:awu", "awu", [{"from": "me", "kind": "text", "text": "回来了"}])[0]
    th = soul_chat._thread_path("lib:awu", "awu")   # she wrote back after that tick (the tick ran on a clock ahead of the wall)
    later = _t.strftime("%Y-%m-%dT%H:%M:%S%z", _t.localtime(now + 20 * 60))
    th.write_text(th.read_text(encoding="utf-8").replace(back["at"], later), encoding="utf-8")
    assert T.status(awu, now=now + 22 * 60)["why"] == "idle_wait"
    assert T.status(awu, now=now + 25 * 60 + 2)["due"], "the player wrote again: a new stretch"


def test_reflect_folds_short_term_into_long_term_every_n_ticks(store, lib):
    from neonrp.core import soul_tick as T

    g = _tick_with(interval_min=1)
    g["nodes"]["reflect"] = {"kind": "reflect", "title": "reflect", "tools": ["memo.write"], "every": 2, "keep": 1}
    SO.save("lib:awu", g)
    awu = soul_chat.resolve("lib:awu", "")
    T.set_on(awu, True)
    keep = '{"keep": ["我开始习惯每天早上补网。"]}'
    fake = Seq(DID, DID, keep)
    t0 = 1_800_000_000
    assert "reflected" not in T.run(awu, adapter=fake, now=t0)
    out = T.run(awu, adapter=fake, now=t0 + 61)
    assert out["reflected"]["ran"] and out["reflected"]["kept"] == ["我开始习惯每天早上补网。"] and out["reflected"]["folded"] == 1
    assert len(fake.calls) == 3 and "我补了渔网。" in fake.calls[2][1], "one more call, reading the short-term events"
    assert "我开始习惯每天早上补网。" in (lib / "long-term-memo" / "reflections.md").read_text(encoding="utf-8")
    assert len(json.loads((lib / "short-term-memo" / "recent_events.json").read_text(encoding="utf-8"))["events"]) == 1, "keep 1"
    assert "reflected" not in T.run(awu, adapter=Seq(DID), now=t0 + 122), "the counter starts again"
    g["nodes"]["reflect"]["every"] = 0
    SO.save("lib:awu", g)
    assert "reflected" not in T.run(awu, adapter=Seq(DID), now=t0 + 183) and "reflected" not in T.run(awu, adapter=Seq(DID), now=t0 + 244), "every 0 = off"
    assert soul_chat.chat_node(awu)["id"] == "chat", "the phone still answers from the chat node"


def test_describe_has_only_what_the_engine_runs():
    from neonrp.core import soul_tick as T

    d = SO.describe()
    assert set(SO.ON_KINDS) == {"chat", "tick", "idle"} and "always" not in d["on"], "always is read by nothing: not offered (a plugin may add its own)"
    assert set(SO.NODE_KINDS) == {"chat", "tick", "reflect", "in_world"} and set(d["node_kinds"]) >= set(SO.NODE_KINDS)
    for k, v in d["node_kinds"].items():
        assert v["steps"] and all(s["by"] in ("engine", "llm", "hook") and s["id"] and s["doc"] for s in v["steps"]), k
        assert set(v["params"]) >= set(v["ranges"]), k
    assert d["node_kinds"]["in_world"]["addable"] is False and d["node_kinds"]["tick"]["addable"] is True
    assert set(d["node_kinds"]["tick"]["params"]) == {"interval_min", "daily_max", "proactive_daily", "prompt"}
    assert (T.INTERVAL_MIN, T.DAILY_MAX, T.PROACTIVE_DAILY) == (10, 24, 2), "the defaults did not move"
    assert callable(T.reflect) and callable(T.tick_node)
    live = {t for t, v in d["tools"].items() if v["live"]}
    assert live == {"sticker", "memo.write"} and d["tools"]["memo.write"]["kinds"] == ["tick", "reflect"]
    assert "memo.write" not in d["node_kinds"]["chat"]["tools"], "a chat writes no memory"
    for t, v in d["tools"].items():
        assert all(t in d["node_kinds"][k]["tools"] for k in v["kinds"]), t


@pytest.fixture
def elena_store(store, monkeypatch):
    shutil.copytree(PRODUCT_TEMPLATES / "stoneford-elena.template", store / "stoneford-elena.template")
    return store / "stoneford-elena.template"


def test_in_world_shows_the_real_setting_and_writes_the_template(elena_store, store, lib, monkeypatch, tmp_path):
    from neonrp import template as TP

    b = SO.bench("tpl:stoneford-elena/elena")
    iw = b["in_world"]
    assert iw["template"] == "stoneford-elena" and iw["sid"] == "elena" and iw["v3"] and iw["variant"] == "S-judge"
    # the orchestration template the world uses says how its characters act (10-19 stage A; the pack said it before)
    assert iw["source"] == "default_variant@orchestration" and iw["per_soul"] is None and not iw["writable"]
    assert [r["depth"] for r in iw["depth"]] == ["silent", "gesture", "speak", "act", "away"]
    assert iw["prompts"][0]["table"] == "soul_step" and "judged" in iw["prompts"][0]["keys"]
    assert all(isinstance(k, str) and len(k) < 40 for p in iw["prompts"] for k in p["keys"]), "names only, never the text"
    with pytest.raises(PermissionError):
        SO.set_in_world("tpl:stoneford-elena/elena", "S-direct")   # built in: read-only
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(store))
    out = SO.set_in_world("tpl:stoneford-elena/elena", "S-direct")
    eng = json.loads((elena_store / "template.json").read_text(encoding="utf-8"))["pack"]["engine"]
    assert eng["turn"]["parallel"]["souls"]["per_soul"]["elena"] == "S-direct" and eng["turn"]["mode"] == "v3", "merged, nothing else lost"
    assert out["in_world"]["variant"] == "S-direct" and out["in_world"]["source"] == "per_soul@template"
    assert SO.in_world(soul_chat.resolve("stoneford-elena", "rowan"))["variant"] == "S-judge", "only her"
    run = tmp_path / "run"
    TP.build(TP.load(elena_store), run)
    assert json.loads((run / "game" / "meta" / "engine.json").read_text(encoding="utf-8"))["turn"]["parallel"]["souls"]["per_soul"]["elena"] == "S-direct"
    from neonrp.core import engine_config

    assert engine_config.get(run, "turn.parallel.souls.per_soul")["elena"] == "S-direct", "a run built from it plays her that way"
    for bad in ({"key": "turn.parallel.souls.per_soul.elena", "value": "S-wild"}, {"key": "turn.solve.max_ops", "value": 3},
                {"key": "turn.parallel.souls.per_soul.nobody", "value": "S-direct"}):
        assert not TP.author.apply_ops(TP.load(elena_store), [{"op": "set_engine_setting", **bad}])["ok"], bad
    SO.set_in_world("tpl:stoneford-elena/elena", "")
    assert "elena" not in json.loads((elena_store / "template.json").read_text(encoding="utf-8"))["pack"]["engine"]["turn"]["parallel"]["souls"]["per_soul"]
    assert SO.bench("lib:awu")["in_world"] is None, "a library character no world links: no in_world beat"


@pytest.mark.timeout(300)
def test_a_turn_runs_her_under_the_variant_the_bench_set(tmp_path, fake_adapter, monkeypatch):
    from test_conversation import _setup_project
    from test_system_one_turn import _world

    from neonrp.core import system_one as s1
    from neonrp.core.conversation import ConversationSession
    from neonrp.core.orchestration_trace import read_turn_traces

    monkeypatch.setenv("NEONRP_TURN_V3", "1")
    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    monkeypatch.setenv("NEONRP_HEARTBEAT", "1")
    monkeypatch.delenv("NEONRP_SOUL_VARIANT", raising=False)
    monkeypatch.delenv("NEONRP_SYSTEM_ONE", raising=False)
    root = _world(_setup_project(tmp_path))
    (root / "game" / "meta" / "engine.json").write_text(json.dumps({"turn": {"parallel": {"souls": {"per_soul": {"elena": "S-direct"}}}}}), encoding="utf-8")

    def stub(state, qs):
        out = {}
        for k in qs:
            if k.endswith(".reacts"):
                out[k] = s1.Answer("noul", 0.95 if "elena" in k else 0.1, {}, 0.9)
            if k.endswith(".depth"):
                out[k] = s1.Answer("choice", "speak", {}, 0.9)
        return out

    s1.install_stub(stub)
    fake_adapter(['{"narration": "她点点头。", "ops": []}'])
    monkeypatch.setattr("neonrp.core.light_chat.ask_soul_deliver", lambda root_, iid, q, *, asker="", **_kw: {"ok": True, "answer": "「嗯。」", "name": "艾琳娜"})

    async def _land(deltas, *, turn_seq, branch="main"):
        return "wc-var"

    try:
        with patch("neonrp.core.conversation.run_conversation_turn"), \
             patch("neonrp.core.world_agent.WorldAgent.land_turn", side_effect=_land), \
             patch("neonrp.core.engage.heartbeat_soul_run", return_value={"ok": True, "line": "…", "name": "x"}):
            res = ConversationSession(root, "test-agent", mode="play").send("你好")
    finally:
        s1.install_stub(None)
    assert res.success
    tr = read_turn_traces(root, "main", last=1)[0]
    assert tr["timing"]["soul_variants"]["si-elena"] == "S-direct"


def test_a_library_character_reads_its_beat_in_the_current_world(store, lib, monkeypatch):
    """S.world (the bench's「当前世界」) arrives as ?world=: a library character linked into that world shows its beat
    there; a world that does not link it falls back to the first that does; the write goes to the world it shows."""
    for t in ("spice-witch", "wuwu"):
        p = store / f"{t}.template" / "template.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["souls"] = [*(d.get("souls") or []), {"lib": "awu", "role": "npc"}]
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    assert SO.bench("lib:awu", world="wuwu")["in_world"]["template"] == "wuwu"
    assert SO.bench("lib:awu", world="spice-witch")["in_world"]["template"] == "spice-witch"
    assert SO.bench("lib:awu", world="stoneford-town")["in_world"]["template"] == "spice-witch", "not linked there: the first world that links it"
    assert SO.bench("tpl:wuwu/vera", world="spice-witch")["in_world"]["template"] == "wuwu", "a world's character: always its own world"
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(store))
    out = SO.set_in_world("lib:awu", "S-free", world="wuwu")
    assert out["id"] == "wuwu" and out["in_world"]["variant"] == "S-free" and out["in_world"]["sid"] == "awu"
    eng = json.loads((store / "wuwu.template" / "template.json").read_text(encoding="utf-8"))["pack"]["engine"]
    assert eng["turn"]["parallel"]["souls"]["per_soul"] == {"awu": "S-free"}
    assert "per_soul" not in json.dumps(json.loads((store / "spice-witch.template" / "template.json").read_text(encoding="utf-8")).get("pack")), "only that world"
