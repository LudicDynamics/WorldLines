"""提示词四语.

① zh is byte-for-byte what it was before the texts left the code (tests/data/prompt_zh_snapshot.json; regenerate with
   tests/gen_prompt_snapshot.py only for a deliberate zh change).
② every prompt unit / string table has zh · en · ja · ko, with the same keys and placeholders.
③ a run in en / ja / ko builds every prompt of the main path without error, in the run's language.
④ engine code carries no more CJK prompt text than recorded (only goes down).
"""
from __future__ import annotations

import ast
import difflib
import json
import re
import sys
from pathlib import Path

import pytest

import prompt_harness as H
from neonrp import prompts

SNAP = Path(__file__).parent / "data" / "prompt_zh_snapshot.json"
SRC = Path(__file__).resolve().parents[1] / "src" / "neonrp"


def test_zh_prompts_are_unchanged_by_the_move(tmp_path):
    want = json.loads(SNAP.read_text(encoding="utf-8"))
    got = H.render_all(tmp_path, None)
    bad = []
    for k in sorted(set(want) | set(got)):
        if want.get(k) != got.get(k):
            diff = "\n".join(list(difflib.unified_diff((want.get(k) or "").splitlines(), (got.get(k) or "").splitlines(), lineterm="", n=1))[:14])
            bad.append(f"── {k}\n{diff}")
    assert not bad, "zh prompt changed:\n" + "\n".join(bad[:6])


# ── ② every unit in four languages ──

def _placeholders(t: str) -> set[str]:
    return set(re.findall(r"\{([a-z_]+)\}", t))


def test_every_unit_has_four_languages():
    u = prompts.units()
    missing = {f"{k}.md": sorted(set(prompts.LANGS) - v) for k, v in u["md"].items() if set(prompts.LANGS) - v}
    missing.update({f"{k}.json": sorted(set(prompts.LANGS) - v) for k, v in u["json"].items() if set(prompts.LANGS) - v})
    assert not missing, f"units missing languages: {missing}"


def test_tables_have_the_same_keys_and_placeholders():
    for table in prompts.units()["json"]:
        zh = prompts._read_json(table, "zh")
        for lg in prompts.LANGS[1:]:
            other = prompts._read_json(table, lg)
            assert set(other) == set(zh), f"{table}.{lg}: keys differ: {sorted(set(zh) ^ set(other))}"
            for k, v in zh.items():
                if isinstance(v, str):
                    assert _placeholders(other[k]) == _placeholders(v), f"{table}.{lg}[{k}] placeholders"


def test_md_units_keep_placeholders_and_protocol_marks():
    marks = ("<lines>", "</lines>", "<mic>", "<board>", "<draft>", "<vars>", "<files>", "next:", "[read", "@世界")
    for unit in prompts.units()["md"]:
        zh = prompts._read_md(unit, "zh") or ""
        for lg in prompts.LANGS[1:]:
            t = prompts._read_md(unit, lg) or ""
            assert _placeholders(t) == _placeholders(zh), f"{unit}.{lg} placeholders"
            for m in marks:
                if m in zh and m != "@世界":
                    assert m in t, f"{unit}.{lg} lost the protocol mark {m!r}"


def test_no_language_carries_a_built_in_world_s_names():
    """test_engine_v3::test_prompt_examples_carry_no_world_names for every language file (10-05: the model copied the
    example's companion in). soul_view's default player name 「旅人」 is a name for the player, not an example."""
    names = set()
    for sj in (SRC / "templates").glob("*/souls/*/soul.json"):
        d = json.loads(sj.read_text(encoding="utf-8"))
        names |= {str(d.get(k)) for k in ("name", "name_local") if d.get(k)}
    names |= {"米拉", "Mira", "ミラ", "미라", "Rowan", "ローワン", "로완", "Elena", "エレナ", "엘레나", "艾琳娜"}
    leaked = {}
    for p in sorted((SRC / "prompts").iterdir()):
        if p.suffix not in (".md", ".json") or p.name.startswith("soul_view."):
            continue
        t = p.read_text(encoding="utf-8")
        hit = sorted(n for n in names if n and len(n) >= 2 and n in t)
        if hit:
            leaked[p.name] = hit
    assert not leaked, leaked


# ── ③ a run in another language ──

_SCRIPT = {"en": "latin", "ja": "kana", "ko": "hangul"}
# the units that are the engine's own words (the user messages carry the zh world's data, so they are measured loosely)
_SKELETON = ("plan.host0.system", "plan.exec.question", "narrate.call0.system", "adv.system", "gate.system",
             "layer_pack.referee", "layer_pack.combat", "layer_pack.dungeon", "plan.resolve_facts")


@pytest.mark.parametrize("lang", ["en", "ja", "ko"])
def test_a_run_in_another_language_builds_every_prompt_in_it(tmp_path, lang):
    out = H.render_all(tmp_path, lang)
    assert set(out) >= {k for k in json.loads(SNAP.read_text(encoding="utf-8"))}
    script = _SCRIPT[lang]
    for k in _SKELETON:
        share = H.script_share(out[k], script)
        floor = 0.3 if lang != "ja" else 0.25  # ja mixes kanji; kana alone is a share of the letters; paths and op names are latin
        assert share >= floor, f"{lang} {k}: {script} share {share:.2f} — skeleton not in the run's language"


# ── ④ CJK prompt text left in engine code ──

_EXEMPT_DIRS = ("tui", "webui", "prompts", "templates", "builtin_skills")
CJK_CAP = None  # set below from the recorded file


def _cjk_string_lines() -> dict[str, int]:
    """Per file: string-literal lines (not docstrings / comments) with Han / kana / hangul."""
    out: dict[str, int] = {}
    cjk = re.compile(r"[぀-ヿ一-鿿가-힯]")
    for p in SRC.rglob("*.py"):
        rel = p.relative_to(SRC)
        if rel.parts[0] in _EXEMPT_DIRS or rel.name in ("i18n.py",):
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        doc_ids = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
                first = node.body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                    doc_ids.add(id(first.value))
        lines: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in doc_ids and cjk.search(node.value):
                lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
        if lines:
            out[rel.as_posix()] = len(lines)
    return out


@pytest.mark.skipif(sys.version_info < (3, 12), reason="the cap is counted with the 3.12 parser (f-strings split differently before 3.12)")
def test_cjk_prompt_text_in_engine_code_only_goes_down():
    cap = json.loads((Path(__file__).parent / "data" / "prompt_cjk_cap.json").read_text(encoding="utf-8"))
    now = _cjk_string_lines()
    grew = {f: (cap.get(f, 0), n) for f, n in now.items() if n > cap.get(f, 0)}
    assert not grew, f"CJK string lines grew (cap, now): {grew} — put prompt text in src/neonrp/prompts/"
