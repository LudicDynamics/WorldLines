"""`neonrp serve` 引擎面 HTTP 冒烟 — 拆分的收口证据。

物理拆分要证的不是"路由还在"(那是 test_web_vanilla_smoke 的活),而是
"两半真的分开了":只挂 EngineRoutes 的服务上,契约面(/api/v1/meta、
/i18n、/api/v1/play/health)照常应答,launcher 面(/api/v1/local/*、
/local 的 SPA 托管)没有挂载点 → 404。全部 hermetic:零 LLM 调用。
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

from neonrp.commands.serve import make_engine_server
from neonrp.core.manifest import Manifest


def _init_project(root: Path) -> None:
    neon = root / ".neonrp"
    (neon / "sessions").mkdir(parents=True)
    (neon / "events").mkdir(parents=True)
    m = Manifest()
    m.branches["main"].head_event = -1
    (neon / "manifest.json").write_text(json.dumps(m.model_dump(), default=str), encoding="utf-8")
    (root / "game").mkdir()


def _serve(tmp_path: Path):
    server = make_engine_server(tmp_path, "world-agent", "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def _status(url: str) -> int:
    try:
        return urllib.request.urlopen(url, timeout=5).status
    except urllib.error.HTTPError as exc:
        return exc.code


def test_engine_contract_answers(tmp_path: Path) -> None:
    """契约面三条(能力发现 / 串表 / 存活探针)在引擎-only 服务上照常 200。"""
    _init_project(tmp_path)
    server, base = _serve(tmp_path)
    try:
        meta = json.loads(urllib.request.urlopen(f"{base}/api/v1/meta", timeout=5).read())
        assert meta["implementation"] == "local-engine"
        assert meta["capabilities"]["play"] is True

        i18n = json.loads(urllib.request.urlopen(f"{base}/i18n?locale=zh", timeout=5).read())
        assert i18n["locale"] == "zh"
        assert isinstance(i18n["strings"], dict) and i18n["strings"]

        health = json.loads(urllib.request.urlopen(f"{base}/api/v1/play/health", timeout=5).read())
        assert health == {"ok": True, "service": "play", "local": True, "sessions": 1}
    finally:
        server.shutdown()


def test_launcher_local_face_absent(tmp_path: Path) -> None:
    """LAUNCHER-LOCAL(/api/v1/local/*)没挂载 → 404,而不是悄悄跟着引擎跑。"""
    _init_project(tmp_path)
    server, base = _serve(tmp_path)
    try:
        assert _status(f"{base}/api/v1/local/worlds") == 404
        assert _status(f"{base}/api/v1/local/settings") == 404
    finally:
        server.shutdown()


def test_launcher_shell_face_absent(tmp_path: Path) -> None:
    """SHELL(/local 的 SPA 托管)没挂载 → 404;引擎不托管壳资产。"""
    _init_project(tmp_path)
    server, base = _serve(tmp_path)
    try:
        assert _status(f"{base}/local") == 404
    finally:
        server.shutdown()
