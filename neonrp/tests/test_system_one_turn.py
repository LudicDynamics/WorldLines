"""exp/jev-system-one — S1 plan, S2 parallel souls, S3 integrate-first, CTB tick.

「S1 到 S4 非常有道理,但设计要非常仔细;多次交互时要有『是否
需要再次沟通』的 confidence;实验另起环境和 branch,大幅提速再迁移」。
Everything here runs offline: System One is the stub backend, LLM seams are
patched, and the baseline (flag off) is asserted byte-for-byte unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from neonrp.core import ctb, system_one as s1, turn_plan as tp
from neonrp.core.conversation import ConversationSession, ConversationTurnResult
from neonrp.core.orchestration_trace import read_turn_traces
from neonrp.core.runtime_contract import set_router_execution_mode

from test_conversation import _setup_project
from test_multiagent_mode import _make_soul_dir, _write_playthrough


@pytest.fixture(autouse=True)
def _pin_v2b_loop(monkeypatch):
    """These tests cover the v2b world-agent loop; the rpg pack's own loop is v3 since 09-30 (Pack.loop)."""
    monkeypatch.setenv("NEONRP_TURN_V3", "0")


@pytest.fixture(autouse=True)
def _stub_backend(monkeypatch):
    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    monkeypatch.setenv("NEONRP_HEARTBEAT", "1")  # conftest 默认关,这里要看心跳路径
    monkeypatch.delenv("NEONRP_SYSTEM_ONE", raising=False)
    monkeypatch.delenv("NEONRP_S1_KEEP_TOOLS", raising=False)
    s1.install_stub(None)
    yield
    s1.install_stub(None)


# ── system_one adapter ────────────────────────────────────────────────


def test_question_constructors_and_stub_answers():
    qs = {
        "u": s1.noul("urgent?"),
        "d": s1.choice("dept", {"billing": "b", "tech": "t"}),
        "f": s1.score("frustration", ["calm", "annoyed", "furious"]),
    }
    assert qs["d"].to_dict()["criteria"] == {"billing": "b", "tech": "t"}
    with pytest.raises(ValueError):
        s1.choice("x", {"only": "one"})
    # default stub = unsure
    ans = s1.ask({"text": "hi"}, qs)
    assert ans["u"].value == 0.5 and ans["u"].confidence == 0.0
    assert ans["d"].value == "billing" and ans["f"].value == 1.0
    # installed stub
    s1.install_stub(lambda state, q: {"u": s1.Answer("noul", 0.95, {}, 0.9)})
    ans = s1.ask({"text": "hi"}, qs)
    assert ans["u"].yes == 0.95 and ans["d"].value == "billing", "缺的问题补 unsure"
    assert s1.last_call()["backend"] == "stub" and s1.last_call()["ok"]


def test_off_backend_returns_none_and_parse_answers(monkeypatch):
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    assert s1.ask({"a": 1}, {"u": s1.noul("x")}) is None and not s1.available()
    a = s1._parse_answer("u", s1.noul("x"), {"type": "noul", "noul": 0.9})
    assert a.yes == 0.9 and a.confidence == pytest.approx(0.8)
    c = s1._parse_answer("d", s1.choice("x", {"a": "", "b": ""}), {"choice": "b", "probabilities": {"a": 0.2, "b": 0.8}, "confidence": 0.6})
    assert c.value == "b" and c.probabilities["b"] == 0.8 and not s1.confidence_ok(c) and s1.confidence_ok(c, 0.5)
    sc = s1._parse_answer("f", s1.score("x", ["l", "m", "h"]), {"score": 1.4, "confidence": 0.9})
    assert sc.value == 1.4


def test_jev_backend_posts_once_and_caches(monkeypatch):
    monkeypatch.setenv("NEONRP_S1_BACKEND", "jev")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key-not-real")
    calls = []

    def fake_post(state, questions, *, model, timeout):
        calls.append((state, sorted(questions), model))
        return {"model": model, "usage": {"input_tokens": 12}, "answers": {"u": {"type": "noul", "noul": 0.8}}}

    monkeypatch.setattr(s1, "_post_jev", fake_post)
    s1._CACHE.clear()
    a1 = s1.ask({"t": "x"}, {"u": s1.noul("q")})
    a2 = s1.ask({"t": "x"}, {"u": s1.noul("q")})
    assert a1["u"].yes == 0.8 and a2["u"].yes == 0.8 and len(calls) == 1, "同 state 同问题走缓存"
    assert s1.last_call()["cached"] is True
    monkeypatch.setattr(s1, "_post_jev", lambda *a, **k: (_ for _ in ()).throw(TimeoutError("slow")))
    assert s1.ask({"t": "y"}, {"u": s1.noul("q")}) is None, "失败 = None,调用方回落"


