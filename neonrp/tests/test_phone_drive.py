"""小手机编排(10-18 soul-drive,docs/planning/SOUL-DRIVE-1018.md)—— 私有层的 phone 插件(nodes/phone.py),没有私有层时整份跳过
(requires_private.txt)。

参数是小手机编排自己的(私有层 phone/orch.json,阶段 B 10-21;不再挂在角色编排上)。
(a) 说过的带回世界:下一回合开始时,这一局每个角色在小手机上(同模板 · 同 sid)还没带过的消息 → 她这一局的记忆(by: phone)+ 主持的
收件箱(<phone sid>);只带一次;不改世界变量;开关 = carry(0 = 关)。有折叠用折叠,没折到的取原话。
(b) 小邀约:invite_daily(默认 0 = 关),答应了的下一回合带回去。
(c) 订阅的角色(TEMPLATE-LAYERS-1019 §2.3):按节奏记账(上限 3、不超过当天剩下的次数),点进去按顺序补跑;一次 = tick → 行为拍 →
世界执行(其他角色异地执行,world_exec)→ 世界卡 → 她可能发一条消息(附世界卡;安静时段不发);每天 6 次世界执行;聊天里
[go …] 触发一次;局忙 = 这件事排着,下一次 tick 或玩家这一局下一回合先结。假模型,不联网。"""
from __future__ import annotations

import copy
import json
import shutil
import time
from pathlib import Path

import pytest

from _paths import PRODUCT_TEMPLATES
from neonrp import template as TP
from neonrp.core import graph_test as G
from neonrp.core import node_kinds, player_data, sdk, soul_chat, soul_tick, turn_v3
from neonrp.core.llm import LLMTurnResult, Message
from neonrp.core.paths import get_data_dir_name
from neonrp.core.registry import load_registry

P = node_kinds.module_of("phone")


class Fake:
    def __init__(self, *raws: str):
        self.raws, self.calls = list(raws) or ["嗯,好。"], []

    def chat(self, messages, tools=None):
        self.calls.append([m.content for m in messages])
        raw = self.raws.pop(0) if len(self.raws) > 1 else self.raws[0]
        return LLMTurnResult(message=Message(role="assistant", content=raw), finished=True, usage={"total_tokens": 5})


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = tmp_path / "store"
    shutil.copytree(PRODUCT_TEMPLATES / "wuwu.template", s / "wuwu.template")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(s))
    return s


def _run(store: Path, tmp_path: Path) -> Path:
    root = tmp_path / "wuwu-run"
    TP.build(TP.load(store / "wuwu.template"), root)
    return root


def _vera(root: Path) -> tuple[str, Path]:
    iid, s = next((i, s) for i, s in player_data.run_souls(root).items() if s["sid"] == "vera")
    return iid, Path(s["dir"])


def _events(sdir: Path) -> list[dict]:
    p = sdir / "short-term-memo" / "recent_events.json"
    return (json.loads(p.read_text(encoding="utf-8")).get("events") or []) if p.is_file() else []


def _state(root: Path) -> tuple:
    rs = (root / get_data_dir_name(root) / "meta" / "run_state.json").read_text(encoding="utf-8")
    return rs, {k: v.value for k, v in load_registry(root).variables.items()}


# ── (a) ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_phone_talk_reaches_her_memory_and_the_host_not_the_world(store, tmp_path):
    root = _run(store, tmp_path)
    iid, sdir = _vera(root)
    before = _state(root)
    soul_chat.send("wuwu", "vera", text="明天陪我去码头看看那艘旧船吧", lang="zh", adapter=Fake("好啊,傍晚去。"))
    out = P.carry(root)
    assert [o["sid"] for o in out] == ["vera"]
    mine = [e for e in _events(sdir) if e.get("by") == "phone"]
    assert any("码头看看那艘旧船" in e["event"] for e in mine) and any("傍晚去" in e["event"] for e in mine)
    host = sdk.render_pack(sdk.pack(root))
    assert "<phone vera>" in host and "码头看看那艘旧船" in host, "the host sees it next turn, as her side"
    assert "傍晚去" in sdk.render_pack(sdk.pack(root, viewer=iid)), "her own beat remembers it"
    assert _state(root) == before, "no variable, no run_state changed"
    assert P.carry(root) == [], "carried once"
    soul_chat.send("wuwu", "vera", text="记得带灯", lang="zh", adapter=Fake("带着呢。"))
    again = P.carry(root)
    assert len(again) == 1 and all("码头" not in x for x in again[0]["lines"]) and any("带灯" in x for x in again[0]["lines"])


