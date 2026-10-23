"""Layered-map routes (core/worldmap.py) for play and the workbench.

Play (bound run, player's lens — undiscovered places come back nameless):
    GET  /api/v1/play/map
    GET  /api/v1/play/map/image?level=T001
    GET  /api/v1/play/map/level?addr=T001                 one level's connectivity graph (G2)
    GET  /api/v1/play/place-image?addr=T001/inn
    GET  /api/v1/play/sprite?id=elena      GET /api/v1/play/portrait?id=elena|player

Workbench (edit session on the world source):
    GET  /api/v1/create/session/edit-local/map            full tree + issues + jobs
    GET  .../map/image?level=T001[&guide=1]
    GET  .../place-image?addr=…   GET .../sprite?id=…   GET .../portrait?id=…
    PUT  .../map/node       {level, addr, x, y}           drag a pin (x/y = % of the image)
    POST .../map/node       {level, name, kind, x, y, summary?, link_to?}
    POST .../map/edge       {level, a, b, remove?, distance?}   add / remove the road between two places
    POST .../map/generate   {level}                        background job
    POST .../place/generate {addr}                         background job
    POST .../soul/portrait  {sid}                          background job (portrait + sprite)
    POST .../place/upload?addr=…                           raw image body → scene image
    GET  .../map/jobs

Every file path is derived from an address that exists in the tree, never from
the client string itself.
"""

from __future__ import annotations

import hashlib
import mimetypes
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from neonrp.webui.http_util import web

_JOBS: dict[str, dict[str, dict[str, Any]]] = {}
_JOBS_LOCK = threading.Lock()


def _jobs_for(root: Path) -> dict[str, dict[str, Any]]:
    with _JOBS_LOCK:
        return {k: dict(v) for k, v in _JOBS.get(str(root.resolve()), {}).items()}


def _start_job(root: Path, key: str, fn: Any) -> bool:
    rk = str(root.resolve())
    with _JOBS_LOCK:
        cur = _JOBS.setdefault(rk, {}).get(key)
        if cur and cur.get("state") == "running":
            return False
        _JOBS[rk][key] = {"state": "running", "started": time.time()}

    def run() -> None:
        try:
            fn()
            res = {"state": "done", "finished": time.time()}
        except Exception as exc:  # noqa: BLE001 — surfaced to the UI
            res = {"state": "error", "error": str(exc)[:300], "finished": time.time()}
        with _JOBS_LOCK:
            _JOBS[rk][key].update(res)

    threading.Thread(target=run, name=f"neonrp-imagejob-{key}", daemon=True).start()
    return True