# ── turn plan ─────────────────────────────────────────────────────────


def _world(root: Path) -> Path:
    """Two present souls + one away, a town map, run_state at T001/gate."""
    set_router_execution_mode(root, "multi-agent")
    _write_playthrough(
        root,
        souls=[
            {"sid": "elena", "instance_id": "si-elena", "version_hash": "v", "head_commit": "", "role": "npc"},
            {"sid": "rowan", "instance_id": "si-rowan", "version_hash": "v", "head_commit": "", "role": "npc"},
            {"sid": "mira", "instance_id": "si-mira", "version_hash": "v", "head_commit": "", "role": "npc"},
        ],
    )
    for sid, iid, name, node in (("elena", "si-elena", "艾琳娜", "T001/gate"), ("rowan", "si-rowan", "罗文", "T001/gate"), ("mira", "si-mira", "米拉", "T001/inn")):
        _make_soul_dir(root, sid, iid)
        sd = root / "souls" / f"{sid}-{iid}"
        (sd / "soul.json").write_text(json.dumps({"schema_version": 1, "sid": sid, "name": sid.title(), "name_local": name}, ensure_ascii=False), encoding="utf-8")
        (sd / "run_state.json").write_text(json.dumps({"location": node}), encoding="utf-8")
        (sd / "soul.md").write_text(f"{name}的人设。", encoding="utf-8")
    (root / "game" / "meta").mkdir(parents=True, exist_ok=True)
    (root / "game" / "meta" / "run_state.json").write_text(json.dumps({"turn_count": 2, "location": {"node": "T001/gate", "node_id": "T001", "subnode_id": "gate"}}), encoding="utf-8")
    (root / "game" / "towns" / "T001").mkdir(parents=True, exist_ok=True)
    (root / "game" / "towns" / "T001" / "town_map.json").write_text(
        json.dumps({"town_id": "T001", "nodes": [{"id": "gate", "name": "北门", "links": ["inn"]}, {"id": "inn", "name": "旅店", "links": ["gate"]}]}, ensure_ascii=False), encoding="utf-8"
    )
    pt_path = root / ".neonrp" / "playthrough.json"
    pt = json.loads(pt_path.read_text(encoding="utf-8"))
    pt["active_souls"] = ["si-elena", "si-rowan"]
    pt_path.write_text(json.dumps(pt), encoding="utf-8")
    return root


class _Understanding:
    player_node = "T001/gate"
    away_roster = (("si-mira", "T001/inn"),)


class _Intent:
    kind = "declared_action"
    declared_action = "对艾琳娜说:你还好吗"


class _Packet:
    scene_label = "北门·清晨"

    def to_prompt_block(self):
        return "scene block"


def test_questions_cover_intent_souls_exits_and_away(tmp_path):
    root = _world(_setup_project(tmp_path))
    from neonrp.core.playthrough import read_playthrough

    rows = tp.roster_rows(root, read_playthrough(root), _Understanding())
    assert [r["name"] for r in rows] == ["艾琳娜", "罗文", "米拉"] and [r["present"] for r in rows] == [True, True, False]
    exits = tp._exits(root, "T001/gate")
    assert exits == {"inn": "旅店"}
    qs = tp.build_questions(rows, exits)
    assert set(qs) >= {"intent.kind", "intent.addressee", "intent.move", "scene.tension", "soul.si-elena.reacts", "soul.si-elena.depth", "away.si-mira.stir"}
    assert "soul.si-mira.depth" not in qs, "异地的不问深度,只问 stir"
    state = tp.build_state(root, user_text="你还好吗", scene_packet=_Packet(), player_intent=_Intent(), rows=rows, exits=exits)
    assert state["present_characters"][0]["name"] == "艾琳娜" and state["exits"] == {"inn": "旅店"}


