"""新开一局的开场指令跟这一局的语言走,不跟进程 / 系统语言(10-15,std-frontend 报:ja 的 Mac 上开 zh 局,开场说了日语)。"""
from __future__ import annotations

import json
import shutil
import threading
import urllib.request
from unittest.mock import patch

from _paths import PRODUCT_TEMPLATES
from neonrp.cli import _build_startup_handoff
from neonrp.tui.i18n import get_message


def test_handoff_takes_the_runs_language():
    assert _build_startup_handoff(None, locale="zh")[0] == get_message("zh", "handoff.start_game")
    assert _build_startup_handoff(None, locale="ja")[0] == get_message("ja", "handoff.start_game")
    with patch("neonrp.tui.i18n.resolve_locale", lambda: "ja"):
        assert _build_startup_handoff(None)[0] == get_message("ja", "handoff.start_game"), "no run language → the machine's"


def test_a_zh_run_on_a_ja_machine_opens_in_zh(tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    store = tmp_path / "store"
    shutil.copytree(PRODUCT_TEMPLATES / "pct-house.template", store / "pct-house.template")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(store))
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "studio"),
        patch("neonrp.tui.i18n.resolve_locale", lambda: "ja"),
        patch("neonrp.commands.web.WebRuntime.gateway_start", lambda self: {"sid": "local", "root": self.root.name}),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            req = urllib.request.Request(base + "/api/v1/play/session", data=json.dumps({"slug": "tpl--pct-house", "output_lang": "zh"}).encode(),
                                         method="POST", headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=120).read()
            assert server.runtime._startup_commands == [get_message("zh", "handoff.start_game")]
        finally:
            server.shutdown()
