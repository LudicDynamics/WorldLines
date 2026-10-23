"""The studio's 前端 desk over HTTP (template/frontends.py, niko 10-17) — the local engine only.

    GET  /api/v1/local/frontends/<tpl>                       builtin + this world's own front ends ({frontends, writable, bound})
    GET  /api/v1/local/frontends/<tpl>/<fid>/tree            the folder's files (node_modules / .godot / dist left out)
    GET  /api/v1/local/frontends/<tpl>/<fid>/file?path=      one text file
    POST /api/v1/local/frontends/<tpl>/<fid>/file {path, content | delete: true}   a world's own front end only
    GET  /api/v1/local/frontends/<tpl>/<fid>/site/<path>     the folder served as a site (the desk's preview iframe;
                                                             builtin.ts: its dist/ build)
    POST /api/v1/local/frontends/<tpl>/<fid>/agent {input, history?}   SSE: chunk · tool_use · done · error (one agent turn)
    POST /api/v1/local/frontends/<tpl>/builtin.ts/build      npm install (once) + vite build --base ./ → its dist/ (the preview)
    POST /api/v1/local/frontends/<tpl>/<fid>/godot/launch   start Godot on the folder, connected to this engine
    POST /api/v1/local/frontends/<tpl>/<fid>/godot/smoke {line?}   godot --headless -s tests/smoke.gd: ONE REAL TURN in the bound run
    POST /api/v1/local/frontends/<tpl>/new {name, kind, title?, lang?}   a new front end in frontends/<name>/ (writable templates);
                                                             lang = the starter page's words (src/neonrp/prompts/frontends.<lang>.json;
                                                             the listing's titles and the agent's prompt take ?lang= / {lang} too)
    POST /api/v1/local/frontends/<tpl>/<fid>/fork {name, title?}  a copy (builtin or this world's) into frontends/<name>/ (10-19)
    GET  /api/v1/local/frontends/<tpl>/<fid>/export          the folder as <fid>.frontend.zip (builtin ones too; no installs / builds)
    POST /api/v1/local/frontends/<tpl>/import?name=<name>    raw zip body (≤ 20 MB) → frontends/<name>/; 422 {problems} and nothing
                                                             written when a path is unsafe, it is too big, or frontend.json fails
    GET  /api/v1/local/frontends/_/connect                   {url, token, protocol}: this engine's /rpc credentials
    GET  /api/v1/local/frontends/_/godot                     {bin, version, running}
    POST /api/v1/local/frontends/_/godot/stop {pid}          only a Godot this engine started

``<tpl>`` = a template id, or ``_`` for none. Everything that writes, starts a process or hands out the token answers
only a loopback client addressed as localhost / 127.0.0.1 (no CORS headers, the token is never logged).
"""
from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

_P = "/api/v1/local/frontends"


