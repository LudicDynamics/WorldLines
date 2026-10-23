"""Class growth policy + creator approvals (core/approvals.py): auto lands, approve queues, creator/forbid refuse."""
from __future__ import annotations

from pathlib import Path

import pytest

from neonrp import template as TP
from neonrp.core import approvals, sdk
from neonrp.core.registry import RegisterError, load_registry, register
from _paths import PRODUCT_TEMPLATES

_EX = PRODUCT_TEMPLATES / "stoneford-market.template"


def _new(name: str) -> dict:
    return {"op": "new", "class": "rumor", "name": name, "props": {"text": name, "heat": 2}}


def _run(tmp_path: Path) -> Path:
    root = tmp_path / "run"
    TP.build(_EX, root)
    return root


def test_auto_is_the_default(tmp_path):
    root = _run(tmp_path)
    reg = load_registry(root)
    assert reg.classes["rumor"].policy == "auto"
    vr = sdk.verify(root, [_new("河边闹鬼")], reg)
    assert vr.accepted and not vr.refused


def test_approve_queues_then_lands_on_approval(tmp_path):
    root = _run(tmp_path)
    register(root, "classes", "rumor", {"policy": "approve"})
    reg = load_registry(root)
    assert reg.classes["rumor"].policy == "approve" and reg.classes["rumor"].folder == "game/rumors"  # overlay keeps the pack's class
    vr = sdk.verify(root, [_new("河边闹鬼")], reg)
    assert not vr.accepted and "waits for the creator's approval" in vr.refused[0].why
    sdk.verify(root, [_new("河边闹鬼")], load_registry(root))  # proposed again → still one request
    rows = approvals.pending(root)
    assert len(rows) == 1 and rows[0]["op"]["name"] == "河边闹鬼"
    row = approvals.decide(root, rows[0]["id"], True)
    assert row["status"] == "approved" and row["created"]
    assert any(e.props.get("name") == "河边闹鬼" for e in load_registry(root).of_class("rumor"))
    assert approvals.pending(root) == []
    with pytest.raises(KeyError):
        approvals.decide(root, rows[0]["id"], True)  # decided once


def test_reject_creator_forbid(tmp_path):
    root = _run(tmp_path)
    register(root, "classes", "rumor", {"policy": "approve"})
    sdk.verify(root, [_new("一")], load_registry(root))
    pid = approvals.pending(root)[0]["id"]
    assert approvals.decide(root, pid, False)["status"] == "rejected"
    assert not any(e.props.get("name") == "一" for e in load_registry(root).of_class("rumor"))
    for policy, word in (("creator", "by the creator only"), ("forbid", "does not grow")):
        register(root, "classes", "rumor", {"policy": policy})
        vr = sdk.verify(root, [_new("二")], load_registry(root))
        assert not vr.accepted and word in vr.refused[0].why
    with pytest.raises(RegisterError):
        register(root, "classes", "rumor", {"policy": "sometimes"})


def test_ticks_are_not_gated(tmp_path):
    root = _run(tmp_path)
    register(root, "classes", "caravan", {"policy": "forbid"})
    res = sdk.tick(root, turns=8, start=1)
    assert any(a["op"] == "new_caravan" for r in res for a in r.applied)  # world rules are the world's own
