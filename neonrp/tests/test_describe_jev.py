"""Describe, then Jev (10-10 experiment): the model says in plain words what changed and why; Jev's typed answers fill
the engine's JSON changes — no pseudo-code. Jev is stood in for here by a keyword reader (the real one answers from
meaning); the point is the conversion: every answer lands in what was offered, the JSON verifies as before."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from test_engine_v3 import _install

from neonrp.core import describe_jev as DJ
from neonrp.core import system_one as s1
from neonrp.core.registry import load_registry
from neonrp.core.turn_v3 import verify


def _reader(state, questions):
    text = str(state.get("changes") or "")
    out = {}
    for k, q in questions.items():
        if q.type == "noul":
            m = re.search(r"「(.+?)」", q.instructions)
            word = (m.group(1).split(" (")[0].split("的")[-1].strip() if m else "")
            hit = {"st_new": "中毒" in text, "st_gone": "好了" in text, "gain": "买了" in text, "lose": "送给" in text,
                   "move": "去了" in text, "clock": ":" in text}.get(k, bool(word) and word in text)
            out[k] = s1.Answer("noul", 0.95 if hit else 0.05)
        elif q.type == "choice":
            best = next((key for key, label in q.criteria.items() if key != "none" and str(label) in text and len(str(label)) > 1), None)
            if best is None:  # numbers: the label that appears after 变成 / 到
                best = next((key for key, label in q.criteria.items() if re.search(rf"(变成|到了?)\s*{re.escape(str(label))}", text)), "none")
            out[k] = s1.Answer("choice", best)
        else:
            out[k] = s1.Answer("score", 3.0)
    return out


@pytest.fixture
def world(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    s1.install_stub(_reader)
    yield _install(tmp_path)
    s1.install_stub(None)


def test_plain_words_become_the_json_changes(world):
    reg = load_registry(world)
    changes = "玩家的金币从 18 变成 12,因为付了药钱。玩家中毒了,喝了不干净的水。玩家买了小治疗药水。"
    ops, options, log = DJ.to_ops(world, reg, changes, ["回北门", "问老苇还卖什么"], "老苇把药水推过来。")
    got = {(o["op"], o.get("var") or o.get("class"), str(o.get("value") or o.get("name"))) for o in ops}
    assert ("set", "player.gold", "12") in got and ("new", "status", "中毒") in got and ("new", "carry", "小治疗药水") in got
    assert all(o.get("_from") == "jev" for o in ops) and log["rounds"]
    vr = verify(world, [{k: v for k, v in o.items()} for o in ops], reg)
    assert not [r for r in vr.refused if "gold" in str(r.op)], vr.refused  # the engine takes them as any JSON change
    assert options and "回北门" in options


def test_nothing_changed_no_changes(world):
    reg = load_registry(world)
    ops, options, _log = DJ.to_ops(world, reg, "没有变化", ["回北门"], "雾还没散。")
    assert ops == [] and options[0] == "回北门" and any(o.startswith("去") for o in options)  # exits are candidates too


def test_parse_takes_the_two_sections():
    ch, po = DJ.parse("<changes>\n金币从 18 变成 12。\n</changes>\n<possible>\n1. 回北门\n- 问路\n</possible>")
    assert ch == "金币从 18 变成 12。" and po == ["回北门", "问路"]