def test_plan_thresholds_addressee_and_fallback(tmp_path):
    root = _world(_setup_project(tmp_path))
    from neonrp.core.playthrough import read_playthrough

    rows = tp.roster_rows(root, read_playthrough(root), _Understanding())
    answers = {
        "intent.kind": s1.Answer("choice", "talk", {}, 0.9),
        "intent.addressee": s1.Answer("choice", "si-elena", {}, 0.9),
        "intent.move": s1.Answer("choice", "inn", {}, 0.9),
        "scene.tension": s1.Answer("score", 1.5, {}, 0.8),
        "soul.si-elena.reacts": s1.Answer("noul", 0.95, {}, 0.9),
        "soul.si-elena.depth": s1.Answer("choice", "gesture", {}, 0.9),
        "soul.si-rowan.reacts": s1.Answer("noul", 0.2, {}, 0.9),
        "soul.si-rowan.depth": s1.Answer("choice", "act", {}, 0.9),
        "away.si-mira.stir": s1.Answer("noul", 0.8, {}, 0.9),
    }
    plan = tp.plan_from_answers(rows, answers, source="stub", ms=12.0)
    assert plan.intent_kind == "talk" and plan.addressee == "si-elena"
    assert plan.move_target is None, "不是 move 意图就不采信去向"
    assert plan.depth_of("si-elena") == "speak", "被点名至少开口"
    assert plan.depth_of("si-rowan") == "silent", "反应概率低于 0.6 → 沉默"
    assert plan.souls["si-mira"].stir == 0.8 and plan.tension == pytest.approx(0.5)
    # unsure depth → speak rather than a guessed act
    answers["soul.si-rowan.reacts"] = s1.Answer("noul", 0.9, {}, 0.9)
    answers["soul.si-rowan.depth"] = s1.Answer("choice", "act", {}, 0.3)
    assert tp.plan_from_answers(rows, answers, source="stub", ms=1).depth_of("si-rowan") == "speak"
    fb = tp.fallback_plan(rows, _Intent(), "对艾琳娜说:你还好吗")
    assert fb.is_fallback and fb.depth_of("si-elena") == "act" and fb.depth_of("si-mira") == "silent" and fb.addressee == "si-elena"


def test_build_turn_plan_uses_stub_then_falls_back(tmp_path, monkeypatch):
    root = _world(_setup_project(tmp_path))
    from neonrp.core.playthrough import read_playthrough

    seen = {}

    def stub(state, qs):
        seen["state"] = state
        return {"soul.si-elena.depth": s1.Answer("choice", "act", {}, 0.95), "soul.si-elena.reacts": s1.Answer("noul", 0.9, {}, 0.9)}

    s1.install_stub(stub)
    plan = tp.build_turn_plan(root, read_playthrough(root), _Packet(), _Intent(), _Understanding(), user_text="你还好吗")
    assert plan.source == "stub" and plan.depth_of("si-elena") == "act"
    assert plan.depth_of("si-rowan") == "speak", "罗文没答 → unsure → 保底开口"
    assert seen["state"]["player_input"] == "你还好吗"
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    assert tp.build_turn_plan(root, read_playthrough(root), _Packet(), _Intent(), _Understanding(), user_text="x").is_fallback


def test_followups_need_confidence(tmp_path):
    root = _world(_setup_project(tmp_path))
    s1.install_stub(lambda state, qs: {"followup.si-elena": s1.Answer("noul", 0.9, {}, 0.95), "followup.si-rowan": s1.Answer("noul", 0.9, {}, 0.2)})
    fu = tp.plan_followups(root, [{"iid": "si-elena", "name": "艾琳娜", "kind": "act", "text": "你为什么问这个?"}, {"iid": "si-rowan", "name": "罗文", "kind": "speak", "text": "嗯。"}], user_text="你还好吗")
    assert fu["si-elena"] == 0.9 and fu["si-rowan"] == 0.5, "低置信 = 不确定,不当作要追问"


# ── the turn: S2 parallel + S3 integrate-first ────────────────────────


def _session(root: Path) -> ConversationSession:
    return ConversationSession(root, "test-agent", mode="play")


async def _land(deltas, *, turn_seq: int, branch: str = "main") -> str:
    return "wc-s1"


