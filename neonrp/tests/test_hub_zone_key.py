"""线上浏览器游玩按区选模型(niko 10-26 · hub/play/boot.js):默认区(官方世界 · 默认区的社区作品)只用 Worldlines 额度(登录或游客),
门上没有「用我自己的 key」,?own=1 不认,存过的 key 留在这个浏览器里但默认区不用;自由区作品额度默认,也能填自己的 key,
key 旁写明只存在这个浏览器里、只发给填的地址。门在下载 Pyodide 之前,不起引擎(tests/hub_play_zone.mjs)。"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLAY = ROOT / "worldlines" / "ui" / "app" / "hub" / "play"
UI = ROOT / "worldlines" / "ui"


@pytest.fixture(scope="module")
def r():
    node = shutil.which("node")
    if not node or not (UI / "node_modules" / "playwright").is_dir():
        pytest.skip("node + worldlines/ui/node_modules/playwright needed")
    out = subprocess.run([node, str(ROOT / "tests" / "hub_play_zone.mjs"), str(PLAY), str(UI / "package.json")],
                         capture_output=True, text=True, timeout=180, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_default_zone_gate_is_credits_only(r):
    for case in ("defaultGuest", "defaultOwnLink"):
        g = r[case]
        assert g["errs"] == [] and g["mode"] == "wl", case
        assert g["keyForm"] == 0 and "自己的 key" not in g["screen"], f"{case}: the default zone offers no own key"
        assert "登录后用 Worldlines 额度玩" in g["screen"]
        assert ["登录 Worldlines(用额度)", "/#/t/official?play=1"] in g["signin"]
        assert not g["modelSheet"], "no model settings in the default zone"


def test_default_zone_keeps_but_ignores_a_stored_key(r):
    for case in ("defaultOwnLink", "defaultSignedKey"):
        g = r[case]
        assert g["mode"] == "wl", f"{case}: a saved key-mode falls back to credits in the default zone"
        assert g["stored"] == {"key": True, "mode": "key"}, f"{case}: the saved key is not deleted"


def test_curated_community_work_needs_sign_in_and_returns_to_the_default_zone(r):
    g = r["curatedGuest"]
    assert g["errs"] == [] and "登录后才能玩这个作品" in g["screen"] and g["keyForm"] == 0
    assert g["signin"] == [["← 回到 Hub", "/#/t/comm-abc123"]], "a default-zone community work goes back to the default zone, not /free/"


def test_free_zone_offers_credits_and_own_key(r):
    g = r["freeGuest"]
    assert g["errs"] == [] and g["keyForm"] == 1 and g["modelSheet"]
    assert "登录 Worldlines(用额度)" in g["screen"] and "用我自己的 key" in g["screen"]
    assert g["screen"].index("登录 Worldlines") < g["screen"].index("用我自己的 key"), "credits come first"
    assert "key 只存在这个浏览器里,只发给你填的地址" in g["screen"]
    assert g["signin"][0][1] == "/free/#/t/w-free-abc123?play=1"
    assert r["freeOwnNoKey"]["keyForm"] == 1, "?own=1 on a free work opens the key form"
    assert r["freeSignedKey"]["mode"] == "key", "a saved key still runs free works"
