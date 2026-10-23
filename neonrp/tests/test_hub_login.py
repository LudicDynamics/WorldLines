"""Hub 登录 / 退出的进行中状态 + 超时 / 重试(niko 10-17:所有平台登录、退出没有加载动画,像卡住;登录偶尔 timeout)。
tests/hub_login.mjs 用假的 identity(auth.test)和假的引擎接口跑 hub/index.html + hub.js:
线上 —— 点「登录」按钮马上转圈 + 「正在打开登录页…」、别的登录按钮锁住、再点不再开;登录页迟迟不开 → 「网络可能有点慢」+ 重试 / 取消 → 超时 + 重试;
回来换 token 时「正在完成登录…」(列表不等它)、连不上自动再试、超时不重发授权码(只能用一次)并给重试;退出「正在退出…」,撤不掉照样本机退出并明说;
少动模式不转圈;本地 —— 引擎后台起浏览器登录:「请在浏览器里批准」+ 取消 + 浏览器没打开时的登录页链接、引擎报超时给重试、取消、退出。
截图:HUB_LOGIN_SHOTS=<目录> 时留在那里。"""
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
    shots = Path(os.environ.get("HUB_LOGIN_SHOTS") or tmp_path_factory.mktemp("shots"))
    shots.mkdir(parents=True, exist_ok=True)
    out = subprocess.run([node, str(ROOT / "tests" / "hub_login.mjs"), str(HUB / "index.html"), str(HUB / "hub.js"), str(UI / "package.json"), str(shots)],
                         capture_output=True, text=True, timeout=240, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_no_page_errors(r):
    assert r["errs"] == []


def test_sign_in_button_spins_at_once_and_locks(r):
    o = r["opening"]
    assert o["btn"] == {"text": "正在打开登录页…", "busy": "true", "spin": True, "disabled": True}
    assert all(o["others"]), "the other providers are locked while one is opening"
    assert o["bar"]["cls"].endswith("open") and o["bar"]["spin"]
    assert r["startCalls"] == 1, "a second tap does not open a second sign-in"


def test_slow_sign_in_page_offers_retry_then_times_out(r):
    assert r["slow"]["text"] == "登录页还没打开,网络可能有点慢" and r["slow"]["btns"] == ["重试", "取消"]
    g = r["giveup"]
    assert g["cls"].endswith("fail") and g["text"] == "登录超时了" and g["btns"][0] == "重试" and not g["spin"]
    assert not any(r["giveupBtns"]), "after the timeout the sign-in buttons work again"


def test_token_exchange_shows_progress_and_does_not_hold_the_page(r):
    f = r["finishing"]
    assert f["bar"]["text"] == "正在完成登录…" and f["bar"]["spin"]
    assert f["cards"] >= 1, "the page is drawn while the token comes back"
    d = r["finished"]
    assert d["bar"] is None and "已登录" in d["toasts"] and d["url"] == "https://hub.test/#/me" and d["calls"] == 1


def test_token_exchange_retries_network_errors_but_not_timeouts(r):
    assert r["netRetry"] == {"signed": True, "calls": 3, "bar": None}
    t = r["tokenTimeout"]
    assert t["calls"] == 1, "the code is single-use: a request that may have arrived is not sent again"
    assert t["bar"]["text"].endswith("登录超时了") and t["bar"]["btns"][0] == "重试" and not t["signed"]


def test_sign_out_spins_and_says_how_it_went(r):
    assert r["out"]["btn"] == {"text": "正在退出…", "busy": "true", "disabled": True} and r["out"]["bar"]["spin"]
    assert r["outDone"] == {"toasts": ["已退出登录"], "auth": None, "calls": 1}
    f = r["outFail"]
    assert f["auth"] is None and f["calls"] == 2, "revoke retried once, then signed out here anyway"
    assert f["toasts"] == ["已在这台设备上退出(线上会话没能撤销,会自己过期)"]


def test_reduced_motion_spinner_does_not_spin(r):
    assert r["reduced"] == {"anim": "none", "style": "dotted"}


def test_local_sign_in_waits_for_the_browser_with_cancel(r):
    assert r["localOpening"]["btn"] == {"text": "正在打开登录页…", "busy": "true", "disabled": True}
    w = r["localWait"]
    assert w["bar"]["cls"].endswith("wait") and w["bar"]["text"].startswith("请在浏览器里批准登录") and "取消" in w["bar"]["btns"]
    assert w["link"] == "https://auth.test/v1/login/start?x=1", "a browser that did not open: the page links the sign-in page"
    assert r["localDone"]["bar"] is None and "已登录" in r["localDone"]["toasts"]


def test_local_timeout_retry_cancel_and_sign_out(r):
    t = r["localTimeout"]
    assert t["text"] == "登录超时了" and t["btns"][0] == "重试"
    c = r["localCancel"]
    assert c["cancel"] == 1 and c["bar"] is None and c["toasts"] == ["已取消登录"] and c["btn"] is False
    assert r["localOut"]["btn"] == {"text": "正在退出…", "busy": "true"}
    d = r["localOutDone"]
    assert d["calls"] == 1 and "已退出登录" in d["toasts"] and not d["btn"] and d["login"]
