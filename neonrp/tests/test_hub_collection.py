"""线上 / iOS Hub 登录后的收集区(10-18,docs/planning/COLLECTION-SYNC-1018.md):直接读账号上的 data hub/collection(两页翻完、
同一样东西两条留新的)、卡图按 catalog 的 rewards 取模板出的图、成就用记录里的四语标题和积分;旧会话没有 data 权限 → 「重新登录后同步」;
没登录不去问 data。自由区作品的角色不进角色收集。tests/hub_collection.mjs 用假的 data(data.test)跑 hub/index.html + hub.js。
截图:HUB_COLLECTION_SHOTS=<目录> 时留在那里。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "worldlines" / "ui"
HUB = UI / "app" / "hub"


@pytest.fixture(scope="module")
def r(tmp_path_factory):
    node = shutil.which("node")
    if not node or not (UI / "node_modules" / "playwright").is_dir() or not (HUB / "hub.js").is_file():
        pytest.skip("node + worldlines/ui/node_modules/playwright needed")
    shots = Path(os.environ.get("HUB_COLLECTION_SHOTS") or tmp_path_factory.mktemp("shots"))
    shots.mkdir(parents=True, exist_ok=True)
    out = subprocess.run([node, str(ROOT / "tests" / "hub_collection.mjs"), str(HUB / "index.html"), str(HUB / "hub.js"), str(UI / "package.json"), str(shots)],
                         capture_output=True, text=True, timeout=240, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_no_page_errors(r):
    assert r["errs"] == []


def test_the_web_reads_the_account_collection_page_by_page(r):
    w = r["web"]
    assert w["calls"] == ["/v1/records/hub/collection?mine||Bearer tok", "/v1/records/hub/collection?mine|p2|Bearer tok"]
    assert [c["key"] for c in w["cards"]] == ["pct-house:behind_the_wall", "pct-house:half_burnt_diary"]
    assert w["cards"][0]["title"] == "The One Behind the Wall", "the newer of two records for the same card"
    assert w["cards"][0]["img"].endswith("/img/pct-house/cards/behind_the_wall.webp") and w["cards"][1]["img"] is None, "the picture from the catalog"
    assert not any(c["pull"] for c in w["cards"]), "pulling a new version is the engine's"
    assert w["roster"] == ["Oswin"] and w["party"] == ["Oswin"]
    assert w["ach"] == ["Another Door +10"], "the achievement's four-language face from the record"
    assert w["sync"] == "ok"


def test_an_old_session_is_asked_to_sign_in_again(r):
    assert r["relogin"]["state"] == "relogin" and "重新登录" in r["relogin"]["text"] and r["relogin"]["hscroll"] == 0
    assert r["relogin"]["signin"], "403 insufficient_scope: a sign-in button right there (a refresh never adds the scope)"


def test_signed_out_never_asks_data(r):
    assert r["signedOut"]["calls"] == 0


def test_free_zone_characters_are_not_in_the_character_collection(r):
    assert r["souls"].count("自由区的陌生人") == 0 and "Oswin" in r["souls"]