def test_baseline_unchanged_when_flag_off(tmp_path):
    root = _world(_setup_project(tmp_path))
    ok = ConversationTurnResult(success=True, run_id="r", assistant_message="hi", turns_used=1)
    with patch("neonrp.core.conversation.run_conversation_turn", return_value=ok) as run, patch(
        "neonrp.core.world_agent.WorldAgent.land_turn", side_effect=_land
    ), patch("neonrp.core.engage.engage_soul_run") as eng, patch("neonrp.core.engage.heartbeat_soul_run", return_value={"ok": False}) as hb:
        res = _session(root).send("你还好吗")
    assert res.success and run.call_count == 1 and eng.call_count == 0
    assert hb.call_count == 2, "老路:在场未点名的两个 soul 各一次串行心跳"
    assert read_turn_traces(root, "main", last=1)[0]["plan"] is None


def test_observe_mode_records_the_plan_and_changes_nothing(tmp_path, monkeypatch):
    root = _world(_setup_project(tmp_path))
    monkeypatch.setenv("NEONRP_SYSTEM_ONE", "observe")
    s1.install_stub(lambda state, qs: {"soul.si-elena.reacts": s1.Answer("noul", 0.9, {}, 0.9), "soul.si-elena.depth": s1.Answer("choice", "act", {}, 0.9)})
    ok = ConversationTurnResult(success=True, run_id="r", assistant_message="hi", turns_used=1)
    with patch("neonrp.core.conversation.run_conversation_turn", return_value=ok) as run, patch(
        "neonrp.core.world_agent.WorldAgent.land_turn", side_effect=_land
    ), patch("neonrp.core.engage.engage_soul_run") as eng, patch("neonrp.core.engage.heartbeat_soul_run", return_value={"ok": False}) as hb:
        _session(root).send("你还好吗")
    trace = read_turn_traces(root, "main", last=1)[0]
    assert trace["plan"]["source"] == "stub" and trace["plan"]["souls"]["si-elena"]["depth"] == "act"
    assert eng.call_count == 0 and hb.call_count == 2 and run.call_args.kwargs["disabled_tools"] == {"ask_user"}
    assert "plan_ms" in trace["timing"]


def test_s1_runs_planned_souls_in_parallel_and_world_agent_integrates(tmp_path, monkeypatch):
    root = _world(_setup_project(tmp_path))
    monkeypatch.setenv("NEONRP_SYSTEM_ONE", "1")
    monkeypatch.setenv("NEONRP_S1_ENGAGE_TURNS", "3")

    def stub(state, qs):
        if any(k.startswith("followup.") for k in qs):
            return {k: s1.Answer("noul", 0.1, {}, 0.9) for k in qs}
        return {
            "intent.kind": s1.Answer("choice", "talk", {}, 0.9),
            "intent.addressee": s1.Answer("choice", "si-elena", {}, 0.9),
            "soul.si-elena.reacts": s1.Answer("noul", 0.95, {}, 0.9),
            "soul.si-elena.depth": s1.Answer("choice", "act", {}, 0.9),
            "soul.si-rowan.reacts": s1.Answer("noul", 0.7, {}, 0.9),
            "soul.si-rowan.depth": s1.Answer("choice", "gesture", {}, 0.9),
            "away.si-mira.stir": s1.Answer("noul", 0.2, {}, 0.9),
        }

    s1.install_stub(stub)
    ok = ConversationTurnResult(success=True, run_id="r", assistant_message="艾琳娜点了点头。", turns_used=1)
    threads: set[str] = set()

    def fake_engage(root_, target, note="", *, provider=None, mode="play", max_turns=None):
        import threading

        threads.add(threading.current_thread().name)
        return {"ok": True, "iid": target, "name": "艾琳娜", "state": "completed", "digest": "艾琳娜:「我没事。」", "intended_action": "", "inner_voice": ""}

    def fake_hb(root_, ref, line):
        import threading

        threads.add(threading.current_thread().name)
        return {"ok": True, "iid": ref.instance_id, "name": "罗文", "line": "罗文抱着手臂看了一眼。"}

    with patch("neonrp.core.conversation.run_conversation_turn", return_value=ok) as run, patch(
        "neonrp.core.world_agent.WorldAgent.land_turn", side_effect=_land
    ), patch("neonrp.core.engage.engage_soul_run", side_effect=fake_engage) as eng, patch(
        "neonrp.core.engage.heartbeat_soul_run", side_effect=fake_hb
    ) as hb:
        res = _session(root).send("艾琳娜,你还好吗")
    assert res.success
    eng.assert_called_once()
    assert eng.call_args.kwargs["max_turns"] == 3 and eng.call_args.args[1] == "si-elena"
    assert hb.call_count == 1, "罗文只在 S2 里心跳一次,回合末不再串行心跳"
    assert all(t.startswith("neonrp-s2") for t in threads), "S2 在线程池里跑"
    kw = run.call_args.kwargs
    assert kw["max_turns"] == 6 and {"engage_soul", "ask_soul"} <= kw["disabled_tools"], "无需追问 → world-agent 只整合"
    wa_input = "\n".join(str(m.content) for m in kw["messages"] if getattr(m, "role", "") == "user")
    assert "[soul:si-elena] 艾琳娜:「我没事。」" in wa_input and "预判 · System One" in wa_input and "在对「艾琳娜」说话" in wa_input
    trace = read_turn_traces(root, "main", last=1)[0]
    assert trace["timing"]["souls"] == {"si-elena": "act", "si-rowan": "gesture"} and trace["timing"]["followups"] == {"si-elena": 0.1}
    assert "world_agent_ms" in trace["timing"] and trace["plan"]["intent"]["addressee"] == "si-elena"
    memo = json.loads((root / "souls" / "rowan-si-rowan" / "short-term-memo" / "recent_events.json").read_text(encoding="utf-8"))
    assert memo["events"][-1]["kind"] == "heartbeat" and "抱着手臂" in memo["events"][-1]["my_reaction"]


