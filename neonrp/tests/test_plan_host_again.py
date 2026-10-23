"""The planning beat's second host round (niko 10-14: 「平均一拍 10 秒」): after the characters answered, System One
decides whether the host speaks again — not by default; that round reads a digest, not the whole context, and its reply
is capped. Needs the private layer (tests/requires_private.txt).

Model calls are stubs that sleep a scaled-down time each (a host round 0.06 s, a character 0.04 s, a System One judgment
0.01 s), so the before / after is in calls and estimated time, not real latency.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

from neonrp.core import system_one as s1

_TPL = Path("src/neonrp/templates/stoneford-elena")
HOST_S, SOUL_S, S1_S = 0.06, 0.04, 0.01


def _install(tmp_path: Path) -> Path:
    root = tmp_path / "w"
    shutil.copytree(_TPL, root)
    (root / ".neonrp").mkdir(exist_ok=True)
    shutil.copy(root / "playthrough.json", root / ".neonrp" / "playthrough.json")
    return root


@pytest.fixture
def talk(tmp_path, monkeypatch):
    """A planning beat with one character present who is handed the mic: who the host was called with, and how long."""
    from neonrp.core import plan_loop
    from neonrp.core.registry import load_registry

    root = _install(tmp_path)
    reg = load_registry(root)
    her = next(e for e in reg.of_class("soul") if e.parent == reg.player_location)
    log: list[dict] = []

    def host(root_, system, user):
        time.sleep(HOST_S)
        log.append({"who": "host", "user": user, "cap": plan_loop._HOST_STREAM.get("max_tokens")})
        if len([x for x in log if x["who"] == "host"]) == 1:
            return f"<lines>\n好,先听听{her.name}怎么说。\n</lines>\n<mic>\n{her.name}: 你觉得呢?\n</mic>\nnext: wait"
        return "<lines>\n那就这么定。\n</lines>\nnext: wait"

    def soul(root_, iid, q, **kw):
        time.sleep(SOUL_S)
        log.append({"who": iid})
        return {"ok": True, "answer": "<lines>\n「我跟你去。」\n</lines>\n<draft>跟着去码头</draft>"}

    monkeypatch.setattr(plan_loop, "_host", host)
    monkeypatch.setattr("neonrp.core.light_chat.ask_soul_deliver", soul)
    yield root, her, log, plan_loop
    s1.install_stub(None)


def _judge(yes: float | None, log: list[dict]):
    def stub(state, qs):
        time.sleep(S1_S)
        log.append({"who": "s1", "qs": sorted(qs), "state": state})
        out = {q: s1.Answer("noul", 0.1, {}, 0.9) for q in qs}  # settled / overrode / gap: no
        if yes is not None and "host_again" in qs:
            out["host_again"] = s1.Answer("noul", yes, {}, 0.9)
        return out
    return stub


def test_no_second_host_round_unless_system_one_says_so(talk, monkeypatch):
    root, her, log, plan_loop = talk
    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    s1.install_stub(_judge(0.1, log))
    out = plan_loop.step(root, user_text=f"@{her.name} 我们去码头。", last_narration="")
    hosts = [x for x in log if x["who"] == "host"]
    assert len(hosts) == 1, "the characters answered and the host has nothing to add: no host-2"
    assert any(x["who"] == "s1" and "host_again" in x["qs"] for x in log)
    s1_state = next(x["state"] for x in log if x["who"] == "s1" and "host_again" in x["qs"])
    assert s1_state["replies"][0]["who"] == her.name and "我跟你去" in s1_state["replies"][0]["said"]
    beat = out["beat"]
    assert [c["who"] for c in beat["calls"]] == ["host", her.id, "s1:host_again"] and beat["rounds"] == 1
    assert beat["host_again"] == 0.1 and beat["board"][her.name] == "跟着去码头"
    assert "我跟你去" in out["narration"].splitlines()[-1]  # her answer is the last word: the talk falls back to the player


def test_no_judge_means_no_second_round(talk, monkeypatch):
    root, her, log, plan_loop = talk
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    out = plan_loop.step(root, user_text=f"@{her.name} 我们去码头。", last_narration="")
    assert len([x for x in log if x["who"] == "host"]) == 1 and out["beat"]["host_again"] is None


def test_when_it_must_the_host_speaks_again_on_a_digest_with_a_short_reply(talk, monkeypatch):
    root, her, log, plan_loop = talk
    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    s1.install_stub(_judge(0.9, log))
    out = plan_loop.step(root, user_text=f"@{her.name} 我们去码头。", last_narration="雨停了,码头那边有灯。")
    hosts = [x for x in log if x["who"] == "host"]
    assert len(hosts) == 2 and [c["who"] for c in out["beat"]["calls"]][:4] == ["host", her.id, "s1:host_again", "host-2"]
    first, second = hosts
    assert first["cap"] is None and second["cap"] == 400  # turn.plan_loop_host2_max_tokens
    assert len(second["user"]) < len(first["user"]) / 2, (len(second["user"]), len(first["user"]))  # a digest
    assert "我们去码头" in second["user"] and "我跟你去" in second["user"] and "跟着去码头" in second["user"]
    assert "<mic>" not in second["user"]  # the round as said and set, not the host's raw reply
    assert plan_loop._HOST_STREAM["max_tokens"] is None  # the cap is the second round's only


def test_a_read_still_gets_its_round(talk, monkeypatch):
    """The host asked to read something: the next round is where it uses the answer — no judge asked."""
    root, her, log, plan_loop = talk
    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    s1.install_stub(_judge(0.1, log))
    n = {"i": 0}

    def host(root_, system, user):
        n["i"] += 1
        log.append({"who": "host"})
        return ("<lines>\n我查一下。\n</lines>\n[read T001]\nnext: wait" if n["i"] == 1 else "<lines>\n查到了。\n</lines>\nnext: wait")

    monkeypatch.setattr(plan_loop, "_host", host)
    plan_loop.step(root, user_text="镇上有什么?", last_narration="")
    assert n["i"] == 2 and not any(x["who"] == "s1" and "host_again" in x.get("qs", []) for x in log)


def test_the_cap_reaches_the_adapter_and_stops_the_continuation(tmp_path, monkeypatch):
    from neonrp.core import plan_loop, turn_v3
    from neonrp.core.llm import LLMTurnResult, Message

    class Ad:
        max_tokens = 4096

        def chat(self, messages, tools=None):
            seen.append((self.max_tokens, getattr(self, "continue_on_length", True)))
            return LLMTurnResult(message=Message(role="assistant", content="好。"), finished=True)

    seen: list = []
    monkeypatch.setattr(turn_v3, "_adapter", lambda *a, **k: Ad())
    plan_loop._host(tmp_path, "s", "u")
    plan_loop._HOST_STREAM["max_tokens"] = 400
    try:
        plan_loop._host(tmp_path, "s", "u")
    finally:
        plan_loop._HOST_STREAM["max_tokens"] = None
    assert seen == [(4096, True), (400, False)]


def test_before_and_after_in_calls_and_time(talk, monkeypatch):
    """The 10-14 shape (host → her → host-2) against the new one (host → her → S1): one model round fewer, by the stub
    clock ~HOST_S − S1_S faster per talk; real calls ~10 s host vs < 1 s Jev."""
    root, her, log, plan_loop = talk
    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    runs = {}
    for name, yes in (("before", 0.9), ("after", 0.1)):  # "before" = System One always says speak again (old default)
        log.clear()
        plan_loop.clear(root)
        s1.install_stub(_judge(yes, log))
        out = plan_loop.step(root, user_text=f"@{her.name} 我们去码头。", last_narration="")
        # time by the stub clock (what each call made costs), not the wall clock: under a loaded full run (-n 8) the
        # engine's own work between calls swamps a 0.06 s difference (10-18)
        est = sum(HOST_S if x["who"] == "host" else S1_S if x["who"] == "s1" else SOUL_S for x in log)
        runs[name] = {"llm": len([x for x in log if x["who"] in ("host", her.id)]), "s": est,
                      "calls": [c["who"] for c in out["beat"]["calls"]]}
    assert runs["before"]["llm"] == 3 and runs["after"]["llm"] == 2, runs
    assert runs["before"]["s"] - runs["after"]["s"] == pytest.approx(HOST_S), runs   # one host round fewer, the same judgments
