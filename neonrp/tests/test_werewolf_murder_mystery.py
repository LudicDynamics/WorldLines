"""10-08 (1.0 UI E1 · E2 · E4): 狼人杀 under murder-mystery@1 — the pack's own end triggers reach the contract's exit,
its seats are the fixed cast, and the settlement carries the accusations (day exiles with the votes) and the truth
(the plot's reveal + every seat's role)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from neonrp import template as TP
from neonrp.core import sdk
from neonrp.core.registry import load_registry
from _paths import PRODUCT_TEMPLATES

SRC = PRODUCT_TEMPLATES / "werewolf-night-village.template"


def _declared(tmp_path: Path) -> Path:
    d = tmp_path / "werewolf-night-village.template"
    shutil.copytree(SRC, d)
    tj = d / "template.json"
    t = json.loads(tj.read_text(encoding="utf-8"))
    t["play_contract"] = "murder-mystery@1"
    tj.write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
    return d


def test_contract_sees_pack_endings_and_seat_cast(tmp_path):
    rep = TP.lint(TP.load(_declared(tmp_path)))
    codes = {(p["code"], p["where"]) for p in rep["problems"] if p["level"] == "block"}
    assert ("contract.exit", "exit.on") not in codes, rep["problems"]  # E1
    assert ("contract.entry", "entry.cast") not in codes, rep["problems"]  # E2
    plot_warn = [p for p in rep["problems"] if "unreachable" in p["msg"]]
    assert not plot_warn, plot_warn


def test_settlement_has_accusation_and_truth(tmp_path):
    run = tmp_path / "run"
    TP.build(TP.load(_declared(tmp_path)), run)
    reg = load_registry(run)
    seats = sorted(reg.of_class("seat"), key=lambda e: e.id)
    wolves = [e.id for e in seats if e.props["role"] == "wolf"]
    others = [e.id for e in seats if e.props["role"] != "wolf"]
    sdk.apply(run, [{"op": "vote", "who": others[0], "target": wolves[0]}, {"op": "vote", "who": others[1], "target": wolves[0]}], load_registry(run), turn=1)
    sdk.apply(run, [{"op": "kill", "target": wolves[0]}], load_registry(run), turn=1)
    sdk.apply(run, [{"op": "phase", "value": "night"}], load_registry(run), turn=2)
    sdk.apply(run, [{"op": "kill", "target": others[2]}], load_registry(run), turn=2)
    sdk.apply(run, [{"op": "phase", "value": "day"}], load_registry(run), turn=3)
    ar = sdk.apply(run, [{"op": "kill", "target": wolves[1]}], load_registry(run), turn=3)
    assert ar.ended and ar.ended["id"] == "E_VILLAGE"
    st = json.loads((run / "game" / "meta" / "settlement.json").read_text(encoding="utf-8"))
    acc = st["accusation"]
    assert [a["target"] for a in acc] == [wolves[0], wolves[1]] and len(acc[0]["votes"]) == 2
    tr = st["truth_reveal"]
    assert tr["text"] and {r["id"]: r["role"] for r in tr["roles"]} == {e.id: e.props["role"] for e in seats}
    assert [n["target"] for n in tr["night"]] == [others[2]]
