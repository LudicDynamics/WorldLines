"""The open engine's seams for a phone plugin (10-18 soul-drive): node_kinds.call_all · soul_chat (chat_system /
chat_reply / chat_sent · answer) · soul_tick (soul_ticked) · the turn (before_turn) · soul_orchestration.extend.
The open engine itself brings no such plugin: without one every seam is a no-op. A test plugin here, stub models."""
from __future__ import annotations

import copy
import json
import shutil

import pytest

from _paths import PRODUCT_TEMPLATES
from neonrp.core import graph_test as G
from neonrp.core import node_kinds, soul_chat, soul_tick
from neonrp.core import soul_orchestration as SO
from neonrp.core.llm import LLMTurnResult, Message


class Fake:
    def __init__(self, raw):
        self.raw, self.calls = raw, []

    def chat(self, messages, tools=None):
        self.calls.append([m.content for m in messages])
        return LLMTurnResult(message=Message(role="assistant", content=self.raw), finished=True, usage={})


class Probe:
    kind = "zz-probe"

    def __init__(self):
        self.seen = []

    def before_turn(self, root):
        self.seen.append(("before_turn", root.name))

    def chat_system(self, c, node, lang):
        return "\nPROBE-RULE"

    def greet_system(self, c, lang):
        return "\nPROBE-GREET"

    def tick_system(self, c, lang):
        return "\nPROBE-TICK"

    def chat_reply(self, c, node, raw, lang):
        keep = [ln for ln in raw.splitlines() if not ln.startswith("[probe")]
        return "\n".join(keep), [{"kind": "probe", "text": "p", "status": "open"}] if len(keep) < len(raw.splitlines()) else []

    def chat_sent(self, c, node, saved, *, adapter=None, lang="zh"):
        self.seen.append(("chat_sent", [m["kind"] for m in saved]))

    def soul_ticked(self, c, out, *, adapter=None, lang="zh"):
        return {"probed": out["did"]}


@pytest.fixture
def probe(monkeypatch, tmp_path):
    s = tmp_path / "store"
    shutil.copytree(PRODUCT_TEMPLATES / "wuwu.template", s / "wuwu.template")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(s))
    p = node_kinds.register(Probe())
    yield p
    node_kinds.unregister(p.kind)


def test_call_all_runs_every_hook_and_survives_a_broken_one(probe):
    class Bad:
        kind = "zz-bad"

        def chat_system(self, *a):
            raise RuntimeError("boom")

    node_kinds.register(Bad())
    try:
        assert node_kinds.call_all("chat_system", None, None, "zh") == ["\nPROBE-RULE"]
        assert node_kinds.call_all("no_such_hook") == []
    finally:
        node_kinds.unregister("zz-bad")


def test_chat_seams_and_answer(probe):
    fake = Fake("好。\n[probe x]")
    out = soul_chat.send("wuwu", "vera", text="嗨", lang="zh", adapter=fake)
    assert "PROBE-RULE" in fake.calls[0][0]
    assert [(m["from"], m["kind"]) for m in out["messages"]] == [("soul", "text"), ("soul", "probe")]
    assert probe.seen == [("chat_sent", ["text", "probe"])]
    pid = out["messages"][1]["id"]
    r = soul_chat.answer("wuwu", "vera", pid, "no")
    assert r["message"]["status"] == "declined" and r["messages"][0]["kind"] == "answer" and r["messages"][0]["of"] == "probe"
    with pytest.raises(soul_chat.ChatError) as e:
        soul_chat.answer("wuwu", "vera", pid, "yes")
    assert e.value.status == 409
    with pytest.raises(soul_chat.ChatError) as e:
        soul_chat.answer("wuwu", "vera", out["messages"][0]["id"], "yes")
    assert e.value.status == 404, "a plain message waits for no answer"
    soul_chat.send("wuwu", "vera", text="再说", lang="zh", adapter=fake)
    assert "薇拉:p" in fake.calls[1][1] and "玩家:p" not in fake.calls[1][1], "the answer record is not in the chat's history"


