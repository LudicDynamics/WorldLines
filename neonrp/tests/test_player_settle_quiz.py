"""标准前端结算屏「真相三问」(worldlines/ui/player/src/settle.js · niko 10-20):发的是额度(niko 10-21:积分是口误),不再「选一个人带走」——
答题页不出选人、提示写保底积分数(引擎 quiz() 的 points);交卷不带 take;结果页:答错 = 保底积分一行,全对但那位早就带着完整记忆
在收藏里 = 说清楚改送积分,没题的局 = 「这一局没有题」+ 领取积分。截图:PLAYER_QUIZ_SHOTS=<目录>(默认 tmp)。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "worldlines" / "ui"


def test_settlement_quiz_floor_is_points(tmp_path):
    node = shutil.which("node")
    if not node or not (UI / "node_modules" / "playwright").is_dir():
        pytest.skip("node + worldlines/ui/node_modules/playwright needed")
    shots = Path(os.environ.get("PLAYER_QUIZ_SHOTS") or tmp_path / "shots")
    res = subprocess.run([node, str(ROOT / "tests" / "player_settle_quiz.mjs"), str(UI / "player" / "src"), str(UI / "package.json"), str(shots)],
                         capture_output=True, text=True, timeout=180)
    assert res.returncode == 0, res.stderr[-2000:]
    r = json.loads(res.stdout.strip().splitlines()[-1])
    for name, c in r.items():
        assert c["errs"] == [], (name, c["errs"])
        assert c["ask"]["take"] == 0, f"{name}: nobody to pick any more"
        assert "take" not in (c["posted"] or {}), name
        assert c["collected"] == [], f"{name}: no collection card flies in — nobody came home"
    w, h, n = r["wrong"], r["home"], r["noq"]
    assert "莲妹" in w["ask"]["hint"] and "完成这一局 200 额度,每答对一题再加 100" in w["ask"]["hint"] and "带走" not in w["ask"]["hint"].replace("跟你走", "")
    assert "额度 +300(待发放)" in w["res"]["text"] and "另送" not in w["res"]["text"], "fallback 0: no extra line"
    assert "早就带着完整记忆在你的收藏里了" in h["res"]["text"] and "全对——带走的人" not in h["res"]["text"] and "额度 +500" in h["res"]["text"]
    assert n["ask"]["go"] == "领取额度" and "直接领 200 额度" in n["ask"]["hint"] and n["posted"] == {"answers": []}
    assert "这一局没有题" in n["res"]["text"] and "额度 +200(待发放)" in n["res"]["text"]
    assert "用自己的 key 时,额度不进平台账户" in w["res"]["text"], "own key: said plainly (lead 10-21)"
    assert not any("积分" in c["res"]["text"] or "积分" in c["ask"]["hint"] for c in r.values()), "积分 = 额度 (niko 10-21)"
    assert "核对后记进你的 Worldlines 账户" in n["res"]["text"] and "不进平台账户" not in h["res"]["text"]
