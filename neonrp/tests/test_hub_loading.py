"""Hub 刚打开的载入中(10-21 审核准备:以前先画一次空列表,闪一下「没有符合的世界」,审核员第一眼就可能看到):
世界列表没到 = 骨架卡片 +「正在载入世界…」(四语,aria-busy);到了出卡片;真的为空 / 拿不到才说「没有符合的世界」,不会一直停在载入中。
本地引擎模式和线上静态目录模式、手机和桌面、角色页都走一遍(tests/hub_loading.mjs,接口是假的、故意慢)。
截图:HUB_LOADING_SHOTS=<目录>。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HUB = ROOT / "worldlines" / "ui" / "app" / "hub"
UI = ROOT / "worldlines" / "ui"


@pytest.fixture(scope="module")
def r(tmp_path_factory):
    node = shutil.which("node")
    if not node or not (UI / "node_modules" / "playwright").is_dir():
        pytest.skip("node + worldlines/ui/node_modules/playwright needed")
    shots = os.environ.get("HUB_LOADING_SHOTS") or str(tmp_path_factory.mktemp("shots"))
    out = subprocess.run([node, str(ROOT / "tests" / "hub_loading.mjs"), str(HUB / "index.html"), str(HUB / "hub.js"), str(UI / "package.json"), shots],
                         capture_output=True, text=True, timeout=240, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_no_page_errors(r):
    assert r["errs"] == []


@pytest.mark.parametrize("name", ["local", "web", "desktop"])
def test_loading_first_then_cards(r, name):
    e, late = r[name]["early"], r[name]["late"]
    assert e["skel"] == 4 and e["busy"] and e["msg"] == "正在载入世界…" and e["cards"] == 0
    assert e["empty"] == "", "no 「没有符合的世界」 while the list is on its way"
    assert late["skel"] == 0 and not late["busy"] and late["cards"] >= 1 and late["empty"] == ""


def test_empty_list_says_empty_only_after_loading(r):
    assert r["empty"]["early"]["empty"] == "" and r["empty"]["early"]["skel"] == 4
    assert r["empty"]["late"] == {"skel": 0, "busy": False, "msg": "", "cards": 0, "empty": "没有符合的世界"}


def test_engine_down_does_not_spin_forever(r):
    late = r["down"]["late"]
    assert late["skel"] == 0 and not late["busy"] and late["empty"] == "没有符合的世界"


def test_four_languages_and_souls_page(r):
    assert r["en"]["early"]["msg"] == "Loading worlds…"
    assert r["souls"]["early"]["skel"] == 4 and r["souls"]["early"]["empty"] == ""