def test_tick_seam(probe, tmp_path):
    from neonrp.core import souls  # a library character ticks (the player's own)

    d = souls.SOUL_HOME / "awu"
    d.mkdir(parents=True)
    (d / "soul.json").write_text(json.dumps({"sid": "awu", "name": "Awu"}), encoding="utf-8")
    (d / "agents").mkdir()
    (d / "agents" / "orchestration.json").write_text(json.dumps({"nodes": {"tick": {"kind": "tick", "title": "tick", "tools": ["memo.write"]}},
        "add": [{"id": "chat>tick:clock", "from": "chat", "to": "tick", "on": {"tick": "clock"}}]}), encoding="utf-8")
    assert "awu" in soul_chat.library_souls()
    c = soul_chat.resolve("lib:awu", "")
    soul_tick.set_on(c, True)
    tick = Fake('{"did": "swept the stall", "mood": "", "message": ""}')
    out = soul_tick.run(c, adapter=tick)
    assert out["ran"] and out["probed"] == "swept the stall"
    assert "PROBE-TICK" in tick.calls[0][0], "tick_system: a plugin's rule for a tick"
    g = Fake("<greeting>\nhi\n</greeting>")
    soul_chat.greet("lib:awu", "", adapter=g)
    assert "PROBE-GREET" in g.calls[0][0], "greet_system: a plugin's rule for the first line"


def test_before_turn_seam_runs_and_the_turn_is_the_same(probe, tmp_path):
    res = G.run({"template": "stoneford-elena", "lines": ["我四处看看"], "root": str(tmp_path / "run")})
    assert ("before_turn", "run") in probe.seen
    assert res["steps"][0]["nodes"]


def test_extend_adds_to_the_soul_vocabulary_hidden_when_private_off(monkeypatch):
    monkeypatch.setenv("NEONRP_PRIVATE", "on")
    SO.describe()  # load the plugins first: what they extend is restored as it was
    saved = copy.deepcopy(SO._EXT)
    try:
        SO.extend(kind="zz", spec={"doc": "x", "tools": [], "params": {"n": 1}, "steps": []}, ranges={"n": (0, 2)}, on={"zz_on": "x"})
        SO.extend(kind="chat", params={"zz_knob": 1}, ranges={"zz_knob": (0, 3)})
        d = SO.describe()
        assert d["node_kinds"]["zz"]["ranges"] == {"n": [0, 2]} and d["node_kinds"]["chat"]["params"]["zz_knob"] == 1 and "zz_on" in d["on"]
        assert SO.node_params({"zz_knob": 3}, "chat")["zz_knob"] == 3 and SO.node_params({"zz_knob": 9}, "chat")["zz_knob"] == 1
        monkeypatch.setenv("NEONRP_PRIVATE", "off")
        d = SO.describe()
        assert "zz" not in d["node_kinds"] and "zz_knob" not in d["node_kinds"]["chat"]["params"] and "zz_on" not in d["on"]
        assert SO.default_graph()["nodes"]["chat"] == {"kind": "chat", "title": "chat", "tools": ["sticker"], **SO.NODE_KINDS["chat"]["params"]}
    finally:
        SO._EXT.clear()
        SO._EXT.update(saved)


def test_one_writer_per_run(tmp_path):
    from neonrp.commands.web import WebRuntime
    from neonrp.core import run_lock

    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    assert run_lock.of(a) is run_lock.of(tmp_path / "a" / ".." / "a") and run_lock.of(a) is not run_lock.of(b)
    assert WebRuntime(a, "world-agent")._busy is run_lock.of(a), "the web turn holds the same lock"
    with run_lock.try_hold(a) as ok:
        assert ok and run_lock.busy()
        with run_lock.try_hold(a, alone=False) as again:
            assert not again, "never two writers on one run"
        with run_lock.try_hold(b) as other:
            assert not other, "alone: no write while any turn runs"
    assert not run_lock.busy()


# ── stage B (10-21): seam-only plugins · a tick a plugin drives · subscription / catch-up ────────────────────────────

