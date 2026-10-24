"""The write-down after the prose in two answers (10-22): the straight one lands at once, the thinking one corrects
the state from the background — unless the player moves on first (cut), the run is being written (cut), or it runs past
its timeout; the beat's own rulings win over both; the player is told what happened (core/write_down_async)."""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest
from _paths import PRODUCT_TEMPLATES

from neonrp import template as TP
from neonrp.core import llm_openai, run_lock, turn_v3
from neonrp.core import write_down_async as wda
from neonrp.core.registry import load_registry


def _world(tmp_path):
    root = tmp_path / "w"
    TP.build(PRODUCT_TEMPLATES / "stoneford-elena.template", root)
    return root


class _Fake:
    """Prose first; then the write-down: the thinking call (thinking on) and the straight one (off) answer differently."""

    base_url = "https://api.deepseek.com/v1"  # a provider with a thinking switch

    def __init__(self, prose, fast, slow, slow_gate=None):
        self.prose, self.fast, self.slow, self.gate = prose, fast, slow, slow_gate
        self.calls = 0
        self.lock = threading.Lock()

    def chat(self, messages, tools=None):
        with self.lock:
            self.calls += 1
            first = self.calls == 1
        if first:
            text = self.prose
        elif llm_openai._THINK.get():
            if self.gate is not None:
                self.gate.wait(10)
            text = self.slow
        else:
            text = self.fast
        return SimpleNamespace(message=SimpleNamespace(content=text), usage={})


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("NEONRP_V3_SOLVE", "narrate")
    monkeypatch.setenv("NEONRP_TRANSITION_THINKING", "1")
    monkeypatch.setenv("NEONRP_TRANSITION_ASYNC", "1")
    root = _world(tmp_path)
    events: list[dict] = []
    wda.listen(root, events.append)
    yield root, events
    wda.listen(root, None)
    turn_v3.ADAPTER_FACTORY = None


def _solve(root, fake, monkeypatch, **kw):
    monkeypatch.setattr(turn_v3, "ADAPTER_FACTORY", lambda root_, provider: fake)
    return turn_v3.solve_turn(root, user_text="住下", provider=None, turn=1, soul_reports=[], **kw)


