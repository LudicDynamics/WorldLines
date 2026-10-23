"""标准前端的回放播放器(niko 10-18:回放 = 把这一局按动画重播;worldlines/ui/player/src/replayer.js · player.html?replay=<id>):
同一套舞台(STAGE / FX),只读不绑局(一次引擎的游玩接口都不叫)、输入框收起;暂停 = 停住;16× 放到结局 → 结局演出带包里的结局插画;
暂停着拖到某一拍 = 前面的字铺好、停在那。回放文档用 test_replay_pack 的同一局造(带拍事件 / 在场角色 / 图)。"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from neonrp.core import replay_export as RE
from test_replay_pack import _run

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "worldlines" / "ui"
PLAYER = UI / "player"
ENTRY = "    if (typeof REPLAYER !== 'undefined' && REPLAYER.wanted()) return REPLAYER.main();\n"


def _page(tmp_path: Path) -> Path:
    """player.html the way build.mjs makes it, replayer.js before app.js (and app.js's one-line entry when the
    checkout's app.js does not have it yet)."""
    node = shutil.which("node")
    if not node or not (UI / "node_modules" / "playwright").is_dir():
        pytest.skip("node + worldlines/ui/node_modules/playwright needed")
    src = re.search(r"const SRC = \[([\s\S]*?)\]\n", (PLAYER / "build.mjs").read_text(encoding="utf-8")).group(1)
    files = re.findall(r"'([^']+)'", re.sub(r"\.\.\.\(DEBUG[^)]*\)\)?,?", "", src))
    files = [f for f in files if f != "src/debug.js"]
    if "src/replayer.js" not in files:
        files.insert(files.index("src/app.js"), "src/replayer.js")
    fb = subprocess.run([node, "-e", f"import('{(PLAYER / 'assets' / 'fallback' / 'inline.mjs').as_posix()}').then(m => process.stdout.write(m.fbartJs()))"],
                        capture_output=True, text=True, check=True).stdout

    def rd(f: str) -> str:
        if f == "fbart":
            return fb
        s = (PLAYER / f).read_text(encoding="utf-8")
        return s.replace("  async function main() {\n", "  async function main() {\n" + ENTRY, 1) if f == "src/app.js" and "REPLAYER.wanted" not in s else s

    esc = "<\\/script>"  # no backslash inside the f-string: Python 3.10 (requires-python) cannot parse one
    js = "\n".join(f"<script>\n{rd(f).replace('</script>', esc)}\n</script>" for f in files)
    page = (PLAYER / "src" / "index.html").read_text(encoding="utf-8").replace("<!--HEAD-->", "").replace(
        "/*CSS*/", (PLAYER / "src" / "player.css").read_text(encoding="utf-8")).replace("<!--SCRIPTS-->", js)
    out = tmp_path / "player.html"
    out.write_text(page, encoding="utf-8")
    return out


def test_player_replays_a_run_on_the_stage(tmp_path):
    page = _page(tmp_path)
    _meta, files = RE.pack_replay(_run(tmp_path / "mist-house-20261018-101010"), lang="en")
    (tmp_path / "doc.json").write_bytes(files["timeline.json"])
    out = subprocess.run([shutil.which("node"), str(ROOT / "tests" / "player_replay.mjs"), str(page), str(tmp_path / "doc.json"), str(UI / "package.json")],
                         capture_output=True, text=True, timeout=180, check=True)
    r = json.loads(out.stdout.strip().splitlines()[-1])
    assert r["errs"] == [], "no engine play calls, no page errors"
    assert r["composer"] == "none", "read-only: the input bar is folded away"
    assert r["start"]["n"] == 3 and r["pausedHeld"], "pause holds the beat"
    assert r["ended"]["end"] and r["ended"]["at"] == 3 and r["ended"]["speed"] == 16
    assert "ask Mira" in r["ended"]["you"]
    assert r["endTitle"] == "Out of the fog" and "assets%2Fending%2FE1.webp" in r["endArt"] and r["barTop"], "the ending's art from the bundle"
    assert r["seek"]["at"] == 2 and r["seek"]["paused"] and not r["seek"]["end"] and r["seek"]["lines"] >= 1
    assert "assets/soul.portrait/mira.png" in r["files"] and "assets/place.scene/T1__study.webp" in r["files"]