def test_followup_keeps_the_engage_tool(tmp_path, monkeypatch):
    root = _world(_setup_project(tmp_path))
    monkeypatch.setenv("NEONRP_SYSTEM_ONE", "1")

    def stub(state, qs):
        if any(k.startswith("followup.") for k in qs):
            return {"followup.si-elena": s1.Answer("noul", 0.9, {}, 0.95)}
        return {"soul.si-elena.reacts": s1.Answer("noul", 0.95, {}, 0.9), "soul.si-elena.depth": s1.Answer("choice", "speak", {}, 0.9), "soul.si-rowan.reacts": s1.Answer("noul", 0.1, {}, 0.9), "soul.si-rowan.depth": s1.Answer("choice", "silent", {}, 0.9)}

    s1.install_stub(stub)
    ok = ConversationTurnResult(success=True, run_id="r", assistant_message="…", turns_used=1)
    with patch("neonrp.core.conversation.run_conversation_turn", return_value=ok) as run, patch(
        "neonrp.core.world_agent.WorldAgent.land_turn", side_effect=_land
    ), patch("neonrp.core.light_chat.ask_soul_deliver", return_value={"ok": True, "iid": "si-elena", "name": "艾琳娜", "answer": "你为什么这么问?"}) as ask, patch(
        "neonrp.core.engage.heartbeat_soul_run", return_value={"ok": False}
    ) as hb:
        _session(root).send("你还好吗")
    ask.assert_called_once()
    assert hb.call_count == 0, "silent 的罗文零 LLM"
    assert run.call_args.kwargs["disabled_tools"] == {"ask_user"}, "TA 反问了 → 允许 world-agent 追问"
    memo = json.loads((root / "souls" / "elena-si-elena" / "short-term-memo" / "recent_events.json").read_text(encoding="utf-8"))
    assert memo["events"][-1]["kind"] == "spoke"


def test_s1_fallback_plan_still_parallelises_present_souls(tmp_path, monkeypatch):
    """No System One at all: the plan is 'everyone acts' — parallel, tools kept
    off only because nobody could ask for a follow-up (fallback → no followup call)."""
    root = _world(_setup_project(tmp_path))
    monkeypatch.setenv("NEONRP_SYSTEM_ONE", "1")
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    ok = ConversationTurnResult(success=True, run_id="r", assistant_message="…", turns_used=1)
    with patch("neonrp.core.conversation.run_conversation_turn", return_value=ok) as run, patch(
        "neonrp.core.world_agent.WorldAgent.land_turn", side_effect=_land
    ), patch("neonrp.core.engage.engage_soul_run", return_value={"ok": True, "name": "x", "state": "completed", "digest": "d"}) as eng, patch(
        "neonrp.core.engage.heartbeat_soul_run", return_value={"ok": False}
    ) as hb:
        _session(root).send("看看四周")
    assert eng.call_count == 2 and hb.call_count == 0
    assert read_turn_traces(root, "main", last=1)[0]["plan"]["source"] == "fallback"
    assert {"engage_soul", "ask_soul"} <= run.call_args.kwargs["disabled_tools"]


