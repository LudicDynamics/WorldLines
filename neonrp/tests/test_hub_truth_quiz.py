"""Hub 创作台「真相三问」e2e(truth-quiz 代理 10-18 · PLATFORM-PLAY-RULES-1015 §11):真引擎(进程内,模型换成假的)+ Hub 页面
(index.html + truthquiz.js + hub.js),一条走完 编辑 → 点生成 → 改 → 检查 → 存,存下来的作品 plots/mine/plot.json 里是改过的三问。
截图:HUB_TQ_SHOTS=<目录>(默认 tmp)。端口 8797(e2e 端口段,被占就跳过,不打别人的服务)。"""
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

from neonrp.template import creation_quiz as CQ
from test_creation_truth_quiz import QS, _Model

ROOT = Path(__file__).resolve().parents[1]
UI, HUB = ROOT / "worldlines" / "ui", ROOT / "worldlines" / "ui" / "app" / "hub"
PORT = int(os.environ.get("HUB_TQ_PORT", "8797"))


def _free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def test_desk_edit_generate_edit_check_save(tmp_path, monkeypatch):
    node = shutil.which("node")
    if not node or not (UI / "node_modules" / "playwright").is_dir():
        pytest.skip("node + worldlines/ui/node_modules/playwright needed")
    if not _free(PORT):
        pytest.skip(f"port {PORT} is taken — not running against someone else's server")
    ro, mine = tmp_path / "official", tmp_path / "mine"
    shutil.copytree(ROOT / "worldlines" / "templates" / "guixiang.template", ro / "guixiang.template", ignore=shutil.ignore_patterns("__pycache__"))
    mine.mkdir()
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", f"{mine}{os.pathsep}{ro}")
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(mine))
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    browsers = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or str(Path.home() / "Library" / "Caches" / "ms-playwright")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    model = _Model(json.dumps({"questions": QS}, ensure_ascii=False))
    monkeypatch.setattr(CQ, "_adapter", lambda: model)
    page = (HUB / "index.html").read_text(encoding="utf-8").replace(
        "<!--SCRIPT-->", "<script>window.HUB={\"mode\":\"auto\"}</script><script>" + (HUB / "truthquiz.js").read_text(encoding="utf-8")
        + "\n" + Path(os.environ.get("HUB_JS_OVERRIDE") or HUB / "hub.js").read_text(encoding="utf-8") + "</script>")
    (tmp_path / "page.html").write_text(page, encoding="utf-8")
    shots = Path(os.environ.get("HUB_TQ_SHOTS") or tmp_path / "shots")
    from neonrp.commands.web import make_server

    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "lib" / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "lib" / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "lib" / "studio"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", PORT)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            res = subprocess.run([node, str(ROOT / "tests" / "hub_truth_quiz.mjs"), f"http://127.0.0.1:{PORT}", str(tmp_path / "page.html"),
                                  str(UI / "package.json"), str(shots)], capture_output=True, text=True, timeout=700,
                                 env={**os.environ, "PLAYWRIGHT_BROWSERS_PATH": browsers})
        finally:
            server.shutdown()
            server.server_close()
    assert res.returncode == 0, res.stderr[-2000:]
    r = json.loads(res.stdout.strip().splitlines()[-1])
    print("SAVE_MS", r.get("saveMs"))
    assert r["errs"] == [], r
    assert r["blank"] == 3
    assert r["generated"] == QS[0]["q"]["zh"], "点生成 fills the draft (over what was hand-written, after confirming)"
    assert len(model.calls) == 1 and "族长把祠堂的钥匙藏进了井里" in model.calls[0][1], "drafted from the reveal on the desk"
    assert r["en"] == QS[0]["q"]["en"], "the four languages came with the draft"
    assert r["preview"][0].startswith("是谁把祠堂钥匙藏进井里的?") and "族长" in r["preview"][0]
    assert "完成这一局 200 额度,每答对一题再加 100" in r["pvHint"] and "积分" not in r["pvHint"] and "选一个角色带走" not in r["pvHint"], \
        "the preview promises the run's credits (10-21: 积分 = 额度)"
    assert "✓" in r["check"], r["check"]
    assert "存好了" in r["save"] or "没存成" not in r["save"], r["save"]
    plot = json.loads((next(mine.glob("guixiang-mine*")) / "plots" / "mine" / "plot.json").read_text(encoding="utf-8"))
    tq = plot["truth_quiz"]
    assert tq["questions"][0]["q"] == {**QS[0]["q"], "zh": "是谁把祠堂钥匙藏进井里的?"}
    assert [x["answer"] for x in tq["questions"]] == [1, 1, 0], "the edited right answer"
    assert tq["reward_soul"] == "xiulian"
