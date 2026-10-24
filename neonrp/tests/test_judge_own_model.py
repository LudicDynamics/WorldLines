"""10-24: deepseek alone, not signed in — the planning talk never settled by itself and the host kept asking
「要不就这么办?」. With no judge at all the run's own model answers the planning beat's one question."""
from __future__ import annotations

from types import SimpleNamespace

from neonrp.core import engine_config, system_one as s1, turn_v3


class _Ad:
    def __init__(self, p: float) -> None:
        self.p = p
        self.calls = 0

    def chat(self, msgs):
        self.calls += 1
        return SimpleNamespace(message=SimpleNamespace(content='{"answers": {"settled": {"noul": %s, "confidence": 0.8}}}' % self.p))


def test_the_runs_own_model_judges_when_there_is_no_judge(tmp_path, monkeypatch):
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    ad = _Ad(0.9)
    monkeypatch.setattr(turn_v3, "ADAPTER_FACTORY", lambda root, provider: ad)
    q = {"settled": s1.noul("done?")}
    assert s1.ask({"board": {"a": 1}}, q) is None and ad.calls == 0  # nobody asked for the own model: off stays off
    a = s1.ask({"board": {"a": 1}}, q, own_model_root=tmp_path)
    assert a is not None and abs(a["settled"].yes - 0.9) < 1e-6 and ad.calls == 1
    assert s1.last_call()["fallback"] == "own-model"
    # the switch: turn.plan_loop_own_judge = false → the deterministic path, as before
    monkeypatch.setattr(engine_config, "get", lambda root, k, d=None: False if k == "turn.plan_loop_own_judge" else d)
    assert s1.ask({"board": {"b": 2}}, q, own_model_root=tmp_path) is None and ad.calls == 1


def test_own_model_judge_is_only_for_the_no_judge_case(tmp_path, monkeypatch):
    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    assert not s1.own_model_judge(tmp_path)
    monkeypatch.setenv("NEONRP_S1_BACKEND", "off")
    assert s1.own_model_judge(tmp_path) and not s1.own_model_judge(None)
