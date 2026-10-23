"""niko 10-14:标准前端(Hub / iOS 的重前端,worldlines/ui/player)不在开源列表里 —— 导出白名单的 worldlines 条目要把它排除。
开源仓里没有 release/(导出脚本只在开发仓),那边跳过。"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "release" / "manifest.toml"


@pytest.mark.skipif(not MANIFEST.is_file(), reason="release/ only exists in the development repo")
def test_standard_frontend_is_not_exported():
    sys.path.insert(0, str(REPO / "release"))
    import export

    man = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))
    files = {p: b"" for p in ("worldlines/ui/player/src/app.js", "worldlines/ui/player/build.mjs", "worldlines/ui/player/e2e/mock_ai.py",
                              "worldlines/ui/player/dist/player.html", "worldlines/ui/app/src/builder.js")}
    out = export.plan(files, man)
    assert not [p for p in out.values() if p.startswith("worldlines/ui/player/")], out
    assert "worldlines/ui/app/src/builder.js" in out.values(), "the test bench (and the builder it shares) still ships"
