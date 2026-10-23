"""模板的分区 zone(10-15,两区:审核区 reviewed / 开源区 open):模板自己在 template.json 里写(或 card.zone / 世界 manifest
的 zone),/api/v1/local/templates 每行带 zone(没写 = null),lint 校验取值。官方 8 个故事世界写的是 reviewed。"""
from __future__ import annotations

import json
import shutil
import threading
import urllib.request
from unittest.mock import patch

import pytest

from _paths import PRODUCT_TEMPLATES
from neonrp import template as TP

OFFICIAL = ("guixiang", "wuwu", "last-train", "pct-house", "stoneford-town", "kagura-island", "spice-witch", "neon-rebirth")


@pytest.mark.parametrize("name", OFFICIAL)
def test_official_worlds_say_reviewed(name):
    t = TP.load(PRODUCT_TEMPLATES / f"{name}.template")
    assert t.zone == "reviewed" and t.meta()["zone"] == "reviewed"
    assert json.loads((t.dir / "template.json").read_text(encoding="utf-8"))["zone"] == "reviewed", "written in the template, not in code"


def _copy(tmp_path, name="stoneford-elena"):
    d = tmp_path / f"{name}.template"
    shutil.copytree(PRODUCT_TEMPLATES / f"{name}.template", d)
    return d


def test_zone_comes_from_the_template_card_or_manifest(tmp_path):
    d = _copy(tmp_path)
    tj = json.loads((d / "template.json").read_text(encoding="utf-8"))
    tj.pop("zone", None)
    tj.get("card", {}).pop("zone", None)
    (d / "template.json").write_text(json.dumps(tj, ensure_ascii=False), encoding="utf-8")
    assert TP.load(d).zone is None and TP.load(d).meta()["zone"] is None
    man = d / str((tj.get("world") or {}).get("path") or "world") / "manifest.json"
    if man.is_file():
        m = json.loads(man.read_text(encoding="utf-8"))
        man.write_text(json.dumps({**m, "zone": "open"}, ensure_ascii=False), encoding="utf-8")
        assert TP.load(d).zone == "open"
    tj["card"]["zone"] = "reviewed"
    (d / "template.json").write_text(json.dumps(tj, ensure_ascii=False), encoding="utf-8")
    assert TP.load(d).zone == "reviewed"
    tj["zone"] = "open"
    (d / "template.json").write_text(json.dumps(tj, ensure_ascii=False), encoding="utf-8")
    assert TP.load(d).zone == "open", "the top-level key wins"


def test_lint_checks_the_value(tmp_path):
    d = _copy(tmp_path)
    tj = json.loads((d / "template.json").read_text(encoding="utf-8"))
    tj["zone"] = "curated"
    (d / "template.json").write_text(json.dumps(tj, ensure_ascii=False), encoding="utf-8")
    probs = [p for p in TP.lint(TP.load(d), i18n=False)["problems"] if p["code"] == "meta.zone"]
    assert probs and probs[0]["level"] == "block"
    tj["zone"] = "open"
    (d / "template.json").write_text(json.dumps(tj, ensure_ascii=False), encoding="utf-8")
    assert not [p for p in TP.lint(TP.load(d), i18n=False)["problems"] if p["code"] == "meta.zone"]


def test_the_template_list_carries_zone(tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    store = tmp_path / "store"
    shutil.copytree(PRODUCT_TEMPLATES / "pct-house.template", store / "pct-house.template")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(store))
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "studio"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{server.server_address[1]}/api/v1/local/templates", timeout=120) as r:
                rows = {x["id"]: x for x in json.loads(r.read())["templates"]}
            assert rows["pct-house"]["zone"] == "reviewed"
            assert all("zone" in x for x in rows.values())
        finally:
            server.shutdown()
