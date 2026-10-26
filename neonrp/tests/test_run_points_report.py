"""一局的结算积分报给平台(2026-10-21 · lead 定的方案):引擎只说「这一局结算了多少分」,发不发、发多少由 billing 按它自己看到的
事实定(这一局这个世界的计费对话 + 时长),chronicle 只是转交。

- 模型调用带 X-Worldlines-World = 绑定那一局的模板 id(只对 ai.worldlines.gg;billing 靠它数这一局的计费调用)
- 真相三问答完 = 一个 settlement.reward(ref settlement:<世界>:<局>,积分合计,score / total),跟在 ending.reached 后面进 chronicle 队列
- 不报:用自己的 key(billing 看不到调用,lead 10-21 e)· 不是模板世界(local:)· 自由区 · 游客 / 没登录 · 0 分;结果 platform 写明是哪一种"""
from __future__ import annotations

import json
from pathlib import Path

from neonrp.core import chronicle, truth_quiz, worldlines_auth
from neonrp.core import llm_openai

from test_platform_share_chronicle import JWT_A, JWT_GUEST, _run, platform  # noqa: F401 — the fake platform


def _bill(root: Path, base: str = "https://ai.worldlines.gg/v1", env: str = "WORLDLINES_API_KEY") -> Path:
    (root / ".neonrp" / "config.json").write_text(json.dumps({"llm": {"model_ref": "m"}, "models": {"m": {
        "provider": "openai", "model": "deepseek-v4-flash", "base_url": base, "api_key_env": env}}}), encoding="utf-8")
    return root


def test_model_calls_say_which_world(tmp_path, monkeypatch):
    run = _run(tmp_path / "tpl-wuwu-20261021-101010")
    monkeypatch.setenv("NEONRP_CHRONICLE", "off")
    chronicle.opened(run)
    assert worldlines_auth.world_header() == {"X-Worldlines-World": "wuwu"}
    seen = {}

    class Completions:
        def create(self, **kw):
            seen.update(kw)
            return "ok"

    class Client:
        chat = type("C", (), {"completions": Completions()})()

    wl = llm_openai.OpenAIAdapter(model="m", base_url="https://ai.worldlines.gg/v1", api_key="k")
    assert wl._create(Client(), {"model": "m", "messages": []}) == "ok"
    assert seen["extra_headers"] == {"X-Worldlines-World": "wuwu"}
    seen.clear()
    own = llm_openai.OpenAIAdapter(model="m", base_url="https://api.deepseek.com/v1", api_key="k")
    own._create(Client(), {"model": "m", "messages": []})
    assert "extra_headers" not in seen, "the player's own provider never hears our world ids"
    chronicle.opened(_run(tmp_path / "stoneford-elena-20261021-101010", tpl=None))
    assert worldlines_auth.world_header() == {}, "a run not built from a template names no world"


def test_bills_run_is_the_worldlines_model_only(tmp_path):
    run = _run(tmp_path / "tpl-wuwu-20261021-101010")
    assert worldlines_auth.bills_run(_bill(run)) is True
    assert worldlines_auth.bills_run(_bill(run, base="http://127.0.0.1:8611/v1")) is True, "the browser engine's web model (page token)"
    assert worldlines_auth.bills_run(_bill(run, base="https://api.deepseek.com/v1", env="WLWEB_OWN_API_KEY")) is False


def test_reward_reports_after_the_ending_or_says_why_not(platform, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("WORLDLINES_API_KEY", JWT_A)
    monkeypatch.setattr(chronicle, "BASE", "http://127.0.0.1:9")   # offline: what is told waits in the spool
    run = _bill(_run(tmp_path / "tpl-wuwu-20261021-101010"))
    chronicle.ending(run, {"id": "E1"})
    assert chronicle.reward(run, ref="settlement:wuwu:" + run.name, points=60, source="settlement:quiz", score=2, total=3) == "reported"
    chronicle._wait()
    q = chronicle.pending()
    ev = [e for e in q if e["type"] == "settlement.reward"]
    assert [e["type"] for e in q].index("ending.reached") < [e["type"] for e in q].index("settlement.reward"), "the ending goes first"
    assert {k: ev[0][k] for k in ("save_id", "ref", "points", "score", "total", "source")} == {
        "save_id": run.name, "ref": f"settlement:wuwu:{run.name}", "points": 60, "score": 2, "total": 3, "source": "settlement:quiz"}
    assert chronicle.reward(run, ref="x", points=0, source="settlement:quiz") == "none"
    own = _bill(_run(tmp_path / "tpl-wuwu-20261021-111111"), base="https://api.deepseek.com/v1", env="DEEPSEEK_API_KEY")
    assert chronicle.reward(own, ref="x", points=60, source="settlement:quiz") == "own_key"
    local = _bill(_run(tmp_path / "stoneford-elena-20261021-101010", tpl=None))
    assert chronicle.reward(local, ref="x", points=60, source="settlement:quiz") == "local"
    from neonrp.core import player_data

    real = player_data.free_zone
    monkeypatch.setattr(player_data, "free_zone", lambda root: True)
    assert chronicle.reward(run, ref="y", points=60, source="settlement:quiz") == "free_zone"
    monkeypatch.setattr(player_data, "free_zone", real)
    monkeypatch.setenv("WORLDLINES_API_KEY", JWT_GUEST)
    assert chronicle.reward(run, ref="z", points=60, source="settlement:quiz") == "guest"
    assert len([e for e in chronicle.pending() if e["type"] == "settlement.reward"]) == 1, "only the one reported"


def test_the_quiz_result_says_what_became_of_the_points(tmp_path, monkeypatch):
    told = []
    monkeypatch.setattr(chronicle, "reward", lambda root, **kw: told.append(kw) or "own_key")
    from test_settlement_rewards import _Model, _build, _kagura_true_ending, _model_quiz, _no_quiz_no_collect

    root = _build("kagura-island", tmp_path / "run", _no_quiz_no_collect)
    _kagura_true_ending(root)
    res = truth_quiz.answer(root, [0, 0, 0], adapter=_Model(_model_quiz()))
    assert res["platform"] == "own_key"
    assert told == [{"ref": f"settlement:kagura-island:{root.name}", "points": sum(r["amount"] for r in res["rewards"]),
                     "source": "settlement:quiz", "score": res["score"], "total": 3}], "one event per run, the sum"
    assert truth_quiz.answer(root, [1, 1, 1], adapter=_Model(_model_quiz())) == res and len(told) == 1, "answered once, told once"


def test_the_ios_shell_says_it_is_the_app(monkeypatch):
    monkeypatch.delenv("WORLDLINES_CLIENT", raising=False)
    assert chronicle.client() == "local"
    monkeypatch.setenv("WORLDLINES_CLIENT", "app")   # the iOS app's embedded engine (wl_host, ios4 10-21)
    assert chronicle.client() == "app"
    monkeypatch.setenv("WORLDLINES_CLIENT", "ios")   # the iOS shell's newer name (funnel 10-25): play records still say app
    assert chronicle.client() == "app"
    monkeypatch.setenv("WORLDLINES_CLIENT", "tv")    # not one of chronicle's: ignored, never a rejected event
    assert chronicle.client() == "local"
