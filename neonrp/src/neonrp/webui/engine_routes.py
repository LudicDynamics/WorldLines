"""引擎面 HTTP 路由(docs/ENGINE-API-CONTRACT.md §2a/2b/2d)。

归属 `CONTRACT-PLAY` / `CONTRACT-CREATE` 的每条路由都住这里:vanilla 面
(`/cmd /start /events /state /traces /trace /rollback /image /i18n`)、Play
契约(`/api/v1/play/*` 与 `/api/v1/meta`)、Create 契约(`/api/v1/create/*`)。

物理拆分:方法体逐字搬自 `neonrp.commands.web`,行为零变化。
`_engine_route_*` 是从原 `_Handler.do_*` if 链里切出的一半 —— 返回 True
表示这一半已经应答,False 表示交给 launcher 面(见 launcher_routes)。
模块级符号(WebRuntime/EditRuntime/_switch_runtime…)仍住 web.py,经
`http_util.web` 代理按名字延迟取,测试的 patch 路径因此不变。
"""

from __future__ import annotations

import json
import queue
import threading
from typing import TYPE_CHECKING, Any

from neonrp.webui.http_util import web
from neonrp.webui.map_routes import MapRoutes
from neonrp.webui.mode_routes import ModeRoutes
from neonrp.webui.schema_routes import SchemaRoutes
from neonrp.webui.template_routes import TemplateRoutes
from neonrp.webui.commit_routes import CommitRoutes
from neonrp.webui.approval_routes import ApprovalRoutes
from neonrp.webui.scene_art_routes import SceneArtRoutes
from neonrp.webui.frontend_routes import FrontendRoutes

if TYPE_CHECKING:  # 仅注解用 —— 运行期一律走 web.<符号>,不建 import 环
    from neonrp.commands.web import EditRuntime, WebRuntime


def _turn_input(body: Any) -> str:
    """A turn's input: ``{"input": "…"}``, or a front end's structured action ``{"action": "inspect" | "pick", "target"}``
    / ``{"action": "skill", "skill", "target"?}`` (core/player_action, 10-14) as its marker — the action wins."""
    from neonrp.core.player_action import from_body

    act = from_body(body)
    if act:
        return act
    return str((body or {}).get("input") or "").strip() if isinstance(body, dict) else ""


