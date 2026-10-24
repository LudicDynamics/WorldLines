"""License boundary: the engine (Apache-2.0) must not take code from the product (worldlines/, AGPL-3.0).

The dependency only goes one way — the product uses the engine. If engine code imported or copied product code, the
engine package would carry AGPL code. Content (worlds, templates, prompts) is shared on purpose: the same authors
publish it under both licenses, so only code files are checked here.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]
ENGINE_SRC = ENGINE_ROOT / "src" / "neonrp"
PRODUCT_PACKAGES = {"worldlines", "worldlines_shim"}
CODE_SUFFIXES = {".py", ".js", ".mjs", ".ts", ".css", ".html", ".vue", ".svelte"}
SKIP_DIRS = {"node_modules", "dist", "spa", "__pycache__", ".venv", "test-results", "playwright-report"}


def _product_dir() -> Path | None:
    # development repository: worldlines/ next to src/ · public repository: worldlines/ next to neonrp/
    for cand in (ENGINE_ROOT / "worldlines", ENGINE_ROOT.parent / "worldlines"):
        if cand.is_dir():
            return cand
    return None


def _walk(root: Path, suffixes: set[str]):
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in suffixes and not (SKIP_DIRS & set(p.relative_to(root).parts)):
            yield p


def test_engine_does_not_import_product_packages():
    bad = []
    for p in _walk(ENGINE_SRC, {".py"}):
        tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            for n in names:
                if n.split(".")[0] in PRODUCT_PACKAGES:
                    bad.append(f"{p.relative_to(ENGINE_ROOT)}:{node.lineno} imports {n}")
    assert not bad, "engine code imports the AGPL product:\n" + "\n".join(bad)


def test_engine_has_no_code_copied_from_product():
    product = _product_dir()
    if product is None:
        pytest.skip("product folder (worldlines/) not present")

    def digest(p: Path) -> str:
        return hashlib.sha1(p.read_bytes()).hexdigest()

    product_code = {}
    for p in _walk(product, CODE_SUFFIXES):
        if p.stat().st_size >= 200:  # tiny files (empty __init__, one-line stubs) match by accident
            product_code.setdefault(digest(p), p)
    copied = [
        f"{p.relative_to(ENGINE_ROOT)} == {product_code[d].relative_to(product.parent)}"
        for p in _walk(ENGINE_SRC, CODE_SUFFIXES)
        if p.stat().st_size >= 200 and (d := digest(p)) in product_code
    ]
    assert not copied, "engine contains code identical to AGPL product files:\n" + "\n".join(copied)


def test_pypi_license_files_in_step():
    # the worldlines package is built from worldlines/packaging/worldlines and can only ship files under it
    product = _product_dir()
    if product is None:
        pytest.skip("product folder (worldlines/) not present")
    pkg = product / "packaging" / "worldlines"
    assert (pkg / "LICENSE-PROPRIETARY.md").read_bytes() == (ENGINE_ROOT / "LICENSE-PROPRIETARY.md").read_bytes()
    assert (pkg / "LICENSE").read_bytes() == (product / "LICENSE").read_bytes()
