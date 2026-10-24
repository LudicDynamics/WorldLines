"""10-17: the local edition ships only 灰橡宅 and 石津镇 (worldlines/templates/shipped.json, at the top of every list);
the other official worlds come down with a Worldlines account into the official cache (NEONRP_OFFICIAL_DIR) — played,
never exported or copied. Only templates saying ``forkable: true`` (the two shipped ones) offer 「复制一份来改」."""

from __future__ import annotations

import json
import re
import shutil

import pytest

from neonrp import template as TP
from neonrp.template import author
from neonrp.template.package import ExportRefused, export_template

from _paths import ENGINE_ROOT, PRODUCT_TEMPLATES

SHIPPED = ["pct-house", "stoneford-town"]


@pytest.fixture
def store(tmp_path, monkeypatch):
    w = tmp_path / "store"
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(w))
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(w))
    monkeypatch.setenv("NEONRP_OFFICIAL_DIR", str(tmp_path / "official"))
    monkeypatch.setenv("WORLDLINES_ASSETS_DIR", str(tmp_path / "assets"))
    monkeypatch.delenv("NEONRP_TEMPLATES", raising=False)
    return w


def _official(tmp_path, src: str, tid: str | None = None):
    """A fetched copy of an official world in the official cache (what core/template_publish.fetch_official writes)."""
    d = tmp_path / "official" / f"{tid or src}.template"
    shutil.copytree(PRODUCT_TEMPLATES / f"{src}.template", d)
    tj = json.loads((d / "template.json").read_text(encoding="utf-8"))
    tj.update({"id": tid or src, "zone": "reviewed", "official": True, "hub_ref": f"hub/template/{tid or src}", "hub_revision": 3})
    tj.pop("forkable", None)
    (d / "template.json").write_text(json.dumps(tj, ensure_ascii=False), encoding="utf-8")
    return d


def test_shipped_list_and_the_wheel_agree():
    ship = json.loads((PRODUCT_TEMPLATES / "shipped.json").read_text(encoding="utf-8"))["builtin"]
    assert ship == SHIPPED and TP.shipped_ids() == SHIPPED
    py = ENGINE_ROOT / "worldlines" / "packaging" / "worldlines" / "pyproject.toml"
    if not py.is_file():
        pytest.skip("the worldlines packaging lives in the dev repo")
    inc = re.findall(r'^"\.\./\.\./templates/([^"]+)"\s*=', py.read_text(encoding="utf-8"), re.M)
    assert sorted(inc) == sorted(["shipped.json", *[f"{t}.template" for t in ship]])   # not the whole folder
    assert not re.search(r'^"\.\./\.\./templates"\s*=', py.read_text(encoding="utf-8"), re.M)
    for t in ship:
        d = TP.load(PRODUCT_TEMPLATES / f"{t}.template")
        assert d.forkable and d.zone == "reviewed" and d.builtin


def test_shipped_first_and_shipped_only_mode(store, monkeypatch):
    found = TP.discover()
    assert list(found)[:2] == SHIPPED
    monkeypatch.setenv("NEONRP_TEMPLATES", "shipped")   # what an installed release sees
    assert list(TP.discover()) == SHIPPED


def test_official_cache_is_searched_last_and_read_only(store, tmp_path, monkeypatch):
    _official(tmp_path, "wuwu")
    monkeypatch.setenv("NEONRP_TEMPLATES", "shipped")
    found = TP.discover()
    assert found["wuwu"] == tmp_path / "official" / "wuwu.template"
    t = TP.load(found["wuwu"])
    m = t.meta()
    assert m["official"] and m["hub_revision"] == 3 and m["forkable"] is False and not m.get("builtin")
    assert not author.writable(t)
    with pytest.raises(ExportRefused):
        export_template(t)
    with pytest.raises(TP.TemplateError, match="not copied"):
        author.fork(t, "wuwu-mine")
    # from source the repo's copy of an official world wins over a downloaded one (the source is what the author edits)
    monkeypatch.delenv("NEONRP_TEMPLATES")
    assert TP.discover()["wuwu"] == PRODUCT_TEMPLATES / "wuwu.template"


def test_fork_matrix(store, tmp_path):
    found = TP.discover()
    # the shipped two: forkable; the copy is the author's own, no official marks
    t = author.fork(found["pct-house"], "pct-mine")
    d = json.loads((t.dir / "template.json").read_text(encoding="utf-8"))
    assert not ({"forkable", "official", "hub_ref", "hub_revision", "zone"} & set(d))
    assert TP.can_fork(t) and TP.load(t.dir).meta()["forkable"]   # own work: always
    # another official template (zone reviewed, no forkable): played, not copied
    assert not TP.can_fork(TP.load(found["guixiang"]))
    with pytest.raises(TP.TemplateError, match="not copied"):
        author.fork(found["guixiang"], "gx-mine")
    # a dev fixture with no zone: still copyable (the authoring tests fork those)
    assert TP.can_fork(TP.load(found["stoneford-market"]))


def test_lint_forkable(store, tmp_path):
    src = author.fork(TP.discover()["stoneford-market"], "lint-fk")
    tj = src.dir / "template.json"
    d = json.loads(tj.read_text(encoding="utf-8"))
    d["forkable"] = "yes"
    tj.write_text(json.dumps(d), encoding="utf-8")
    codes = {(p["level"], p["code"]) for p in TP.lint(src.dir)["problems"]}
    assert ("block", "meta.forkable") in codes
    d["forkable"] = True   # on the author's own (zoneless) work it means nothing
    tj.write_text(json.dumps(d), encoding="utf-8")
    codes = {(p["level"], p["code"]) for p in TP.lint(src.dir)["problems"]}
    assert ("warn", "meta.forkable") in codes and ("block", "meta.forkable") not in codes


def test_open_source_export_carries_only_the_shipped_templates():
    import sys
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        import tomli as tomllib

    man_p = ENGINE_ROOT / "release" / "manifest.toml"
    if not man_p.is_file():
        pytest.skip("release/ only exists in the development repo")
    sys.path.insert(0, str(ENGINE_ROOT / "release"))
    import export

    man = tomllib.loads(man_p.read_text(encoding="utf-8"))
    ids = sorted(p.name[: -len(".template")] for p in PRODUCT_TEMPLATES.glob("*.template") if (p / "template.json").is_file())
    files = {f"worldlines/templates/{i}.template/template.json": b"" for i in ids}
    files["worldlines/templates/shipped.json"] = b""
    out = export.plan(files, man)
    got = sorted(v.split("/")[2][: -len(".template")] for v in out.values() if v.endswith("/template.json"))
    assert got == sorted(SHIPPED), got
    assert "worldlines/templates/shipped.json" in out.values()
