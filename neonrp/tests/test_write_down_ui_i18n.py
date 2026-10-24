"""写状态先快后修正(10-22):网页前端的提示文案和 TUI 的 wd.* 一字不差(src/neonrp/tui/i18n.py 是唯一的来源)。

两处:测试台 worldlines/ui/app/real/engine.js 的 WD_T(JSON)· 标准前端 worldlines/ui/player/src/i18n.js 的 wdPending …(四语)。"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from neonrp.tui.i18n import get_message
from _paths import PRODUCT

ROOT = Path(__file__).resolve().parents[1]
KEYS = ("pending", "corrected", "same", "cut", "timeout", "failed")
LANGS = ("zh", "en", "ja", "ko")


def test_test_bench_strings_are_the_tuis():
    src = (PRODUCT / "ui/app/real/engine.js").read_text(encoding="utf-8")
    m = re.search(r"const WD_T = (\{.*?\});\n", src)
    assert m, "WD_T in engine.js"
    tab = json.loads(m.group(1))
    for lang in LANGS:
        for k in KEYS:
            assert tab[lang][k] == get_message(lang, f"wd.{k}"), (lang, k)


@pytest.mark.skipif(not (PRODUCT / "ui" / "player" / "src").is_dir(), reason="the standard front end (ui/player) is not in the open repo")
def test_standard_front_end_strings_are_the_tuis():
    src = (PRODUCT / "ui/player/src/i18n.js").read_text(encoding="utf-8")
    rows = [ln for ln in src.splitlines() if "wdPending:" in ln]
    assert len(rows) == 4, "one row per language, in zh · en · ja · ko order"

    def js_str(row: str, key: str) -> str:
        m = re.search(key + r": '((?:[^'\\]|\\.)*)'", row)
        assert m, key
        return m.group(1).replace("\\'", "'").replace("\\\\", "\\")

    for lang, row in zip(LANGS, rows):
        for k in KEYS:
            assert js_str(row, "wd" + k[0].upper() + k[1:]) == get_message(lang, f"wd.{k}"), (lang, k)
