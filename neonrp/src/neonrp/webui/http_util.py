"""两面共用的 HTTP 小工具 + web.py 模块代理。

`HttpMixin` 是 engine/launcher 两个路由 mixin 都要用的底座(CORS 头、
JSON/SSE 写出、body 读取);`web` 是 `neonrp.commands.web` 的延迟句柄 ——
物理拆分只搬 handler 方法,WebRuntime/EditRuntime/_spa_root/_switch_runtime
这些模块级符号仍住 web.py(测试 patch 的正是 `neonrp.commands.web.<符号>`),
按名字延迟取既保住 patch 路径,又不在 web.py ↔ 本包之间建 import 环。
"""

from __future__ import annotations

import json
from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neonrp.commands.web import WebRuntime


class _WebModuleProxy:
    """`neonrp.commands.web` 的按名延迟取属性代理。"""

    def __getattr__(self, name: str) -> Any:
        return getattr(import_module("neonrp.commands.web"), name)


web = _WebModuleProxy()


class HttpMixin:
    """BaseHTTPRequestHandler 之上、两面路由之下的共用层。"""

    server: Any  # ThreadingHTTPServer with .runtime attached

    def log_message(self, *args: Any) -> None:  # quiet by default
        pass

    def handle(self) -> None:  # noqa: N802 — http.server API
        """A client that disconnects mid-response (tab reload / navigate —
        the rollback's location.reload() is a common trigger, and SSE streams
        break on every reload) surfaces as BrokenPipeError / ConnectionReset
        from wfile.write. Expected and harmless — swallow it instead of dumping
        a traceback to the console."""
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            pass

    @staticmethod
    def _locale(rt: "WebRuntime | None") -> str:
        if rt is not None:
            return rt.locale()
        from neonrp.tui.i18n import resolve_locale

        return resolve_locale()

    def _cors_headers(self) -> None:
        origin = self.headers.get("Origin") or ""
        if origin.startswith(("http://localhost", "http://127.0.0.1")):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Provider-Key")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")

    # ── gateway facade POST routes ──
    def _read_json_body(self) -> dict[str, Any] | None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, OSError):
            return None
        return payload if isinstance(payload, dict) else None

    def _send_json(self, obj: Any, status: int = 200) -> None:
        # default=str: library entries carry Path objects (source_dir /
        # template) — serialize them as their string form instead of 500ing.
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()  # no-op unless a local dev origin is calling
        self.end_headers()
        self.wfile.write(body)

    def _sse_write(self, event: dict[str, Any]) -> None:
        data = json.dumps(event, ensure_ascii=False)
        self.wfile.write(f"data: {data}\n\n".encode())
        self.wfile.flush()
