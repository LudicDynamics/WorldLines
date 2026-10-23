"""The golden record of today's turn (10-17 第 4 批 S0) — what each scripted turn did (spans in order · the beat · the
plan · who acted how · ops applied / refused · the engine's answers · the prose · what moved), held fixed so the step
runner refactor (S3–S5: the turn cut into steps run off the graph) can prove it changes nothing by default.

Each scenario runs through core/graph_test on a stub model (scripted replies, no network) and is compared with
``tests/golden/turns/<name>.json``. A deliberate behaviour change regenerates them: ``NEONRP_GOLDEN_UPDATE=1 pytest
tests/test_golden_turns.py`` — and the diff of those files is the review.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from neonrp.core import graph_test as G

GOLDEN = Path(__file__).parent / "golden" / "turns"
HOST_ADVANCE = "<lines>\n(假模型)主持:那就走。\n</lines>\n<board>\n玩家: 出发\n</board>\nnext: advance"


def _no_plan_graph() -> dict:
    from neonrp.template import v3

    g = v3.graph_of("stoneford-elena")["graph"]
    d = {k: g[k] for k in ("id", "start", "nodes", "edges")}
    d["nodes"] = {k: v for k, v in d["nodes"].items() if k != "plan"}
    d["edges"] = [e for e in d["edges"] if "plan" not in (e["from"], e["to"])]
    d["start"] = "resolve"
    return d


SCENARIOS: dict[str, dict] = {
    # 商量 → 「定」→ 清算:叙事 + 一条变化(玩家走到主街)
    "commit_move": {"template": "stoneford-elena", "lines": ["我去主街看看", "定"],
                    "replies": [G.EDITOR_HOST, "<lines>\n你走上主街,雾还没散。\n</lines>", "<vars>\nlocation = T001/main_street\n</vars>\n<files>\n</files>"]},
    # @主持:主持决定推进
    "dm_advance": {"template": "stoneford-elena", "lines": ["我四处看看", "@dm 走吧"],
                   "replies": [G.EDITOR_HOST, HOST_ADVANCE, "<lines>\n你们离开北门。\n</lines>", "<vars>\n</vars>\n<files>\n</files>"]},
    # 叙事里写进层的标记(战斗)
    "combat_tag": {"template": "stoneford-elena", "lines": ["我拔剑冲向码头工人", "定", "我再砍一刀"],
                   "replies": [G.EDITOR_HOST, "<lines>\n码头工人围了上来。\n[combat 码头工人]\n</lines>", "<vars>\n</vars>\n<files>\n</files>"]},
    # 角色变体:默认 S-judge
    "soul_variant": {"template": "stoneford-elena", "lines": ["艾琳娜,我们走吧", "定"],
                     "engine": {"turn": {"parallel": {"souls": {"default_variant": "S-judge"}}}}},
    # 编排图里删掉商量拍:第一句就是普通回合
    "no_plan_graph": {"template": "stoneford-elena", "lines": ["我四处看看", "我去主街"], "graph": "no_plan"},
    # 普通回合里角色并行出手,变体 S-judge(判断 + 一次发言)
    "no_plan_sjudge": {"template": "stoneford-elena", "lines": ["艾琳娜,帮我看看这张地图"], "graph": "no_plan",
                       "engine": {"turn": {"parallel": {"souls": {"default_variant": "S-judge"}}}}},
    # 图上的步骤设置真的生效(S2):草稿把角色出手方式设成 S-direct(玩法包默认 S-judge)
    "step_param_variant": {"template": "stoneford-elena", "lines": ["艾琳娜,帮我看看这张地图"], "graph": "no_plan+s_direct"},
    # 游戏客户端的交互(石津镇):插件跑自己的小图
    "interaction_examine": {"template": "stoneford-town",
                            "lines": ['<interaction>{"kind": "examine", "target": "T001/gate_north"}</interaction>']},
}


def _run(name: str) -> dict:
    sc = dict(SCENARIOS[name])
    if sc.get("graph") == "no_plan":
        sc["graph"] = _no_plan_graph()
    elif sc.get("graph") == "no_plan+s_direct":
        sc["graph"] = _no_plan_graph()
        sc["graph"]["nodes"]["resolve"] = {**sc["graph"]["nodes"]["resolve"], "step_params": {"s2_souls": {"default_variant": "S-direct"}}}
    res = G.run({"defaults": {"host": G.EDITOR_HOST}, **sc, "record": True})
    return {"scenario": name, "model_calls": res["model_calls"],
            "steps": [{"line": s["line"], "nodes": s["nodes"], "advanced_by": s["advanced_by"], **s["digest"]} for s in res["steps"]]}


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_turn_matches_its_golden_record(name):
    got = _run(name)
    p = GOLDEN / f"{name}.json"
    if os.environ.get("NEONRP_GOLDEN_UPDATE") == "1" or not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(got, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        if os.environ.get("NEONRP_GOLDEN_UPDATE") != "1":
            pytest.fail(f"no golden record for {name} yet — wrote {p}; review it and commit")
        return
    want = json.loads(p.read_text(encoding="utf-8"))
    assert got == want, f"{name}: the turn no longer does what tests/golden/turns/{name}.json recorded"
