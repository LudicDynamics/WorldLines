"""商量拍的数值设置:0 是合法值(10-24 本地创作台 e2e:「谈一句世界走几分钟」设 0、门槛设 0,以前 `int(… or 2)` 读回成默认)。
只在没设(None / 空)时用默认;读不懂的值也用默认。要私有层(tests/requires_private.txt)。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from neonrp.core import node_kinds


@pytest.fixture
def plan():
    m = node_kinds.module_of("plan")
    if m is None:
        pytest.skip("needs the private layer (the planning beat)")
    return m


def _root(tmp_path: Path, turn: dict) -> Path:
    from neonrp.core.paths import get_data_dir_name

    root = tmp_path / "w"
    (root / get_data_dir_name(root) / "meta").mkdir(parents=True)
    (root / get_data_dir_name(root) / "meta" / "engine.json").write_text(json.dumps({"turn": turn}), encoding="utf-8")
    return root


def test_zero_stays_zero(plan, tmp_path):
    root = _root(tmp_path, {"plan_loop_talk_minutes": 0, "plan_loop_settle_at": 0, "plan_loop_host_again_at": 0,
                            "plan_loop_overrode_at": 0, "plan_loop_check_gap_at": 0})
    assert plan._talk_step(root) == 0
    for key in ("settle_at", "host_again_at", "overrode_at", "check_gap_at"):
        assert plan._ec_num(root, f"turn.plan_loop_{key}", 0.6) == 0.0, key


def test_unset_and_unreadable_take_the_default(plan, tmp_path):
    root = _root(tmp_path, {"plan_loop_talk_limit": "", "plan_loop_max_rounds": "lots"})
    assert plan._talk_step(root) == 2           # not set
    assert plan._talk_limit(root) == 20         # set to "" = not set
    assert plan._ec_num(root, "turn.plan_loop_max_rounds", 4) == 4   # unreadable
    root2 = _root(tmp_path / "b", {"plan_loop_talk_minutes": 30, "plan_loop_max_rounds": "6"})
    assert plan._talk_step(root2) == 30
    assert plan._ec_num(root2, "turn.plan_loop_max_rounds", 4) == 6 and isinstance(plan._ec_num(root2, "turn.plan_loop_max_rounds", 4), int)
