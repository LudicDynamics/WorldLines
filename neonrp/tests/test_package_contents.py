"""What goes to PyPI (10-23, before 1.0.1): the source package is the engine only — no docs/ (play records, full
prompts, planning), no worldlines/ — and neither package carries the worlds whose rights are not cleared."""
from __future__ import annotations

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _hatch() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"]["build"]["targets"]


def test_the_source_package_is_the_engine_only():
    sd = _hatch()["sdist"]
    inc = sd["only-include"]
    assert "src/neonrp" in inc and not any(p.startswith(("docs", "worldlines", "benchmarks", "tests")) for p in inc)
    assert {"src/neonrp/templates/daogui/**", "src/neonrp/templates/lianyu/**", "src/neonrp/webui/devtools/**"} <= set(sd["exclude"])


def test_the_wheel_leaves_out_the_uncleared_worlds():
    ex = set(_hatch()["wheel"]["exclude"])
    assert {"src/neonrp/templates/daogui/**", "src/neonrp/templates/lianyu/**"} <= ex