class EngineRoutes(ModeRoutes, SchemaRoutes, MapRoutes, TemplateRoutes, CommitRoutes, ApprovalRoutes, SceneArtRoutes, FrontendRoutes):
    """引擎契约面的 handler mixin(与 BaseHTTPRequestHandler 合体使用)。"""

    server: Any  # ThreadingHTTPServer with .runtime attached
    path: str

    # ── gateway facade routing (docs/WEBUI-UNIFICATION.md P0) ──
    # Local mirror of play_gateway's /api/v1/play/* so the shared play UI can
    # point ENDPOINT at this server. CORS is answered for local dev origins
    # (the SPA's vite dev server on another localhost port).

    _API_PREFIX = "/api/v1/play"
    _CREATE_PREFIX = "/api/v1/create"

    def _engine_route_options(self) -> bool:
        if self.path.startswith((self._API_PREFIX, self._CREATE_PREFIX)):
            self.send_response(204)
            self._cors_headers()
            self.end_headers()
            return True
        return False

    def _engine_route_put(self) -> bool:
        if self._map_route_put():
            return True
        # PUT portrait 不存在;见 do_POST 的 portrait 路由
        # PUT file — 工作台直写一个文件(弧线画布 arc.json/story.md 等)
        if self.path == f"{self._CREATE_PREFIX}/session/{web.EditRuntime.SID}/file":
            ert: EditRuntime | None = web._try_rebind_edit_runtime(self.server)
            if ert is None:
                self.send_error(409, "no edit session")
                return True
            body = self._read_json_body() or {}
            rel = str(body.get("path") or "").strip().lstrip("/")
            content = str(body.get("content") or "")
            if not rel or ".." in rel.split("/") or rel.startswith(".neonrp"):
                self.send_error(400, "bad path")
                return True
            target = (ert.world_dir / rel).resolve()
            try:
                target.relative_to(ert.world_dir.resolve())
            except ValueError:
                self.send_error(400, "bad path")
                return True
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            self._send_json({"ok": True, "path": rel})
            return True
        # PUT name — 改世界显示名(工作台概览的 ✎;写 game-start.json)
        if self.path == f"{self._CREATE_PREFIX}/session/{web.EditRuntime.SID}/name":
            ert: EditRuntime | None = web._try_rebind_edit_runtime(self.server)
            if ert is None:
                self.send_error(409, "no edit session")
                return True
            body = self._read_json_body() or {}
            new_name = str(body.get("name") or "").strip()
            if not new_name:
                self.send_error(400, "missing name")
                return True
            web._set_world_display_name(ert.world_dir, new_name[:60])
            self._send_json({"ok": True, "world_name": new_name[:60]})
            return True
        # PUT llm — 工作台内换创作 LLM(创作里没有任何 provider 设置口)
        if self.path == f"{self._CREATE_PREFIX}/session/{web.EditRuntime.SID}/llm":
            ert: EditRuntime | None = web._try_rebind_edit_runtime(self.server)
            if ert is None:
                self.send_error(409, "no edit session")
                return True
            body = self._read_json_body() or {}
            preset = str(body.get("preset_id") or "").strip()
            if not preset or not web._apply_run_preset(ert.world_dir, preset):
                self.send_error(400, "unknown preset")
                return True
            try:
                from neonrp.presets import set_create_provider

                set_create_provider(preset)  # 持久:之后的创作默认它
            except Exception:  # noqa: BLE001
                pass
            ert._session = None  # 下一条消息用新 config 重建 agent 会话
            self._send_json({"ok": True, "preset": preset})
            return True
        # PUT canvas/{map|story|relation} — 画布保存(校验后原子写;
        # map 写回世界 world_map.json,story/relation 写 STUDIO_HOME)。
        canvas_prefix = f"{self._CREATE_PREFIX}/session/{web.EditRuntime.SID}/canvas/"
        if self.path.startswith(canvas_prefix):
            ert: EditRuntime | None = web._try_rebind_edit_runtime(self.server)
            if ert is None:
                self.send_error(409, "no edit session")
                return True
            kind = self.path[len(canvas_prefix):]
            if kind not in web.EditRuntime.CANVAS_KINDS:
                self.send_error(404)
                return True
            body = self._read_json_body()
            if body is None:
                self.send_error(400, "bad json")
                return True
            status, result = ert.canvas_put(kind, body)
            self._send_json(result, status=status)
            return True
        return False

    def _engine_route_delete(self, rt: "WebRuntime | None") -> bool:
        # DELETE /api/v1/play/saves/<sid> — remove one run dir. The active
        # run is refused (switch away first).
        prefix = f"{self._API_PREFIX}/saves/"
        if self.path.startswith(prefix):
            sid = web._path_seg(self.path[len(prefix):])
            if not web._safe_name(sid):
                self.send_error(400)
                return True
            from neonrp.worlds import PLAYS_HOME

            run_dir = PLAYS_HOME / sid
            if not run_dir.is_dir():
                self.send_error(404)
                return True
            if rt is not None and run_dir.resolve() == rt.root.resolve():
                self.send_error(409)  # can't delete the run being played
                return True
            import shutil

            try:
                shutil.rmtree(run_dir)
            except OSError:
                self.send_error(500)
                return True
            self._send_json({"ok": True})
            return True
        return False

    def _engine_route_get(self, rt: "WebRuntime | None") -> bool:
        from neonrp.core import play_view

        if self.path.startswith("/api/v1/play/engine/debug/"):  # the host's working: local engine only (core/play_view, 10-15)
            if not play_view.debug_enabled():
                self.send_error(404)
                return True
            sub = self.path.split("?", 1)[0][len("/api/v1/play/engine/debug/"):]
            if sub in ("schema", "state", "traces", "trace"):
                if rt is None:
                    self.send_error(409, "no play session")
                    return True
                if sub == "schema":
                    from neonrp.webui.schema_routes import schema_view

                    self._send_json(schema_view(rt.root))
                elif sub == "state":
                    self._send_json(rt.hello())
                elif sub == "traces":
                    self._send_json({"turns": rt.traces_summary()})
                else:
                    from urllib.parse import parse_qs, urlparse

                    try:
                        trace = rt.trace_at(int((parse_qs(urlparse(self.path).query).get("i") or [""])[0]))
                    except ValueError:
                        self.send_error(400)
                        return True
                    if trace is None:
                        self.send_error(404)
                    else:
                        self._send_json(trace)
                return True
        if self._map_route_get(rt):
            return True
        if self._schema_route_get(rt):
            return True
        if self._mode_route(rt, "GET"):
            return True
        if self._template_route_get(rt):
            return True
        if self._frontend_route_get(rt):  # 10-17 前端台(template/frontends)
            return True
        if self._scene_art_get(rt):  # 10-16「画这一幕」(core/scene_art)
            return True
        if self._commit_route_get(rt):
            return True
        if self.path.split("?", 1)[0] == "/api/v1/play/engine/beat-kinds":
            # R3 (10-09): how this run's beats are shown — the pack's ui.beats (private layer over the pack, like the graph)
            if rt is None:
                self.send_error(409, "no play session")
                return True
            from neonrp.core.orchestration import beat_kinds

            self._send_json(beat_kinds(rt.root))
            return True
        if self.path.split("?", 1)[0] in ("/api/v1/play/engine/view-schema", "/api/v1/play/engine/round", "/api/v1/play/engine/var-history"):
            # V1–V3 (TESTBENCH-AUTOVIEW-1005, 10-06): read-only views for the test bench
            if rt is None:
                self.send_error(409, "no play session")
                return True
            from urllib.parse import parse_qs, urlparse

            from neonrp.core import view_schema as _vs

            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            route = self.path.split("?", 1)[0].rsplit("/", 1)[-1]
            if route == "view-schema":
                self._send_json(_vs.view_schema(rt.root))
            elif route == "round":
                try:
                    b = _vs.round_bundle(rt.root, int(q.get("i", "-1")))
                except ValueError:
                    b = None
                if b is None:
                    self.send_error(404, "no such round")
                else:
                    self._send_json(b)
            else:
                if not q.get("var"):
                    self.send_error(400, "var required")
                else:
                    self._send_json({"var": q["var"], "history": _vs.var_history(rt.root, q["var"])})
            return True
        if self._approval_route_get(rt):
            return True
        if self.path == "/api/v1/meta":
            # Capability discovery (docs/WEBUI-UNIFICATION.md L0.0): the shared
            # UI band asks the backend WHO it is and WHAT it can do, and renders
            # accordingly — one codebase, two backends, no scattered
            # local-vs-hosted special cases in components. The hosted gateway
            # grows the same endpoint when it converges on this contract.
            from neonrp import __version__ as _engine_version

            self._send_json(
                {
                    "implementation": "local-engine",
                    "engine_version": _engine_version,
                    "auth": "none",
                    "multi_user": False,
                    "session_model": "single-swap",
                    "capabilities": {
                        # play contract
                        "play": True,
                        "stream": True,
                        "resume": True,
                        "saves": True,
                        "rollback": True,       # local engine feature (commit DAG)
                        "replay": True,          # orchestration traces
                        "multi_agent": True,     # not gated locally
                        "quotas": False,         # no token walls locally
                        "save_zip": False,       # hosted-only today
                        "locations": False,      # hosted-only today
                        "soul_detail": False,    # hosted-only today
                        "map": True,            # layered image map (core/worldmap)
                        "engine_mode": True,    # one-click turn.mode v2b ⇄ v3 (webui/mode_routes.py)
                        "schema": 1,            # open/closed schema HTTP shape v1: read · register · SSE subscribe (webui/schema_routes.py)
                        "template": 1,          # templates: run view + local store lint (webui/template_routes.py)
                        "approvals": 1,         # class growth policy + creator approval queue (webui/approval_routes.py)
                        "commits": 1,           # the run's commit DAG (webui/commit_routes.py) — rollback forks a branch
                        # create contract (local end, L0.1)
                        "create": True,
                        # shell namespaces
                        "local_library": True,   # /api/v1/local/* exists
                        "local_settings": True,  # provider presets/keys/test
                        "local_souls": True,     # soul library list/delete
                    },
                }
            )
            return True
        if self.path.startswith(self._API_PREFIX):
            if self.path == f"{self._API_PREFIX}/health":
                self._send_json(
                    {
                        "ok": True,
                        "service": "play",
                        "local": True,
                        "sessions": 1 if rt is not None else 0,
                    }
                )
                return True
            if self.path == f"{self._API_PREFIX}/saves":
                self._send_json(web._library_saves(rt.root if rt is not None else None))
                return True
            # GET /api/v1/play/session/limit?tpl=<id> — can one more NEW run of this world start (core/save_limits, 10-21)?
            # → {ok: true} · {ok: false, error: save_limit, tier, kind, limit, saves} (the page asks before the builder screen)
            if self.path.split("?", 1)[0] == f"{self._API_PREFIX}/session/limit":
                from urllib.parse import parse_qs, urlparse

                from neonrp.core import save_limits as _sl
                from neonrp.worlds import PLAYS_HOME

                tid = (parse_qs(urlparse(self.path).query).get("tpl") or [""])[0]
                try:
                    _sl.check_new_run(tid, PLAYS_HOME)
                    self._send_json({"ok": True})
                except _sl.SaveLimit as lim:
                    self._send_json({"ok": False, **lim.to_dict()})
                return True
            # GET /api/v1/play/chat-room — 群聊:在场者名单 + 房间线程(T2)。
            if self.path == f"{self._API_PREFIX}/chat-room":
                if rt is None:
                    self._send_json({"ok": False, "error": "no session"}, status=409)
                    return True
                from neonrp.core.light_chat import read_room_thread, resolve_room_souls

                souls = resolve_room_souls(rt.root)
                self._send_json(
                    {
                        "ok": True,
                        "participants": [
                            {"iid": iid, "name": name} for iid, _d, name in souls
                        ],
                        "thread": read_room_thread(rt.root),
                    }
                )
                return True
            # GET /api/v1/play/chat/<iid> — 对话拍线程 + 可聊性(T1,
            # HARNESS-TEAM-DESIGN:同场景门在引擎侧,UI 据 co_located 定入口)。
            if self.path.startswith(f"{self._API_PREFIX}/chat/"):
                iid = web._path_seg(self.path[len(f"{self._API_PREFIX}/chat/"):])
                if not web._safe_name(iid):
                    self.send_error(400)
                    return True
                if rt is None:
                    self._send_json({"ok": False, "error": "no session"}, status=409)
                    return True
                from neonrp.core.light_chat import (
                    read_thread,
                    remote_comms,
                    resolve_reachable_soul,
                )

                resolved = resolve_reachable_soul(rt.root, iid)
                _remote = bool(resolved and resolved[2])
                self._send_json(
                    {
                        "ok": True,
                        # 语义=可达(同场或经远程媒介);字段名保持 UI 兼容。
                        "co_located": resolved is not None,
                        "remote": _remote,
                        "medium": (remote_comms(rt.root) or {}).get("medium")
                        if _remote
                        else None,
                        "name": resolved[1] if resolved else None,
                        "thread": read_thread(rt.root, iid),
                    }
                )
                return True
            self.send_error(404)
            return True
        if self.path.startswith(self._CREATE_PREFIX):
            ert: EditRuntime | None = web._try_rebind_edit_runtime(self.server)
            if ert is None:
                self.send_error(409, "no edit session - POST /api/v1/create/session first")
                return True
            if self.path == f"{self._CREATE_PREFIX}/session/{web.EditRuntime.SID}/tree":
                from neonrp.worlds import read_local_world_name

                try:
                    wname = read_local_world_name(ert.world_dir) or ert.world_id
                except Exception:  # noqa: BLE001
                    wname = ert.world_id
                self._send_json(
                    {"world_id": ert.world_id, "world_name": wname, "files": ert.tree()}
                )
                return True
            if self.path.startswith(f"{self._CREATE_PREFIX}/session/{web.EditRuntime.SID}/file"):
                from urllib.parse import parse_qs, urlparse

                qs = parse_qs(urlparse(self.path).query)
                rel = (qs.get("path") or [""])[0]
                status, content = ert.read_file(rel)
                if status != 200:
                    self.send_error(status, content)
                    return True
                self._send_json({"path": rel, "content": content})
                return True
            # GET canvas/{map|story|relation}(docs/STUDIO-CANVAS-PLAN.md)
            canvas_prefix = f"{self._CREATE_PREFIX}/session/{web.EditRuntime.SID}/canvas/"
            if self.path.startswith(canvas_prefix):
                kind = self.path[len(canvas_prefix):]
                if kind not in web.EditRuntime.CANVAS_KINDS:
                    self.send_error(404)
                    return True
                self._send_json(ert.canvas_get(kind))
                return True
            if self.path.startswith(f"{self._CREATE_PREFIX}/session/{web.EditRuntime.SID}/portrait"):
                img = ert.world_dir / "assets" / (
                    "cover.png" if (ert.world_dir / "game").is_dir() else "portrait.png"
                )
                if not img.is_file():
                    img = ert.world_dir / "assets" / "portrait.png"
                if not img.is_file():
                    self.send_error(404)
                    return True
                data = img.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-cache")
                self._cors_headers()
                self.end_headers()
                self.wfile.write(data)
                return True
            if self.path == f"{self._CREATE_PREFIX}/session/{web.EditRuntime.SID}/entities":
                self._send_json(ert.entities())
                return True
            # 导入转换状态(工坊三选项面板)+ 源卡原文件(参考展示)
            if self.path == f"{self._CREATE_PREFIX}/session/{web.EditRuntime.SID}/import-status":
                self._send_json(web._import_status_payload(ert.world_dir))
                return True
            if self.path == f"{self._CREATE_PREFIX}/session/{web.EditRuntime.SID}/import-source":
                from neonrp.core.import_plan import plan_path

                imp = plan_path(ert.world_dir).parent
                found = sorted(imp.glob("source.*")) if imp.is_dir() else []
                if not found:
                    self.send_error(404)
                    return True
                src = found[0]
                ctype = {
                    ".png": "image/png",
                    ".json": "application/json; charset=utf-8",
                    ".txt": "text/plain; charset=utf-8",
                    ".md": "text/plain; charset=utf-8",
                    ".zip": "application/zip",
                }.get(src.suffix.lower(), "application/octet-stream")
                data = src.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-cache")
                self._cors_headers()
                self.end_headers()
                self.wfile.write(data)
                return True
            self.send_error(404)
            return True
        # /i18n works with or without a bound session — the PlayStage empty
        # state and the LocalShell both need the string table in launcher mode.
        if self.path == "/i18n" or self.path.startswith("/i18n?"):
            from urllib.parse import parse_qs, urlparse

            from neonrp.webui.i18n import web_strings

            q = parse_qs(urlparse(self.path).query)
            want = (q.get("locale") or [""])[0].strip()
            if want not in ("en", "zh", "ja", "ko"):
                if rt is not None:
                    want = rt.locale()
                else:
                    from neonrp.tui.i18n import resolve_locale

                    want = resolve_locale()
            self._send_json({"locale": want, "strings": web_strings(want)})
            return True
        if rt is None:
            # launcher 面接管(原 if 链此处必定应答:根路径引导页 / 409)
            return False
        if self.path == "/state":  # the player's view: only the characters they know (core/play_view; full: debug/state)
            self._send_json(play_view.safe_sse(rt.hello(), rt.root))
            return True
        if self.path == "/traces":
            # running: a turn is in flight (a queued line waits for it — worldlines/ui/player, 10-17)
            self._send_json({"turns": rt.traces_summary(), "running": rt._busy.locked()})
            return True
        if self.path.startswith("/trace?i="):
            try:
                idx = int(self.path.split("=", 1)[1])
            except ValueError:
                self.send_error(400)
                return True
            trace = rt.trace_at(idx)
            if trace is None:
                self.send_error(404)
                return True
            self._send_json(play_view.trace(trace))  # the player's view (full: debug/trace)
            return True
        if self.path.startswith("/image"):
            import mimetypes
            from urllib.parse import parse_qs, urlparse

            qs = parse_qs(urlparse(self.path).query)
            kind = (qs.get("kind") or ["world"])[0]
            soul_id = (qs.get("id") or [""])[0]
            # only allow plain token ids (defence against path traversal)
            if soul_id and not all(c.isalnum() or c in "-_" for c in soul_id):
                self.send_error(400)
                return True
            img = rt.image_path(kind, soul_id)
            if img is None or not img.is_file():
                self.send_error(404)
                return True
            try:
                data = img.read_bytes()
            except OSError:
                self.send_error(404)
                return True
            ctype = mimetypes.guess_type(img.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
            return True
        if self.path in ("/events", "/events?debug=1"):
            from neonrp.core import play_view as _pv

            raw = self.path.endswith("debug=1") and _pv.debug_enabled()  # the test bench: everything (local engine only)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            q = rt.broadcast.register()
            try:
                self._sse_write(rt.hello() if raw else _pv.safe_sse(rt.hello(), rt.root))
                idle = 0.0
                while True:
                    # 换局(POST /api/v1/play/session 起了新的 WebRuntime,广播也是新的):这条流还挂在旧的广播上,
                    # 再也收不到新一局的 chunk / turn_done —— 告诉页面「换局了」并断开,让它重连(曾卡在「主持在想」)
                    if getattr(self.server, "runtime", None) is not rt:
                        self._sse_write({"kind": "rebound"})
                        break
                    try:
                        event = q.get(timeout=2)
                    except queue.Empty:
                        idle += 2
                        if idle >= 15:
                            idle = 0.0
                            self.wfile.write(b": keepalive\n\n")
                            self.wfile.flush()
                        continue
                    idle = 0.0
                    if not raw:  # a player's page: the turn record trimmed, no thinking, no characters they do not know
                        event = _pv.safe_sse(event, rt.root)
                        if event is None:
                            continue
                    self._sse_write(event)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                rt.broadcast.unregister(q)
            return True
        return False

    def _engine_route_post(self, rt: "WebRuntime | None") -> bool:
        if self._map_route_post():
            return True
        if self._schema_route_post():
            return True
        if self._template_route_post(rt):
            return True
        if self._frontend_route_post(rt):
            return True
        if self._scene_art_post(rt):
            return True
        if self._approval_route_post(rt):
            return True
        if self._mode_route(rt, "POST"):
            return True
        if self.path.startswith(self._CREATE_PREFIX):
            self._post_create()
            return True
        if self.path == "/api/v1/play/engine/dry-run":  # R4: one beat through a throwaway copy of the run
            if rt is None:
                self.send_error(409, "no play session")
                return True
            from neonrp.core import dry_run

            body = self._read_json_body() or {}
            beat = str(body.get("beat") or "auto")
            if beat not in ("plan", "resolve", "auto") or not str(body.get("input") or "").strip():
                self.send_error(400, "input required; beat is plan | resolve | auto")
                return True
            self._send_json(dry_run.run(rt.root, str(body["input"]), beat=beat, overrides=body.get("overrides") or None,
                                        provider=getattr(rt, "provider", None)))
            return True
        if self.path.startswith(self._API_PREFIX):
            self._post_api(rt)
            return True
        if rt is None:
            # launcher 面接管(原 if 链此处是 launcher mode 的 409)
            return False
        if self.path == "/cmd":
            self._post_cmd(rt)
            return True
        if self.path == "/cancel":
            # 10-08:网页的「停止」—— 和 TUI 一样调 ConversationSession.cancel():当前这一步做完就停(send 开头会清掉标记)
            running = rt._busy.locked()
            if running:
                try:
                    rt.session().cancel()
                except Exception as exc:  # noqa: BLE001 — a session that is gone has nothing to stop
                    self._send_json({"ok": False, "running": True, "error": str(exc)[:200]})
                    return True
            self._send_json({"ok": True, "running": running})
            return True
        if self.path == "/start":
            # Fire the localized opening once on a fresh game (forwarded from
            # the launcher). Idempotent: a refresh / already-played game is a
            # no-op. Always 200 so the page never errors on load.
            started = rt.kickoff()
            self._send_json({"started": started})
            return True
        if self.path == "/rollback":
            self._post_rollback(rt)
            return True
        return False

    # ── CREATE contract POST routes (L0.1) ──
    def _post_create(self) -> None:
        ert: EditRuntime | None = web._try_rebind_edit_runtime(self.server)
        if self.path == f"{self._CREATE_PREFIX}/session":
            body = self._read_json_body() or {}
            # 角色工坊(完全照搬世界工坊)—— soul 目录当迷你世界打开,
            # 同一 EditRuntime/同一对话/同一树。白模=艾琳娜。
            soul_dir_req = str(body.get("soul_dir") or "").strip()
            if body.get("soul_template") or soul_dir_req:
                from neonrp.core.souls import SOUL_HOME

                if soul_dir_req:
                    if not web._safe_name(soul_dir_req):
                        self.send_error(400, "bad soul_dir")
                        return
                    starget = SOUL_HOME / soul_dir_req
                    if not (starget / "soul.json").exists():
                        self.send_error(404, "unknown soul")
                        return
                    # 已入库角色补基建(老角色没有 .neonrp)
                    if not (starget / ".neonrp" / "manifest.json").exists():
                        from neonrp.core.manifest import Manifest
                        from neonrp.core.storage import atomic_write_json, ensure_dirs

                        ensure_dirs(starget)
                        atomic_write_json(
                            starget / ".neonrp" / "manifest.json", Manifest().model_dump()
                        )
                        cpreset0 = web._resolve_creation_preset("")
                        if cpreset0:
                            web._apply_run_preset(starget, cpreset0)
                else:
                    try:
                        starget = web._scaffold_soul_blank(
                            str(body.get("name") or "角色").strip() or "角色",
                            str(body.get("seed") or "").strip(),
                        )
                    except Exception as exc:  # noqa: BLE001
                        self.send_error(500, f"soul scaffold failed: {exc}"[:120])
                        return
                cpreset = web._resolve_creation_preset("")
                if cpreset:
                    web._apply_run_preset(starget, cpreset)
                self.server.edit_runtime = web._make_edit_runtime(starget)
                ert = self.server.edit_runtime
                self._send_json({
                    "session_id": web.EditRuntime.SID,
                    "world_id": ert.world_id,
                    "kind": "soul",
                    "template": "soul-blank" if not soul_dir_req else None,
                    "files": ert.tree(),
                })
                return
            world_id = str(body.get("world_id") or "").strip()
            if world_id:
                from neonrp.worlds import get_owned_world_dir

                target = get_owned_world_dir(world_id)
                if target is None:
                    self.send_error(404, "unknown owned world")
                    return
                template = None
            else:
                from neonrp.worlds import WORLDS_HOME, scaffold_template_into

                template = str(body.get("template") or "white-blank").strip()
                if not web._safe_name(template):
                    self.send_error(400, "bad template")
                    return
                human_name = str(body.get("name") or "").strip()
                slug = web._new_world_slug(human_name)
                target = WORLDS_HOME / slug
                try:
                    from neonrp import template as TP

                    hit = TP.discover().get(template)
                    if hit is not None:
                        # a v3 template (10-06): world + overlay + souls + plots, like a new run of it — the old scaffold only knows
                        # the built-in worlds (a template with its own world folder failed; an overlay template lost its overlay)
                        from neonrp.core.manifest import Manifest
                        from neonrp.core.paths import get_manifest_path
                        from neonrp.core.storage import atomic_write_json, ensure_dirs
                        from neonrp.worlds import seed_run_model

                        TP.build(TP.load(hit), target)
                        ensure_dirs(target)
                        atomic_write_json(get_manifest_path(target), Manifest().model_dump())
                        seed_run_model(target, None)
                    else:
                        scaffold_template_into(template, target)
                except Exception as exc:  # noqa: BLE001 — clean HTTP error
                    import shutil

                    shutil.rmtree(target, ignore_errors=True)
                    self.send_error(400, f"scaffold failed: {exc}"[:120])
                    return
                # 人类可读名写进 game-start(read_local_world_name 的显示名
                # SoT)—— 中文名 slug 化后目录只剩 world-<ts>,不写的话
                # 书房/工坊满屏时间戳(「名字乱码」)。
                if human_name:
                    web._set_world_display_name(target, human_name)
            # 创作会话的 agent 用世界目录自己的 config —— 把解析出的创作
            # LLM(书房设置/全局 key)写进去,外面配好的模型里面直接可用
            # (实测矛盾:外面有 LLM,进工坊说没有)。
            cpreset = web._resolve_creation_preset("")
            if cpreset:
                web._apply_run_preset(target, cpreset)
            self.server.edit_runtime = web._make_edit_runtime(target)
            ert = self.server.edit_runtime
            self._send_json(
                {
                    "session_id": web.EditRuntime.SID,
                    "world_id": ert.world_id,
                    "template": template,
                    "files": ert.tree(),
                }
            )
            return
        if ert is None:
            self.send_error(409, "no edit session - POST /api/v1/create/session first")
            return
        # POST portrait — 生成立绘/封面(书房配置的 image 后端;
        # 角色没有封面图,要接 ComfyUI 生成 + 上传)。body {prompt?}。
        if self.path == f"{self._CREATE_PREFIX}/session/{web.EditRuntime.SID}/portrait":
            if ert is None:
                self.send_error(409, "no edit session")
                return
            body = self._read_json_body() or {}
            prompt = str(body.get("prompt") or "").strip()
            if not prompt:
                prompt = web._portrait_prompt_from(ert.world_dir)
            from neonrp.core.imagegen import generate_image, load_image_config

            icfg = load_image_config()
            if not icfg.is_configured:
                self._send_json(
                    {"ok": False, "error": "image backend not configured - set ComfyUI in Library settings"},
                    status=400,
                )
                return
            # 世界会话生成横版封面(cover.png,与封面卡/游玩页同一约定);
            # soul 会话生成竖版立绘(portrait.png)。
            is_world = (ert.world_dir / "game").is_dir() or (
                ert.world_dir / ".neonrp" / "runtime_contract.json"
            ).exists()
            fname = "cover.png" if is_world else "portrait.png"
            w, h = (1216, 832) if is_world else (832, 1216)
            try:
                out = generate_image(prompt, ert.world_dir / "assets", cfg=icfg, width=w, height=h)
                final = ert.world_dir / "assets" / fname
                final.parent.mkdir(parents=True, exist_ok=True)
                if out != final:
                    out.replace(final)
            except Exception as exc:  # noqa: BLE001 — comfy/network errors
                self._send_json({"ok": False, "error": str(exc)[:200]}, status=502)
                return
            self._send_json({"ok": True, "path": f"assets/{fname}"})
            return
        # POST portrait/upload — 手动上传(raw image body)
        if self.path == f"{self._CREATE_PREFIX}/session/{web.EditRuntime.SID}/portrait/upload":
            if ert is None:
                self.send_error(409, "no edit session")
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length <= 0 or length > 20_000_000:
                self.send_error(400, "missing or oversized body")
                return
            data = self.rfile.read(length)
            is_world_u = (ert.world_dir / "game").is_dir()
            fname_u = "cover.png" if is_world_u else "portrait.png"
            final = ert.world_dir / "assets" / fname_u
            final.parent.mkdir(parents=True, exist_ok=True)
            final.write_bytes(data)
            self._send_json({"ok": True, "path": f"assets/{fname_u}"})
            return
        if self.path == f"{self._CREATE_PREFIX}/session/{web.EditRuntime.SID}/message":
            body = self._read_json_body() or {}
            text = str(body.get("input") or "").strip()
            if not text:
                self.send_error(400)
                return
            self._api_create_message(ert, text)
            return
        if self.path == f"{self._CREATE_PREFIX}/session/{web.EditRuntime.SID}/playtest":
            from neonrp.worlds import instantiate_run

            try:
                run_dir = instantiate_run(ert.world_id)
            except (KeyError, OSError) as exc:
                self.send_error(500, f"instantiate failed: {exc}"[:120])
                return
            status, detail = web._switch_runtime(self.server, run_dir.name)
            if status != 200:
                self.send_error(status, detail)
                return
            payload = self.server.runtime.gateway_start()
            payload["note"] = "playtest run"
            self._send_json(payload)
            return
        self.send_error(404)

    @staticmethod
    def _tool_event(name: str, args: Any) -> dict[str, Any]:
        """Terse tool descriptor for the workbench stream — never echo full
        args (write_file content can be huge); surface the path-ish bit."""
        a = args if isinstance(args, dict) else {}
        path = str(a.get("path") or a.get("file_path") or a.get("target") or "")
        return {"name": name, "path": path}

    def _api_create_message(self, ert: "EditRuntime", text: str) -> None:
        """One edit turn as SSE: thinking/chunk/tool_use/tool_result → done."""
        if not ert._busy.acquire(blocking=False):
            self.send_response(409)
            self._cors_headers()
            self.end_headers()
            return
        q: "queue.Queue[tuple[str, Any]]" = queue.Queue()
        result_holder: list[Any] = []
        error_holder: list[str] = []

        def _run() -> None:
            try:
                r = ert.session().send(
                    text,
                    on_thinking=lambda t: q.put(("thinking", {"text": t})) if t else None,
                    on_chunk=lambda t: q.put(("chunk", {"text": t})) if t else None,
                    on_tool_use=lambda name, args: q.put(
                        ("tool_use", self._tool_event(name, args))
                    ),
                    on_tool_result=lambda name, args, res: q.put(
                        (
                            "tool_result",
                            {**self._tool_event(name, args), "summary": str(res)[:300]},
                        )
                    ),
                )
                result_holder.append(r)
            except Exception as exc:  # noqa: BLE001 — surface on the stream
                error_holder.append(f"edit turn crashed: {exc}")
            finally:
                q.put(("__end__", None))
                ert._busy.release()

        threading.Thread(target=_run, daemon=True).start()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self._cors_headers()
        self.end_headers()

        def _emit(name: str, data: dict[str, Any]) -> None:
            payload = json.dumps(data, ensure_ascii=False, default=str)
            self.wfile.write(f"event: {name}\ndata: {payload}\n\n".encode())
            self.wfile.flush()

        try:
            while True:
                try:
                    event = q.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                name, data = event
                if name == "__end__":
                    break
                _emit(name, data)
            if error_holder:
                _emit("error", {"error": error_holder[0]})
                return
            r = result_holder[0] if result_holder else None
            _emit(
                "done",
                {
                    "session_id": web.EditRuntime.SID,
                    "world_id": ert.world_id,
                    "success": bool(getattr(r, "success", False)),
                    "assistant_message": getattr(r, "assistant_message", "") or "",
                    "error": getattr(r, "error", None),
                },
            )
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # client left; the edit finishes server-side
        # NOTE: no unregister needed — the queue is per-request local.

    def _post_api(self, rt: "WebRuntime | None") -> None:
        sid = web.WebRuntime._LOCAL_SID
        # POST /api/v1/play/portrait {kind:'soul'|'player', id, prompt?} — 给本局
        # 的实体生成立绘(连生图)。落到 image_path 读取的 assets/,
        # 前端 imageUrl 立即显示。需先配 image backend(ComfyUI/OpenAI)。
        if self.path == f"{self._API_PREFIX}/portrait":
            if rt is None:
                self.send_error(409, "no active session")
                return
            body = self._read_json_body() or {}
            kind = str(body.get("kind") or "soul").strip()
            ent_id = str(body.get("id") or "").strip()
            from neonrp.core.imagegen import generate_image, load_image_config

            icfg = load_image_config()
            if not icfg.is_configured:
                self._send_json({"ok": False, "error": "image backend not configured"}, status=400)
                return
            adir, prompt = rt.portrait_target(kind, ent_id)
            if adir is None:
                self.send_error(404, "entity not found")
                return
            prompt = str(body.get("prompt") or "").strip() or prompt
            try:
                out = generate_image(prompt, adir, cfg=icfg, width=832, height=1216)
                final = adir / "portrait.png"
                final.parent.mkdir(parents=True, exist_ok=True)
                if out != final:
                    out.replace(final)
            except Exception as exc:  # noqa: BLE001 — comfy/network errors surface to UI
                self._send_json({"ok": False, "error": str(exc)[:200]}, status=502)
                return
            self._send_json({"ok": True})
            return
        if self.path == f"{self._API_PREFIX}/session":
            # StartRequest.slug, locally, selects WHICH run this server wraps:
            # empty/current = attach to the active one; an existing PLAYS_HOME
            # run = resume it; an owned world id = instantiate a fresh run; a
            # built-in world id = scaffold a fresh run. In launcher mode
            # (runtime None) a resolvable slug BINDS the first session.
            body = self._read_json_body() or {}
            slug = str(body.get("slug") or "").strip()
            preset = str(body.get("preset") or "").strip()
            # 本局输出语(语言隔离):前端传 wl-local-lang,落进
            # run_state.output_lang,soul-agent 隐藏模板/裁定按它选中/英/日。
            output_lang = str(body.get("output_lang") or "").strip()
            souls = [s for s in (body.get("souls") or []) if isinstance(s, str) and s.strip()]
            # 面板玩家(10-14,template/builder.py):捏人界面捏好的角色 {fields, companion};只对模板新开一局有效,
            # 引擎先校验(点数 / 必填 / 选项),不过 → 400 {ok:false, errors},什么都不建
            player = body.get("player") if isinstance(body.get("player"), dict) else None
            detail = ""
            if slug or self.server.runtime is None:
                # 玩家选的语言驱动平行世界文件夹选择(fresh 开局 scaffold 时)。
                # replace(10-21 存档上限):玩家选了删哪一局来开这一局 —— 新局建好后删掉它
                replace = str(body.get("replace") or "").strip() or None
                status, detail = web._switch_runtime(self.server, slug, locale=output_lang or None, player=player, replace=replace)
                if status in (400, 409) and detail.startswith("{"):   # 400 捏人不过 / bad_replace · 409 save_limit(带这个世界的存档)
                    self._send_json(json.loads(detail), status=status)
                    return
                if status != 200:
                    self.send_response(status)
                    self._cors_headers()
                    self.end_headers()
                    self.wfile.write(detail.encode("utf-8"))
                    return
            # Casting ②(TUI CastingScreen 的 web 版):只对本次 bind 新建的
            # run 投放 souls —— resume 一个已有存档时带 souls 是无效输入。
            if souls and detail == "switched-fresh" and self.server.runtime is not None:
                # 前端传的是 souls 库的 dir_name;投放函数吃完整路径 —
                # 先经 resolve_soul_dir(同 `neonrp cast` 的 token 解析)。
                from neonrp.cli import _cast_bring_in_souls
                from neonrp.core.placement import PlacementError, resolve_soul_dir

                try:
                    dirs = tuple(str(resolve_soul_dir(s.strip())) for s in souls)
                    _cast_bring_in_souls(self.server.runtime.root, dirs)
                except (PlacementError, OSError) as exc:
                    self.send_error(400, f"cast failed: {exc}"[:120])
                    return
            # 分身当主角(10-15,Hub「我的」):avatar = 分身文件名 或 "current";只对本次新开的一局、且没走捏人
            # (player)时生效 —— 把分身的字段并进这一局的主角档、立绘换成分身的(players.apply_avatar_to_run)
            avatar = str(body.get("avatar") or "").strip()
            if avatar and player is None and detail == "switched-fresh" and self.server.runtime is not None:
                from neonrp import players as _players

                stem = _players.current_avatar() if avatar == "current" else avatar
                try:
                    _players.apply_avatar_to_run(self.server.runtime.root, stem or "")
                except (OSError, ValueError):
                    pass
            # 开局兜底 provider(niko 2026-09-03 实测):从世界选择器直接 bind
            # 一个新 run 时没带 preset → run config 无 model → souls 停在 stub。
            # fresh 开局若没显式 preset,就用书房默认(create_provider)。resume
            # 已有存档不动(它自带本局 config)。auto=兜底(失败静默,不把成功的
            # 开局变 400);显式传的坏 preset 仍 400。
            preset_is_auto = False
            if not preset and detail == "switched-fresh" and self.server.runtime is not None:
                preset = web._resolve_creation_preset("")
                preset_is_auto = bool(preset)
            # 落本局输出语到 run_state(bind 后 runtime.root 就绪)。缺省不写,
            # 读取侧 resolve_output_lang 回退世界 source_lang → zh。
            # 接着一局(10-16):这一局按某种语言建的(模板的 i18n 层),世界文件就是那种语言,换不回来 —— 请求别的语言不改,
            # 照这一局的语言续,回包带 lang_kept 让前端提示「这一局是英文的,要不要用日文新开」(之前改成请求的语言,一局两种语言混着)
            lang_note: dict[str, Any] = {}
            if output_lang and self.server.runtime is not None:
                try:
                    from neonrp.core.output_lang import built_lang, normalize_prompt_lang, write_output_lang

                    built = built_lang(self.server.runtime.root) if detail != "switched-fresh" else None
                    if built and normalize_prompt_lang(output_lang) != built:
                        write_output_lang(self.server.runtime.root, built)
                        lang_note = {"lang": built, "lang_requested": normalize_prompt_lang(output_lang), "lang_kept": True}
                    else:
                        write_output_lang(self.server.runtime.root, output_lang)
                except Exception:  # noqa: BLE001 — 语言落盘 best-effort,不阻塞开局
                    pass
            # PrePlay 模型接入:把本局要用的 provider 写进 run 的 config,
            # 并重建 runtime 让新会话立刻用上(旧 session 持有旧 config)。
            if preset and self.server.runtime is not None:
                run_dir = self.server.runtime.root
                applied = web._apply_run_preset(run_dir, preset)
                if not applied and not preset_is_auto:
                    self.send_error(400, "unknown preset")
                    return
                if not applied:
                    # 兜底 provider 没配好:开局照常(souls 落 stub),不阻塞 bind。
                    preset = ""
                agent = web.get_startup_entry_agent(run_dir) or self.server.runtime.agent_id
                # 重建 runtime 让新 config 生效 —— 但必须继承开场指令,
                # 否则新开一局不自动开演(二次实测:PrePlay 总是带
                # preset,重建把 bind 注入的 startup_commands 丢了)。
                carried = list(self.server.runtime._startup_commands or [])
                self.server.runtime = web.WebRuntime(
                    run_dir, agent, startup_commands=carried, reopen=self.server.runtime._reopen
                )
            if self.server.runtime is not None:  # chronicle: this world was opened (and the run exists) — sent in the background
                try:
                    from neonrp.core import chronicle

                    chronicle.opened(self.server.runtime.root)
                except Exception:  # noqa: BLE001 — telling chronicle never stops a bind
                    pass
            self._send_json({**self.server.runtime.gateway_start(), **lang_note})
            return
        # POST /session/<sid>/resume — the shared PlayPage's continue path.
        # Locally a save's sid IS its run-dir name, so resume = switch + start.
        if self.path.startswith(f"{self._API_PREFIX}/session/") and self.path.endswith(
            "/resume"
        ):
            rsid = web._path_seg(self.path[len(f"{self._API_PREFIX}/session/"):-len("/resume")])
            status, detail = web._switch_runtime(self.server, rsid)
            if status != 200:
                self.send_response(status)
                self._cors_headers()
                self.end_headers()
                self.wfile.write(detail.encode("utf-8"))
                return
            self._send_json(self.server.runtime.gateway_start())
            return
        if rt is None:  # turn/stream need a bound session
            self.send_error(409, "no active session - POST /session with a slug first")
            return
        # POST /session/<sid>/save — 命名快照(TUI /save 的 web 版)
        if self.path == f"{self._API_PREFIX}/session/{sid}/save":
            from neonrp.commands.save import create_save_snapshot

            body = self._read_json_body()
            name = str((body or {}).get("name") or "").strip() or None
            try:
                result = create_save_snapshot(rt.root, name)
            except (ValueError, OSError) as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
                return
            self._send_json({"ok": True, **result})
            return
        # POST /api/v1/play/chat — 对话拍(T1):一次纯 LLM 轻调用直聊。
        # 时钟不走、回合不加、不结算;对话行进 pending,下个世界拍 preflight 固化。
        if self.path == f"{self._API_PREFIX}/chat":
            from neonrp.core.light_chat import light_chat_reply

            body = self._read_json_body() or {}
            iid = str(body.get("iid") or "").strip()
            text = str(body.get("text") or "")
            if not iid or not web._safe_name(iid):
                self.send_error(400)
                return
            out = light_chat_reply(rt.root, iid, text)
            self._send_json(out, status=200 if out.get("ok") else 409)
            return
        # POST /api/v1/play/say — 寻址输入统一受理(M24 §0.5):@名字→直聊,
        # #→群聊;lane=world 原样返还,前端走原 /cmd(世界拍管线不经此层)。
        if self.path == f"{self._API_PREFIX}/say":
            from neonrp.core.address import parse_address
            from neonrp.core.light_chat import light_chat_reply, room_chat_reply

            body = self._read_json_body() or {}
            parsed = parse_address(rt.root, str(body.get("text") or ""))
            if parsed["lane"] == "dialogue" and parsed["target"]:
                if not parsed["text"]:
                    # 只 @ 了名字:开线程不发话(UI 打开抽屉即可)。
                    self._send_json(
                        {"ok": True, "lane": "dialogue", "target": parsed["target"], "open_only": True}
                    )
                    return
                out = light_chat_reply(rt.root, parsed["target"], parsed["text"])
                self._send_json(
                    {"lane": "dialogue", "target": parsed["target"], **out},
                    status=200 if out.get("ok") else 409,
                )
                return
            if parsed["lane"] == "room":
                if not parsed["text"]:
                    # 裸 #:开房间不发话(UI 打开群聊视图即可)。
                    self._send_json({"ok": True, "lane": "room", "open_only": True})
                    return
                out = room_chat_reply(rt.root, parsed["text"])
                self._send_json({"lane": "room", **out}, status=200 if out.get("ok") else 409)
                return
            self._send_json({"ok": True, "lane": "world", "text": parsed["text"]})
            return
        # POST /api/v1/play/chat-room — 群聊一轮(T2):在场 souls 顺序轻调用,
        # 自选接话或 [沉默];时钟不走、不结算。
        if self.path == f"{self._API_PREFIX}/chat-room":
            from neonrp.core.light_chat import room_chat_reply

            body = self._read_json_body() or {}
            out = room_chat_reply(
                rt.root,
                str(body.get("text") or ""),
                primary_iid=str(body.get("primary_iid") or "") or None,
            )
            self._send_json(out, status=200 if out.get("ok") else 409)
            return
        # POST /session/<sid>/undo|redo — TUI /undo //redo 的 web 版。
        # 回退/重做后前端应重新拉 /session/<sid>(状态已变)。
        if self.path == f"{self._API_PREFIX}/session/{sid}/undo":
            from neonrp.commands.branch import perform_undo

            self._send_json(perform_undo(rt.root))
            return
        if self.path == f"{self._API_PREFIX}/session/{sid}/redo":
            from neonrp.commands.branch import perform_redo

            self._send_json(perform_redo(rt.root))
            return
        if self.path == f"{self._API_PREFIX}/session/{sid}/turn":
            body = self._read_json_body()
            text = _turn_input(body)
            if not text:
                self.send_error(400)
                return
            resp = rt.gateway_turn(text)
            if resp is None:
                self.send_response(409)
                self._cors_headers()
                self.end_headers()
                return
            self._send_json(resp)
            return
        if self.path == f"{self._API_PREFIX}/session/{sid}/turn/stream":
            body = self._read_json_body()
            text = _turn_input(body)
            if not text:
                self.send_error(400)
                return
            self._api_turn_stream(rt, text)
            return
        self.send_error(404)

    # Broadcast kinds forwarded verbatim as SSE events. thinking/chunk/
    # soul_status/trace match the hosted gateway's event names; the rest are
    # local extras a client may ignore (or adopt — they carry the richer
    # native-web data like soul_psyche and the map's positions).
    _STREAM_KINDS = (
        "thinking",
        "chunk",
        "soul_status",
        "trace",
        "soul_psyche",
        "tool",
        "agent_error",
        "positions",
        # contract 1.0 beat events (R6, core/beat_events.py)
        "node.enter",
        "node.leave",
        "plan.beat",
        "resolve.beat",
        "dice",
        "dice.rolled",  # 10-17: a die the moment its tool returns (before the beat lands)
        "state.changed",
        "run.settled",
        # 10-14 (the standard front end): who joined / left, a plot stage reached, a template picture to show
        "party.join",
        "party.leave",
        "stage.changed",
        "show",
        "soul.mind",  # 10-15: what a character present made of the beat
        "place.discovered",  # 10-15: a place the player learned of
        "audio.cue",  # 10-15: the music / ambient bed changed (core/audio)
    )

    def _api_turn_stream(self, rt: "WebRuntime", text: str) -> None:
        """Gateway-shaped SSE turn: same event names + a final `done` payload.

        Rides the broadcast bus for the live events (registered BEFORE the
        turn starts so nothing is missed) and takes the authoritative done
        payload from the blocking gateway_turn result on a worker thread."""
        result_holder: list[dict[str, Any] | None] = []
        q = rt.broadcast.register()
        worker = threading.Thread(
            target=lambda: result_holder.append(rt.gateway_turn(text)),
            daemon=True,
        )
        worker.start()
        # gateway_turn returns None instantly when a turn is already running —
        # give it a beat, then reject like the hosted gateway would.
        worker.join(0.05)
        if result_holder and result_holder[0] is None:
            rt.broadcast.unregister(q)
            self.send_response(409)
            self._cors_headers()
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self._cors_headers()
        self.end_headers()

        def _emit(name: str, data: dict[str, Any]) -> None:
            payload = json.dumps(data, ensure_ascii=False)
            self.wfile.write(f"event: {name}\ndata: {payload}\n\n".encode())
            self.wfile.flush()

        try:
            while True:
                try:
                    event = q.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                kind = str(event.get("kind") or "")
                if kind == "turn_done":
                    break
                if kind in self._STREAM_KINDS:
                    from neonrp.core import play_view as _pv

                    event = _pv.safe_sse(event, rt.root)  # a player's stream: the trace trimmed, no thinking (core/play_view, 10-15)
                    if event is not None:
                        _emit(kind, {k: v for k, v in event.items() if k != "kind"})
            worker.join(10)
            done = result_holder[0] if result_holder else None
            if done is None:
                _emit("error", {"error": "turn did not produce a result"})
            elif done.get("success"):
                _emit("done", done)
            else:
                # Hosted gateway emits `error` (no done) on a crashed turn —
                # match it so the shared client has one failure path.
                _emit("error", {"error": done.get("error") or "turn failed", **({"billing": done["billing"]} if done.get("billing") else {})})
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # client went away mid-stream; the turn finishes server-side
        finally:
            rt.broadcast.unregister(q)

    def _post_rollback(self, rt: "WebRuntime") -> None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
            commit_id = str(payload.get("commit") or "").strip()
        except (ValueError, OSError):
            self.send_error(400)
            return
        if not commit_id:
            self.send_error(400)
            return
        self._send_json(rt.rollback(commit_id))

    def _post_cmd(self, rt: "WebRuntime") -> None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
            # a front end's structured action {action: inspect | pick, target} · {action: skill, skill, target?}
            # (core/player_action, 10-14) wins over the text
            from neonrp.core.player_action import from_body

            text = from_body(payload) or str(payload.get("text") or "").strip()
        except (ValueError, OSError):
            self.send_error(400)
            return
        if not text:
            self.send_error(400)
            return
        if not rt.submit(text):
            # a turn (the opening, or the line before) is still running: say so, so a front end can queue the line
            # instead of guessing (an empty 409 still means busy to older pages)
            self._send_json({"error": "busy", "reason": "turn_running"}, status=409)
            return
        self.send_response(202)
        self.end_headers()
