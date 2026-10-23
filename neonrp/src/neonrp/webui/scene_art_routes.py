"""「画这一幕」over HTTP (core/scene_art, niko 10-16).

    GET  /api/v1/play/engine/scene-art                  the pictures this run drew {items: [{id, i, kind, caption, stored, local}],
                                                         cg: {i: {slot, label, by}}} (beats that showed the author's picture)
    GET  /api/v1/play/engine/scene-art/brief?i=N[&kind=milestone&caption=…]
                                                         what beat N would be drawn from (the author's CG first: ``cg``);
                                                         a world with ``realtime_art`` off (the default) → {disabled: true,
                                                         reason: realtime_art_off, cg} and platform/generate → 403 realtime_art_off
    GET  /api/v1/play/engine/scene-art/file?id=          a picture the platform could not store (kept in the run)
    POST /api/v1/play/engine/scene-art/record {id | b64_png, i, kind?, caption?, size?, credits?}
    POST /api/v1/play/engine/scene-art/forget {id}

The local engine's door to the platform (its own Worldlines sign-in; the browser build's page calls ai / billing itself):

    GET  /api/v1/play/engine/scene-art/platform/status   {signed_in, available, reason?, upgrade_url?, price?}
    POST /api/v1/play/engine/scene-art/platform/generate the ai request as is → ai's status and answer as they are
    GET  /api/v1/play/engine/scene-art/platform/url?id=  a fresh link (ai GET /v1/images/scenes/:id)
    POST /api/v1/play/engine/scene-art/platform/delete {id}
"""
from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

_BASE = "/api/v1/play/engine/scene-art"


class SceneArtRoutes:
    path: str

    def _scene_art_q(self) -> dict[str, str]:
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items() if v}

    def _scene_art_get(self, rt: Any) -> bool:
        route = urlparse(self.path).path.rstrip("/")
        if route != _BASE and not route.startswith(_BASE + "/"):
            return False
        from neonrp.core import scene_art

        q = self._scene_art_q()
        if route == _BASE + "/platform/status":
            if not self._scene_art_local():
                return True
            st, body = scene_art.platform("status")
            self._send_json(body, status=st)
            return True
        if route == _BASE + "/platform/url":
            if not self._scene_art_local():
                return True
            st, body = scene_art.platform("url", iid=q.get("id", ""))
            self._send_json(body, status=st or 502)
            return True
        if rt is None:
            self.send_error(409, "no play session")
            return True
        if route == _BASE:
            self._send_json(scene_art.listing(rt.root, rt._branch()))
        elif route == _BASE + "/brief":
            try:
                i = int(q["i"]) if q.get("i", "") != "" else None
                self._send_json(scene_art.brief(rt.root, i=i, branch=rt._branch(), kind=q.get("kind"), caption=q.get("caption")))
            except (LookupError, ValueError) as e:
                self._send_json({"error": str(e)}, status=404)
        elif route == _BASE + "/file":
            self._send_file(scene_art.inline_file(rt.root, q.get("id", "")), cache="private, max-age=31536000, immutable")
        else:
            self.send_error(404)
        return True

    def _scene_art_post(self, rt: Any) -> bool:
        route = urlparse(self.path).path.rstrip("/")
        if route != _BASE and not route.startswith(_BASE + "/"):
            return False
        from neonrp.core import scene_art

        body = self._read_json_body() or {}
        if route in (_BASE + "/platform/generate", _BASE + "/platform/delete"):
            if not self._scene_art_local():
                return True
            if route.endswith("/generate"):
                if rt is not None and scene_art.mode(rt.root) == "off":  # 10-16: the world's switch is off — never draws
                    self._send_json({"error": {"code": "realtime_art_off", "message": "This world does not draw scenes live."}}, status=403)
                    return True
                st, out = scene_art.platform("generate", body)
            else:
                st, out = scene_art.platform("delete", iid=str(body.get("id") or ""))
            self._send_json(out, status=st or 502)
            return True
        if rt is None:
            self.send_error(409, "no play session")
            return True
        if route == _BASE + "/record":
            try:
                self._send_json(scene_art.record(rt.root, body), status=201)
            except ValueError as e:
                self._send_json({"error": f"bad {e}"}, status=422)
        elif route == _BASE + "/forget":
            self._send_json({"forgotten": scene_art.forget(rt.root, str(body.get("id") or ""))})
        else:
            self.send_error(404)
        return True

    def _scene_art_local(self) -> bool:
        """The platform door is the local engine's: under Pyodide the page holds the sign-in and calls itself."""
        import sys

        if sys.platform == "emscripten":
            self._send_json({"error": {"code": "page_calls", "message": "the browser build's page calls the platform itself"}}, status=404)
            return False
        return True
