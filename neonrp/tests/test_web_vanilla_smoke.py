"""Vanilla 引擎面 HTTP 冒烟 — 拆分安全网。

契约 §2a 的 vanilla 路由此前零 HTTP 覆盖(/cmd /start /rollback /i18n
/image /upload);物理拆分是"纯搬家",这组用例钉住每条路由的存在性与
最小语义,防止搬家时静默丢路由。全部 hermetic:不触发任何 LLM 调用
(空输入 400 早退、kickoff 无 startup_commands 即 no-op、rollback 只走
错误分支、upload 只走 415 分支)。
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

from neonrp.commands.web import make_server
from neonrp.core.manifest import Manifest


def _init_project(root: Path) -> None:
    neon = root / ".neonrp"
    (neon / "sessions").mkdir(parents=True)
    (neon / "events").mkdir(parents=True)
    m = Manifest()
    m.branches["main"].head_event = -1
    (neon / "manifest.json").write_text(
        json.dumps(m.model_dump(), default=str), encoding="utf-8"
    )
    (root / "game").mkdir()


def _serve(tmp_path: Path):
    server = make_server(tmp_path, "world-agent", "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def _post(base: str, path: str, body: bytes, ctype: str = "application/json"):
    req = urllib.request.Request(
        f"{base}{path}", data=body, headers={"Content-Type": ctype}
    )
    return urllib.request.urlopen(req, timeout=5)


def test_vanilla_routes_smoke(tmp_path: Path) -> None:
    _init_project(tmp_path)
    server, base = _serve(tmp_path)
    try:
        # /i18n — 播放串表,无需会话绑定
        i18n = json.loads(
            urllib.request.urlopen(f"{base}/i18n?locale=zh", timeout=5).read()
        )
        assert i18n["locale"] == "zh"
        assert isinstance(i18n["strings"], dict) and i18n["strings"]

        # /image — 空项目无美术:404(路由存在,而非 send_error(404) 之外的崩溃)
        try:
            urllib.request.urlopen(f"{base}/image?kind=world", timeout=5)
            raise AssertionError("expected 404 for missing art")
        except urllib.error.HTTPError as e:
            assert e.code == 404

        # /image — id 路径穿越防御
        try:
            urllib.request.urlopen(f"{base}/image?kind=soul&id=../x", timeout=5)
            raise AssertionError("expected 400 for traversal id")
        except urllib.error.HTTPError as e:
            assert e.code == 400

        # /start — 无 startup_commands 的老项目:幂等 no-op,永远 200
        started = json.loads(_post(base, "/start", b"").read())
        assert started == {"started": False}

        # /cmd — 空输入 400 早退(不触发回合)
        try:
            _post(base, "/cmd", json.dumps({"text": ""}).encode())
            raise AssertionError("expected 400 for empty text")
        except urllib.error.HTTPError as e:
            assert e.code == 400

        # /rollback — 缺 commit 400;未知 commit 走错误 JSON(不炸 500)
        try:
            _post(base, "/rollback", b"{}")
            raise AssertionError("expected 400 for missing commit")
        except urllib.error.HTTPError as e:
            assert e.code == 400
        r = json.loads(
            _post(base, "/rollback", json.dumps({"commit": "no-such"}).encode()).read()
        )
        assert r.get("ok") is False

        # /upload — 随 legacy vanilla 通路退役(29ddc02),现在是干净的 404,
        # 不再是 415 早退。
        try:
            _post(base, "/upload?kind=world", b"zzz", ctype="text/plain")
            raise AssertionError("expected 404 for the retired /upload route")
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        server.shutdown()
