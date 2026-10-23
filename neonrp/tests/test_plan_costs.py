"""The plan's agreed payments are settled by the engine (10-22, PL12: of 9 real runs paying for an inn, 4 missed the payment
and 3 charged it twice — the payment was one more sentence on the board and the state transition guessed):

- the board's 「花费: <variable> <amount> <why>」 lines are read with the checks, summed per variable
- at the Resolve each one is held against the purse: ok (landed by the engine, the transition's own copy of the variable
  loses), short (nothing taken; the narrator is told it could not be paid)
- what landed is kept for a few beats and shown to the talk and the next Resolve, so nobody charges it again
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from _paths import PRODUCT_TEMPLATES

from neonrp import template as TP
from neonrp.core import turn_v3
from neonrp.core.registry import load_registry

try:  # the planning beat is a private-layer plugin; without it every case here is skipped (requires_private.txt)
    from neonrp.core import plan_loop
except ImportError:
    plan_loop = None

pytestmark = pytest.mark.skipif(plan_loop is None, reason="private layer not installed")


def _world(tmp_path):
    root = tmp_path / "w"
    TP.build(PRODUCT_TEMPLATES / "stoneford-elena.template", root)
    return root


class _Fake:
    def __init__(self, outputs):
        self.outputs, self.calls = list(outputs), []

    def chat(self, messages, tools=None):
        self.calls.append(messages)
        return SimpleNamespace(message=SimpleNamespace(content=self.outputs.pop(0) if self.outputs else ""),
                               usage={"prompt_tokens": 1, "completion_tokens": 1})


def test_the_boards_money_lines_are_read_and_summed_per_variable():
    raw = ("<board>\n玩家: 住店\n花费: player.gold -3 通铺\n花费：player.gold 3 艾琳娜那铺\n收入: player.silver 2 卖灯\n"
           "花费: 三枚金币\n检定: 无\n</board>")
    assert plan_loop._costs(raw) == [{"var": "player.gold", "delta": -6, "why": "通铺; 艾琳娜那铺"},
                                     {"var": "player.silver", "delta": 2, "why": "卖灯"}]
    assert plan_loop._costs("<board>\npay: player.gold 12 potion\n</board>") == [{"var": "player.gold", "delta": -12, "why": "potion"}]
    assert plan_loop._costs("<board>\n玩家: 付三金住店\n</board>") == []


def test_each_amount_is_held_against_the_purse(tmp_path):
    reg = load_registry(_world(tmp_path))
    gold = reg.variables["player.gold"].value
    got = plan_loop.settle_costs(reg, [{"var": "player.gold", "delta": -3, "why": "通铺"},
                                       {"var": "player.gold", "delta": -(gold + 1), "why": "单间"},
                                       {"var": "nobody.gold", "delta": -3, "why": "x"}])
    assert [c["status"] for c in got] == ["ok", "short", "unknown"]
    assert (got[0]["before"], got[0]["after"]) == (gold, gold - 3) and got[1]["have"] == gold


def test_an_agreed_payment_rides_the_board_into_the_resolve(tmp_path, monkeypatch):
    root = _world(tmp_path)
    monkeypatch.setattr(plan_loop, "settled", lambda *a, **k: None)
    monkeypatch.setattr(plan_loop, "overrode", lambda *a, **k: None)
    monkeypatch.setattr(plan_loop, "check_gap", lambda *a, **k: None)
    monkeypatch.setattr(plan_loop, "host_again", lambda *a, **k: None)
    outs = iter(["<lines>\n通铺 3 金一晚。\n</lines>\n<board>\n玩家: 住通铺\n花费: player.gold -3 通铺一晚\n</board>\nnext: wait",
                 "<lines>\n那就住下。\n</lines>\n<board>\n玩家: 付钱住通铺\n</board>\nnext: advance"])
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: next(outs))
    first = plan_loop.step(root, user_text="我要一张通铺", last_narration="x")
    assert first["kind"] == "plan" and first["beat"]["costs"] == [{"var": "player.gold", "delta": -3, "why": "通铺一晚"}]
    out = plan_loop.step(root, user_text="定", last_narration="x")  # the second round did not restate it: it is kept
    assert out["kind"] == "resolve" and out["costs"] == [{"var": "player.gold", "delta": -3, "why": "通铺一晚"}]


def test_the_engine_lands_the_payment_and_the_transitions_copy_loses(tmp_path, monkeypatch):
    root = _world(tmp_path)
    monkeypatch.setenv("NEONRP_V3_SOLVE", "narrate")
    gold = load_registry(root).variables["player.gold"].value
    # the transition counts the board's 「付 3 金」 once more on top of the prose's: the old double charge
    a = _Fake(["<lines>\n米拉收了三枚金币,把号牌推过来。\n</lines>", f"<vars>\nplayer.gold = {gold - 6}\n</vars>\n<files>\n</files>"])
    monkeypatch.setattr(turn_v3, "ADAPTER_FACTORY", lambda root_, provider: a)
    try:
        out = turn_v3.solve_turn(root, user_text="定", provider=None, turn=1, soul_reports=[],
                                 ruled_ops=[{"op": "add", "var": "player.gold", "delta": -3}])
    finally:
        turn_v3.ADAPTER_FACTORY = None
    assert out["apply"].variables["player.gold"] == gold - 3
    assert "player.gold -3" in a.calls[1][1].content  # the transition was told it is settled


def test_the_brief_says_what_was_paid_or_could_not_be_and_the_ledger_keeps_it(tmp_path):
    root = _world(tmp_path)
    reg = load_registry(root)
    gold = reg.variables["player.gold"].value
    costs = plan_loop.settle_costs(reg, [{"var": "player.gold", "delta": -3, "why": "通铺"},
                                         {"var": "player.silver", "delta": -999, "why": "单间"}])
    ctx = {"board": {"玩家": "住店"}, "checks": [], "costs": costs, "beat": {"kind": "resolve"}}
    brief = plan_loop.resolve_facts(ctx, root)
    assert f"player.gold -3({gold}→{gold - 3})" in brief and "钱不够" in brief
    node = plan_loop._PlanNode()
    assert node.ruled(ctx, root) == [{"op": "add", "var": "player.gold", "delta": -3}, {"op": "add", "var": "player.silver", "delta": 0}]
    applied = SimpleNamespace(applied=[{"op": "add", "var": "player.gold", "from": gold, "to": gold - 3}])
    beat = node.finish(ctx, root, {"apply": applied})
    assert beat["costs"] == costs
    assert plan_loop.load_paid(root) == [{"var": "player.gold", "delta": -3, "why": "通铺"}]
    later = plan_loop.resolve_facts({"board": {"玩家": "睡到天亮"}, "checks": []}, root)
    assert "前几拍已经付过的钱" in later and "通铺:player.gold -3" in later


def test_a_restated_payment_is_not_taken_twice_and_a_short_one_not_at_all(tmp_path, monkeypatch):
    """PL1 r1 (10-22): the potion's 12 was taken, the next beat's board asked 12 again; the engine refused it for want of
    money, and the transition took the 6 that was left. A payment in the ledger is not taken again, and a payment the
    engine did not take is no change — the transition's copy of it loses too."""
    root = _world(tmp_path)
    reg = load_registry(root)
    gold = reg.variables["player.gold"].value
    plan_loop.record_paid(root, [{"var": "player.gold", "delta": -12, "why": "药水"}])
    got = plan_loop.settle_costs(reg, [{"var": "player.gold", "delta": -12, "why": "药水"}, {"var": "player.silver", "delta": -99, "why": "x"}],
                                 plan_loop.load_paid(root))
    assert [c["status"] for c in got] == ["paid_before", "short"]
    ctx = {"board": {"玩家": "买药"}, "checks": [], "costs": got}
    ruled = plan_loop._PlanNode().ruled(ctx, root)
    assert ruled == [{"op": "add", "var": "player.gold", "delta": 0}, {"op": "add", "var": "player.silver", "delta": 0}]
    assert "这笔前面已经付过了" in plan_loop.resolve_facts(ctx, root)
    monkeypatch.setenv("NEONRP_V3_SOLVE", "narrate")
    a = _Fake(["<lines>\n你又摸出钱袋。\n</lines>", f"<vars>\nplayer.gold = {gold - 12}\n</vars>\n<files>\n</files>"])
    monkeypatch.setattr(turn_v3, "ADAPTER_FACTORY", lambda root_, provider: a)
    try:
        out = turn_v3.solve_turn(root, user_text="定", provider=None, turn=1, soul_reports=[], ruled_ops=ruled)
    finally:
        turn_v3.ADAPTER_FACTORY = None
    assert out["apply"].variables["player.gold"] == gold