class MapRoutes:
    server: Any
    path: str

    _MAP_PLAY = "/api/v1/play"
    _MAP_EDIT = "/api/v1/create/session/edit-local"

    # ── helpers ──
    def _q(self) -> dict[str, str]:
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items() if v}

    def _route(self) -> str:
        return urlparse(self.path).path

    def _send_file(self, p: Path | None, cache: str = "no-cache") -> None:
        """A file with an ETag (path · mtime · size): a request carrying it back gets 304 and no body (10-15)."""
        if p is None or not p.is_file():
            self.send_error(404)
            return
        st = p.stat()
        etag = '"' + hashlib.sha1(f"{p.resolve()}|{st.st_mtime_ns}|{st.st_size}".encode()).hexdigest()[:20] + '"'
        if etag in [x.strip() for x in (self.headers.get("If-None-Match") or "").split(",")]:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", cache)
            self._cors_headers()
            self.end_headers()
            return
        data = p.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(p.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", cache)
        self._cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def _edit_root(self) -> Path | None:
        ert = web._try_rebind_edit_runtime(self.server)
        if ert is None or not (ert.world_dir / "game").is_dir():
            return None
        return ert.world_dir

    def _serve_assets(self, root: Path, sub: str, lens: str) -> bool:
        from neonrp.core import worldmap as M

        q = self._q()
        if sub == "/map/image":
            tree = M.build_map_tree(root)
            level = q.get("level", M.ROOT)
            if level not in M.map_levels(tree):
                self.send_error(404)
                return True
            if q.get("guide") == "1" and lens == "studio":
                self._send_file(M.map_guide_path(root, level))
            else:
                self._send_file(M.map_image_path(root, level))
            return True
        if sub == "/place-image":
            tree = M.build_map_tree(root)
            addr = q.get("addr", "")
            if addr not in tree["nodes"]:
                self.send_error(404)
                return True
            if lens == "play" and (tree["nodes"][addr].get("state") or {}).get("discovered") is False:
                self.send_error(404)
                return True
            self._send_file(M.scene_image_path(root, addr))
            return True
        if sub == "/portrait":
            sid = q.get("id", "")
            if not sid or not all(c.isalnum() or c in "-_" for c in sid):
                self.send_error(400)
                return True
            if sid == "player":
                pdir = M._gdir(root) / "player" / "assets"
                self._send_file(next((pdir / f"portrait{e}" for e in M._IMG_EXTS if (pdir / f"portrait{e}").is_file()), None))
            else:
                self._send_file(M.soul_asset(root, sid, "portrait"))
            return True
        if sub == "/sprite":
            sid = q.get("id", "")
            if not sid or not all(c.isalnum() or c in "-_" for c in sid):
                self.send_error(400)
                return True
            self._send_file(M.soul_asset(root, sid, "sprite"))
            return True
        return False

    # ── GET ──
    def _map_route_get(self, rt: Any) -> bool:
        from neonrp.core import worldmap as M

        route = self._route()
        if route == f"{self._MAP_PLAY}/map/level":  # G2: one level's connectivity graph (?addr=T001; default the world)
            if rt is None:
                self.send_error(409, "no play session")
                return True
            from neonrp.core import place_tree as PT

            g = PT.level_graph(rt.root, (self._q().get("addr") or PT.WORLD).split("/", 1)[0] if self._q().get("addr") else PT.WORLD)
            if g is None:
                self.send_error(404, "no such level")
                return True
            self._send_json(g)
            return True
        if route.startswith(f"{self._MAP_PLAY}/") and route[len(self._MAP_PLAY):] in (
            "/map", "/map/image", "/place-image", "/sprite", "/portrait"
        ):
            if rt is None:
                self.send_error(409, "no play session")
                return True
            sub = route[len(self._MAP_PLAY):]
            if sub == "/map":
                self._send_json(M.map_view(rt.root, lens="play"))
                return True
            return self._serve_assets(rt.root, sub, "play")
        if route.startswith(f"{self._MAP_EDIT}/") and route[len(self._MAP_EDIT):] in (
            "/map", "/map/image", "/map/jobs", "/place-image", "/sprite", "/portrait"
        ):
            root = self._edit_root()
            if root is None:
                self.send_error(409, "no world edit session")
                return True
            sub = route[len(self._MAP_EDIT):]
            if sub == "/map":
                self._send_json({**M.map_view(root, lens="studio"), "jobs": _jobs_for(root)})
                return True
            if sub == "/map/jobs":
                self._send_json(_jobs_for(root))
                return True
            return self._serve_assets(root, sub, "studio")
        return False

    # ── PUT ──
    def _map_route_put(self) -> bool:
        from neonrp.core import worldmap as M

        if self._route() != f"{self._MAP_EDIT}/map/node":
            return False
        root = self._edit_root()
        if root is None:
            self.send_error(409, "no world edit session")
            return True
        body = self._read_json_body() or {}
        try:
            res = M.move_node(root, str(body.get("level") or ""), str(body.get("addr") or ""),
                              float(body.get("x")), float(body.get("y")))
        except (TypeError, ValueError, KeyError) as exc:
            self._send_json({"error": str(exc)[:200]}, status=400)
            return True
        self._send_json({"ok": True, **res})
        return True

    # ── POST ──
    def _map_route_post(self) -> bool:
        from neonrp.core import worldmap as M

        route = self._route()
        if not route.startswith(f"{self._MAP_EDIT}/") or route[len(self._MAP_EDIT):] not in (
            "/map/node", "/map/edge", "/map/generate", "/place/generate", "/soul/portrait", "/place/upload"
        ):
            return False
        root = self._edit_root()
        if root is None:
            self.send_error(409, "no world edit session")
            return True
        sub = route[len(self._MAP_EDIT):]
        if sub == "/place/upload":
            addr = self._q().get("addr", "")
            if addr not in M.build_map_tree(root)["nodes"]:
                self._send_json({"error": "unknown place"}, status=400)
                return True
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length <= 0 or length > 20_000_000:
                self.send_error(400, "missing or oversized body")
                return True
            try:
                out = M.bind_scene(root, addr, self.rfile.read(length))
            except Exception as exc:  # noqa: BLE001 — not an image
                self._send_json({"error": f"not an image: {exc}"[:200]}, status=400)
                return True
            self._send_json({"ok": True, "path": str(out.relative_to(root))})
            return True
        body = self._read_json_body() or {}
        tree = M.build_map_tree(root)
        if sub == "/map/node":
            level = str(body.get("level") or "")
            if level not in M.map_levels(tree) or M.level_kind(tree, level) == "dungeon":
                self._send_json({"error": "can't add places on this map"}, status=400)
                return True
            name = str(body.get("name") or "").strip()[:60]
            if not name:
                self._send_json({"error": "name required"}, status=400)
                return True
            try:
                res = M.add_node(root, level, name=name, kind=str(body.get("kind") or ""),
                                 xp=float(body.get("x")), yp=float(body.get("y")),
                                 summary=str(body.get("summary") or "")[:500],
                                 link_to=str(body.get("link_to") or "") or None)
            except (TypeError, ValueError) as exc:
                self._send_json({"error": str(exc)[:200]}, status=400)
                return True
            self._send_json({"ok": True, **res})
            return True
        if sub == "/map/edge":
            try:
                res = M.set_road(root, str(body.get("level") or ""), str(body.get("a") or ""), str(body.get("b") or ""),
                                 remove=bool(body.get("remove")), distance=body.get("distance"))
            except ValueError as exc:
                self._send_json({"error": str(exc)[:200]}, status=400)
                return True
            self._send_json({"ok": True, **res})
            return True
        if sub == "/map/generate":
            level = str(body.get("level") or M.ROOT)
            if level not in M.map_levels(tree):
                self._send_json({"error": "no drawable map there"}, status=400)
                return True
            started = _start_job(root, f"map:{level}", lambda: M.generate_map(root, level))
            self._send_json({"ok": True, "job": f"map:{level}", "started": started}, status=202)
            return True
        if sub == "/place/generate":
            addr = str(body.get("addr") or "")
            if addr not in tree["nodes"] or addr == M.ROOT:
                self._send_json({"error": "unknown place"}, status=400)
                return True
            started = _start_job(root, f"place:{addr}", lambda: M.generate_scene(root, addr))
            self._send_json({"ok": True, "job": f"place:{addr}", "started": started}, status=202)
            return True
        if sub == "/soul/portrait":
            sid = str(body.get("sid") or "")
            if not any(e["kind"] == "soul" and e["id"] == sid for e in tree["entities"]):
                self._send_json({"error": "unknown soul"}, status=400)
                return True
            started = _start_job(root, f"portrait:{sid}", lambda: M.generate_portrait(root, sid))
            self._send_json({"ok": True, "job": f"portrait:{sid}", "started": started}, status=202)
            return True
        return False