def test_no_phone_talk_writes_nothing_into_the_run(store, tmp_path):
    """No thread with anyone of the run: the turn's carry touches no file of the run (a turn writes only what it changes)."""
    root = _run(store, tmp_path)
    _, sdir = _vera(root)
    before = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
    assert P.carry(root) == []
    assert sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()) == before
    assert not (root / get_data_dir_name(root) / "meta" / "phone_carry.json").exists()


def test_the_fold_is_her_side_and_replaces_the_raw_lines(store, tmp_path):
    root = _run(store, tmp_path)
    _, sdir = _vera(root)
    soul_chat.send("wuwu", "vera", text="今晚井边见?", lang="zh", adapter=Fake("行,我早点到。"))
    fake = Fake("- 我答应了今晚去井边见玩家\n- 我打算早点到")
    rec = P.fold("wuwu", "vera", adapter=fake, lang="zh")
    assert rec["notes"] == ["我答应了今晚去井边见玩家", "我打算早点到"]
    assert "今晚井边见?" in fake.calls[0][0] and "最多 3 条" in fake.calls[0][0]
    assert P.fold("wuwu", "vera", adapter=fake, lang="zh") is None, "nothing new since the last fold"
    assert P.carry(root)[0]["lines"] == ["我答应了今晚去井边见玩家", "我打算早点到"]
    assert [e["event"] for e in _events(sdir) if e.get("by") == "phone"] == ["(通过手机)我答应了今晚去井边见玩家", "(通过手机)我打算早点到"]


def _conf(monkeypatch, **kw):
    """The phone orchestration's parameters for this test (its own file otherwise)."""
    monkeypatch.setattr(P, "orchestration", lambda: {"params": {**P._DEFAULTS, **kw}})


def test_switch_off_in_the_phone_orchestration(store, tmp_path, monkeypatch):
    _conf(monkeypatch, carry=0)
    root = _run(store, tmp_path)
    _, sdir = _vera(root)
    soul_chat.send("wuwu", "vera", text="在吗", lang="zh", adapter=Fake("在。"))
    assert P.carry(root) == []
    assert not [e for e in _events(sdir) if e.get("by") == "phone"] and "<phone" not in sdk.render_pack(sdk.pack(root))
    assert P.fold("wuwu", "vera", adapter=Fake("x")) is None


def test_the_next_turn_hands_it_to_the_host(tmp_path, monkeypatch):
    """A real turn (graph_test, stub model): the host's input carries the phone line; the world moves as without it."""
    seen: list[str] = []
    orig = G._ScriptAdapter.chat

    def spy(self, messages, *a, **k):
        seen.append("\n".join(str(m.content) for m in messages))
        return orig(self, messages, *a, **k)

    monkeypatch.setattr(G._ScriptAdapter, "chat", spy)
    graph = _no_plan_graph()

    def turn(root: Path) -> dict:
        res = G.run({"template": "stoneford-elena", "graph": graph, "lines": ["我四处看看"], "root": str(root), "record": True})
        return res["steps"][0]["digest"]["state"]

    control = turn(tmp_path / "control")
    assert not any("<phone" in s for s in seen)
    seen.clear()
    soul_chat.send("stoneford-elena", "elena", text="今晚北门见,别迟到", lang="zh", adapter=Fake("知道了,我会早点去。"))
    root = tmp_path / "phone"
    assert turn(root) == control, "the world moved the same: the phone changed nothing in it"
    assert any("<phone elena>" in s and "北门见" in s for s in seen), "the host's input has the phone line"
    sdir = next(Path(s["dir"]) for s in player_data.run_souls(root).values() if s["sid"] == "elena")
    assert any(e.get("by") == "phone" and "北门见" in e["event"] for e in _events(sdir))


def _lib_soul(folder: str, sid: str, name: str, persona: str) -> Path:
    from neonrp.core import souls

    d = souls.SOUL_HOME / folder
    d.mkdir(parents=True)
    (d / "soul.json").write_text(json.dumps({"schema_version": 1, "sid": sid, "name": sid, "name_local": name}, ensure_ascii=False), encoding="utf-8")
    (d / "soul.md").write_text(persona + "\n", encoding="utf-8")
    return d


