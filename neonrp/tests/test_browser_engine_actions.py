"""浏览器版(Pyodide)的引擎路径:wlweb 的 shim(没有线程 · 回合在请求答完之后跑 · 手动驱动 asyncio · debug 读关)下,
「拿起 / 仔细看看」这类直接动作的回合要收尾(turn_done)、记回合(10-15,player2 报浏览器版卡住)。另:玩家视角的事件过滤
出错时,页面仍收到事件名、回合不受影响。

每个用例在子进程里跑(wlweb 会改 threading / asyncio,不能留在测试进程里);stub 模型,不调真模型。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from _paths import PRODUCT

REPO = Path(__file__).resolve().parents[1]
# the browser engine bridge (worldlines/ui/app/hub/play/wlweb.py) is part of the Hub, which is not in the open repo
pytestmark = pytest.mark.skipif(not (PRODUCT / "ui" / "app" / "hub" / "play" / "wlweb.py").is_file(), reason="the Hub source is not in the open repo")

SCRIPT = r'''
import json, os, shutil, sys, tempfile, importlib.util
from pathlib import Path
repo, tpl, fail_filter = Path(sys.argv[1]), sys.argv[2], sys.argv[3] == "1"
tmp = Path(tempfile.mkdtemp()); store = tmp / "store"
shutil.copytree(repo / "worldlines" / "templates" / f"{tpl}.template", store / f"{tpl}.template")
spec = importlib.util.spec_from_file_location("wlweb", repo / "worldlines/ui/app/hub/play/wlweb.py")
wl = importlib.util.module_from_spec(spec); spec.loader.exec_module(wl)
os.environ.update(NEONRP_TEMPLATE_PATH=str(store), NEONRP_DISABLE_CLAUDE_CODE="1", HOME=str(tmp / "home"), NEONRP_DEBUG_ROUTES="0")
wl._threads(); wl._asyncio(); wl._memo_runtime_contract()
out = []
wl.HOST["emit"] = lambda s: out.append(json.loads(s))
import neonrp.worlds as W
W.WORLDS_HOME, W.PLAYS_HOME, W.STUDIO_HOME = tmp / "w", tmp / "p", tmp / "s"
from neonrp.commands import web
web.WebRuntime.gateway_start = lambda self: {"sid": "local", "root": self.root.name}
if fail_filter:
    from neonrp.core import play_view
    def boom(event, root, known=None):
        raise RuntimeError("filter broke")
    play_view.sse = boom
def req(m, p, b=None):
    st, h, body = wl.request(m, p, json.dumps({"Content-Type": "application/json"}), json.dumps(b).encode() if b is not None else b"")
    wl.run_pending()
    return st
req("POST", "/api/v1/play/session", {"slug": f"tpl--{tpl}", "output_lang": "zh"})
root = Path(wl.SERVER.runtime.root)
(root / ".neonrp" / "config.json").write_text(json.dumps({"llm": {"provider": "stub", "model": "stub-model"}}))
from neonrp.core.registry import load_registry
from neonrp.core.orchestration_trace import read_turn_traces
reg = load_registry(root); here = reg.player_location
item = next((e.id for e in reg.entries.values() if e.parent == here and e.cls == "item"), None) or next(e.id for e in reg.entries.values() if e.cls == "item")
res = []
for kind in ("inspect", "pick"):
    out.clear(); n0 = len(read_turn_traces(root, "main"))
    st = req("POST", "/cmd", {"action": kind, "target": item})
    res.append({"kind": kind, "status": st, "events": [e.get("kind") for e in out], "traces": len(read_turn_traces(root, "main")) - n0,
                "trace_body": next((bool(e.get("trace")) for e in out if e.get("kind") == "trace"), None)})
print("RESULT " + json.dumps(res))
'''


def _run(tpl: str, fail_filter: bool = False) -> list[dict]:
    p = subprocess.run([sys.executable, "-c", SCRIPT, str(REPO), tpl, "1" if fail_filter else "0"], capture_output=True, text=True, timeout=600)
    line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT ")), None)
    assert line, p.stdout[-2000:] + p.stderr[-4000:]
    return json.loads(line[7:])


@pytest.mark.parametrize("tpl", ["pct-house", "neon-rebirth"])
def test_direct_actions_finish_in_the_browser_engine(tpl):
    for r in _run(tpl):
        assert r["status"] == 202 and r["traces"] == 1, r
        assert "resolve.beat" in r["events"] and r["events"][-1] == "turn_done", r


def test_a_broken_filter_never_stops_a_turn():
    for r in _run("pct-house", fail_filter=True):
        assert r["traces"] == 1 and r["events"][-1] == "turn_done", r
        assert r["trace_body"] is False, "the event name only — never the unfiltered body"
