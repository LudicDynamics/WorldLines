"""launcher 面 HTTP 路由(docs/ENGINE-API-CONTRACT.md §0 归属列)。

归属 `LAUNCHER-LOCAL`(`/api/v1/local/*` 全部 —— 本地库/设置/导入/hub 桥,
读写 `~/.worldlines`)、`SHELL`(`/local` `/assets` 的 SPA 托管、顶层静态
文件、根路径引导/302)的每条路由都住这里。(旧 `LEGACY-VANILLA` 通路——vanilla 页
`_page_html` + 裸 `/upload`——已整体退役 2026-08-31;SPA 走 `/api/v1/*` 上传。)

物理拆分:方法体逐字搬自 `neonrp.commands.web`,行为零变化。
`_launcher_route_*` 是从原 `_Handler.do_*` if 链里切出的另一半 —— 返回
True 表示已应答,False 表示两半都不认领(调用方原样 404)。模块级符号仍
住 web.py,经 `http_util.web` 代理按名字延迟取,patch 路径因此不变。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from neonrp.webui.http_util import web

if TYPE_CHECKING:  # 仅注解用 —— 运行期一律走 web.<符号>,不建 import 环
    from neonrp.commands.web import WebRuntime


# the browser sign-in the Hub / studio starts (POST /api/v1/local/account/login): one at a time, in the background.
# state: idle · running · error · cancelled;error_code = the identity code (login_timeout · unreachable · access_denied …) for the
# page's four-language message. Cancel (10-17) = this one no longer counts (gen moves on) and a new one may start at once —
# the old loopback listener just runs out (its sign-in, if the player still finishes it, is kept like any other).
_LOGIN: dict[str, Any] = {"state": "idle", "error": None, "code": None, "url": None, "gen": 0}
LOGIN_TIMEOUT_S = 300  # the identity client's loopback wait (local_login timeout_s)


def _start_login() -> None:
    import threading

    if _LOGIN["state"] == "running":
        return
    _LOGIN["gen"] += 1
    gen = _LOGIN["gen"]
    _LOGIN.update(state="running", error=None, code=None, url=None)

    def mine(**kw: Any) -> None:
        if _LOGIN["gen"] == gen:
            _LOGIN.update(**kw)

    def run() -> None:
        from neonrp.core import worldlines_auth

        try:
            worldlines_auth.connect(open_browser=True, on_url=lambda u: mine(url=str(u)))
            mine(state="idle", url=None)
        except Exception as e:  # noqa: BLE001 — shown to the player as it is
            mine(state="error", error=str(e)[:300], code=str(getattr(e, "code", "") or type(e).__name__), url=None)

    threading.Thread(target=run, daemon=True, name="worldlines-login").start()


def _cancel_login() -> None:
    if _LOGIN["state"] == "running":
        _LOGIN["gen"] += 1
        _LOGIN.update(state="cancelled", error=None, code=None, url=None)


class LauncherRoutes:
    """launcher 面的 handler mixin(与 BaseHTTPRequestHandler 合体使用)。"""

    server: Any  # ThreadingHTTPServer with .runtime attached
    path: str

    def _launcher_route_options(self) -> bool:
        if self.path.startswith("/api/v1/local"):
            self.send_response(204)
            self._cors_headers()
            self.end_headers()
            return True
        return False

    def _launcher_route_put(self) -> bool:
        if self._avatar_route("PUT"):
            return True
        # PUT /api/v1/local/settings/key {preset_id, api_key, model_override?}
        # — persist a provider key to ~/.neonrp/config.json (the same
        # _save_key_to_user_config the TUI settings screen uses) and export it
        # into the running process so it's usable immediately.
        if self.path == "/api/v1/local/settings/key":
            body = self._read_json_body() or {}
            preset_id = str(body.get("preset_id") or "").strip()
            api_key = str(body.get("api_key") or "").strip()
            model_override = str(body.get("model_override") or "").strip() or None
            if not preset_id or not api_key:
                self.send_error(400)
                return True
            import os

            from neonrp.presets import (
                PRESETS,
                _save_key_to_user_config,
                list_presets,
            )

            try:
                _save_key_to_user_config(
                    preset_id, api_key, model_override=model_override
                )
            except Exception as exc:  # noqa: BLE001
                self.send_error(400, str(exc)[:120])
                return True
            env_name = (PRESETS.get(preset_id) or {}).get("api_key_env")
            if env_name:
                os.environ[str(env_name)] = api_key
            self._send_json({"ok": True, "presets": list_presets()})
            return True
        # PUT /api/v1/local/settings/custom-model {id, base_url, model, api_key?}
        # — 添加自定义 OpenAI 兼容 API 端点(TUI settings「自定义模型」的 web 版:
        # 写 ~/.neonrp/config.json.models[id]);之后作为 preset 出现在列表里。
        if self.path == "/api/v1/local/settings/custom-model":
            body = self._read_json_body() or {}
            from neonrp.presets import list_presets, save_custom_model

            try:
                mid = save_custom_model(
                    str(body.get("id") or ""),
                    str(body.get("base_url") or ""),
                    str(body.get("model") or ""),
                    str(body.get("api_key") or ""),
                )
            except ValueError as exc:
                self.send_error(400, str(exc)[:120])
                return True
            except Exception as exc:  # noqa: BLE001
                self.send_error(400, str(exc)[:120])
                return True
            self._send_json({"ok": True, "id": mid, "presets": list_presets()})
            return True
        # PUT /api/v1/local/settings/create-provider {preset_id: str|null}
        # — 创作用 LLM,独立于游玩模型(TUI settings「creation LLM」)。
        if self.path == "/api/v1/local/settings/create-provider":
            body = self._read_json_body() or {}
            preset_id = body.get("preset_id")
            from neonrp.presets import set_create_provider

            try:
                set_create_provider(
                    str(preset_id).strip() if preset_id else None
                )
            except Exception as exc:  # noqa: BLE001
                self.send_error(400, str(exc)[:120])
                return True
            self._send_json({"ok": True, "create_provider": preset_id or None})
            return True
        # PUT /api/v1/local/settings/image {backend?, comfyui_url?, ...}
        # — 图像生成后端(TUI settings「图像」;写 ~/.neonrp/config.json.image)。
        if self.path == "/api/v1/local/settings/image":
            body = self._read_json_body() or {}
            from neonrp.core.imagegen import load_image_config, save_image_config

            cfg = load_image_config()
            for field in (
                "backend",
                "comfyui_url",
                "comfyui_ckpt",
                "comfyui_workflow",
                "comfyui_input_node",
                "comfyui_neg_node",
                "comfyui_output_node",
                "comfyui_seed_node",
                "openai_key",
                "openai_model",
                "codex_bin",
            ):
                if field in body:
                    setattr(cfg, field, str(body.get(field) or "").strip())
            try:
                save_image_config(cfg)
            except Exception as exc:  # noqa: BLE001
                self.send_error(400, str(exc)[:120])
                return True
            self._send_json({"ok": True, "configured": cfg.is_configured})
            return True
        return False

    def _launcher_route_delete(self) -> bool:
        if self._replay_route(None, "DELETE"):
            return True
        # DELETE /api/v1/local/settings/entry/<id> — 删除用户 config 里的
        # 自定义模型条目(TUI settings 条目详情的「删除」)。
        prefix = "/api/v1/local/settings/entry/"
        if self.path.startswith(prefix):
            entry_id = web._path_seg(self.path[len(prefix):])
            if not entry_id:
                self.send_error(400)
                return True
            from neonrp.presets import list_presets
            from neonrp.tui.settings_flow import delete_entry

            try:
                delete_entry(entry_id)
            except Exception as exc:  # noqa: BLE001
                self.send_error(400, str(exc)[:120])
                return True
            self._send_json({"ok": True, "presets": list_presets()})
            return True
        # DELETE /api/v1/local/worlds/<id> — remove an owned world (library
        # source + its runs; built-ins refuse inside delete_owned_world).
        prefix = "/api/v1/local/worlds/"
        if self.path.startswith(prefix):
            world_id = web._path_seg(self.path[len(prefix):])
            if not web._safe_name(world_id):
                self.send_error(400)
                return True
            from neonrp.worlds import delete_owned_world

            ok = False
            try:
                ok = delete_owned_world(world_id)
            except OSError:
                ok = False
            self._send_json({"ok": bool(ok)})
            return True
        # DELETE /api/v1/local/souls/<dir_name> — remove a soul from the
        # library (core.souls.delete_soul refuses path escapes itself).
        prefix = "/api/v1/local/souls/"
        if self.path.startswith(prefix):
            dir_name = web._path_seg(self.path[len(prefix):])
            if not web._safe_name(dir_name):
                self.send_error(400)
                return True
            from neonrp.core.souls import delete_soul

            try:
                ok = delete_soul(dir_name)
            except Exception:  # noqa: BLE001
                ok = False
            self._send_json({"ok": bool(ok)})
            return True
        return False

    def _chat_route(self, rt: "WebRuntime | None", method: str) -> bool:
        """Talking with a character outside its world (core/soul_chat, 10-15): /api/v1/chat/souls · thread · sticker · send · answer · presence ·
        subscription · catchup · world_card;
        a character is ``tpl`` + ``sid`` or one ``ref`` (``lib:<folder>`` · ``tpl:<template>/<sid>``, 10-16).
        The soul side of the orchestration bench (core/soul_orchestration, Local only — not in the browser engine):
        GET /api/v1/souls/catalog · GET /api/v1/souls/orchestration?ref= · POST /api/v1/souls/orchestration {ref, graph} ·
        POST /api/v1/souls/orchestration/lint {graph} · GET/POST /api/v1/souls/stickers(?ref=&id= raw PNG)· /stickers/meta
        {ref, id, label, when} · /stickers/remove {ref, id} · GET /api/v1/souls/ambient?ref=[&replicate=1] · POST /api/v1/souls/ambient
        {ref, world} · POST /api/v1/souls/ambient/generate {ref, lang?} (core/soul_ambient: the simple world a tick happens in) ·
        POST /api/v1/souls/in_world {ref, variant, world?} (its variant in its world's engine settings)."""
        from urllib.parse import parse_qs, urlparse

        u = urlparse(self.path)
        if u.path.startswith("/api/v1/souls/"):
            return self._soul_bench_route(method, u.path, {k: v[0] for k, v in parse_qs(u.query).items() if v})
        if u.path.startswith("/api/v1/phone/"):
            return self._phone_bench_route(method, u.path)
        if not u.path.startswith("/api/v1/chat/"):
            return False
        from neonrp.core import soul_chat
        from neonrp.core.soul_orchestration import split_ref

        q = {k: v[0] for k, v in parse_qs(u.query).items() if v}
        if q.get("ref"):
            q["tpl"], q["sid"] = split_ref(q["ref"])
        try:
            if method == "GET" and u.path == "/api/v1/chat/souls":
                self._send_json(soul_chat.souls(q.get("lang")))
            elif method == "GET" and u.path == "/api/v1/chat/thread":
                self._send_json(soul_chat.thread(q.get("tpl", ""), q.get("sid", ""), q.get("lang")))
            elif u.path in ("/api/v1/chat/tick", "/api/v1/chat/tick/settings"):  # the foreground tick (core/soul_tick, off by default)
                from neonrp.core import soul_tick

                b = (self._read_json_body() or {}) if method == "POST" else {}
                if b.get("ref"):
                    b["tpl"], b["sid"] = split_ref(str(b["ref"]))
                c = soul_chat.resolve(str(b.get("tpl") or q.get("tpl") or ""), str(b.get("sid") or q.get("sid") or ""))
                if method == "GET" and u.path == "/api/v1/chat/tick":
                    self._send_json(soul_tick.status(c))
                elif method == "POST" and u.path == "/api/v1/chat/tick/settings":
                    self._send_json(soul_tick.set_on(c, bool(b.get("on"))))
                elif method == "POST":
                    self._send_json(soul_tick.run(c, lang=b.get("lang"), catchup=bool(b.get("catchup"))))
                else:
                    self.send_error(405)
            elif method == "GET" and u.path == "/api/v1/chat/sticker":
                self._send_file(soul_chat.sticker_file(q.get("tpl", ""), q.get("sid", ""), q.get("id", "")))
            elif method == "POST" and u.path == "/api/v1/chat/send":
                b = self._read_json_body() or {}
                if b.get("ref"):
                    b["tpl"], b["sid"] = split_ref(str(b["ref"]))
                self._send_json(soul_chat.send(str(b.get("tpl") or ""), str(b.get("sid") or ""), kind=str(b.get("kind") or "text"),
                                               text=str(b.get("text") or ""), sticker=str(b.get("sticker") or ""), lang=b.get("lang"), rt=rt))
            elif method == "GET" and u.path == "/api/v1/chat/world_card":  # a world result a message carries (10-21)
                self._send_json(soul_chat.world_card(q.get("run", ""), q.get("id", "")))
            elif u.path == "/api/v1/chat/subscription":  # following a character · her owed turns (a plugin's, 10-21)
                b = (self._read_json_body() or {}) if method == "POST" else None
                if b and b.get("ref"):
                    b["tpl"], b["sid"] = split_ref(str(b["ref"]))
                src = b if b is not None else q
                self._send_json(soul_chat.subscription(str(src.get("tpl") or ""), str(src.get("sid") or ""), b, lang=src.get("lang")))
            elif method == "POST" and u.path == "/api/v1/chat/catchup":  # run her owed turns in order (a plugin's, 10-21)
                b = self._read_json_body() or {}
                if b.get("ref"):
                    b["tpl"], b["sid"] = split_ref(str(b["ref"]))
                self._send_json(soul_chat.catchup(str(b.get("tpl") or ""), str(b.get("sid") or ""), lang=b.get("lang"), rt=rt))
            elif method == "POST" and u.path == "/api/v1/chat/presence":  # the phone's heartbeat: online with her (10-19)
                b = self._read_json_body() or {}
                if b.get("ref"):
                    b["tpl"], b["sid"] = split_ref(str(b["ref"]))
                self._send_json(soul_chat.presence(str(b.get("tpl") or ""), str(b.get("sid") or ""), typing=bool(b.get("typing")),
                                                   lang=b.get("lang"), rt=rt))
            elif method == "POST" and u.path == "/api/v1/chat/answer":  # yes / no to a message that waits for one (10-18)
                b = self._read_json_body() or {}
                if b.get("ref"):
                    b["tpl"], b["sid"] = split_ref(str(b["ref"]))
                self._send_json(soul_chat.answer(str(b.get("tpl") or ""), str(b.get("sid") or ""), str(b.get("id") or ""),
                                                 str(b.get("answer") or "")))
            elif method == "POST" and u.path == "/api/v1/chat/greet":  # the first time: her opening line, written once (10-17)
                b = self._read_json_body() or {}
                if b.get("ref"):
                    b["tpl"], b["sid"] = split_ref(str(b["ref"]))
                self._send_json(soul_chat.greet(str(b.get("tpl") or ""), str(b.get("sid") or ""), lang=b.get("lang"), rt=rt))
            else:
                self.send_error(404)
        except soul_chat.ChatError as e:
            self._send_json({"error": str(e), **e.extra}, status=e.status)
        return True

    def _phone_bench_route(self, method: str, path: str) -> bool:
        """The phone orchestration on the local front-end desk (10-21, stage B; this machine only): GET
        /api/v1/phone/orchestration · POST …/orchestration {params} (only what differs from the default is kept; out of
        range = 400) · POST …/orchestration/lint {params} · POST …/orchestration/reset. A plugin answers
        (``phone_orch_bench``); none = 404."""
        from neonrp.core import node_kinds

        ops = {("GET", "/api/v1/phone/orchestration"): "get", ("POST", "/api/v1/phone/orchestration"): "save",
               ("POST", "/api/v1/phone/orchestration/lint"): "lint", ("POST", "/api/v1/phone/orchestration/reset"): "reset"}
        op = ops.get((method, path))
        if op is None:
            return False
        ip = str((self.client_address or ("",))[0])
        host = str(self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        if ip not in ("127.0.0.1", "::1", "::ffff:127.0.0.1") or host not in ("127.0.0.1", "localhost", "::1"):
            self._send_json({"error": "the phone orchestration is edited on this machine only"}, status=403)
            return True
        body = (self._read_json_body() or {}) if method == "POST" else None
        out = next((r for r in node_kinds.call_all("phone_orch_bench", op, body) if isinstance(r, dict)), None)
        if out is None:
            self._send_json({"error": "no phone orchestration on this engine"}, status=404)
        else:
            self._send_json(out, status=400 if out.get("ok") is False else 200)
        return True

    def _soul_bench_route(self, method: str, path: str, q: dict[str, str]) -> bool:
        import os

        from neonrp.core import soul_chat
        from neonrp.core import soul_orchestration as SO

        routes = ("/api/v1/souls/catalog", "/api/v1/souls/orchestration", "/api/v1/souls/orchestration/lint",
                  "/api/v1/souls/ambient", "/api/v1/souls/ambient/generate",
                  "/api/v1/souls/stickers", "/api/v1/souls/stickers/meta", "/api/v1/souls/stickers/remove", "/api/v1/souls/in_world")
        if path not in routes:
            return False
        if os.environ.get("WORLDLINES_PRODUCT") == "hub":  # the browser engine (Hub web): no bench (10-16: 编排台只在 Local)
            self._send_json({"error": "the orchestration bench is local only"}, status=404)
            return True
        try:
            if method == "GET" and path == "/api/v1/souls/catalog":
                self._send_json(SO.catalog(q.get("lang")))
            elif method == "GET" and path == "/api/v1/souls/orchestration":
                self._send_json(SO.bench(q.get("ref", ""), q.get("lang"), q.get("world")))
            elif method == "POST" and path == "/api/v1/souls/in_world":   # the in_world node: its variant in its world (the template's engine settings)
                b = self._read_json_body() or {}
                self._send_json(SO.set_in_world(str(b.get("ref") or ""), b.get("variant"), b.get("world")))
            elif method == "POST" and path == "/api/v1/souls/orchestration":
                b = self._read_json_body() or {}
                self._send_json(SO.save(str(b.get("ref") or ""), b.get("graph")))
            elif method == "POST" and path == "/api/v1/souls/orchestration/lint":
                b = self._read_json_body() or {}
                g = b.get("graph") if isinstance(b.get("graph"), dict) else {}
                self._send_json({"lint": SO.lint({**g, "subject": g.get("subject", SO.SUBJECT)})})
            elif path.startswith("/api/v1/souls/stickers"):  # the character's own stickers (S5): GET list · POST ?ref=&id= raw PNG · /meta · /remove
                if method == "GET":
                    self._send_json(SO.stickers(q.get("ref", "")))
                elif path == "/api/v1/souls/stickers":
                    length = int(self.headers.get("Content-Length") or 0)
                    if length > SO.STICKER_MAX:
                        raise ValueError("a sticker is a PNG up to 2 MB")
                    self._send_json(SO.sticker_put(q.get("ref", ""), q.get("id", ""), self.rfile.read(length)))
                else:
                    b = self._read_json_body() or {}
                    if path.endswith("/meta"):
                        self._send_json(SO.sticker_meta_set(str(b.get("ref") or ""), str(b.get("id") or ""), b.get("label"), b.get("when")))
                    else:
                        self._send_json(SO.sticker_remove(str(b.get("ref") or ""), str(b.get("id") or "")))
            elif path.startswith("/api/v1/souls/ambient"):
                from neonrp.core import soul_ambient as SA

                b = (self._read_json_body() or {}) if method == "POST" else {}
                c = soul_chat.resolve(*SO.split_ref(str(b.get("ref") or q.get("ref") or "")))
                lang = str(b.get("lang") or q.get("lang") or c["lang"])
                if method == "GET" and path == "/api/v1/souls/ambient":
                    w = SA.replicate(c, lang) if q.get("replicate") and c.get("t") is not None else SA.read(c, lang)
                    self._send_json({"world": w, "layers": [{"scope": k, "path": str(p), "exists": p.is_file()} for k, p in SA.sources(c)],
                                     "can_replicate": c.get("t") is not None})
                elif method == "POST" and path == "/api/v1/souls/ambient":
                    self._send_json(SA.save(c, b.get("world")))
                elif method == "POST" and path == "/api/v1/souls/ambient/generate":
                    self._send_json({"world": SA.generate(c, lang)})
                else:
                    self.send_error(405)
            else:
                self.send_error(405)
        except soul_chat.ChatError as e:
            self._send_json({"error": str(e), **e.extra}, status=e.status)
        except PermissionError as e:
            self._send_json({"error": str(e)}, status=403)
        except ValueError as e:
            self._send_json({"error": str(e)}, status=400)
        return True

    def _replay_route(self, rt: "WebRuntime | None", method: str) -> bool:
        """Replays kept on this machine (core/replay_library, 10-18): GET /api/v1/local/replays?world=<template id> ·
        POST /api/v1/local/replays {session_id?} (export a run; the bound one without an id) · GET /replays/<id>
        (the worldlines.replay/1 document) · GET /replays/<id>/cover · /replays/<id>/file?path=assets/… ·
        POST /replays/<id>/share {text?, lang?} ·
        DELETE /replays/<id>."""
        from urllib.parse import parse_qs, quote, urlparse

        u = urlparse(self.path)
        base = "/api/v1/local/replays"
        if u.path != base and not u.path.startswith(base + "/"):
            return False
        from neonrp.core import replay_library as RL
        from neonrp.core import replay_share

        q = {k: v[0] for k, v in parse_qs(u.query).items() if v}
        parts = [web._path_seg(x) for x in u.path[len(base):].strip("/").split("/") if x]
        with_cover = lambda e: {**e, "cover_url": f"{base}/{quote(e['id'])}/cover" if e.get("has_cover") else None}  # noqa: E731
        try:
            if method == "GET" and not parts:
                self._send_json({"replays": [with_cover(e) for e in RL.list_replays(q.get("world") or None, q.get("lang") or "")]})
            elif method == "POST" and not parts:
                from neonrp.worlds import PLAYS_HOME

                b = self._read_json_body() or {}
                sid = str(b.get("session_id") or "")
                if sid and not web._safe_name(sid):
                    raise RL.ReplayLibraryError(400, "bad_session_id")
                run = PLAYS_HOME / sid if sid else (rt.root if rt is not None else None)
                if run is None:
                    raise RL.ReplayLibraryError(404, "no_such_run", "no session_id and no run bound")
                self._send_json(with_cover(RL.export(run, lang=str(b.get("lang") or q.get("lang") or ""))))
            elif method == "GET" and len(parts) == 1:
                doc = RL.get(parts[0])
                self._send_json({**doc, "local": with_cover(doc["local"])})
            elif method == "GET" and len(parts) == 2 and parts[1] == "cover":
                self._send_file(RL.cover(parts[0]))
            elif method == "GET" and len(parts) == 2 and parts[1] == "file":   # a picture the player shows (assets/…)
                self._send_file(RL.file(parts[0], q.get("path") or ""), cache="private, max-age=3600")
            elif method == "POST" and len(parts) == 2 and parts[1] == "share":
                b = self._read_json_body() or {}
                self._send_json(RL.share(parts[0], text=str(b.get("text") or ""), lang=b.get("lang")))
            elif method == "DELETE" and len(parts) == 1:
                RL.delete(parts[0])
                self._send_json({"ok": True})
            else:
                self.send_error(404)
        except RL.ReplayLibraryError as e:
            self._send_json(e.to_dict(), status=e.status)
        except replay_share.ShareError as e:
            self._send_json(e.to_dict(), status=e.status)
        return True

    def _avatar_route(self, method: str) -> bool:
        """The player's 分身 for Hub「我的」(10-15, players.py): GET/POST /api/v1/local/avatar · /avatar/current ·
        /avatar/portrait?file= (GET the image; POST the raw png / jpg / webp bytes)."""
        from urllib.parse import parse_qs, urlparse

        u = urlparse(self.path)
        if not u.path.startswith("/api/v1/local/avatar"):
            return False
        from neonrp import players

        q = {k: v[0] for k, v in parse_qs(u.query).items() if v}
        if method == "GET" and u.path == "/api/v1/local/avatar":
            # ?tpl=<id>: also the builder screen's draft prefilled from the current 分身 (players.builder_prefill)
            cur = players.current_avatar()
            rows = [{k: v for k, v in a.items() if k != "path"} for a in players.list_avatars()]
            out: dict[str, Any] = {"current": cur, "avatar": next((a for a in rows if a["file"] == cur), None), "avatars": rows}
            if q.get("tpl"):
                from neonrp import template as TP

                found = TP.discover().get(q["tpl"])
                out["prefill"] = players.builder_prefill(TP.load(found), cur or "") if found and cur else {"fields": {}}
            self._send_json(out)
        elif method == "GET" and u.path == "/api/v1/local/avatar/portrait":
            self._send_file(players.portrait_path(q.get("file", "")))
        elif method in ("POST", "PUT") and u.path == "/api/v1/local/avatar":
            b = self._read_json_body() or {}
            try:
                path = players.save_avatar_fields(b, str(b.get("file") or "") or None)
            except ValueError as e:
                self._send_json({"ok": False, "error": str(e)}, status=400)
                return True
            self._send_json({"ok": True, "file": path.stem})
        elif method == "POST" and u.path == "/api/v1/local/avatar/current":
            b = self._read_json_body() or {}
            ok = players.set_current_avatar(str(b.get("file") or ""))
            self._send_json({"ok": ok, "current": players.current_avatar()}, status=200 if ok else 404)
        elif method == "POST" and u.path == "/api/v1/local/avatar/portrait":
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length <= 0 or length > 20_000_000:
                self.send_error(400, "missing or oversized body")
                return True
            p = players.save_portrait(q.get("file", ""), self.rfile.read(length))
            if p is None:
                self._send_json({"ok": False, "error": "no such avatar, or not a png / jpg / webp"}, status=400)
            else:
                self._send_json({"ok": True, "portrait_url": players.portrait_url(p.name.split(".portrait")[0])})
        else:
            self.send_error(404)
        return True

    # 10-21 (web-create · iOS creation desk): a page with no token of its own (the app, the local Hub) asks the engine, which
    # holds the Worldlines session, to call the platform's ai for it. Only the creation desk's picture service goes through:
    # this is not a general proxy.
    AI_PROXY = ("create/art",)
    AI_PROXY_MAX = 16 * 1024   # a request body (the platform takes 8 KB)

    def _ai_proxy_route(self, method: str) -> bool:
        """GET / POST /api/v1/local/ai/create/art[?…] → ``<WORLDLINES_API_BASE>/create/art[?…]`` with the engine's session
        (the page's Authorization is ignored). 401 not_signed_in when the engine is signed out; the platform's status and
        JSON pass through as they are (402 with billing_url included — the page decides whether to show it)."""
        import json as _json
        import urllib.error
        import urllib.request
        from urllib.parse import urlparse

        u = urlparse(self.path)
        pre = "/api/v1/local/ai/"
        if not u.path.startswith(pre) or u.path[len(pre):].rstrip("/") not in self.AI_PROXY:
            return False
        from neonrp.core import worldlines_auth

        origin = self.headers.get("Origin") or ""
        if origin and not origin.startswith(("http://localhost", "http://127.0.0.1")):   # it spends the player's credits: our own pages only
            self._send_json({"error": {"code": "forbidden_origin"}}, status=403)
            return True
        tok = worldlines_auth.access_token()
        if not tok or tok == "-":
            self._send_json({"error": {"code": "not_signed_in", "message": "sign in to Worldlines first"}}, status=401)
            return True
        data = None
        if method == "POST":
            n = int(self.headers.get("Content-Length") or 0)
            if n > self.AI_PROXY_MAX:
                self._send_json({"error": {"code": "too_large"}}, status=413)
                return True
            data = self.rfile.read(n) if n else b"{}"
        url = f"{worldlines_auth.API_BASE.rstrip('/')}/{u.path[len(pre):].rstrip('/')}" + (f"?{u.query}" if u.query else "")
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {tok}", "Content-Type": "application/json", **worldlines_auth.headers()})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:   # a picture takes 20–60 s
                status, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read() or b"{}"
        except (urllib.error.URLError, OSError) as e:
            self._send_json({"error": {"code": "unreachable", "message": str(e)[:200]}}, status=502)
            return True
        try:
            body = _json.loads(raw or b"{}")
        except ValueError:
            body = {"error": {"code": "platform_error"}}
        self._send_json(body if isinstance(body, dict) else {"data": body}, status=status)
        return True

    def _hub_route(self, method: str) -> bool:
        """The Hub's free zone + the Worldlines account (core/template_publish, 10-16):
            GET  /api/v1/local/hub/open           the free zone's works (no credential; client=local) — rows + cover_url
            GET  /api/v1/local/hub/cover?id=      a work's published cover (kept per revision)
            GET  /api/v1/local/hub/mine?lang=     the signed-in author's works (status · zone · review note · takedown)
            POST /api/v1/local/hub/fetch {id}     download a public work and install it as a local template
            POST /api/v1/local/hub/report {id, reason} · /unpublish {id} · /submit {id} · /withdraw {id}   (lang? in every body)
            GET  /api/v1/local/hub/official?lang=  the default zone for a signed-in player (10-17): {signed_in, works: [row +
                                                  official · version · installed {where, version, revision} · update · cover_url]}
            POST /api/v1/local/hub/official/fetch {id}   get / update a default-zone world into the official cache
            GET  /api/v1/local/hub/remote         the online Hub's catalog (no credential): {base, templates}; its worlds play there
            GET  /api/v1/local/account            {signed_in, login: idle|running|error|cancelled, login_url?, login_error?, login_code?}
            POST /api/v1/local/account/login      sign in through the browser (the TUI's /login), in the background
            POST /api/v1/local/account/login/cancel · /logout   stop waiting for that sign-in · sign out (the revoke runs behind)
            GET  /api/v1/local/account/run-points  {signed_in, runs, rewards} — billing's word on this account's run points (core/run_points)
            POST /api/v1/local/account/rewards/<id>/claim   claim a claimable one (billing's free-claim caps apply)"""
        from urllib.parse import parse_qs, urlparse

        u = urlparse(self.path)
        path, q = u.path.rstrip("/"), parse_qs(u.query)
        one = lambda k: (q.get(k) or [""])[0]  # noqa: E731
        if path == "/api/v1/local/account" and method == "GET":
            from neonrp.core import worldlines_auth

            st, tok = worldlines_auth.status(), worldlines_auth.access_token()
            self._send_json({"signed_in": bool(tok and tok != "-"), "source": st["source"], "login": _LOGIN["state"], "login_timeout_s": LOGIN_TIMEOUT_S,
                             **({"login_error": _LOGIN["error"], "login_code": _LOGIN["code"]} if _LOGIN["error"] else {}),
                             **({"login_url": _LOGIN["url"]} if _LOGIN["url"] and _LOGIN["state"] == "running" else {})})
            return True
        if path == "/api/v1/local/account/login" and method == "POST":
            _start_login()
            self._send_json({"login": _LOGIN["state"], "login_timeout_s": LOGIN_TIMEOUT_S})
            return True
        if path == "/api/v1/local/account/login/cancel" and method == "POST":
            _cancel_login()
            self._send_json({"login": _LOGIN["state"]})
            return True
        if path == "/api/v1/local/account/logout" and method == "POST":
            from neonrp.core import worldlines_auth

            _cancel_login()
            worldlines_auth.disconnect(background=True)  # the file goes now; the revoke does not hold up the page
            tok = worldlines_auth.access_token()
            self._send_json({"signed_in": bool(tok and tok != "-"), "source": worldlines_auth.status()["source"], "login": _LOGIN["state"]})
            return True
        if path == "/api/v1/local/account/run-points" and method == "GET":  # 「我的」: what billing made of the run points (10-21)
            from neonrp.core import run_points

            self._send_json(run_points.mine())
            return True
        if path.startswith("/api/v1/local/account/rewards/") and path.endswith("/claim") and method == "POST":
            from neonrp.core import run_points

            st, body = run_points.claim(path.split("/")[-2], self.headers.get("X-Worldlines-Device"))
            self._send_json(body, status=st or 502)
            return True
        if not path.startswith("/api/v1/local/hub/"):
            return False
        from neonrp.core import template_publish as _tp

        sub = path[len("/api/v1/local/hub/"):]
        try:
            if method == "GET" and sub == "open":
                works = _tp.open_works(client="local", lang=one("lang") or None)
                from neonrp import template as TP

                have = {tid: d for tid, d in TP.discover().items()}
                for w in works:
                    w["cover_url"] = f"/api/v1/local/hub/cover?id={w['id']}&rev={w.get('published_revision') or ''}" if w["meta"].get("cover") else None
                    w["local"] = w["id"] if w["id"] in have else None
                self._send_json({"works": works})
            elif method == "GET" and sub == "official":
                d = _tp.official_works(lang=one("lang") or None)
                for w in d["works"]:
                    w["cover_url"] = f"/api/v1/local/hub/cover?id={w['id']}&rev={w.get('published_revision') or ''}" if w["meta"].get("cover") else None
                self._send_json(d)
            elif method == "GET" and sub == "remote":   # the online Hub's list, signed in or not (10-24)
                self._send_json(_tp.remote_catalog())
            elif method == "POST" and sub == "official/fetch":
                b = self._read_json_body() or {}
                self._send_json(_tp.fetch_official(str(b.get("id") or ""), lang=(str(b.get("lang") or "") or None)))
            elif method == "GET" and sub == "cover":
                got = _tp.cover(one("id"))
                if got is None:
                    self.send_error(404)
                else:
                    data, ct = got
                    self.send_response(200)
                    self.send_header("Content-Type", ct)
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "max-age=86400" if one("rev") else "max-age=300")
                    self._cors_headers()
                    self.end_headers()
                    self.wfile.write(data)
            elif method == "GET" and sub == "mine":
                self._send_json({"works": _tp.mine(lang=one("lang") or None)})
            elif method == "GET" and sub == "blocks":   # the authors I blocked (by a work of theirs)
                self._send_json({"blocks": _tp.blocks(lang=one("lang") or None)})
            elif method == "POST" and sub in ("fetch", "report", "unpublish", "submit", "withdraw", "block", "unblock"):
                b = self._read_json_body() or {}
                wid, lang = str(b.get("id") or ""), (str(b.get("lang") or "") or None)
                if sub == "fetch":
                    self._send_json(_tp.fetch(wid, lang=lang))
                elif sub == "report":
                    self._send_json(_tp.report(wid, str(b.get("reason") or ""), lang=lang))
                else:
                    self._send_json({"unpublish": _tp.unpublish, "withdraw": _tp.withdraw, "block": _tp.block, "unblock": _tp.unblock}.get(sub, _tp.submit)(wid, lang=lang))
            else:
                return False
        except _tp.PublishError as e:
            self._send_json(e.to_dict(), status=e.status)
        return True

    def _launcher_route_get(self, rt: "WebRuntime | None") -> bool:
        if self._chat_route(rt, "GET") or self._avatar_route("GET") or self._replay_route(rt, "GET"):
            return True
        if self._ai_proxy_route("GET"):
            return True
        if self._hub_route("GET"):
            return True
        if self.path.split("?", 1)[0] == "/api/v1/local/plays":  # Hub「我的」继续世界 (10-15)
            from urllib.parse import parse_qs, urlparse

            q = parse_qs(urlparse(self.path).query)
            self._send_json(web._local_plays(rt.root if rt is not None else None, (q.get("lang") or [""])[0] or self._locale(rt),
                                             every=(q.get("all") or [""])[0] == "1"))
            return True
        if self._spec_route_get():
            return True
        if self.path.startswith("/api/v1/local"):
            if self.path == "/api/v1/local/worlds":
                self._send_json(web._library_worlds(self._locale(rt)))
                return True
            if self.path.startswith("/api/v1/local/worlds/") and self.path.endswith("/cover"):
                world_id = web._path_seg(self.path[len("/api/v1/local/worlds/"):-len("/cover")])
                if not web._safe_name(world_id):
                    self.send_error(400)
                    return True
                data = web._world_cover_bytes(world_id)
                if data is None:
                    self.send_error(404)
                    return True
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "max-age=300")
                self._cors_headers()
                self.end_headers()
                self.wfile.write(data)
                return True
            # GET /api/v1/local/worlds/<id>/export — zip the OWNED library
            # source and stream it as a download(对齐 CLI export-world --world)。
            if self.path.startswith("/api/v1/local/worlds/") and self.path.endswith("/export"):
                world_id = web._path_seg(self.path[len("/api/v1/local/worlds/"):-len("/export")])
                if not web._safe_name(world_id):
                    self.send_error(400)
                    return True
                from neonrp.worlds import get_owned_world_dir

                source = get_owned_world_dir(world_id)
                if source is None:
                    self.send_error(404, "not an owned world")
                    return True
                import tempfile

                from neonrp.core.world_export import export_world as core_export

                with tempfile.TemporaryDirectory() as td:
                    try:
                        final = core_export(
                            source, Path(td) / f"{world_id}.zip", include_logs=False
                        )
                        data = final.read_bytes()
                    except (FileNotFoundError, ValueError) as exc:
                        self._send_json({"error": str(exc)}, status=400)
                        return True
                from urllib.parse import quote as _q

                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Length", str(len(data)))
                self.send_header(
                    "Content-Disposition",
                    f"attachment; filename*=UTF-8''{_q(world_id)}.zip",
                )
                self._cors_headers()
                self.end_headers()
                self.wfile.write(data)
                return True
            # GET /api/v1/local/{templates|souls}/<id>/export — 引擎里改好的东西打成包带走(template/package.py)
            for _pre, _kind in (("/api/v1/local/templates/", "template"), ("/api/v1/local/souls/", "soul")):
                if self.path.split("?")[0].startswith(_pre) and self.path.split("?")[0].endswith("/export"):
                    from urllib.parse import quote as _q

                    from neonrp.template import TemplateError
                    from neonrp.template import package as _pkg

                    name = web._path_seg(self.path.split("?")[0][len(_pre):-len("/export")])
                    if not web._safe_name(name):
                        self.send_error(400)
                        return True
                    try:
                        data = _pkg.export_template(name) if _kind == "template" else _pkg.export_soul(name)
                    except _pkg.ExportRefused:   # 10-16:默认区(含官方世界)不导出,只给自由区作品
                        from urllib.parse import parse_qs as _pq

                        from neonrp.core.template_publish import _msg

                        lang = ((_pq(self.path.partition("?")[2]).get("lang") or [""])[0]) or self._locale(rt)
                        self._send_json({"ok": False, "error": "default_zone", "message": _msg("export_default_zone", lang)}, status=403)
                        return True
                    except (TemplateError, TypeError) as exc:
                        self._send_json({"ok": False, "error": str(exc)[:300]}, status=404)
                        return True
                    self.send_response(200)
                    self.send_header("Content-Type", "application/zip")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{_q(name)}.{_kind}.zip")
                    self._cors_headers()
                    self.end_headers()
                    self.wfile.write(data)
                    return True
            if self.path.startswith("/api/v1/local/souls/") and self.path.endswith("/bindings"):
                # 角色库独立,世界里只放 link —— 这个角色被哪些模板链接了(角色页「在哪些世界里」)
                dir_name = web._path_seg(self.path[len("/api/v1/local/souls/"):-len("/bindings")])
                if not web._safe_name(dir_name):
                    self.send_error(400)
                    return True
                from neonrp import template as _tp

                self._send_json({"soul": dir_name, "bindings": _tp.bindings_of(dir_name)})
                return True
            if self.path.startswith("/api/v1/local/souls/") and self.path.endswith("/portrait"):
                dir_name = web._path_seg(self.path[len("/api/v1/local/souls/"):-len("/portrait")])
                if not web._safe_name(dir_name):
                    self.send_error(400)
                    return True
                from neonrp.core.souls import SOUL_HOME

                img = SOUL_HOME / dir_name / "assets" / "portrait.png"
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
            if self.path == "/api/v1/local/souls":
                from neonrp.core.souls import list_souls
                from neonrp.players import list_avatars

                try:
                    avatars = list_avatars()
                except Exception:  # noqa: BLE001 — avatars are optional extras
                    avatars = []
                self._send_json(
                    {"souls": list_souls(locale=self._locale(rt)), "avatars": avatars}
                )
                return True
            if self.path.split("?", 1)[0] == "/api/v1/local/player-data":  # 10-15: characters · endings · achievements
                from urllib.parse import parse_qs, urlparse

                from neonrp.core import player_data

                q = parse_qs(urlparse(self.path).query)
                pid = (q.get("player") or [""])[0]
                d = player_data.read("".join(c for c in pid if c.isalnum() or c in "-_.") or None)
                # 「我的」页(10-15):each achievement with its face in the asked language (core/achievements.describe)
                from neonrp.core import achievements

                lang = (q.get("lang") or [""])[0] or self._locale(rt)
                d["achievements"] = [{**a, **(achievements.describe(str(a.get("id") or ""), str(a.get("world") or ""), lang) or {})}
                                     for a in d["achievements"]]
                # 收集区(10-18):cards in the asked language + whether the author shipped a new version (core/rewards)
                if pid in ("", player_data.player_id()):
                    from neonrp.core import collection_sync, rewards

                    d.update(rewards.listing(lang))
                    collection_sync.maybe_pull()  # signed in: the account's collection comes down (10-18)
                    d["sync"] = {k: v for k, v in collection_sync.state().items() if k != "t"}
                self._send_json(d)
                return True
            if self._soul_update_route("GET"):
                return True
            if self.path.split("?", 1)[0] == "/api/v1/local/player-data/card":  # a kept card's picture (core/rewards)
                from urllib.parse import parse_qs, urlparse

                from neonrp.core import player_data, rewards

                q = parse_qs(urlparse(self.path).query)
                world, cid = (q.get("world") or [""])[0], (q.get("id") or [""])[0]
                rec = next((c for c in player_data.read()["cards"] if c.get("world") == world and c.get("id") == cid), None)
                d = rewards.card_dir(world).resolve()
                f = (d / str(rec["image"])).resolve() if rec and rec.get("image") else None
                self._send_file(f if f is not None and f.is_file() and f.is_relative_to(d) else None, cache="private, max-age=300")
                return True
            if self.path == "/api/v1/local/settings":
                from neonrp.presets import get_create_provider, list_presets

                try:
                    create_provider = get_create_provider()
                except Exception:  # noqa: BLE001
                    create_provider = None
                # 图像生成配置(TUI 设置「图像」的 web 版)— 只回可展示字段,
                # openai_key 永不回传(只写)。
                image: dict[str, Any] = {}
                try:
                    from neonrp.core.imagegen import load_image_config

                    icfg = load_image_config()
                    image = {
                        "backend": icfg.backend,
                        "comfyui_url": icfg.comfyui_url,
                        "comfyui_ckpt": icfg.comfyui_ckpt,
                        "comfyui_workflow": icfg.comfyui_workflow,
                        "comfyui_input_node": icfg.comfyui_input_node,
                        "comfyui_neg_node": icfg.comfyui_neg_node,
                        "comfyui_output_node": icfg.comfyui_output_node,
                        "comfyui_seed_node": icfg.comfyui_seed_node,
                        "openai_model": icfg.openai_model,
                        "openai_key_set": bool(icfg.openai_key),
                        "configured": icfg.is_configured,
                    }
                except Exception:  # noqa: BLE001 — image config is optional
                    pass
                self._send_json(
                    {
                        "presets": list_presets(),
                        "create_provider": create_provider,
                        "image": image,
                    }
                )
                return True
            self.send_error(404)
            return True
        # ── LocalShell SPA (docs/WEBUI-UNIFICATION.md §7.5 LP1) ──
        # The assembled shell build (env dir or packaged copy — see
        # _spa_root) is served same-origin: /local/* is the SPA (history
        # fallback → index.html), /assets/* its hashed vite bundles, plus the
        # build's other top-level files (vite.svg…). No shell resolved
        # → /local 404s with a hint and everything else behaves as before.
        spa = web._spa_root()
        _local = self.path.split("?", 1)[0]  # /local?tpl=… is the same page (the UI reads the query)
        if _local == "/local" or _local.startswith("/local/"):
            if spa is None:
                self.send_error(
                    404,
                    "no web shell found - install the WorldLines shell and "
                    "point NEONRP_SPA_DIR at its SPA dist directory "
                    "(https://github.com/LudicDynamics/WorldLines)",
                )
                return True
            self._serve_spa_file(spa, "index.html")
            return True
        if spa is not None and self.path.startswith("/assets/"):
            rel = self._spa_rel(self.path)
            if rel is None:
                self.send_error(400)
                return True
            self._serve_spa_file(spa, rel)
            return True
        if spa is not None:
            # Other top-level build files (vite.svg, favicon…). Single plain
            # component with an extension only — never shadows the app routes
            # ("/", /state, /events…) or the vanilla page's /index.html.
            top = self._spa_rel(self.path)
            if (
                top and "/" not in top and "." in top
                and top != "index.html" and spa.joinpath(top).is_file()
            ):
                self._serve_spa_file(spa, top)
                return True
        # Launcher mode (no session yet): the engine is API-only until the
        # LocalShell (or any client) binds a session. The old vanilla
        # /launcher page is deleted — /local owns launching now; the root
        # serves a minimal status page pointing there (or, when the SPA build
        # is packaged, redirects straight into it).
        if rt is None:
            if self.path in ("/", "/index.html", "/launcher"):
                if spa is not None:
                    self.send_response(302)
                    self.send_header("Location", "/local")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return True
                body = (
                    "<!doctype html><meta charset='utf-8'>"
                    "<title>WorldLines · local engine</title>"
                    "<body style='background:#0A0A0A;color:#9A9AA0;"
                    "font:14px/1.8 -apple-system,PingFang SC,sans-serif;"
                    "display:grid;place-items:center;min-height:96vh'><div>"
                    "<p style='color:#F5F5F7'>● WorldLines 本地引擎在跑,"
                    "还没有绑定世界。</p>"
                    "<p>入口:<b style='color:#34E879'>/local</b>"
                    "(UI: <code>cd worldlines/ui &amp;&amp; npm run build</code>, then NEONRP_SPA_DIR=worldlines/ui/dist-local)</p>"
                    "<p style='font-size:12px'>API 契约就绪:/api/v1/meta · "
                    "/api/v1/play/* · /api/v1/create/* · /api/v1/local/*</p>"
                    "</div></body>"
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return True
            self.send_error(409, "no active session - bind one via /api/v1/play/session")
            return True
        # Session bound: root belongs to the WorldLines shell. Redirect into
        # /local (the shell serves it, or 404s with a "install the shell" hint
        # when no SPA is resolved). The old vanilla `_page_html` page is gone.
        if self.path in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/local")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True
        return False

    def _soul_update_route(self, method: str) -> bool:
        """A taken character's update from its author (core/soul_update, 10-20):
            GET  /api/v1/local/player-data/souls/<world>/<sid>/update[?lang=]   the diff
            POST /api/v1/local/player-data/souls/<world>/<sid>/update {token, choices | all}
            GET  /api/v1/local/player-data/souls/<world>/<sid>/updates          the saved decisions
            GET  /api/v1/local/player-data/souls/<world>/<sid>/file?side=mine|theirs&f=<rel>   a file of either side"""
        from urllib.parse import parse_qs, urlparse

        base = "/api/v1/local/player-data/souls/"
        u = urlparse(self.path)
        if not u.path.startswith(base):
            return False
        parts = [web._path_seg(x) for x in u.path[len(base):].strip("/").split("/") if x]
        if len(parts) != 3 or not all(web._safe_name(x) for x in parts[:2]) or parts[2] not in ("update", "updates", "file"):
            self._send_json({"error": "not_found"}, status=404)
            return True
        world, sid, what = parts
        from neonrp.core import soul_update

        q = parse_qs(u.query)
        try:
            if method == "GET" and what == "update":
                self._send_json(soul_update.diff(world, sid, (q.get("lang") or ["zh"])[0]))
            elif method == "GET" and what == "updates":
                self._send_json({"updates": soul_update.updates(world, sid)})
            elif method == "GET" and what == "file":
                f = soul_update.side_file(world, sid, (q.get("side") or ["mine"])[0], (q.get("f") or [""])[0])
                self._send_file(f, cache="private, max-age=60")
            elif method == "POST" and what == "update":
                b = self._read_json_body() or {}
                ch = b.get("choices") if isinstance(b.get("choices"), dict) else None
                self._send_json(soul_update.apply(world, sid, token=b.get("token"), choices=ch, all_=b.get("all"),
                                                  lang=str(b.get("lang") or "zh")))
            else:
                self._send_json({"error": "method_not_allowed"}, status=405)
        except soul_update.UpdateError as e:
            self._send_json({"error": e.code, "message": str(e)}, status=e.status)
        return True

    def _launcher_route_post(self, rt: "WebRuntime | None") -> bool:
        if self._chat_route(rt, "POST") or self._avatar_route("POST") or self._replay_route(rt, "POST"):
            return True
        if self._ai_proxy_route("POST"):
            return True
        if self._hub_route("POST"):
            return True
        if self._soul_update_route("POST"):
            return True
        if self.path == "/api/v1/local/player-data/sync":  # 收集库 ↔ Worldlines 账号, now (core/collection_sync, 10-18)
            from neonrp.core import collection_sync

            self._send_json({k: v for k, v in collection_sync.sync().items() if k != "t"})
            return True
        if self.path == "/api/v1/local/player-data/refresh":  # 收集区:pull the author's new version (core/rewards, 10-18)
            from neonrp.core import rewards

            b = self._read_json_body() or {}
            kind, world = str(b.get("kind") or ""), str(b.get("world") or "")
            cid = str(b.get("id") or b.get("sid") or "")
            if not world or not cid:
                self._send_json({"ok": False, "error": "bad_request"}, status=400)
                return True
            r = rewards.refresh(kind, world, cid)
            self._send_json(r, status=200 if r.get("ok") else (400 if r.get("error") == "bad_kind" else 404))
            return True
        if self.path == "/api/v1/local/replay/share":  # share a run's replay to the platform + SNS (core/replay_share, 10-15)
            from neonrp.core import replay_share
            from neonrp.worlds import PLAYS_HOME

            b = self._read_json_body() or {}
            sid = str(b.get("session_id") or "")
            if sid and not web._safe_name(sid):
                self._send_json({"error": "bad_session_id"}, status=400)
                return True
            run = PLAYS_HOME / sid if sid else (rt.root if rt is not None else None)
            try:
                if run is None:
                    raise replay_share.ShareError(404, "no_such_run", "no session_id and no run bound")
                self._send_json(replay_share.share(run, text=str(b.get("text") or ""), lang=b.get("lang")))
            except replay_share.ShareError as e:
                self._send_json(e.to_dict(), status=e.status)
            return True
        if self.path.startswith("/api/v1/local/souls/") and self.path.endswith("/portrait"):
            dir_name = web._path_seg(self.path[len("/api/v1/local/souls/"):-len("/portrait")])
            if not web._safe_name(dir_name):
                self.send_error(400)
                return True
            from neonrp.core.souls import SOUL_HOME

            sdir = SOUL_HOME / dir_name
            if not (sdir / "soul.json").exists():
                self.send_error(404)
                return True
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length <= 0 or length > 20_000_000:
                self.send_error(400, "missing or oversized body")
                return True
            data = self.rfile.read(length)
            final = sdir / "assets" / "portrait.png"
            final.parent.mkdir(parents=True, exist_ok=True)
            final.write_bytes(data)
            self._send_json({"ok": True})
            return True
        if self.path == "/api/v1/local/settings/test":
            body = self._read_json_body() or {}
            preset_id = str(body.get("preset_id") or "").strip()
            if not preset_id:
                self.send_error(400)
                return True
            from neonrp.presets import test_preset

            try:
                self._send_json(test_preset(preset_id))
            except Exception as exc:  # noqa: BLE001 — clean HTTP error
                self.send_error(400, str(exc)[:120])
            return True
        # POST /api/v1/local/settings/test-all — 逐个测所有可用 preset
        # (TUI settings「测试全部」;串行,每个短超时)。
        if self.path == "/api/v1/local/settings/test-all":
            from neonrp.presets import list_presets, test_preset

            results = []
            for p in list_presets():
                if not p.get("available"):
                    continue
                try:
                    r = test_preset(str(p["id"]), timeout=4.0)
                except Exception as exc:  # noqa: BLE001
                    r = {"ok": False, "error": str(exc)[:120]}
                results.append({"id": p["id"], **r})
            self._send_json({"results": results})
            return True
        if self.path.startswith("/api/v1/local/import/"):
            self._post_local_import()
            return True
        # POST /api/v1/local/souls/blank {name, intro?} — 角色库里从零新建一个角色(本地工作台「＋ 新建角色」):
        # 不调模型,只有 soul.json + soul.md 骨架;写人设交给编辑 / 创作 agent。建完可 link 进世界(templates/<id>/souls/link)
        if self.path == "/api/v1/local/souls/blank":
            body = self._read_json_body() or {}
            name = str(body.get("name") or "").strip()[:40]
            if not name:
                self._send_json({"ok": False, "error": "missing name"}, status=400)
                return True
            from neonrp.core.importers.sillytavern import name_to_id, resolve_id_conflict
            from neonrp.core.souls import SoulSource, create_soul_dir, list_souls, read_soul_json, write_soul_json

            existing = {str(s.get("sid")) for s in list_souls() if s.get("sid")}
            sid = resolve_id_conflict(name_to_id(name), existing)
            ascii_name = name.isascii()
            try:
                soul_dir = create_soul_dir(sid, name=name if ascii_name else sid, name_local="" if ascii_name else name,
                                           source=SoulSource(kind="local-create"))
                lang, intro = str(body.get("lang") or "zh"), str(body.get("intro") or "").strip()[:400]
                meta = read_soul_json(soul_dir)
                if meta is not None:
                    meta.source_lang = lang
                    if intro:
                        meta.summary_i18n = {lang: intro}
                    write_soul_json(soul_dir, meta)
            except (OSError, ValueError) as exc:
                self._send_json({"ok": False, "error": str(exc)[:300]}, status=400)
                return True
            self._send_json({"ok": True, "soul_dir": soul_dir.name, "sid": sid, "name": name})
            return True
        # POST /api/v1/local/souls {name, seed, preset?} — 创作角色(B1):
        # 名 + 一句话种子 → soul-authoring skill 一次生成完整 soul 进库
        # (与酒馆卡导入同一条 scaffold_soul 管线;TUI SoulSeedScreen 的 web 版)。
        if self.path == "/api/v1/local/souls":
            body = self._read_json_body() or {}
            name = str(body.get("name") or "").strip()
            seed = str(body.get("seed") or "").strip()
            if not name:
                self.send_error(400, "missing name")
                return True
            preset = web._resolve_creation_preset(str(body.get("preset") or "").strip())
            if not preset:
                self._send_json(
                    {"ok": False, "error": "no usable LLM - add an API key in Library settings"},
                    status=400,
                )
                return True
            try:
                from importlib import resources as _res

                from neonrp.core.config import _parse_config, resolve_provider
                from neonrp.core.llm import get_adapter_from_config
                from neonrp.core.soul_authoring import scaffold_soul
                from neonrp.core.importers.sillytavern import (
                    name_to_id,
                    resolve_id_conflict,
                )
                from neonrp.core.souls import SoulSource, create_soul_dir, list_souls
                from neonrp.presets import build_config_dict

                llm = get_adapter_from_config(
                    resolve_provider(_parse_config(build_config_dict(preset)))
                )
                existing = {s.get("sid") for s in list_souls()}
                existing.discard(None)
                sid = resolve_id_conflict(name_to_id(name), existing)
                soul_dir = create_soul_dir(
                    sid, name=name, tags=[], source=SoulSource(kind="local-create")
                )
                try:
                    skill_body = (
                        _res.files("neonrp.builtin_skills")
                        .joinpath("soul-authoring/SKILL.md")
                        .read_text(encoding="utf-8")
                    )
                except OSError:
                    skill_body = ""
                scaffold_soul(
                    soul_dir,
                    description=seed or name,
                    sid=sid,
                    agent_template="heroine-classic",
                    llm=llm,
                    skill_body=skill_body,
                )
            except ValueError as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
                return True
            except Exception as exc:  # noqa: BLE001 — LLM/network failures
                self._send_json({"ok": False, "error": f"authoring failed: {exc}"}, status=502)
                return True
            self._send_json({"ok": True, "soul_dir": soul_dir.name, "sid": sid})
            return True
        # POST /api/v1/local/hub/download {kind, query} — 从 Hub registry 拉
        # 世界/soul 进本地库(CLI `world|soul download` 的 web 版)。hosted
        # 沙盒经此把目录条目物化进账户家目录:soul → Soul Talk 原生开聊,
        # world → 非内置世界可玩(HUB-GOLIVE §P5 上传线的另一半)。registry
        # 基址随 WORLDHUB_REGISTRY_BASE(隔离栈指本地 registry)。
        if self.path == "/api/v1/local/hub/download":
            body = self._read_json_body() or {}
            kind = "souls" if str(body.get("kind") or "worlds") == "souls" else "worlds"
            query = str(body.get("query") or "").strip()
            if not query:
                self.send_error(400, "missing query")
                return True
            try:
                from neonrp.core.worldhub import WorldHubError, download

                target = download(query, kind=kind)
            except WorldHubError as exc:
                self._send_json({"ok": False, "error": str(exc)[:200]}, status=404)
                return True
            except OSError as exc:
                self._send_json({"ok": False, "error": str(exc)[:200]}, status=502)
                return True
            self._send_json({"ok": True, "kind": kind, "id": target.name})
            return True
        # POST /api/v1/local/hub/submit {kind, id, name?, summary?, version?}
        # — 提交审查(HUB-GOLIVE §P5):打包 owned 世界/库 soul,POST 给
        # hub 栈 registry 的审查队列(pending 三态),等后台批准后进目录。
        # 仅在配置了审查 API(hosted 沙盒/本地 hub 栈)时可用,纯本地 501。
        if self.path == "/api/v1/local/hub/submit":
            body = self._read_json_body() or {}
            kind = "souls" if str(body.get("kind") or "worlds") == "souls" else "worlds"
            item_id = str(body.get("id") or "").strip()
            if not item_id or not web._safe_name(item_id):
                self.send_error(400, "missing id")
                return True
            if kind == "worlds":
                from neonrp.worlds import get_owned_world_dir

                source = get_owned_world_dir(item_id)
            else:
                from neonrp.core.souls import SOUL_HOME

                cand = SOUL_HOME / item_id
                source = cand if (cand / "soul.json").exists() else None
            if source is None:
                self.send_error(404, "unknown local item")
                return True
            from neonrp.core.worldhub import WorldHubError, submit_for_review

            try:
                meta = submit_for_review(
                    source,
                    kind=kind,
                    name=str(body.get("name") or "").strip() or None,
                    slug=str(body.get("slug") or "").strip() or None,
                    summary=str(body.get("summary") or "").strip(),
                    version=str(body.get("version") or "1.0").strip(),
                )
            except WorldHubError as exc:
                status = 501 if "no review API" in str(exc) else 502
                self._send_json({"ok": False, "error": str(exc)[:300]}, status=status)
                return True
            self._send_json({"ok": True, "meta": meta})
            return True
        # POST /api/v1/local/hub/upload {kind, id, name?, slug?, version?,
        # changelog?, unlisted?, token?} — 上传 owned 世界 / 库 soul 到 Hub
        # (CLI `world|soul upload` 的 web 版;token=worldlines.gg/account 的
        # session token,或环境变量 HUB_API_TOKEN)。
        if self.path == "/api/v1/local/hub/upload":
            body = self._read_json_body() or {}
            kind = "souls" if str(body.get("kind") or "worlds") == "souls" else "worlds"
            item_id = str(body.get("id") or "").strip()
            if not item_id or not web._safe_name(item_id):
                self.send_error(400, "missing id")
                return True
            if kind == "worlds":
                from neonrp.worlds import get_owned_world_dir

                source = get_owned_world_dir(item_id)
            else:
                from neonrp.core.souls import SOUL_HOME

                cand = SOUL_HOME / item_id
                source = cand if (cand / "soul.json").exists() else None
            if source is None:
                self.send_error(404, "unknown local item")
                return True
            from neonrp.core.worldhub import WorldHubError, upload_via_api

            try:
                entry = upload_via_api(
                    source,
                    kind=kind,
                    name=str(body.get("name") or "").strip() or None,
                    slug=str(body.get("slug") or "").strip() or None,
                    version=str(body.get("version") or "1.0").strip(),
                    changelog=str(body.get("changelog") or "").strip(),
                    unlisted=bool(body.get("unlisted")),
                    api_token=str(body.get("token") or "").strip() or None,
                )
            except WorldHubError as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
                return True
            except Exception as exc:  # noqa: BLE001 — network failures
                self._send_json({"ok": False, "error": f"upload failed: {exc}"}, status=502)
                return True
            self._send_json({"ok": True, "entry": entry})
            return True
        if rt is None:  # launcher mode: only the session API can bind a run
            self.send_error(409, "no active session - bind one via /api/v1/play/session")
            return True
        return False

    def _post_local_import(self) -> None:
        """POST /api/v1/local/import/{world|soul} — raw file body upload.

        world: an exported .zip → extracted into WORLDS_HOME(load_world_zip)。
        soul:  SillyTavern PNG/JSON card → authored into ~/.worldlines/souls
               via the soul-card-authoring skill(需要 creation LLM;取
               create_provider,没配则用 ?preset= 指定;都没有 → 400)。
        文件名经 ?filename= 传(决定 .png/.json 解析);body 就是文件字节。"""
        import tempfile
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(self.path)
        route = parsed.path[len("/api/v1/local/import/"):]
        q = parse_qs(parsed.query)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > 200_000_000:
            self.send_error(400, "missing or oversized body")
            return
        data = self.rfile.read(length)

        if route == "package":
            # 10-08:导回来 —— 模板包 / 角色包(template/package.py 认 pack.json 里的 kind);?id= 指定新 id
            from neonrp.template import TemplateError
            from neonrp.template import package as _pkg

            try:
                self._send_json({"ok": True, **_pkg.import_package(data, new_id=(q.get("id") or [None])[0])})
            except TemplateError as exc:
                self._send_json({"ok": False, "error": str(exc)[:300]}, status=400)
            return

        if route == "card":
            # 新导入 UX:卡片先入工坊,不直接转换入库。
            # 建工作台 + 持久化源卡(game/import/source.*)+ 尺寸估计;
            # 三条转换路径(①计划-分批/②一次性/③手动)由工坊右侧面板
            # 显式选择 —— 这里零 LLM 调用,秒回。
            from neonrp.core.import_plan import estimate_source, persist_source_card

            kind = (q.get("kind") or ["world"])[0]
            filename = (q.get("filename") or ["card.png"])[0]
            stem = Path(filename).stem or "import"
            suffix = Path(filename).suffix.lower() or ".png"
            if suffix not in (".png", ".json", ".zip", ".txt", ".md"):
                self._send_json(
                    {"ok": False, "error": f"unsupported card type: {suffix}"}, status=400
                )
                return
            with tempfile.TemporaryDirectory() as td:
                card = Path(td) / f"source{suffix}"
                card.write_bytes(data)
                try:
                    if kind == "soul":
                        target = web._scaffold_soul_blank(stem, "")
                    else:
                        from neonrp.worlds import WORLDS_HOME, scaffold_template_into

                        slug = web._new_world_slug(stem)
                        target = WORLDS_HOME / slug
                        scaffold_template_into("white-blank", target)
                        web._set_world_display_name(target, stem)
                    dest = persist_source_card(target, card)
                    est = estimate_source(dest)
                except Exception as exc:  # noqa: BLE001 — clean HTTP error
                    self._send_json(
                        {"ok": False, "error": f"import failed: {exc}"[:200]}, status=400
                    )
                    return
            cpreset = web._resolve_creation_preset("")
            if cpreset:
                web._apply_run_preset(target, cpreset)
            self.server.edit_runtime = web._make_edit_runtime(target)
            self._send_json(
                {
                    "ok": True,
                    "session_id": web.EditRuntime.SID,
                    "world_id": target.name,
                    "kind": "soul" if kind == "soul" else "world",
                    "import": {
                        "source_rel": dest.relative_to(target).as_posix(),
                        "format": est.get("format"),
                        "bytes": est.get("bytes"),
                        "entries": est.get("entries"),
                        "recommend_plan": bool(est.get("recommend_plan")),
                    },
                }
            )
            return

        if route == "world":
            from neonrp.core.world_export import load_world_zip

            overwrite = (q.get("overwrite") or ["0"])[0] == "1"
            with tempfile.TemporaryDirectory() as td:
                zp = Path(td) / "import.zip"
                zp.write_bytes(data)
                try:
                    target = load_world_zip(zp, overwrite=overwrite)
                except (FileNotFoundError, ValueError) as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=400)
                    return
            self._send_json({"ok": True, "world_id": target.name})
            return

        if route == "soul":
            filename = (q.get("filename") or ["card.png"])[0]
            suffix = ".json" if filename.lower().endswith(".json") else ".png"
            preset = web._resolve_creation_preset((q.get("preset") or [""])[0].strip())
            if not preset:
                self._send_json(
                    {"ok": False, "error": "no usable LLM - add an API key in Library settings"},
                    status=400,
                )
                return
            try:
                from neonrp.core.config import _parse_config, resolve_provider
                from neonrp.core.importers.card_to_soul import import_card_to_library
                from neonrp.core.llm import get_adapter_from_config
                from neonrp.presets import build_config_dict

                llm = get_adapter_from_config(
                    resolve_provider(_parse_config(build_config_dict(preset)))
                )
                with tempfile.TemporaryDirectory() as td:
                    card = Path(td) / f"card{suffix}"
                    card.write_bytes(data)
                    soul_dir = import_card_to_library(card, llm=llm)
            except ValueError as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
                return
            except Exception as exc:  # noqa: BLE001 — LLM/network failures
                self._send_json({"ok": False, "error": f"authoring failed: {exc}"}, status=502)
                return
            self._send_json({"ok": True, "soul_dir": soul_dir.name})
            return

        self.send_error(404)

    # ── LocalShell SPA serving helpers (§7.5 LP1) ──
    @staticmethod
    def _spa_rel(url_path: str) -> str | None:
        """URL path → safe spa-relative path, or None (traversal / hidden).

        Every component must be a plain name: no empty segments, no '.'/'..'
        hops, no dotfiles — the packaged build never ships those anyway."""
        from urllib.parse import unquote, urlparse

        rel = unquote(urlparse(url_path).path).lstrip("/")
        parts = rel.split("/")
        if any(not p or p in (".", "..") or p.startswith(".") for p in parts):
            return None
        return rel

    def _serve_spa_file(self, spa: Any, rel: str) -> None:
        """Serve one file of the packaged SPA build. `rel` is slash-separated
        and already validated by the caller. Walks the Traversable segment by
        segment and reads bytes — works for a real directory (source checkout)
        AND a zip member (installed wheel); never assumes a filesystem path."""
        node = spa
        for part in rel.split("/"):
            node = node.joinpath(part)
        try:
            if not node.is_file():
                self.send_error(404)
                return
            data = node.read_bytes()
        except (FileNotFoundError, OSError):
            self.send_error(404)
            return
        suffix = ("." + rel.rsplit(".", 1)[1].lower()) if "." in rel else ""
        self.send_response(200)
        self.send_header(
            "Content-Type", web._SPA_CONTENT_TYPES.get(suffix, "application/octet-stream")
        )
        self.send_header("Content-Length", str(len(data)))
        # vite asset names are content-hashed → cache hard; index.html (and
        # other stable names) must revalidate so a re-sync shows up.
        if rel.startswith("assets/"):
            self.send_header("Cache-Control", "max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _spec_route_get(self) -> bool:
        """10-08:agent 直接读 spec —— GET /llms.txt(索引)· /api/v1/spec(列表)· /api/v1/spec/<name>?lang=&pack=(Markdown)。"""
        from urllib.parse import parse_qs, urlparse

        u = urlparse(self.path)
        if u.path not in ("/llms.txt", "/api/v1/spec") and not u.path.startswith("/api/v1/spec/"):
            return False
        from neonrp import spec

        if u.path == "/api/v1/spec":
            self._send_json({"specs": spec.names()})
            return True
        if u.path == "/llms.txt":
            host = self.headers.get("Host") or ""
            text = spec.llms_txt(f"http://{host}" if host else "")
        else:
            q = parse_qs(u.query)
            try:
                text = spec.read(u.path[len("/api/v1/spec/"):], lang=(q.get("lang") or ["zh"])[0], pack=(q.get("pack") or [None])[0])
            except KeyError as e:
                self.send_error(404, str(e).strip("'\""))
                return True
            except Exception as e:  # noqa: BLE001 — an unknown pack etc.: a clean error, not a dropped connection
                self.send_error(400, str(e)[:200])
                return True
        data = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/markdown; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(data)
        return True