def _link(store: Path, folder: str, sid: str) -> None:
    p = store / "wuwu.template" / "template.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["souls"] = [*(d.get("souls") or []), {"lib": folder, "sid": sid, "role": "npc"}]
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def test_a_library_character_linked_into_the_world_carries_its_phone_talk(store, tmp_path):
    """The library's own thread (lib:<folder>) comes back into a run of a world that links it: into its folder in the run
    when the run made it a soul, else the host's inbox only."""
    _lib_soul("awu", "awu", "阿雾", "码头卖鱼的姑娘,说话很冲。")
    _link(store, "awu", "awu")
    root = _run(store, tmp_path)
    soul_chat.send("lib:awu", "awu", text="明早给我留两条鱼", lang="zh", adapter=Fake("行,早点来。"))
    _lib_soul("ah-shan", "ahshan", "阿山", "灯塔的守夜人。")
    _link(store, "ah-shan", "ahshan")  # linked after the run was made: not one of its souls
    soul_chat.send("lib:ah-shan", "ahshan", text="今晚灯塔见", lang="zh", adapter=Fake("好。"))
    before = _state(root)
    out = {o["sid"]: o for o in P.carry(root)}
    assert set(out) == {"awu", "ahshan"}
    host = sdk.render_pack(sdk.pack(root))
    assert "<phone awu>" in host and "两条鱼" in host and "<phone ahshan>" in host and "灯塔见" in host
    inrun = {s["sid"]: s for s in player_data.run_souls(root).values()}
    assert "awu" in inrun, "the run made her a soul"
    assert any(e.get("by") == "phone" and "两条鱼" in e["event"] for e in _events(Path(inrun["awu"]["dir"])))
    assert "ahshan" not in inrun
    assert _state(root) == before, "nothing in the world changed"
    assert P.carry(root) == [], "carried once (the library thread's own cursor)"


# ── 隔空联系(10-19:玩家不在角色身边,现代靠手机,奇幻靠一种传话的法术或信物)──────────────────────────────────

def test_every_phone_prompt_says_you_are_apart_through_the_worlds_medium(store, tmp_path, monkeypatch):
    fake = Fake("嗯。")
    soul_chat.send("wuwu", "vera", text="在吗", lang="zh", adapter=fake)
    assert "你们不在一起" in fake.calls[0][0] and "通过手机" in fake.calls[0][0], "a world without a fantasy tag: the phone"
    shutil.copytree(PRODUCT_TEMPLATES / "stoneford-town.template", store / "stoneford-town.template")
    f2 = Fake("嗯。")
    soul_chat.send("stoneford-town", "elena", text="在吗", lang="zh", adapter=f2)
    assert "一种隔空传话的法术或信物" in f2.calls[0][0], "a fantasy world (its card tags): a spell or a token"
    p = store / "wuwu.template" / "template.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["phone"] = {"medium": {"zh": "港务所的旧电台", "en": "the harbour office's old radio"}}
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    f3 = Fake("嗯。")
    soul_chat.send("wuwu", "vera", text="还在吗", lang="en", adapter=f3)
    assert "through the harbour office's old radio" in f3.calls[0][0], "the template's own phone.medium, in the chat's language"
    root = _run(store, tmp_path)
    lines = P.carry(root)[0]["lines"]
    assert any("通过港务所的旧电台" in x for x in lines) and "通过港务所的旧电台隔空说过话" in sdk.render_pack(sdk.pack(root)), "what comes back says how"


def test_the_first_line_and_a_tick_are_apart_too(store, tmp_path):
    g = Fake("<greeting>\n你好\n</greeting>")
    soul_chat.greet("wuwu", "vera", lang="zh", adapter=g)
    assert "你们不在一起" in g.calls[0][0]
    player_data._add("characters", {"sid": "vera", "name": "薇拉", "world": "wuwu", "how": "test", "memory": "fresh"}, ("sid", "world"))
    c = soul_chat.resolve("wuwu", "vera")
    t = Fake('{"did": "我在工坊", "mood": "", "message": "在忙"}')
    soul_tick.run(c, adapter=t, lang="zh", force=True)
    assert "你们不在一起" in t.calls[0][0] and "通过手机" in t.calls[0][0]


