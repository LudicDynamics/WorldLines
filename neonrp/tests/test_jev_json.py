"""Jev fills the JSON line by line (10-10): our registered tools are the
tag list, their fields the skeleton, the candidates come out of the line; one request; unsure lines → the fallback."""
from __future__ import annotations

from pathlib import Path

import pytest
from test_engine_v3 import _install

from neonrp.core import jev_json as J
from neonrp.core import system_one as s1
from neonrp.core.registry import load_registry

LINES = "玩家从石津镇北门(T001/gate_north)移动到冒险者公会(T001/guild)。\n赫伦打开公会的门。"


def _stub(state, Q):
    out = {}
    for k, q in Q.items():
        if q.type == "noul":
            hit = (k == "t0.move_to") or (k == "t1.patch")
            out[k] = s1.Answer("noul", 0.9 if k == "t0.move_to" else (0.45 if hit else 0.05))
        elif q.type == "choice":
            crit = q.criteria
            want = {"who": "player", "to": "T001/guild"}
            field = k.rsplit(".", 1)[-1]
            key = next((ck for ck, cv in crit.items() if cv == want.get(field)), "none")
            out[k] = s1.Answer("choice", key, probabilities={key: 0.9})
    return out


@pytest.fixture
def world(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    s1.install_stub(_stub)
    yield _install(tmp_path)
    s1.install_stub(None)


def test_tools_come_from_the_registry(world):
    t = J.tools(load_registry(world), "zh")
    assert t["move_to"]["fields"] == ["who", "to"] and "write" not in t and t["move_to"]["doc"]


def test_one_label_per_value(world):
    reg = load_registry(world)
    c = J._cands("to", "移动到冒险者公会(T001/guild)", reg, J._L(world), "")
    assert list(c.values()).count("T001/guild") == 1  # 「冒险者公会 (T001/guild)」 and 「T001/guild」 no longer split the vote


def test_lines_become_our_tools_json_and_the_unsure_one_goes_to_the_fallback(world):
    ops, fallback, log = J.to_ops(world, load_registry(world), LINES, "")
    assert [{k: v for k, v in o.items() if not k.startswith("_")} for o in ops if o["_from"] == "jev"] == [{"op": "move_to", "who": "player", "to": "T001/guild"}]
    assert fallback == ["赫伦打开公会的门。"]  # tagged, but not surely → written by the pseudo-code fallback
    assert len(log["rounds"]) == 1  # one Jev request


def test_ablation_switches(world, monkeypatch):
    monkeypatch.setenv("NEONRP_JEV_PARTS", "vars")
    ops, fallback, log = J.to_ops(world, load_registry(world), LINES, "")
    assert log["parts"] == ["vars"] and fallback == [] and not any(o.get("op") == "move_to" for o in ops)
