"""10-14:标准前端(Hub / iOS 的重前端,worldlines/ui/player)不在开源列表里 —— 导出白名单的 worldlines 条目要把它排除。
开源仓里没有 release/(导出脚本只在开发仓),那边跳过。"""
from __future__ import annotations

import sys
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib
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


@pytest.mark.skipif(not MANIFEST.is_file(), reason="release/ only exists in the development repo")
def test_official_worlds_and_legacy_ui_tests_are_not_exported():
    """10-17: the open repo carries the shipped worlds only. The engine's old-format 神楽島 is the same world as the
    excluded kagura-island.template, so it stays home too (10-24); Stoneford is the open example world and ships. The old
    UI's Playwright specs (ui/e2e-legacy, not in the config) stay home as well."""
    sys.path.insert(0, str(REPO / "release"))
    import export

    man = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))
    files = {p: b"" for p in ("src/neonrp/templates/kagura-island/souls/hane/soul.md", "src/neonrp/templates/kagura-island-ja/CLAUDE.md",
                              "src/neonrp/templates/kagura-island-en/game/meta/world.json", "src/neonrp/templates/stoneford-elena/game/meta/world.json",
                              "src/neonrp/templates/white-blank/game/meta/world.json",
                              "worldlines/ui/e2e-legacy/shell.spec.ts", "worldlines/ui/e2e/app.spec.ts")}
    out = set(export.plan(files, man).keys())
    assert not [p for p in out if "kagura-island" in p], out
    assert not [p for p in out if "e2e-legacy" in p], out
    assert {"neonrp/src/neonrp/templates/stoneford-elena/game/meta/world.json", "neonrp/src/neonrp/templates/white-blank/game/meta/world.json",
            "worldlines/ui/e2e/app.spec.ts"} <= out


@pytest.mark.skipif(not MANIFEST.is_file(), reason="release/ only exists in the development repo")
def test_internal_references_are_reported_but_do_not_block():
    """10-24: internal doc paths, decision ids, the private repo's name and dated personal notes are listed in the export
    report ([scan] warn) so they are seen before a release — they are not secrets, so they never fail the export."""
    sys.path.insert(0, str(REPO / "release"))
    import export

    man = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))
    note = "(" + "ni" + "ko 10-18)"   # a dated personal note; spelled apart so this file itself carries none
    staged = {"neonrp/src/x.py": f"# see docs/planning/FOO-1001.md and D-20261018-combat-one-shot-node {note}\n".encode(),
              "LICENSE.md": b"Copyright worldlines-nikoloside\n", "neonrp/README.md": b"NeonRP-private is where the layer lives\n"}
    warns = export.scan_warn(staged, man)
    assert {(w["rule"], w["path"]) for w in warns} == {("internal-doc-path", "neonrp/src/x.py"), ("decision-id", "neonrp/src/x.py"),
                                                       ("person-note", "neonrp/src/x.py"), ("private-repo", "neonrp/README.md")}, warns
    assert export.scan(staged, man) == []   # none of it is a blocking hit
