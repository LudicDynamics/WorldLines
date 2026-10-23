"""Hub 创作台「编排模板」只读执行图 e2e(orch-preview 10-18 · 10-19 阶段 A 改成选模板):真引擎(进程内)+ Hub 的 index.html + orchview.js。
网页版:图 = build_static 出的 orch/<id>.json(这里用同一个函数 core/orch_presets.views 生成);本地版:引擎路由。
选模板 → 图跟着换 → 两拍的参数(快商量)在卡下面选 → 节点拖不动、没有能改的控件 → 点节点看步骤 → 缩放;手机宽 390 不横向溢出;只有本地版有「到编排台编辑」。
截图:HUB_OV_SHOTS=<目录>(默认 tmp)。端口 8798(e2e 端口段,被占就跳过)。"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from neonrp import template as TP
from neonrp.core import node_kinds, orch_presets as O

ROOT = Path(__file__).resolve().parents[1]
UI, HUB = ROOT / "worldlines" / "ui", ROOT / "worldlines" / "ui" / "app" / "hub"
PORT = int(os.environ.get("HUB_OV_PORT", "8798"))
MOUNT = """<style>header.top{position:static}</style><script>
const q = new URLSearchParams(location.search); let cur = ''
document.getElementById('app').innerHTML = '<div id="cf-orch"></div>'
WLOrchView.mount(document.getElementById('cf-orch'), { tid: q.get('tid'), lang: q.get('lang'), local: q.get('mode') === 'local',
  src: 'orch/' + q.get('tid') + '.json', value: () => cur, set: v => { cur = v; window.__chosen = v } })