class FrontendRoutes:
    server: Any
    headers: Any
    path: str
    client_address: Any
    wfile: Any

    # ── helpers ──
    def _fe_local(self) -> bool:
        ip = str((self.client_address or ("",))[0])
        host = str(self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        return ip in ("127.0.0.1", "::1", "::ffff:127.0.0.1") and host in ("127.0.0.1", "localhost", "::1")

    def _fe_split(self) -> tuple[str, str, str] | None:
        route = urlparse(self.path).path
        if route != _P and not route.startswith(_P + "/"):
            return None
        tpl, _, rest = route[len(_P) + 1:].partition("/")
        fid, _, sub = rest.partition("/")
        return unquote(tpl), unquote(fid), sub

    def _fe_tpl(self, tpl: str) -> Any:
        if tpl in ("", "_"):
            return None
        from neonrp import template as TP

        d = TP.discover().get(tpl)
        return TP.load(d) if d is not None else False

    def _fe_send_text(self, body: bytes, ctype: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _fe_connect(self) -> dict[str, Any]:
        from neonrp.net import protocol as P
        from neonrp.net.host import hub_of

        port = self.server.server_address[1]
        return {"url": f"http://127.0.0.1:{port}", "token": hub_of(self.server).token, "protocol": P.PROTOCOL}

    def _fe_bound(self, rt: Any) -> str | None:
        if rt is None:
            return None
        try:
            from neonrp.webui.template_routes import TP_meta

            return str((TP_meta(rt.root) or {}).get("id") or "") or None
        except Exception:  # noqa: BLE001
            return None

    # ── GET ──
    def _frontend_route_get(self, rt: Any) -> bool:
        sp = self._fe_split()
        if sp is None:
            return False
        from neonrp.template import frontends as FE

        tpl, fid, sub = sp
        q = parse_qs(urlparse(self.path).query)
        if tpl == "_" and fid == "connect":
            if not self._fe_local():
                self.send_error(403, "local only")
                return True
            body = json.dumps(self._fe_connect()).encode("utf-8")
            self._fe_send_text(body, "application/json; charset=utf-8")
            return True
        if tpl == "_" and fid == "godot":
            self._send_json(FE.godot_status())
            return True
        t = self._fe_tpl(tpl)
        if t is False:
            self.send_error(404, "no such template")
            return True
        if not fid:
            from neonrp.template import author

            self._send_json({"tpl": t.id if t else None, "writable": bool(t and author.writable(t)), "bound": self._fe_bound(rt),
                             "frontends": FE.listing(t, (q.get("lang") or [""])[0] or None)})
            return True
        try:
            d, writable, info = FE.resolve(t, fid)
        except FE.FrontendError as e:
            self._send_json({"error": str(e)}, 404)
            return True
        if sub == "export":
            if not self._fe_local():
                self.send_error(403, "local only")
                return True
            body = FE.export_zip(d, fid)
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="{fid}.frontend.zip"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif sub == "tree":
            self._send_json({"id": fid, "writable": writable, "info": info, "files": FE.tree(d)})
        elif sub == "file":
            try:
                self._send_json({"path": (q.get("path") or [""])[0], "content": FE.read(d, (q.get("path") or [""])[0])})
            except FileNotFoundError:
                self._send_json({"error": "not found"}, 404)
            except FE.FrontendError as e:
                self._send_json({"error": str(e)}, 400)
        elif sub == "site" or sub.startswith("site/"):
            base = d / str(info.get("site") or "") if info.get("site") else d
            rel = unquote(sub[5:]) or "index.html"
            try:
                p = FE._inside(base, rel) if base.is_dir() else None
            except FE.FrontendError:
                p = None
            if p is not None and p.is_dir():
                p = p / "index.html"
            if p is None or not p.is_file():
                self.send_error(404)
                return True
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            if p.suffix in (".js", ".mjs"):
                ctype = "text/javascript"
            self._fe_send_text(p.read_bytes(), ctype + ("; charset=utf-8" if ctype.startswith("text/") else ""))
        else:
            self.send_error(404)
        return True

    # ── POST ──
    def _frontend_route_post(self, rt: Any) -> bool:
        sp = self._fe_split()
        if sp is None:
            return False
        from neonrp.template import frontends as FE

        if not self._fe_local():
            self.send_error(403, "local only")
            return True
        tpl, fid, sub = sp
        if fid == "import" and not sub:
            self._fe_import(tpl)
            return True
        body = self._read_json_body() or {}
        lang = str(body.get("lang") or "") or (parse_qs(urlparse(self.path).query).get("lang") or [""])[0] or None
        if tpl == "_" and fid == "godot" and sub == "stop":
            self._send_json({"stopped": FE.godot_stop(int(body.get("pid") or 0))})
            return True
        t = self._fe_tpl(tpl)
        if t is False:
            self.send_error(404, "no such template")
            return True
        if fid == "new" and not sub:
            try:
                self._send_json(FE.create(t, str(body.get("name") or ""), str(body.get("kind") or ""), str(body.get("title") or ""), lang))
            except (FE.FrontendError, AttributeError) as e:
                self._send_json({"error": str(e) if t else "no world"}, 400)
            return True
        try:
            d, writable, info = FE.resolve(t, fid)
        except FE.FrontendError as e:
            self._send_json({"error": str(e)}, 404)
            return True
        world = (t.id if t else "") or self._fe_bound(rt) or ""
        if sub == "file":
            if not writable:
                self._send_json({"error": "read-only front end"}, 403)
                return True
            try:
                if body.get("delete"):
                    self._send_json({"deleted": FE.delete(d, str(body.get("path") or ""))})
                else:
                    FE.write(d, str(body.get("path") or ""), str(body.get("content") or ""))
                    self._send_json({"ok": True})
            except FE.FrontendError as e:
                self._send_json({"error": str(e)}, 400)
        elif sub == "fork":
            try:
                self._send_json(FE.fork(t, fid, str(body.get("name") or ""), str(body.get("title") or "")))
            except (FE.FrontendError, AttributeError) as e:
                self._send_json({"error": str(e) if t else "no world"}, 400)
        elif sub == "build":
            try:
                self._send_json(FE.build(fid) if fid in FE.BUILTIN else FE.build(fid, d=d, info=info))
            except FE.FrontendError as e:
                self._send_json({"error": str(e)}, 409)
        elif sub == "godot/launch":
            c = self._fe_connect()
            try:
                self._send_json(FE.godot_launch(d, host=c["url"], token=c["token"], world=world))
            except FE.FrontendError as e:
                self._send_json({"error": str(e)}, 409)
        elif sub == "godot/smoke":
            if rt is None:
                self._send_json({"error": "no run open: start one first"}, 409)
                return True
            c = self._fe_connect()
            try:
                self._send_json(FE.godot_smoke(d, host=c["url"], token=c["token"], world=world, line=str(body.get("line") or "Look around.")))
            except FE.FrontendError as e:
                self._send_json({"error": str(e)}, 409)
        elif sub == "agent":
            self._fe_agent(rt, d, writable, info, t, body, lang)
        else:
            self.send_error(404)
        return True

    def _fe_import(self, tpl: str) -> None:
        from neonrp.template import frontends as FE

        q = parse_qs(urlparse(self.path).query)
        name, lang = (q.get("name") or [""])[0], (q.get("lang") or [""])[0] or None
        t = self._fe_tpl(tpl)
        if not t:
            self._send_json({"error": "no such template"}, 404)
            return
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > FE._ZIP_MAX:
            self._send_json({"error": "zip body: 1 byte … 20 MB"}, 413 if n > 0 else 400)
            return
        data = self.rfile.read(n)
        try:
            self._send_json(FE.import_zip(t, name, data, lang))
        except FE.FrontendImportRefused as e:
            self._send_json({"error": str(e), "problems": e.problems}, 422)
        except FE.FrontendError as e:
            self._send_json({"error": str(e)}, 400)

    def _fe_agent(self, rt: Any, d: Path, writable: bool, info: dict[str, Any], t: Any, body: dict[str, Any], lang: str | None) -> None:
        from neonrp.template import frontends as FE

        if not writable:
            self._send_json({"error": "read-only front end: make it this world's own first"}, 403)
            return
        text = str(body.get("input") or "").strip()
        if not text:
            self._send_json({"error": "empty"}, 400)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def emit(ev: str, data: dict[str, Any]) -> None:
            self.wfile.write(f"event: {ev}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8"))
            self.wfile.flush()

        try:
            hist = [h for h in body.get("history") or [] if isinstance(h, dict)]
            for ev, data in FE.agent(d, info, t, text, history=hist, root=getattr(rt, "root", None) or d, lang=lang):
                emit(ev, data)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as e:  # noqa: BLE001 — the desk shows why (no model configured …)
            try:
                emit("error", {"error": f"{type(e).__name__}: {e}"})
            except OSError:
                pass
