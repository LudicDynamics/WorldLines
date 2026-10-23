"""10-08 (1.0 UI E3): an ending image not generated yet must not stop a run from starting — prompt first, image later;
10-16 (niko): the template lint only warns about it too — the slot stays declared, the image comes later."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from neonrp import template as TP
from _paths import PRODUCT_TEMPLATES

SRC = PRODUCT_TEMPLATES / "pct-house.template"


def _with_missing_image(tmp_path: Path) -> Path:
    d = tmp_path / "pct-house.template"
    shutil.copytree(SRC, d)
    pj = d / "plots" / "P01" / "plot.json"
    plot = json.loads(pj.read_text(encoding="utf-8"))
    eid = next(iter(plot["endings"]))
    plot["endings"][eid]["assets"] = {"image": "assets/not-yet.png"}
    pj.write_text(json.dumps(plot, ensure_ascii=False), encoding="utf-8")
    return d


def test_build_goes_on_lint_only_warns(tmp_path):
    d = _with_missing_image(tmp_path)
    t = TP.load(d)
    TP.build(t, tmp_path / "run")  # used to raise: plot has lint errors … file not found
    assert (tmp_path / "run" / "game" / "plots" / "P01" / "plot.json").is_file()
    rep = TP.lint(t)
    hits = [p for p in rep["problems"] if p["code"] == "plot" and "not-yet.png" in p["msg"]]  # (the i18n layer also flags its own path drift)
    assert hits and all(p["level"] == "warn" for p in hits)
    assert not any(p["level"] == "block" and "file not found" in p["msg"] for p in rep["problems"])


def test_bad_asset_path_still_blocks(tmp_path):
    d = _with_missing_image(tmp_path)
    pj = d / "plots" / "P01" / "plot.json"
    plot = json.loads(pj.read_text(encoding="utf-8"))
    eid = next(iter(plot["endings"]))
    plot["endings"][eid]["assets"] = {"image": "../outside.png"}
    pj.write_text(json.dumps(plot, ensure_ascii=False), encoding="utf-8")
    rep = TP.lint(TP.load(d))
    assert any(p["level"] == "block" and "inside the plot folder" in p["msg"] for p in rep["problems"])
