"""网页实时流 · 换局与停止(曾卡在「主持 · 在想」):
- 每开一局引擎都起新的 WebRuntime(广播也是新的);已经连着的 /events 还挂在旧广播上,收不到新一局的消息 ——
  现在流会发 {"kind": "rebound"} 并断开,页面据此重连
- POST /cancel = ConversationSession.cancel()(和 TUI 一样);没有回合在跑时只回 running: false"""

from __future__ import annotations

import json
import shutil
import threading
import time
import urllib.error
import urllib.request
from unittest.mock import patch

from _paths import PRODUCT_TEMPLATES


def test_events_stream_says_rebound_after_a_new_run_and_cancel_is_safe(tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    store = tmp_path / "store"
    shutil.copytree(PRODUCT_TEMPLATES / "pct-house.template", store / "pct-house.template")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(store))
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "studio"),
        patch("neonrp.commands.web.WebRuntime.gateway_start", lambda self: {"sid": "local", "root": self.root.name}),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def post(path, body):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as exc:
                raise AssertionError(f"POST {path} → {exc.code}") from exc
        try:
            post("/api/v1/play/session", {"slug": "tpl--pct-house", "output_lang": "zh"})
            got: list[str] = []

            def listen() -> None:
                with urllib.request.urlopen(base + "/events", timeout=30) as r:
                    for raw in r:
                        line = raw.decode("utf-8").strip()
                        if line.startswith("data:"):
                            got.append(json.loads(line[5:]).get("kind"))
                            if got[-1] == "rebound":
                                return

            th = threading.Thread(target=listen, daemon=True)
            th.start()
            t0 = time.time()
            while "hello" not in got and time.time() - t0 < 10:
                time.sleep(0.1)
            assert post("/cancel", {}) == {"ok": True, "running": False}   # 没有回合在跑:什么都不做
            post("/api/v1/play/session", {"slug": "tpl--pct-house", "output_lang": "zh"})   # 换一局
            th.join(timeout=15)
            assert got and got[-1] == "rebound", got
        finally:
            server.shutdown()
