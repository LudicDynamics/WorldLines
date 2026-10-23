"""`neonrp serve` — 只挂引擎面的 HTTP 服务。

`neonrp web` 是历史堆积:一个 handler 同时管引擎契约和 launcher 资产
(本地库/设置/SPA 托管)。物理拆分后本命令起的服务只挂 EngineRoutes ——
project 作用域的纯引擎 API(vanilla 面 + Play/Create 契约),
`/api/v1/local/*` 与 `/local` 这些 launcher 面路径没有挂载点,自然 404。

内部命令,不进玩家文档;玩家入口仍是 `worldlines web`。
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import click

from neonrp.commands.web import WebRuntime, _bind_server, start_parent_watchdog
from neonrp.core.paths import get_manifest_path, get_project_root
from neonrp.core.runtime_contract import get_startup_entry_agent
from neonrp.net.host import NetRoutes, describe
from neonrp.webui.engine_routes import EngineRoutes
from neonrp.webui.http_util import HttpMixin


class _EngineHandler(NetRoutes, EngineRoutes, HttpMixin, BaseHTTPRequestHandler):
    """引擎面 handler —— launcher 面不挂载,那半边路径一律落 404。联网层(10-10:headless = 主进程)在 /rpc 与 /rpc/events。"""

    server: Any  # ThreadingHTTPServer with .runtime attached

    def do_OPTIONS(self) -> None:  # noqa: N802 — http.server API
        if self._engine_route_options():
            return
        self.send_error(404)

    def do_PUT(self) -> None:  # noqa: N802 — http.server API
        if self._engine_route_put():
            return
        self.send_error(404)

    def do_DELETE(self) -> None:  # noqa: N802 — http.server API
        if self._engine_route_delete(self.server.runtime):
            return
        self.send_error(404)

    def do_GET(self) -> None:  # noqa: N802 — http.server API
        if self._net_route_get() or self._engine_route_get(self.server.runtime):
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802 — http.server API
        if self._net_route_post() or self._engine_route_post(self.server.runtime):
            return
        self.send_error(404)


def make_engine_server(
    root: Path | None,
    agent_id: str,
    host: str,
    port: int,
    startup_commands: list[str] | None = None,
) -> ThreadingHTTPServer:
    """引擎面 HTTP 服务(可测缝,与 web.make_server 同形)。

    `root=None` 同样合法:未绑定 run 时引擎面只应答 /api/v1/meta、/i18n
    与能在 launcher mode 下绑会话的 POST /api/v1/play/session。端口被占
    时退到下一个空闲端口(读 ``server.server_address[1]``)。"""
    server = _bind_server(host, port, handler=_EngineHandler)
    server.daemon_threads = True
    server.runtime = (  # type: ignore[attr-defined]
        WebRuntime(root, agent_id, startup_commands=startup_commands) if root is not None else None
    )
    server.edit_runtime = None  # type: ignore[attr-defined]  # CREATE contract (L0.1)
    return server


@click.command()
@click.option(
    "--project",
    "-p",
    type=click.Path(exists=True, file_okay=False),
    default=None,
    help="Project directory (default: current directory).",
)
@click.option("--host", default="127.0.0.1", help="Bind host (default 127.0.0.1).")
@click.option("--port", default=8788, type=int, help="Port (default 8788).")
@click.option(
    "--parent-pid",
    default=None,
    type=int,
    help="Exit when this process dies (desktop shells pass their own pid).",
)
def serve(
    project: str | None,
    host: str,
    port: int,
    parent_pid: int | None,
) -> None:
    """[internal] The engine API for one world (no web UI) — players: use `worldlines web`.

    Serves the engine's HTTP API for the project only: no web UI and no
    `/api/v1/local/*` library routes. For front ends that bring their own
    interface (Godot, a custom web client …).


    \b
        neonrp serve --project playground/stoneford-elena
        → http://127.0.0.1:8788/api/v1/meta
    """
    root: Path | None
    if project:
        root = Path(project).resolve()
        if not get_manifest_path(root).exists():
            click.echo("Error: Not initialized. Run 'neonrp init' first.", err=True)
            raise SystemExit(1)
    else:
        cwd_root = get_project_root()
        root = cwd_root if get_manifest_path(cwd_root).exists() else None

    # /debug-grade recording for the lanes, no NEONRP_DEBUG needed.
    from neonrp.core.debug_flag import force_enable

    force_enable()

    # 桌面壳兜底:壳进程没了(哪怕 SIGKILL)引擎也自杀,不留孤儿占端口。
    if parent_pid is not None:
        start_parent_watchdog(parent_pid)

    agent_id = (get_startup_entry_agent(root) if root else None) or "world-agent"
    server = make_engine_server(root, agent_id, host, port)
    bound_port = server.server_address[1]
    scope = root.name if root is not None else "unbound"
    click.echo(f"neonrp serve · engine API · {scope} · agent={agent_id}")
    if bound_port != port:
        click.echo(f"  (port {port} was busy — using {bound_port})")
    click.echo(f"→ http://{host}:{bound_port}/api/v1/meta")
    click.echo(f"  clients (TUI --connect): {describe(server, host, bound_port)}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        click.echo("\nbye")
    finally:
        server.shutdown()
