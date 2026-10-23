"""Hub 的只读回放页 #/replay/<id>(replay 代理 10-18,hub.js):本地模式读引擎 /api/v1/local/replays/<id>,点「分享到平台」没登录 → 说要登录;
线上模式读 storage 公开下载地址 → timeline.json,只给复制链接。回放文档用 test_replay_pack 的同一局造。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from neonrp.core import replay_pack as RP
from test_replay_pack import _run
def _hub_replay(tmp_path, mode, hub_js=None):
    """Hub 只读回放页(hub.js #/replay/<id>),playwright 里跑:本地模式读引擎接口,线上模式读 storage 公开下载。"""
    import shutil
    import subprocess

    root = Path(__file__).resolve().parents[1]
    ui, hub = root / "worldlines" / "ui", root / "worldlines" / "ui" / "app" / "hub"
    node = shutil.which("node")
    if not node or not (ui / "node_modules" / "playwright").is_dir():
        pytest.skip("node + worldlines/ui/node_modules/playwright needed")
    cfg = '{"mode":"auto"}' if mode == "local" else '{"mode":"static","catalog":"catalog.json","storage":"http://storage.test"}'
    js = Path(hub_js) if hub_js else hub / "hub.js"
    page = (hub / "index.html").read_text(encoding="utf-8").replace(
        "<!--SCRIPT-->", f"<script>window.HUB={cfg}</script><script>" + js.read_text(encoding="utf-8") + "</script>")
    (tmp_path / "page.html").write_text(page, encoding="utf-8")
    doc = RP.build_replay_doc(_run(tmp_path / "mist-house-20261018-101010"), world_id="mist-house", world_name="Mist House", lang="en")
    (tmp_path / "doc.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    out = subprocess.run([node, str(root / "tests" / "hub_replay.mjs"), str(tmp_path / "page.html"), str(tmp_path / "doc.json"), str(ui / "package.json"), mode],
                         capture_output=True, text=True, timeout=180, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("mode", ["local", "online"])
def test_hub_replay_page(tmp_path, mode):
    import os

    r = _hub_replay(tmp_path, mode, os.environ.get("HUB_JS_OVERRIDE"))
    assert r["errs"] == []
    assert r["sections"] == 3 and r["tags"][0].startswith("Opening") and r["tags"][1].startswith("Turn 2 · Mist House · Study · Day 1 21:00")
    assert r["you"] == ["ask Mira"] and r["dice"] and "Ines Spot 1d100 = 12 vs 40" in r["dice"][0]
    assert "The study is cold." in r["text"] and "Out of the fog" in r["text"] and "intends" not in r["text"]
    if mode == "local":
        assert r["play"] == ["/player.html?replay=r1&lang=en"], "play = the standard front end's stage (replayer.js)"
        assert r["share"] and r["shares"] and "sign in to worldlines" in r["toast"].lower(), "401 → say to sign in"
    else:
        assert not r["share"] and r["copy"] == ["https://neonrp.worldlines.gg/#/replay/r-pub"] and r["play"] == []

