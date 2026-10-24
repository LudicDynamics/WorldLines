"""Hub「我的 · 收集区」:角色的作者更新了 → diff 页(10-20,core/soul_update):一项一项选「留我的 / 用作者的」(默认值来自引擎)、
三个一键(全部按推荐 / 全用作者的 / 全留我的)、「按这样更新」POST choices + token、作者又改了(409)重新拉一次再更新。
diff 是真引擎算出来的(灰橡宅 · 温妮:作者改了人设和一条记忆);引擎接口用 page.route 假装。截图:HUB_SOUL_UPDATE_SHOTS=<目录>。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from test_soul_update import _author_changes, _take, store  # noqa: F401 — the store copy fixture

from neonrp.core import soul_update as U
from _paths import PRODUCT

ROOT = Path(__file__).resolve().parents[1]
UI = PRODUCT / "ui"
HUB = UI / "app" / "hub"


@pytest.fixture
def r(store, tmp_path):  # noqa: F811
    node = shutil.which("node")
    if not node or not (UI / "node_modules" / "playwright").is_dir() or not (HUB / "hub.js").is_file():
        pytest.skip("node + worldlines/ui/node_modules/playwright + the Hub source (not in the open repo) needed")
    snap = _take(store, tmp_path)
    U.diff("pct-house", "chara")
    _author_changes(store)
    d = U.diff("pct-house", "chara")
    assert len(d["items"]) == 2
    (tmp_path / "diff.json").write_text(json.dumps({lg: U.diff("pct-house", "chara", lg) for lg in ("zh", "en")}, ensure_ascii=False), encoding="utf-8")
    page = (HUB / "index.html").read_text(encoding="utf-8").replace(
        "<!--SCRIPT-->", "<script>window.HUB={}</script><script>" + (HUB / "hub.js").read_text(encoding="utf-8") + "</script>")
    (tmp_path / "page.html").write_text(page, encoding="utf-8")
    shots = Path(os.environ.get("HUB_SOUL_UPDATE_SHOTS") or tmp_path / "shots")
    shots.mkdir(parents=True, exist_ok=True)
    out = subprocess.run([node, str(ROOT / "tests" / "hub_soul_update.mjs"), str(tmp_path / "page.html"), str(tmp_path / "diff.json"),
                          str(UI / "package.json"), str(shots)], capture_output=True, text=True, timeout=240, check=True)
    return d, json.loads(out.stdout.strip().splitlines()[-1])


def test_the_diff_page(r):
    d, o = r
    assert o["errs"] == []
    ids = [it["id"] for it in d["items"]]
    assert o["defaults"] == [[it["id"], it["default"]] for it in d["items"]], "the engine's defaults are preselected"
    assert o["both"] == sum(it["both_changed"] for it in d["items"]) and o["groups"] == ["设定 · 2"]
    assert sorted(o["labels"]) == sorted(["人设 · 性格类型", "人设 · 害怕的东西"]), "names for the player, not the raw keys"
    assert sorted(o["chips"]) == [["mine", "黑暗里的敲墙声", "你的"], ["theirs", "钟声", "新增"]] and not o["brackets"], "a list as one line each, what differs marked"
    assert o["allTheirs"] == [[i, "theirs"] for i in ids] and o["allMine"] == [[i, "mine"] for i in ids]
    assert o["edited"][0] == [ids[0], "mine"]
    assert o["afterStale"]["open"] and any("又改了" in x for x in o["afterStale"]["toast"]), "409: the diff is fetched again"
    assert not o["afterGo"]["open"] and any("已更新" in x for x in o["afterGo"]["toast"])
    first, last = o["posts"]
    assert first["token"] == d["token"] and first["choices"] == {ids[0]: "mine", **{i: it["default"] for i, it in zip(ids[1:], d["items"][1:])}}
    assert last["choices"] == {it["id"]: it["default"] for it in d["items"]}, "fetched again after 409: the defaults again"
    for k in ("10-soul-update-diff-en", "11-soul-update-diff-zh-phone", "12-soul-update-diff-en-phone"):
        assert o[k]["hscroll"] == 0, k
    assert "author updated" in o["12-soul-update-diff-en-phone"]["h2"]
    assert sorted(o["10-soul-update-diff-en"]["labels"]) == ["Persona · Fears", "Persona · Personality"]