def test_a_reply_that_puts_the_player_beside_her_is_recorded_not_blocked(store):
    out = soul_chat.send("wuwu", "vera", text="冷", lang="zh", adapter=Fake("来,我把围巾递给你。"))
    assert out["messages"][0]["text"] == "来,我把围巾递给你。", "never blocked"
    rows = [json.loads(x) for x in (player_data.HOME / player_data.player_id() / "phone_lint.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["code"] == "phone.copresence" and "递给你" in rows[-1]["words"] and rows[-1]["sid"] == "vera"
    soul_chat.send("wuwu", "vera", text="好", lang="zh", adapter=Fake("我晚点打给你。"))
    assert len((player_data.HOME / player_data.player_id() / "phone_lint.jsonl").read_text(encoding="utf-8").splitlines()) == 1


# ── 在线主动消息(10-19:连线的时候 TA 知道你在线;不是 tick,不触发世界执行)────────────────────────────────

def _online_model(monkeypatch, *raws):
    fake = Fake(*raws)
    monkeypatch.setattr(soul_chat, "_adapter", lambda rt=None: fake)
    return fake


def test_online_she_may_text_and_it_writes_only_the_thread(store, tmp_path, monkeypatch):
    root = _run(store, tmp_path)
    files = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
    monkeypatch.setattr(turn_v3, "solve_turn", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no world execution")))
    fake = _online_model(monkeypatch, "<msg>看到你上线了~</msg>\n<msg>我刚从码头回来</msg>")
    out = soul_chat.presence("wuwu", "vera", lang="zh")
    assert [m["text"] for m in out["messages"]] == ["看到你上线了~", "我刚从码头回来"] and all(m["origin"] == "online" for m in out["messages"])
    assert "玩家刚上线" in fake.calls[0][1] and "你们不在一起" in fake.calls[0][0], "she knows they just came online; still apart"
    assert sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()) == files, "the run is untouched"
    assert not (player_data.HOME / player_data.player_id() / "ticks.json").exists(), "not a tick: the tick's counters are not touched"
    assert soul_chat.presence("wuwu", "vera", lang="zh")["messages"] == [] and len(fake.calls) == 1, "not again before the gap"
    assert any("码头回来" in x for x in P.carry(root)[0]["lines"]), "what she said online comes back like any phone talk"


def test_online_she_can_choose_to_say_nothing_and_never_while_typing_or_just_answered(store, monkeypatch):
    monkeypatch.setattr(P, "ONLINE_GAP_S", (0, 0))  # every heartbeat is a look: only the rules below keep her quiet
    t0 = time.time()
    fake = _online_model(monkeypatch, "<none/>")
    assert soul_chat.presence("wuwu", "vera", lang="zh", now=t0)["messages"] == [] and len(fake.calls) == 1, "the model may send nothing"
    assert soul_chat.presence("wuwu", "vera", lang="zh", typing=True, now=t0 + 1)["messages"] == [] and len(fake.calls) == 1, "typing: no call at all"
    soul_chat.send("wuwu", "vera", text="我在想事情", lang="zh", adapter=Fake("嗯。"))
    assert soul_chat.presence("wuwu", "vera", lang="zh", now=time.time() + 5)["messages"] == [], "the player just wrote: the chat answers that"
    assert len(fake.calls) == 1


def test_online_at_most_six_an_hour_and_offline_nothing(store, monkeypatch):
    fake = _online_model(monkeypatch, "<msg>在吗</msg>")
    t0 = time.mktime(time.strptime(time.strftime("%Y-%m-%d %H:00:00"), "%Y-%m-%d %H:%M:%S")) + 1
    got = sum(len(soul_chat.presence("wuwu", "vera", lang="zh", now=t0 + i * 301)["messages"]) for i in range(11))
    assert got == 6, "ONLINE_HOURLY"
    n = len(soul_chat.read_thread("wuwu", "vera"))
    assert len(soul_chat.read_thread("wuwu", "vera")) == n, "offline = no heartbeat = nothing (the phone sends none while hidden)"


# ── (b) ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_invite_is_off_by_default(store):
    fake = Fake("好。\n[invite 今晚去码头看船]")
    out = soul_chat.send("wuwu", "vera", text="无聊", lang="zh", adapter=fake)
    assert [m["kind"] for m in out["messages"]] == ["text"], "no invitation while the node does not allow one"
    assert "[invite" not in fake.calls[0][0]


def test_invite_daily_cap_answer_and_carry(store, tmp_path, monkeypatch):
    _conf(monkeypatch, invite_daily=1)
    root = _run(store, tmp_path)
    fake = Fake("好。\n[invite 今晚去码头看船]")
    out = soul_chat.send("wuwu", "vera", text="无聊", lang="zh", adapter=fake)
    assert "[invite" in fake.calls[0][0] and "最多还能约 1 次" in fake.calls[0][0]
    inv = next(m for m in out["messages"] if m["kind"] == "invite")
    assert inv["text"] == "今晚去码头看船" and inv["status"] == "open" and inv["from"] == "soul"
    fake2 = Fake("嗯。\n[invite 明早一起去集市]")
    out2 = soul_chat.send("wuwu", "vera", text="还有呢", lang="zh", adapter=fake2)
    assert "[invite" not in fake2.calls[0][0] and [m["kind"] for m in out2["messages"]] == ["text"], "one a day"
    P.carry(root)  # what came before the answer
    assert soul_chat.answer("wuwu", "vera", inv["id"], "yes")["message"]["status"] == "accepted"
    assert P.carry(root)[0]["lines"] == ["我通过手机约玩家:今晚去码头看船——玩家答应了"]
    assert "答应了" in sdk.render_pack(sdk.pack(root))


# ── (c) subscribed characters (stage B) ──────────────────────────────────────────────────────────────────────────

VERA_I, KITE_I, MO_I = "si-vera0001", "si-silverkite0001", "si-oldmo0001"


def _own(sid: str, name: str = "") -> dict:
    player_data._add("characters", {"sid": sid, "name": name or sid, "world": "wuwu", "how": "test", "memory": "fresh"}, ("sid", "world"))
    return soul_chat.resolve("wuwu", sid)


def _play(store, tmp_path, monkeypatch, *, prose="<lines>\n薇拉去了工坊,修好了码头的绞盘;银鸢在灯塔上看雾。\n</lines>"):
    """A run in the plays folder, the world's model scripted, everyone elsewhere answering through a stub soul_turn."""
    from neonrp import worlds
    from neonrp.core import mechanics

    plays = tmp_path / "plays"
    monkeypatch.setattr(worlds, "PLAYS_HOME", plays)
    root = G._world({"template": str(store / "wuwu.template"), "root": str(plays / "wuwu-1")}, tmp_path)
    world = G._ScriptAdapter([prose, "<vars>\ntown.alert = 1\nplayer.gold = 9\n</vars>\n<files>\n</files>"])
    monkeypatch.setattr(turn_v3, "ADAPTER_FACTORY", lambda root, provider: world)
    away: list[str] = []
    real = mechanics.get

    def get(root, seam):
        if seam != "soul_turn":
            return real(root, seam)

        def soul_turn(root, iid, **kw):
            away.append(iid)
            return {"ok": True, "name": iid, "text": "我在灯塔上看雾", "proposed_move": "T001/lighthouse" if iid == KITE_I else None}
        return soul_turn

    monkeypatch.setattr(mechanics, "get", get)
    monkeypatch.setattr(P, "quiet_now", lambda now=None: False)
    return root, away


def _owed(c, minutes: int, cadence: int = 60):
    """Subscribed ``minutes`` ago at ``cadence``: what is owed by now."""
    st = P._sub(c)
    st.update(on=True, cadence=cadence, anchor=time.time() - minutes * 60, owed=0)
    P._save_sub(c, st)


def test_the_phone_orchestration_is_its_own(store):
    from neonrp.core import soul_orchestration as SO

    d = SO.describe()
    assert "act" not in d["node_kinds"] and "carry" not in d["node_kinds"]["chat"]["params"] and "ticked" not in d["on"], \
        "nothing of the phone hangs on the characters' orchestration any more"
    assert "phone" not in node_kinds.kinds() and "phone" in node_kinds.seams(), "no world orchestration lists it as a node"
    g = P.orchestration()
    assert g["id"] == "phone" and set(g["nodes"]) >= {"chat", "tick", "act", "online"}
    assert g["params"]["world_exec_daily"] == 6 and g["params"]["cadence_default"] == 60 and g["params"]["owed_max"] == 3
    subs = g["params"]["subscriptions"]
    assert (subs["free"], subs["story"], subs["supporter"], subs["vivid"]) == (1, 3, 3, 5), "10-21: Voyager follows 5"


def test_subscribe_one_free_three_on_traveler_only_your_own(store):
    vera, mo = _own("vera", "薇拉"), _own("oldmo", "老莫")
    trial = soul_chat.resolve("wuwu", "silverkite")
    assert soul_chat.subscription("wuwu", "silverkite", {"on": True})["why"] == "not_yours" and trial["access"] != "obtained"
    assert soul_chat.subscription("wuwu", "vera", {"on": True})["on"] is True
    r = soul_chat.subscription("wuwu", "oldmo", {"on": True})
    assert r["ok"] is False and r["why"] == "limit" and r["limit"] == 1, "free: one at a time"
    assert soul_chat.subscription("wuwu", "oldmo", {"on": True, "plan": "traveler"})["on"] is True, "traveler: three"
    assert soul_chat.subscription("wuwu", "vera", {"cadence": 45})["why"] == "cadence"
    assert soul_chat.subscription("wuwu", "vera", {"cadence": 30})["cadence"] == 30
    assert soul_chat.subscription("wuwu", "vera")["on"] is True and P.subscribed(vera) and P.subscribed(mo)


def test_the_plan_comes_from_the_accounts_billing_tier(store, monkeypatch):
    from neonrp.core import worldlines_auth

    _own("vera", "薇拉"), _own("oldmo", "老莫")
    monkeypatch.setattr(worldlines_auth, "entitlements", lambda ttl=60.0: {"plan": "story", "tier": "story"})
    assert P.plan() == "story"
    soul_chat.subscription("wuwu", "vera", {"on": True})
    assert soul_chat.subscription("wuwu", "oldmo", {"on": True})["on"] is True, "story (Traveler): three at a time"
    monkeypatch.setattr(worldlines_auth, "entitlements", lambda ttl=60.0: None)
    assert P.plan({"plan": "vivid"}) == "vivid" and P.plan() == "free", "no account: what the app says, else free"


def test_owed_by_cadence_at_most_three_and_never_past_the_days_left(store):
    vera = _own("vera", "薇拉")
    soul_chat.subscription("wuwu", "vera", {"on": True})
    _owed(vera, 95, cadence=30)
    assert soul_chat.subscription("wuwu", "vera")["owed"] == 3
    _owed(vera, 600, cadence=30)
    assert soul_chat.subscription("wuwu", "vera")["owed"] == 3, "the bubble stops at 3"
    st = P._sub(vera)
    st["execs"] = 5
    P._save_sub(vera, st)
    _owed(vera, 600, cadence=30)
    assert soul_chat.subscription("wuwu", "vera")["owed"] == 1, "one world execution left today"
    assert soul_chat.subscription("wuwu", "vera", {"on": False})["owed"] == 0, "off: nothing owed"


def test_catch_up_runs_the_owed_in_order_world_exec_card_and_message(store, tmp_path, monkeypatch):
    root, away = _play(store, tmp_path, monkeypatch)
    vera = _own("vera", "薇拉")
    soul_chat.subscription("wuwu", "vera", {"on": True})
    _owed(vera, 125)  # two owed at 1 h
    gold = _state(root)[1]["player.gold"]
    me = Fake('{"did": "我在琢磨那台坏绞盘", "mood": "", "message": "我不该在这里发"}', '<act where="T001/workshop">去工坊把绞盘修好</act>',
              "<msg>绞盘修好啦,码头那边都听见了</msg>")
    out = P.catchup(vera, adapter=me, lang="zh")
    assert out["done"] == 1 and out["left"] == 1, "one owed turn per call: 「补上 1 / 2」"
    acted = out["step"]["acted"]
    assert acted["ok"] and sorted(away) == sorted([KITE_I, MO_I]), "everyone else took her turn elsewhere, once"
    after = _state(root)[1]
    assert after["town.alert"] == 1 and after["player.gold"] == gold, "the world settled it with the player away"
    card = json.loads((root / get_data_dir_name(root) / "meta" / "world_results.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert card["id"] == acted["card"] and card["by"] == "tick:vera"
    msg = out["step"]["message"]
    assert msg["text"] == "绞盘修好啦,码头那边都听见了" and msg["attach"] == {"kind": "world_card", "run": root.name, "id": card["id"]}
    texts = [m.get("text") for m in soul_chat.read_thread("wuwu", "vera")]
    assert "我不该在这里发" not in texts, "the message comes after the world execution, not from the tick's own call"
    assert f"world_result:{card['id']}" in sdk.render_pack(sdk.pack(root)), "the host sees it next turn"
    assert P.catchup(vera, adapter=Fake('{"did": "又去码头", "mood": "", "message": ""}', "<none/>"), lang="zh")["left"] == 0


def test_a_busy_run_stops_the_catch_up_and_keeps_it_owed(store, tmp_path, monkeypatch):
    from neonrp.core import run_lock

    root, away = _play(store, tmp_path, monkeypatch)
    vera = _own("vera", "薇拉")
    soul_chat.subscription("wuwu", "vera", {"on": True})
    _owed(vera, 125)
    lk = run_lock.of(root)
    lk.acquire()
    try:
        out = P.catchup(vera, adapter=Fake("x"), lang="zh")
    finally:
        lk.release()
    assert out["why"] == "busy" and out["done"] == 0 and out["left"] == 2 and away == []


def test_an_action_the_run_could_not_take_is_settled_first_by_the_players_next_turn(store, tmp_path, monkeypatch):
    from neonrp.core import run_lock

    root, away = _play(store, tmp_path, monkeypatch)
    vera = _own("vera", "薇拉")
    soul_chat.subscription("wuwu", "vera", {"on": True})
    other = run_lock.of(tmp_path / "another-run")  # a turn running in this process: no world execution now
    other.acquire()
    try:
        out = soul_tick.run(vera, adapter=Fake('{"did": "想去码头", "mood": "", "message": ""}', '<act where="T001/berth7">去码头搬货</act>'),
                            lang="zh", force=True)
    finally:
        other.release()
    assert out["acted"]["why"] == "deferred" and _state(root)[1]["town.alert"] == 0
    assert soul_chat.subscription("wuwu", "vera")["pending"] is True
    P._PhoneNode().before_turn(root)  # the player's next turn in that run
    assert _state(root)[1]["town.alert"] == 1 and soul_chat.subscription("wuwu", "vera")["pending"] is False


def test_six_world_executions_a_day(store, tmp_path, monkeypatch):
    root, away = _play(store, tmp_path, monkeypatch)
    vera = _own("vera", "薇拉")
    soul_chat.subscription("wuwu", "vera", {"on": True})
    st = P._sub(vera)
    st["execs"] = 6
    P._save_sub(vera, st)
    out = soul_tick.run(vera, adapter=Fake('{"did": "x", "mood": "", "message": ""}'), lang="zh", force=True)
    assert out["acted"] == {"ok": False, "why": "daily_max"} and away == []


def test_quiet_hours_no_message_the_world_goes_on(store, tmp_path, monkeypatch):
    root, away = _play(store, tmp_path, monkeypatch)
    monkeypatch.setattr(P, "quiet_now", lambda now=None: True)
    vera = _own("vera", "薇拉")
    soul_chat.subscription("wuwu", "vera", {"on": True})
    me = Fake('{"did": "x", "mood": "", "message": ""}', '<act>去工坊修绞盘</act>', "<msg>修好了</msg>")
    out = soul_tick.run(vera, adapter=me, lang="zh", force=True)
    assert out["acted"]["ok"] and not out.get("message") and len(me.calls) == 2, "no message call in the quiet hours"
    assert _state(root)[1]["town.alert"] == 1


def test_a_chat_that_decides_to_go_runs_one_tick_with_her_words(store, tmp_path, monkeypatch):
    root, away = _play(store, tmp_path, monkeypatch)
    monkeypatch.setattr(P, "GO_ASYNC", False)
    vera = _own("vera", "薇拉")
    soul_chat.subscription("wuwu", "vera", {"on": True})
    me = Fake("好,我这就去。\n[go 去7号码头找银鸢]", '<act where="T001/berth7">去7号码头找银鸢</act>', "<none/>")
    out = soul_chat.send("wuwu", "vera", text="能帮我问问银鸢吗", lang="zh", adapter=me)
    assert "[go" in me.calls[0][0], "a subscribed character may decide to go"
    assert [m["text"] for m in out["messages"]] == ["好,我这就去。"], "the [go] line is not shown"
    assert "去7号码头找银鸢" in me.calls[1][0], "her tick's doing is what she said: no tick call of its own"
    card = json.loads((root / get_data_dir_name(root) / "meta" / "world_results.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert card["by"] == "tick:vera" and soul_chat.subscription("wuwu", "vera")["left_today"] == 5, "it counts toward the day"


def test_not_subscribed_go_and_ticks_do_nothing_in_the_world(store, tmp_path, monkeypatch):
    root, away = _play(store, tmp_path, monkeypatch)
    monkeypatch.setattr(P, "GO_ASYNC", False)
    vera = _own("vera", "薇拉")
    me = Fake("好,我去。\n[go 去码头]")
    out = soul_chat.send("wuwu", "vera", text="去码头吗", lang="zh", adapter=me)
    assert "[go" not in me.calls[0][0] and [m["text"] for m in out["messages"]] == ["好,我去。"] and len(me.calls) == 1
    assert "acted" not in soul_tick.run(vera, adapter=Fake('{"did": "x", "mood": "", "message": ""}'), lang="zh", force=True)
    assert not (root / get_data_dir_name(root) / "meta" / "world_results.jsonl").exists() and away == []


def test_off_clears_what_is_owed_and_what_waits(store):
    vera = _own("vera", "薇拉")
    soul_chat.subscription("wuwu", "vera", {"on": True})
    _owed(vera, 200)
    st = P._sub(vera)
    st["pending"] = {"run": "x", "iid": VERA_I, "text": "去码头"}
    P._save_sub(vera, st)
    r = soul_chat.subscription("wuwu", "vera", {"on": False})
    assert r["owed"] == 0 and r["pending"] is False


def test_her_tick_reads_where_she_is_in_the_run(store, tmp_path, monkeypatch):
    root, away = _play(store, tmp_path, monkeypatch)
    vera = _own("vera", "薇拉")
    soul_chat.subscription("wuwu", "vera", {"on": True})
    t = Fake('{"did": "我在港务所发呆", "mood": "", "message": ""}', "<act></act>")
    soul_tick.run(vera, adapter=t, lang="zh", force=True)
    assert "你现在在你的世界里的位置" in t.calls[0][1] and "港务所" in t.calls[0][1] and "## simple world" not in t.calls[0][1]


def test_a_plot_character_from_the_creation_desk(store, tmp_path, monkeypatch):
    """mine_N01 — a plot npc entry without a soul folder: chats, comes back, and once followed acts in the world."""
    t = store / "wuwu.template"
    (t / "plots" / "mine").mkdir(parents=True)
    (t / "plots" / "mine" / "plot.json").write_text(json.dumps({"id": "mine", "title": "我的", "entries": {
        "mine_N01": {"class": "npc", "name": "阿岩", "parent": "T001/berth7", "props": {"persona": "码头的搬运工,话少,力气大"}}}}, ensure_ascii=False), encoding="utf-8")
    d = json.loads((t / "template.json").read_text(encoding="utf-8"))
    d["plots"] = [*(d.get("plots") or []), "plots/mine"]
    (t / "template.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    root, away = _play(store, tmp_path, monkeypatch, prose="<lines>\n阿岩把最后一箱货搬上了船。\n</lines>")
    c = _own("mine_N01", "阿岩")
    assert c["npc"] and c["access"] == "obtained"
    fake = Fake("嗯。")
    soul_chat.send("wuwu", "mine_N01", text="明早帮我搬箱子?", lang="zh", adapter=fake)
    assert "码头的搬运工" in fake.calls[0][0], "it speaks from what the plot says of it"
    assert [o["sid"] for o in P.carry(root)] == ["mine_N01"] and "<phone mine_N01>" in sdk.render_pack(sdk.pack(root))
    soul_chat.subscription("wuwu", "mine_N01", {"on": True})
    out = soul_tick.run(c, adapter=Fake('{"did": "我在码头歇着", "mood": "", "message": ""}', '<act where="T001/berth7">把最后一箱货搬上船</act>', "<none/>"),
                        lang="zh", force=True)
    assert out["acted"]["ok"], out
    assert _state(root)[1]["town.alert"] == 1


def _no_plan_graph() -> dict:
    from neonrp.template import v3

    g = v3.graph_of("stoneford-elena")["graph"]
    d = {k: g[k] for k in ("id", "start", "nodes", "edges")}
    d["nodes"] = {k: v for k, v in d["nodes"].items() if k != "plan"}
    d["edges"] = [e for e in d["edges"] if "plan" not in (e["from"], e["to"])]
    d["start"] = "resolve"
    return d


def test_the_phone_list_shows_whats_owed_and_a_message_opens_its_world_card(store, tmp_path, monkeypatch):
    root, away = _play(store, tmp_path, monkeypatch)
    vera = _own("vera", "薇拉")
    soul_chat.subscription("wuwu", "vera", {"on": True})
    _owed(vera, 125)
    row = next(r for r in soul_chat.souls("zh")["souls"] if r["sid"] == "vera")
    assert row["phone"] == {"on": True, "owed": 2}
    out = P.catchup(vera, adapter=Fake('{"did": "x", "mood": "", "message": ""}', '<act>去工坊修绞盘</act>', "<msg>修好了</msg>"), lang="zh")
    att = out["step"]["message"]["attach"]
    card = soul_chat.world_card(att["run"], att["id"])
    assert card["id"] == att["id"] and card["items"][0]["kind"] == "act"
    with pytest.raises(soul_chat.ChatError):
        soul_chat.world_card("../etc", att["id"])


def test_the_local_desk_edits_the_phone_orchestration(store):
    """GET / lint / save / reset (the front-end desk's 「编排」 tab): only what differs from the default is kept, out of
    range is refused and nothing is written, the edit is what the orchestration runs with, reset removes it."""
    g = P.bench("get")
    assert g["source"] == "private" and g["params"]["world_exec_daily"] == 6 and set(g["describe"]["node_kinds"]) >= {"chat", "tick", "act", "online"}
    assert {x["msg"].split(":")[0] for x in P.bench("lint", {"params": {"carry": 9, "quiet_hours": [25, 8]}})["lint"]} == {"carry", "quiet_hours"}
    bad = P.bench("save", {"params": {**g["params"], "carry": 9}})
    assert bad["ok"] is False and not P.overlay_path().exists()
    ok = P.bench("save", {"params": {**g["params"], "world_exec_daily": 4}})
    assert ok["ok"] and ok["source"] == "local" and json.loads(P.overlay_path().read_text(encoding="utf-8"))["params"] == {"world_exec_daily": 4}
    assert P.conf("world_exec_daily") == 4, "the edit is what runs"
    assert P.bench("reset")["source"] == "private" and P.conf("world_exec_daily") == 6 and not P.overlay_path().exists()