# ── CTB scheduler ─────────────────────────────────────────────────────


def test_ctb_gauges_fill_by_speed_and_order_is_deterministic(tmp_path):
    s = ctb.CTBScheduler()
    s.upsert("si-a", name="A", speed=1.0)
    s.upsert("si-b", name="B", speed=0.5)
    s.upsert("si-c", name="C", speed=0.0)
    assert s.next_up()[0].iid == "si-a" and s.eta("si-a") == pytest.approx(60.0) and s.eta("si-c") is None
    assert s.tick(30) == []
    ready = s.tick(30)
    assert [a.iid for a in ready] == ["si-a"], "A 满槽,B 半槽"
    s.after_action("si-a", ctb.COST_ACT)
    assert s.actors["si-a"].gauge == 0.0 and s.actors["si-a"].last_acted_at == 60
    ready = s.tick(60)
    assert [a.iid for a in ready] == ["si-a", "si-b"] or [a.iid for a in ready] == ["si-b", "si-a"]
    s.save(tmp_path)
    s2 = ctb.CTBScheduler.load(tmp_path)
    assert s2.now == 120 and s2.actors["si-b"].speed == 0.5


def test_plan_offscene_actions_uses_s1_stir_and_budget():
    s = ctb.CTBScheduler()
    for iid in ("si-a", "si-b", "si-c"):
        s.upsert(iid)
    acts = ctb.plan_offscene_actions(s, minutes=90, stirs={"si-a": 1.0, "si-b": 0.9, "si-c": 0.05}, budget=1)
    assert acts == [("si-a", "act")] or acts == [("si-a", "speak")]
    assert s.actors["si-c"].gauge < ctb.GAUGE_FULL, "没人期待它动的角色慢慢攒"
    acts2 = ctb.plan_offscene_actions(s, minutes=30, budget=2)
    assert any(iid == "si-b" for iid, _ in acts2)


def test_failed_jev_falls_back_to_an_llm_judge(monkeypatch):
    """Jev fails (timeout / HTTP / quota) → the same questions to an LLM judge → only then None."""
    import json as _json

    from neonrp.core import system_one as s1

    class _Res:
        def __init__(self, text):
            self.message = type("M", (), {"content": text})()

    class _Judge:
        calls = 0

        def chat(self, msgs):
            _Judge.calls += 1
            return _Res(_json.dumps({"follow": {"noul": 0.9, "confidence": 0.8}}))

    def _boom(*a, **k):
        raise RuntimeError("jev down")

    monkeypatch.setenv("NEONRP_S1_BACKEND", "jev")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key-not-real")  # a pinned Jev with no key is not tried at all (10-25)
    monkeypatch.setattr(s1, "_post_jev", _boom)
    s1._CACHE.clear()
    q = {"follow": s1.noul("她会跟着走吗?")}
    assert s1.ask({"t": "x1"}, q) is None  # middle step off (conftest): the old chain
    monkeypatch.setenv("NEONRP_S1_LLM_FALLBACK", "1")
    monkeypatch.setattr(s1, "LLM_ADAPTER_FACTORY", lambda: _Judge())
    a = s1.ask({"t": "x2"}, q)
    assert a is not None and a["follow"].value == 0.9 and _Judge.calls == 1
    assert s1.last_call()["fallback"] == "llm" and "jev down" in str(s1.last_call()["primary_error"])


def test_fast_judge_available_only_for_jev_proxy_stub(monkeypatch):
    """10-01: slow / absent judges keep judgments off the critical path (souls write their own fields, settle runs after the reply)."""
    from neonrp.core import system_one as s1

    for b, want in (("stub", True), ("llm", False), ("off", False)):
        monkeypatch.setenv("NEONRP_S1_BACKEND", b)
        assert s1.fast_judge_available() is want, b
    monkeypatch.setenv("NEONRP_S1_BACKEND", "jev")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key-not-real")
    monkeypatch.setattr(s1, "quota_blocked", lambda: True)
    assert s1.fast_judge_available() is False