</script>"""


def _free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


@pytest.mark.skipif(node_kinds.get("plan") is None, reason="needs the private layer (the two-beat template)")
def test_pick_a_template_and_read_its_graph(tmp_path, monkeypatch):
    node = shutil.which("node")
    if not node or not (UI / "node_modules" / "playwright").is_dir():
        pytest.skip("node + worldlines/ui/node_modules/playwright needed")
    if not _free(PORT):
        pytest.skip(f"port {PORT} is taken — not running against someone else's server")
    ro, mine = tmp_path / "official", tmp_path / "mine"
    shutil.copytree(ROOT / "worldlines" / "templates" / "pct-house.template", ro / "pct-house.template", ignore=shutil.ignore_patterns("__pycache__"))
    mine.mkdir()
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", f"{mine}{os.pathsep}{ro}")
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(mine))
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    browsers = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or str(Path.home() / "Library" / "Caches" / "ms-playwright")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    orch = tmp_path / "orch"
    orch.mkdir()
    (orch / "pct-house.json").write_text(json.dumps(O.views(TP.load(TP.discover()["pct-house"])), ensure_ascii=False), encoding="utf-8")
    page = (HUB / "index.html").read_text(encoding="utf-8").replace(
        "<!--SCRIPT-->", "<script>" + (HUB / "orchview.js").read_text(encoding="utf-8") + "</script>" + MOUNT)
    (tmp_path / "page.html").write_text(page, encoding="utf-8")
    shots = Path(os.environ.get("HUB_OV_SHOTS") or tmp_path / "shots")
    from neonrp.commands.web import make_server

    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "lib" / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "lib" / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "lib" / "studio"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", PORT)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            res = subprocess.run([node, str(ROOT / "tests" / "hub_orch_view.mjs"), f"http://127.0.0.1:{PORT}", str(tmp_path / "page.html"),
                                  str(orch), str(UI / "package.json"), str(shots)], capture_output=True, text=True, timeout=300,
                                 env={**os.environ, "PLAYWRIGHT_BROWSERS_PATH": browsers})
        finally:
            server.shutdown()
            server.server_close()
    assert res.returncode == 0, res.stderr[-2000:]
    r = json.loads(res.stdout.strip().splitlines()[-1])
    assert r["errs"] == [], r
    assert r["opts"] == ["two_beat", "one_beat"] and r["checked"] == "two_beat", "the world's own template is picked"
    assert r["chips"] == ["pace=normal*", "pace=quick"], "the two beats' pace is a parameter under its card"
    assert r["chosenQuick"] == "two_beat?pace=quick" and r["quickChecked"] == "quick"
    # 10-23: the two paces read differently — each has its own graph, the planning node lists the settings it changes
    assert r["refNormal"] == "two_beat" and r["refQuick"] == "two_beat?pace=quick"
    assert r["setsNormal"] and [x[0] for x in r["setsNormal"]] == [x[0] for x in r["setsQuick"]]
    differ = [q for n, q in zip(r["setsNormal"], r["setsQuick"]) if n[1] != q[1]]
    assert differ and all(q[2] for q in differ) and not any(n[2] for n in r["setsNormal"]), (r["setsNormal"], r["setsQuick"])
    assert r["detailSets"] and any(x[2] for x in r["detailSets"]), "the node's detail lists them too, the changed ones marked"
    assert r["nodesDefault"][:2] == ["plan", "resolve"] and "combat" in r["nodesDefault"]
    assert r["after"] == "one_beat" and "plan" not in r["nodesOneBeat"] and r["chosen"] == "one_beat", "picking a template redraws the graph"
    assert r["chipsOneBeat"] == 0, "the single beat has no parameter"
    assert r["dragMoved"] is False and r["controls"] == 0, "read-only: no node moves, nothing to type into"
    assert r["detail"] == "plan" and r["steps"] == ["打包世界", "玩家这句", "在场角色各自想", "主持"]
    assert "scale(1.5625)" in r["zoomed"]
    assert r["overflow390"] <= 0 and r["overflowZoom"] <= 0, "no sideways scroll at 390"
    assert r["editWeb"] == 0 and r["editLocal"] == "/local?screen=orch&edit=pct-house", "only the local desk links to the bench"
    assert r["titleEn"] == "Talk first, then act" and r["titleJa"] == "相談してから動く"


@pytest.mark.skipif(node_kinds.get("plan") is None, reason="needs the private layer (the two-beat template)")
def test_the_desk_stores_the_picked_template(tmp_path, monkeypatch):
    """The real Hub desk (hub.js mounts orchview.js): pick 「两拍」 with its quick pace → addition.orchestration → check →
    save → the work's template.json ``uses`` names it and the work plays as it; the draft remembers the pick after a reload."""
    node = shutil.which("node")
    if not node or not (UI / "node_modules" / "playwright").is_dir():
        pytest.skip("node + worldlines/ui/node_modules/playwright needed")
    if not _free(PORT):
        pytest.skip(f"port {PORT} is taken — not running against someone else's server")
    ro, mine = tmp_path / "official", tmp_path / "mine"
    shutil.copytree(ROOT / "worldlines" / "templates" / "stoneford-town.template", ro / "stoneford-town.template", ignore=shutil.ignore_patterns("__pycache__"))
    mine.mkdir()
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", f"{mine}{os.pathsep}{ro}")
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(mine))
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    browsers = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or str(Path.home() / "Library" / "Caches" / "ms-playwright")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    hub = Path(os.environ.get("HUB_JS_OVERRIDE") or HUB / "hub.js")   # a hub.js to try instead (the committed one + a patch)
    js = ";\n".join([*((HUB / f).read_text(encoding="utf-8") for f in ("orchview.js", "truthquiz.js", "create_assist.js")), hub.read_text(encoding="utf-8")])
    page = (HUB / "index.html").read_text(encoding="utf-8").replace(
        "<!--SCRIPT-->", "<script>window.HUB={\"mode\":\"auto\"}</script><script>" + js.replace("</script>", "<\\/script>") + "</script>")
    if os.environ.get("HUB_PAGE_OVERRIDE"):   # a built hub.html (worldlines/ui/app/build.mjs → dist-local/hub.html) instead
        page = Path(os.environ["HUB_PAGE_OVERRIDE"]).read_text(encoding="utf-8")
    (tmp_path / "page.html").write_text(page, encoding="utf-8")
    shots = Path(os.environ.get("HUB_OV_SHOTS") or tmp_path / "shots")
    from neonrp.commands.web import make_server

    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "lib" / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "lib" / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "lib" / "studio"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", PORT)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            res = subprocess.run([node, str(ROOT / "tests" / "hub_orch_desk.mjs"), f"http://127.0.0.1:{PORT}", str(tmp_path / "page.html"),
                                  "stoneford-town", "two_beat?pace=quick", str(UI / "package.json"), str(shots)], capture_output=True, text=True, timeout=900,
                                 env={**os.environ, "PLAYWRIGHT_BROWSERS_PATH": browsers})
        finally:
            server.shutdown()
            server.server_close()
    assert res.returncode == 0, res.stderr[-2000:]
    r = json.loads(res.stdout.strip().splitlines()[-1])
    assert r["errs"] == [], r
    assert r["before"] is None, "the world's own template is not written"
    assert r["after"] == "two_beat?pace=quick" and r["graph"] == "two_beat" and r["overflow"] <= 0
    assert r["check"]["status"] == 200 and r["check"]["body"].get("ok") is True, r["check"]
    assert r["save"]["status"] == 200 and r["save"]["body"].get("ok") is True, r["save"]
    w = TP.load(TP.discover()[r["save"]["body"]["id"]])
    assert w.data["uses"] == {"template": "two_beat", "version": "1.0", "soul": "S-judge", "params": {"pace": "quick"}}
    assert "plan_loop" not in (w.pack.get("engine") or {}).get("turn", {}), "the world's single-beat switch is not carried over"
    assert O.default_for(w) == "two_beat?pace=quick"
    assert r["reloaded"] == "two_beat" and r["reloadedParam"] == "pace=quick", "the draft remembers the pick"
    assert r["save"]["body"]["orchestration"] == "two_beat?pace=quick", "the work route says which template the work plays as"
    assert r["rowPickers"] == 0, "no orchestration picker on a character's row (niko 10-19)"
    assert not (w.dir / "prompts" / "souls").exists()
    assert r["askedWork"], "the desk asked the engine about the work"
    assert r["fromWork"] == "two_beat" and r["fromWorkParam"] == "pace=quick", f"{r.get('draft')}: a draft without the pick asks the engine about the work"
