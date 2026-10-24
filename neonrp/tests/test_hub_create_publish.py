"""创作台「提交到默认区」的前端一半(10-24「创作台能不能测试发布作品」;引擎那一半在 test_creation_publish_flow.py):
网页创作台和 iOS 创作台是同一份 hub.js,这里按 iOS / 本地那样打开(window.HUB.createSubmit,账号在引擎里),手机宽度,
引擎接口装成有状态的假引擎(tests/hub_create_publish.mjs)。"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HUB = ROOT / "worldlines" / "ui" / "app" / "hub"
UI = ROOT / "worldlines" / "ui"


def _page(tmp_path: Path) -> Path:
    js = (HUB / "create-art.js").read_text(encoding="utf-8") + ";\n" + (HUB / "hub.js").read_text(encoding="utf-8")
    hub = '{"openZone":false,"createSubmit":true,"createArt":true,"noPayLinks":true,"app":true}'
    page = (HUB / "index.html").read_text(encoding="utf-8").replace("<!--SCRIPT-->", f"<script>window.HUB={hub}</script><script>{js}</script>")
    (tmp_path / "page.html").write_text(page, encoding="utf-8")
    return tmp_path / "page.html"


def test_submit_flow_on_the_desk(tmp_path):
    node = shutil.which("node")
    if not node or not (UI / "node_modules" / "playwright").is_dir():
        pytest.skip("node + worldlines/ui/node_modules/playwright needed")
    shots = tmp_path / "shots"
    shots.mkdir()
    r = subprocess.run([node, str(ROOT / "tests" / "hub_create_publish.mjs"), str(_page(tmp_path)), str(UI / "package.json"), str(shots)],
                       capture_output=True, text=True, timeout=240)
    assert r.returncode == 0, r.stderr[-3000:]
    o = json.loads(r.stdout.strip().splitlines()[-1])
    assert o["errs"] == []
    assert "作品名" in o["needTitle"] and o["workPostsBefore"] == 0, "no source-language title: stopped before anything is saved"
    assert o["unsigned"]["sign"] and not o["unsigned"]["go"] and "登录" in o["unsigned"]["text"], "not signed in: only the sign-in button"
    assert o["blocked"]["disabled"] and "封面:还没有图" in o["blocked"]["text"] and "先把上面的问题改好" in o["blocked"]["text"]
    assert "没提交成功" in o["failed"]["text"] and "平台暂时连不上" in o["failed"]["text"] and o["failed"]["again"] and not o["failed"]["mine"], "a failure says why and the button works again"
    assert "已提交到默认区审核" in o["retried"]["text"] and o["retried"]["mine"]
    assert re.fullmatch(r"#/t/stoneford-town/create\?w=stoneford-town-mine-[0-9a-f]{6}", o["newHref"]), o["newHref"]
    assert o["workIds"][-1] == o["newHref"].split("w=")[1], "the second work is saved under its own id"
    assert o["publishPosts"] == ["/api/v1/local/templates/stoneford-town-mine/publish"] * 2 + [f"/api/v1/local/templates/{o['workIds'][-1]}/publish"]
    assert len(o["mine"]) == 2 and all("审核中" in m and "撤回" in m for m in o["mine"]), o["mine"]


def _edit_page(tmp_path: Path, mode: str) -> Path:
    js = ";\n".join((HUB / f).read_text(encoding="utf-8") for f in ("orchview.js", "create-art.js", "hub.js"))
    hub = ('{"openZone":false,"createSubmit":true,"createArt":true,"noPayLinks":true,"app":true}' if mode == "ios"
           else '{"createSubmit":true}')   # 网页(本地 / 桌面那种宽度):同一份 hub.js,不带 iOS 的几个开关
    page = (HUB / "index.html").read_text(encoding="utf-8").replace("<!--SCRIPT-->", f"<script>window.HUB={hub}</script><script>{js}</script>")
    (tmp_path / f"edit-{mode}.html").write_text(page, encoding="utf-8")
    return tmp_path / f"edit-{mode}.html"


@pytest.mark.parametrize("mode", ["web", "ios"])
def test_edit_flow_on_the_desk(tmp_path, mode):
    """lead 10-24:发布之外的「编辑」—— 草稿继续编辑后保存再进 · 审核中改版再提交 · 上架后改版(旧版照常在线)· 两份互不串改。"""
    node = shutil.which("node")
    if not node or not (UI / "node_modules" / "playwright").is_dir():
        pytest.skip("node + worldlines/ui/node_modules/playwright needed")
    shots = tmp_path / "shots"
    shots.mkdir()
    r = subprocess.run([node, str(ROOT / "tests" / "hub_create_edit.mjs"), str(_edit_page(tmp_path, mode)), str(UI / "package.json"), mode, str(shots)],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-3000:]
    o = json.loads(r.stdout.strip().splitlines()[-1])
    assert o["errs"] == []
    first = o["firstSave"]
    assert first["card"]["ko"]["title"] == "안개 밤의 사냥꾼" and first["addition"]["soul"][0]["name"] == "阿青"
    assert first["addition"]["orchestration"] == "two_beat?pace=quick", "the pace the author picked goes with the work"
    assert o["coverUploads1"] == 1
    assert o["reopened"] == {"zh": "雾夜猎人", "ko": "안개 밤의 사냥꾼", "soul": "阿青", "pace": "quick"}, "reopening the desk brings the draft back"
    second = o["secondSave"]
    assert second["card"]["zh"]["title"] == "雾夜猎人 · 改" and second["addition"]["soul"][0]["name"] == "阿白"
    assert "orchestration" not in second["addition"], "back to the world's default pace = nothing written"
    assert o["coverUploads2"] == 2, "the new cover is uploaded again"
    # 本地网页版(10-24)只有自由区那一页,创作台的地址在 #/free/ 下;iOS 没有自由区
    assert "已提交到默认区审核" in o["submit1"] and o["revise"] == ("#/t/stoneford-town/create" if mode == "ios" else "#/free/t/stoneford-town/create")
    assert o["revisedOpen"] == "雾夜猎人 · 改", "「改版再提交」opens this very work"
    assert "顶掉了排队的那一版" in o["submit2"], "in review: a new version replaces the queued one"
    assert "旧版照常在线" in o["submit3"] and "旧版在线" in o["mineAfter"] and "审核中" in o["mineAfter"]
    assert len(o["works"]) == 1 and o["works"][0][1] == 3, "one work on the platform, three versions"
    assert re.fullmatch(r"stoneford-town-mine-[0-9a-f]{6}", o["second"]) and o["secondSaved"]["card"]["zh"]["title"] == "雾里的第二封信"
    assert o["firstStill"] == {"zh": "雾夜猎人 · 改", "soul": "阿白"}, "editing the second work leaves the first one's draft alone"


def test_desktop_local_desk_publishes_to_the_free_zone(tmp_path):
    """10-24「local 可以自由上传到自由区」:worldlines web 起的 /hub.html(没有 window.HUB)创作台也有发布按钮,发的是自由区(zone open)。"""
    node = shutil.which("node")
    if not node or not (UI / "node_modules" / "playwright").is_dir():
        pytest.skip("node + worldlines/ui/node_modules/playwright needed")
    js = ";\n".join((HUB / f).read_text(encoding="utf-8") for f in ("create-art.js", "hub.js"))
    page = (HUB / "index.html").read_text(encoding="utf-8").replace("<!--SCRIPT-->", f"<script>{js}</script>")
    (tmp_path / "free.html").write_text(page, encoding="utf-8")
    shots = tmp_path / "shots"
    shots.mkdir()
    r = subprocess.run([node, str(ROOT / "tests" / "hub_create_free.mjs"), str(tmp_path / "free.html"), str(UI / "package.json"), str(shots)],
                       capture_output=True, text=True, timeout=240)
    assert r.returncode == 0, r.stderr[-3000:]
    o = json.loads(r.stdout.strip().splitlines()[-1])
    assert o["errs"] == []
    assert "发布到自由区" in o["button"] and "发布到自由区" in o["savedMsg"], (o["button"], o["savedMsg"])
    assert o["unsigned"]["sign"] and not o["unsigned"]["go"] and "发布要先登录" in o["unsigned"]["text"]
    assert "自由区先上后管" in o["sheet"] and "默认区走快审" not in o["sheet"]
    assert "公开在自由区" in o["done"]["text"] and o["done"]["mine"]
    assert o["publishBodies"] == [["/api/v1/local/templates/stoneford-town-mine/publish", "open"]]
    assert len(o["mine"]) == 1 and "公开中" in o["mine"][0] and "撤下" in o["mine"][0] and "申请进默认区" in o["mine"][0], o["mine"]
