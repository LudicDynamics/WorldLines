"""R1 acceptance (APP-REQUESTS-PACK-BEATS-1009, 10-10): the open engine carries none of our planning beat — no module, no
prompt, and none of its words (「商量 / 清算 / 谈定」) anywhere in the engine's source, prompts or pack data. The planning
beat is a node-kind plugin of the private layer (NeonRP-private)."""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "neonrp"
WORDS = re.compile("商量|清算|谈定")
_SKIP = ("webui/spa/",)  # a built front-end bundle, excluded from the export


def test_no_planning_module_or_prompt_in_the_engine():
    assert not (SRC / "core" / "plan_loop.py").exists()
    for unit in ("plan_sys", "plan_loop", "plan_check_grammar", "soul_plan_rule", "soul_exec_rule"):
        assert not list((SRC / "prompts").glob(f"{unit}.*")), unit


def test_none_of_its_words_in_the_engine():
    hits = []
    for f in SRC.rglob("*"):
        rel = f.relative_to(SRC).as_posix()
        if not f.is_file() or "__pycache__" in f.parts or rel.startswith(_SKIP) or f.suffix in (".pyc", ".png", ".jpg", ".webp"):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        hits += [f"{rel}:{i}" for i, ln in enumerate(text.splitlines(), 1) if WORDS.search(ln)]
    assert not hits, hits[:20]