def test_the_ledger_keeps_what_the_transition_took_without_a_money_line(tmp_path):
    """PL1 r2: no money line on the board, the transition took the 12 — the ledger has it all the same, purses only."""
    root = _world(tmp_path)
    reg = load_registry(root)
    assert plan_loop.purse_like(reg.variables["player.gold"])
    assert not any(plan_loop.purse_like(reg.variables[v]) for v in ("player.hp", "time.day", "town.alert"))
    applied = SimpleNamespace(applied=[{"op": "set", "var": "player.gold", "from": 18, "to": 6},
                                       {"op": "add", "var": "player.hp", "from": 24, "to": 20},
                                       {"op": "add", "var": "player.silver", "from": 3, "to": 5}])
    plan_loop._PlanNode().finish({"board": {}, "checks": [], "beat": {"kind": "resolve"}}, root, {"apply": applied})
    assert plan_loop.load_paid(root) == [{"var": "player.gold", "delta": -12, "why": ""}]


def test_a_fraction_of_an_integer_purse_is_left_to_the_prose(tmp_path):
    """PL1 r3: 「九金五」 came as player.gold -9.5 and the integer purse rounded it; it is not this variable's unit."""
    reg = load_registry(_world(tmp_path))
    assert plan_loop.settle_costs(reg, [{"var": "player.gold", "delta": -9.5, "why": "药水"}])[0]["status"] == "unknown"