def _settle(root, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        p = wda.pending(root)
        if p is None or p.state != "running":
            return
        time.sleep(0.05)
    raise AssertionError("the background write-down never finished")


def _kinds(events):
    return [e["kind"] for e in events]


def test_the_straight_answer_lands_now_and_the_thinking_one_corrects_it(world, monkeypatch):
    root, events = world
    reg = load_registry(root)
    gold, clock = reg.variables["player.gold"].value, reg.variables["time.clock"].value
    fake = _Fake("<lines>\n你在通铺躺下,一觉睡到夜深。\n</lines>", f"<vars>\nplayer.gold = {gold - 3}\n</vars>",
                 f"<vars>\nplayer.gold = {gold - 3}\ntime.clock = 23:40\n</vars>", slow_gate=threading.Event())
    out = _solve(root, fake, monkeypatch)
    assert out["apply"].variables["player.gold"] == gold - 3 and out["apply"].variables["time.clock"] == clock  # the straight answer
    assert _kinds(events) == ["write_down.pending"]
    from neonrp.core import orchestration_trace as ot

    ot.append_turn_trace(root, "main", ot.TurnTrace(turn_seq=1, apply={"applied": [], "variables": dict(out["apply"].variables)}))
    fake.gate.set()
    _settle(root)
    reg = load_registry(root)
    assert reg.variables["time.clock"].value == "23:40" and reg.variables["player.gold"].value == gold - 3
    done = events[-1]
    assert done["kind"] == "write_down.corrected" and any(a.get("var") == "time.clock" for a in done["applied"])
    rec = ot.read_turn_traces(root, "main")[-1]  # the turn's record ends on the corrected state (/traces, replays)
    assert rec["write_down"]["state"] == "corrected" and rec["apply"]["variables"]["time.clock"] == "23:40"
    assert any(a.get("corrected") and a.get("var") == "time.clock" for a in rec["apply"]["applied"])


def test_the_player_moving_on_cuts_the_correction(world, monkeypatch):
    root, events = world
    clock = load_registry(root).variables["time.clock"].value
    gate = threading.Event()
    _solve(root, _Fake("<lines>\n夜深了。\n</lines>", "<vars>\n</vars>", "<vars>\ntime.clock = 23:40\n</vars>", gate), monkeypatch)
    wda.cut(root)  # the next turn starts before the thinking answer is back
    gate.set()
    time.sleep(0.5)
    assert load_registry(root).variables["time.clock"].value == clock
    assert _kinds(events) == ["write_down.pending", "write_down.cut"]


def test_a_correction_that_comes_while_the_beat_finishes_waits_and_lands(world, monkeypatch):
    """10-23 real deepseek: the thinking answer came 0.5–0.8 s after turn_done, while the beat's own tail still held the
    run's lock — 7 of 11 were dropped as busy. It waits for the lock now and lands when the tail lets go."""
    root, events = world
    gate = threading.Event()
    _solve(root, _Fake("<lines>\n夜深了。\n</lines>", "<vars>\n</vars>", "<vars>\ntime.clock = 23:40\n</vars>", gate), monkeypatch)
    lk = run_lock.of(root)
    lk.acquire()  # the beat's tail
    try:
        gate.set()
        time.sleep(0.4)
        assert wda.pending(root).state == "running"  # waiting, not dropped
    finally:
        lk.release()
    _settle(root)
    assert load_registry(root).variables["time.clock"].value == "23:40"
    assert events[-1]["kind"] == "write_down.corrected"


def test_a_new_line_while_the_correction_waits_cuts_it(world, monkeypatch):
    root, events = world
    clock = load_registry(root).variables["time.clock"].value
    gate = threading.Event()
    _solve(root, _Fake("<lines>\n夜深了。\n</lines>", "<vars>\n</vars>", "<vars>\ntime.clock = 23:40\n</vars>", gate), monkeypatch)
    with run_lock.of(root):  # the next line: it takes the run's lock, then cuts (ConversationSession.send)
        gate.set()
        time.sleep(0.2)
        wda.cut(root)
        _settle(root)
    assert load_registry(root).variables["time.clock"].value == clock
    assert [e for e in events if e["kind"] == "write_down.cut"] == [{"kind": "write_down.cut", "turn": 1, "why": "next_turn"}]


def test_a_run_held_past_the_wait_drops_the_correction_as_busy(world, monkeypatch):
    root, events = world
    monkeypatch.setenv("NEONRP_TRANSITION_SLOW_LOCK_WAIT_S", "0.3")
    clock = load_registry(root).variables["time.clock"].value
    gate = threading.Event()
    _solve(root, _Fake("<lines>\n夜深了。\n</lines>", "<vars>\n</vars>", "<vars>\ntime.clock = 23:40\n</vars>", gate), monkeypatch)
    with run_lock.of(root):
        gate.set()
        _settle(root)
    assert load_registry(root).variables["time.clock"].value == clock
    assert events[-1] == {"kind": "write_down.cut", "turn": 1, "why": "busy"}


def test_the_careful_model_defaults_to_the_accounts_entitlement(tmp_path, monkeypatch):
    """10-23: the platform's careful write-down is live — ``auto`` unless the world (or the env) names one; ``""`` in the
    world's settings = always the beat's own model."""
    from neonrp.core import beat_budget

    monkeypatch.delenv("NEONRP_TRANSITION_SLOW_MODEL", raising=False)
    root = _world(tmp_path)
    assert beat_budget.transition_slow_model(root) == "auto"
    assert wda.slow_spec(root) == ""  # not signed in: the beat's own model
    monkeypatch.setattr(beat_budget, "_cfg", lambda r, k: "" if k == "turn.transition_slow_model" else None)
    assert beat_budget.transition_slow_model(root) == ""
    monkeypatch.setenv("NEONRP_TRANSITION_SLOW_MODEL", "worldlines:gemini-3.8-flash")
    assert beat_budget.transition_slow_model(root) == "worldlines:gemini-3.8-flash"


def test_a_thinking_answer_past_its_timeout_is_dropped(world, monkeypatch):
    root, events = world
    monkeypatch.setenv("NEONRP_TRANSITION_SLOW_TIMEOUT_S", "0.3")
    clock = load_registry(root).variables["time.clock"].value
    gate = threading.Event()
    _solve(root, _Fake("<lines>\n夜深了。\n</lines>", "<vars>\n</vars>", "<vars>\ntime.clock = 23:40\n</vars>", gate), monkeypatch)
    _settle(root)
    gate.set()
    time.sleep(0.3)
    assert load_registry(root).variables["time.clock"].value == clock
    assert _kinds(events)[-1] == "write_down.timeout"


def test_the_beats_rulings_win_over_the_thinking_answer():
    """A variable the beat's own rulings set (a tool's verdict, an agreed payment) is not touched by the correction."""
    reg = SimpleNamespace(variables={k: SimpleNamespace(value=v) for k, v in {"player.gold": 15, "player.hp": 24}.items()},
                          resolve=lambda x: x)
    p = wda.Pending(root=None, turn=1, future=None, timeout=90, base=[{"op": "add", "var": "player.gold", "delta": -3}],
                    fast_ops=[{"op": "add", "var": "player.gold", "delta": -3}], pre={"player.gold": 18, "player.hp": 24},
                    post={"player.gold": 15, "player.hp": 24})
    ops = wda.correction_ops(p, [{"op": "set", "var": "player.gold", "value": 9}, {"op": "set", "var": "player.hp", "value": 20}], reg)
    assert ops == [{"op": "set", "var": "player.hp", "value": 20}]


def test_what_only_the_straight_answer_set_goes_back_and_what_changed_since_is_left_alone():
    reg = SimpleNamespace(variables={k: SimpleNamespace(value=v) for k, v in
                                     {"a": 2, "b": 5, "c": 9, "location": "T001/inn"}.items()}, resolve=lambda x: x)
    p = wda.Pending(root=None, turn=1, future=None, timeout=90, base=[],
                    fast_ops=[{"op": "set", "var": "a", "value": 2}, {"op": "set", "var": "c", "value": 7}],
                    pre={"a": 1, "b": 5, "c": 1, "location": "T001/inn"}, post={"a": 2, "b": 5, "c": 7, "location": "T001/inn"})
    ops = wda.correction_ops(p, [{"op": "set", "var": "b", "value": 6}, {"op": "set", "var": "c", "value": 3}], reg)
    # a: only the straight answer set it → back to 1; b: the thinking answer's 6; c: changed since (9 ≠ 7) → left alone
    assert ops == [{"op": "set", "var": "a", "value": 1}, {"op": "set", "var": "b", "value": 6}]


def test_the_thinking_answer_can_run_on_another_model(world, monkeypatch):
    """turn.transition_slow_model: the straight answer on the beat's model, the correction on the named preset (10-22:
    deepseek straight, gemini-3.8-flash via Cloudflare behind)."""
    root, events = world
    from neonrp.core import hub_publish

    clock = load_registry(root).variables["time.clock"].value
    other = _Fake("", "", "<vars>\ntime.clock = 22:10\n</vars>")
    other.calls = 1  # its first call is the write-down, not prose
    asked: list[str] = []
    monkeypatch.setattr(hub_publish, "adapter_for_preset", lambda name: (asked.append(name), other)[1])
    monkeypatch.setattr(wda, "_ADAPTERS", {})
    monkeypatch.setenv("NEONRP_TRANSITION_SLOW_MODEL", "cf-gemini")
    beat = _Fake("<lines>\n夜深了。\n</lines>", "<vars>\n</vars>", "<vars>\ntime.clock = 03:00\n</vars>")
    out = _solve(root, beat, monkeypatch)
    assert out["apply"].variables["time.clock"] == clock
    _settle(root)
    assert load_registry(root).variables["time.clock"].value == "22:10"  # the other model's answer, not the beat model's
    assert asked == ["cf-gemini"] and events[-1].get("model") == "cf-gemini"


def test_a_slow_model_that_cannot_be_built_leaves_the_beats_own(world, monkeypatch):
    root, _events = world
    from neonrp.core import hub_publish

    def boom(name):
        raise KeyError(name)

    monkeypatch.setattr(hub_publish, "adapter_for_preset", boom)
    monkeypatch.setattr(wda, "_ADAPTERS", {})
    monkeypatch.setenv("NEONRP_TRANSITION_SLOW_MODEL", "nope")
    _solve(root, _Fake("<lines>\n夜深了。\n</lines>", "<vars>\n</vars>", "<vars>\ntime.clock = 23:40\n</vars>"), monkeypatch)
    _settle(root)
    assert load_registry(root).variables["time.clock"].value == "23:40"


class _Relay(_Fake):
    """Our relay (ai.worldlines.gg): answers the write-down, or refuses it for money."""

    base_url = "https://ai.worldlines.gg/v1"

    def __init__(self, slow, refuse=False):
        super().__init__("", "", slow)
        self.calls, self.refuse, self.extra_kwargs, self.model = 1, refuse, {}, "deepseek-v4-flash"

    def chat(self, messages, tools=None):
        if self.refuse:
            return SimpleNamespace(message=SimpleNamespace(content=""), usage={},
                                   error="quota used up [worldlines-billing:quota_exceeded kind=careful_writedown]")
        return super().chat(messages, tools)


def test_auto_asks_the_platform_which_model_and_tells_our_relay_what_the_call_is(world, monkeypatch):
    """``auto``: the account's entitlements name the relay's model for the careful write-down while any is left;
    the call says what it is (X-Worldlines-Purpose) so the relay meters it on its own."""
    root, events = world
    from neonrp.core import hub_publish, worldlines_auth

    relay = _Relay("<vars>\ntime.clock = 22:10\n</vars>")
    monkeypatch.setattr(hub_publish, "adapter_for_preset", lambda name: relay)
    monkeypatch.setattr(wda, "_ADAPTERS", {})
    monkeypatch.setattr(worldlines_auth, "entitlements", lambda ttl=60.0: {"models": {"careful_writedown": "gemini-3.8-flash"},
                                                                           "usage": {"careful_writedown_remaining": 37}})
    monkeypatch.setenv("NEONRP_TRANSITION_SLOW_MODEL", "auto")
    _solve(root, _Fake("<lines>\n夜深了。\n</lines>", "<vars>\n</vars>", "<vars>\ntime.clock = 03:00\n</vars>"), monkeypatch)
    _settle(root)
    assert load_registry(root).variables["time.clock"].value == "22:10"
    assert relay.model == "gemini-3.8-flash" and relay.extra_kwargs["extra_headers"] == {"X-Worldlines-Purpose": "writedown-correction"}
    assert events[-1]["model"] == "worldlines:gemini-3.8-flash"
    monkeypatch.setattr(worldlines_auth, "entitlements", lambda ttl=60.0: {"models": {"careful_writedown": "gemini-3.8-flash"},
                                                                           "usage": {"careful_writedown_remaining": 0}})
    assert wda.slow_spec(root) == ""  # none left: the beat's own model
    monkeypatch.setattr(worldlines_auth, "entitlements", lambda ttl=60.0: None)
    assert wda.slow_spec(root) == ""  # not signed in / no answer


def test_a_correction_refused_for_money_runs_on_the_beats_own_model(world, monkeypatch):
    """The account's careful corrections are used up mid-month: this beat is corrected by the beat's own model, the
    event says why, and the refusal is not left as the player's last billing stop."""
    root, events = world
    from neonrp.core import billing_stop, hub_publish

    before = billing_stop.last()
    monkeypatch.setattr(hub_publish, "adapter_for_preset", lambda name: _Relay("", refuse=True))
    monkeypatch.setattr(wda, "_ADAPTERS", {})
    monkeypatch.setenv("NEONRP_TRANSITION_SLOW_MODEL", "worldlines:gemini-3.8-flash")
    _solve(root, _Fake("<lines>\n夜深了。\n</lines>", "<vars>\n</vars>", "<vars>\ntime.clock = 23:40\n</vars>"), monkeypatch)
    _settle(root)
    assert load_registry(root).variables["time.clock"].value == "23:40"  # the beat's own thinking answer
    assert events[-1]["kind"] == "write_down.corrected" and events[-1]["fallback"] == "quota_exceeded"
    assert billing_stop.last() is before


def test_a_transition_slow_unit_reaches_only_the_thinking_call(world, monkeypatch):
    """10-23: the transition prompt is one for both write-downs; a line meant to shape thinking (the private layer's
    thinking budget, C) goes in a ``transition_slow`` unit that only the thinking call reads."""
    root, _events = world
    monkeypatch.setenv("NEONRP_PRIVATE", "off")  # the open engine: a private layer (when the tests run with one) ships this unit
    assert turn_v3.slow_extra(root, "zh") == ""  # the open engine ships no such unit
    (root / "game" / "meta" / "prompts").mkdir(parents=True, exist_ok=True)
    (root / "game" / "meta" / "prompts" / "transition_slow.zh.md").write_text("## THINK-BUDGET-MARK\n", encoding="utf-8")
    seen: dict[str, str] = {}

    class _Rec(_Fake):
        def chat(self, messages, tools=None):
            with self.lock:
                n = self.calls + 1
            out = super().chat(messages, tools)
            if n > 1:
                m = messages[-1]
                seen["slow" if llm_openai._THINK.get() else "fast"] = str(m.get("content") if isinstance(m, dict) else getattr(m, "content", m))
            return out

    fake = _Rec("<lines>\n你在通铺躺下。\n</lines>", "<vars>\n</vars>", "<vars>\n</vars>", slow_gate=threading.Event())
    _solve(root, fake, monkeypatch)
    fake.gate.set()
    _settle(root)
    assert "THINK-BUDGET-MARK" in seen["slow"] and "THINK-BUDGET-MARK" not in seen["fast"]
    assert turn_v3.slow_extra(root, "zh").startswith("## THINK-BUDGET-MARK")
