"""Hub「我的」· 对局积分(worldlines/ui/app/hub/runpoints.js,2026-10-21):billing 核对过的一局积分。本地模式,引擎代问
(/api/v1/local/account/run-points,core/run_points)的回答在 playwright 里给:核对中写进度(计费对话次数 / 分钟)、核对过写积分、
能领的出「领取」按钮(走 …/rewards/<id>/claim)、只记录 / 到上限 / 没核对上各说清楚;页面拼法和 build 一样(runpoints.js + hub.js 一段)。
另:引擎 core/run_points 没登录 / 离线不出错,登录了读 billing 两个接口、只留 kind run_points。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UI, HUB = ROOT / "worldlines" / "ui", ROOT / "worldlines" / "ui" / "app" / "hub"


def test_me_shows_run_points_and_claims(tmp_path):
    node = shutil.which("node")
    if not node or not (UI / "node_modules" / "playwright").is_dir():
        pytest.skip("node + worldlines/ui/node_modules/playwright needed")
    js = (HUB / "runpoints.js").read_text(encoding="utf-8") + "\n" + (HUB / "hub.js").read_text(encoding="utf-8")
    page = (HUB / "index.html").read_text(encoding="utf-8").replace("<!--SCRIPT-->", '<script>window.HUB={"mode":"auto"}</script><script>' + js + "</script>")
    (tmp_path / "page.html").write_text(page, encoding="utf-8")
    shots = Path(os.environ.get("HUB_RP_SHOTS") or tmp_path / "shots")
    res = subprocess.run([node, str(ROOT / "tests" / "hub_run_points.mjs"), str(tmp_path / "page.html"), str(UI / "package.json"), str(shots)],
                         capture_output=True, text=True, timeout=180)
    assert res.returncode == 0, res.stderr[-2000:]
    r = json.loads(res.stdout.strip().splitlines()[-1])
    assert r["errs"] == []
    assert not any("积分" in x for x in r["rows"]), "积分 = 额度 (niko 10-21)"
    rows = r["rows"]
    assert len(rows) == 5
    assert "核对中 · 计费对话 3/8 次 · 12/5 分钟" in rows[0] and "申请 60" in rows[0]
    assert "+80 额度" in rows[1] and "领取 160 额度" in rows[1]
    assert "+50 额度 · 已记进账户" in rows[2], "verified, nothing to claim (e.g. credits_per_point 0)"
    assert "今天的上限到了" in rows[3] and "没核对上" in rows[4]
    assert r["claims"] == ["POST"] and r["toast"] == "领到了"
    assert "✓ 已领取" in r["after"][1] and r["gets"] >= 2, "claimed → read again"


def test_engine_reads_billing_for_the_local_hub(monkeypatch):
    from neonrp.core import run_points

    monkeypatch.setattr(run_points, "_token", lambda: None)
    assert run_points.mine() == {"signed_in": False, "runs": [], "rewards": []}
    assert run_points.claim("x")[0] == 401
    monkeypatch.setattr(run_points, "_token", lambda: "tok")
    calls = []

    def fake(method, path, token, headers=None):
        calls.append((method, path, headers))
        if path == "/v1/me/run-points":
            return 200, {"runs": [{"ref": "hub:settlement:a:b", "status": "verified"}]}
        if path == "/v1/me/rewards":
            return 200, {"rewards": [{"kind": "run_points", "id": "1"}, {"kind": "invite", "id": "2"}]}
        return 200, {"reward": {"state": "claimed"}}

    monkeypatch.setattr(run_points, "_call", fake)
    got = run_points.mine()
    assert got["signed_in"] and got["runs"][0]["status"] == "verified" and [x["id"] for x in got["rewards"]] == ["1"]
    assert run_points.claim("not-a-uuid")[0] == 400
    rid = "11111111-2222-4333-8444-555555555555"
    assert run_points.claim(rid, "dev-1")[0] == 200 and calls[-1] == ("POST", f"/v1/me/rewards/{rid}/claim", {"X-Worldlines-Device": "dev-1"})
    monkeypatch.setattr(run_points, "_call", lambda *a, **k: (0, {"error": "offline"}))
    assert run_points.mine()["error"] == "offline"