class TickProbe:
    kind = "zz-tick"

    def __init__(self):
        self.again = None

    def tick_context(self, c, lang):
        return "## where you are\nPROBE-PLACE"

    def tick_owns_message(self, c):
        return True

    def soul_ticked(self, c, out, *, adapter=None, lang="zh"):
        self.again = soul_tick.run(c, adapter=adapter, force=True, did="x")  # her tick is still under way
        return {"acted": True, "message": {"text": "PROBE-AFTER", "attach": {"kind": "world_card", "id": "wr-1"}}}

    def phone_subscription(self, c, body, *, lang=None):
        return {"sid": c["sid"], "body": body}


def _awu():
    from neonrp.core import souls

    d = souls.SOUL_HOME / "awu"
    d.mkdir(parents=True, exist_ok=True)
    (d / "soul.json").write_text(json.dumps({"sid": "awu", "name": "Awu"}), encoding="utf-8")
    return soul_chat.resolve("lib:awu", "")


def test_a_seam_plugin_is_no_node_kind(monkeypatch):
    p = node_kinds.register_seams(TickProbe())
    try:
        assert "zz-tick" not in node_kinds.kinds() and "zz-tick" in node_kinds.seams()
        assert node_kinds.call_all("tick_owns_message", None) == [True]
        assert node_kinds.module_of("zz-tick") is not None
    finally:
        node_kinds.unregister(p.kind)
    assert "zz-tick" not in node_kinds.seams()


def test_a_plugin_driven_tick_one_at_a_time_message_after(tmp_path):
    c = _awu()
    p = node_kinds.register_seams(TickProbe())
    try:
        out = soul_tick.run(c, force=True, did="went to the pier")  # no model call: what she does is known; no tick node, no switch
        assert out["ran"] and out["did"] == "went to the pier" and out["acted"] is True
        assert p.again == {"ran": False, "why": "running"}, "one tick at a time per character, the plugin's step included"
        assert out["message"]["text"] == "PROBE-AFTER" and out["message"]["attach"]["id"] == "wr-1" and out["message"]["origin"] == "tick"
        tick = Fake('{"did": "swept", "mood": "", "message": "OWN-MSG"}')
        out2 = soul_tick.run(c, adapter=tick, force=True)
        assert "PROBE-PLACE" in tick.calls[0][1] and "## simple world" not in tick.calls[0][1], "tick_context instead of the simple world"
        assert "OWN-MSG" not in [m.get("text") for m in soul_chat.read_thread("lib:awu", "awu")], "the plugin owns the message"
        assert out2["ran"]
    finally:
        node_kinds.unregister(p.kind)


def test_force_still_needs_her_to_be_the_players(probe):
    c = soul_chat.resolve("wuwu", "vera")  # only tried out
    assert soul_tick.run(c, force=True, did="x")["ran"] is False


def test_subscription_and_catchup_need_a_plugin(monkeypatch):
    monkeypatch.setenv("NEONRP_PRIVATE", "off")  # the open engine alone: no phone orchestration
    _awu()
    with pytest.raises(soul_chat.ChatError) as e:
        soul_chat.subscription("lib:awu", "")
    assert e.value.status == 404
    with pytest.raises(soul_chat.ChatError):
        soul_chat.catchup("lib:awu", "")
    p = node_kinds.register_seams(TickProbe())
    try:
        assert soul_chat.subscription("lib:awu", "", {"on": True}) == {"sid": "awu", "body": {"on": True}}
    finally:
        node_kinds.unregister(p.kind)


def test_chat_reply_plugins_chain(probe):
    class Second:
        kind = "zz-second"

        def chat_reply(self, c, node, raw, lang):
            assert "[probe" not in raw, "it gets what the plugin before it left"
            return raw.replace("好", "好的"), []

    node_kinds.register_seams(Second())
    try:
        out = soul_chat.send("wuwu", "vera", text="嗨", lang="zh", adapter=Fake("好。\n[probe x]"))
        assert [m.get("text") for m in out["messages"]] == ["好的。", "p"]
    finally:
        node_kinds.unregister("zz-second")
