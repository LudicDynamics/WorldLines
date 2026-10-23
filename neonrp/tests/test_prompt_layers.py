"""R3 (engine handover 10-05): prompts layer run (the template's, game/meta/prompts) → pack → engine."""
from __future__ import annotations

import shutil
from pathlib import Path

from neonrp import prompts
from neonrp.core import turn_v3
from _paths import PRODUCT_TEMPLATES

try:  # the planning beat lives in the private layer (10-10 R1); the open engine has none
    from neonrp.core import plan_loop
except ImportError:
    plan_loop = None

TPL = PRODUCT_TEMPLATES / "stoneford-elena.template"


def _build(tmp_path: Path, override: dict[str, str] | None) -> Path:
    from neonrp.template import build

    t = tmp_path / "t.template"
    shutil.copytree(TPL, t)
    if override:
        (t / "prompts" / "engine").mkdir(parents=True, exist_ok=True)
        for name, body in override.items():
            (t / "prompts" / "engine" / name).write_text(body, encoding="utf-8")
    dest = tmp_path / "run"
    build(t, dest)
    return dest


def test_a_template_overrides_the_planning_prompt(tmp_path):
    root = _build(tmp_path, {"plan_sys.zh.md": "你是测试主持。{check_grammar}\n"})
    assert plan_loop.plan_sys(root).startswith("你是测试主持。")
    assert "检定" in plan_loop.plan_sys(root), "the pack's check grammar still fills its slot"


def test_without_an_override_nothing_changes(tmp_path):
    root = _build(tmp_path, None)
    assert prompts.text("plan_sys", "zh", root) == prompts.text("plan_sys", "zh")
    assert prompts.text("narrate", "zh", root) == turn_v3.NARRATE["zh"]


def test_an_override_in_one_language_falls_back_for_the_others(tmp_path):
    root = _build(tmp_path, {"narrate.zh.md": "只写叙事(测试)。"})
    assert prompts.text("narrate", "zh", root) == "只写叙事(测试)。"
    assert prompts.text("narrate", "ja", root) == turn_v3.NARRATE["ja"]
