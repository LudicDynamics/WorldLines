"""Class growth policies + the creator's approval queue over HTTP (core/approvals.py).

    GET  /api/v1/play/engine/approvals              {pending: [...], policies: {class: policy}}
    POST /api/v1/play/engine/approvals/<id>         {approve: true|false}   → the row (approved = landed now)
    POST /api/v1/play/engine/policy                 {class, policy}          → sets the run's class policy (overlay)

The bound run is the player's own world line; in it the player is also its creator (local, or their own
account's engine on the Hub), so these are play-side routes.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote, urlparse

_Q = "/api/v1/play/engine/approvals"
_POLICY = "/api/v1/play/engine/policy"


def _policies(root: Any) -> dict[str, str]:
    from neonrp.core.registry import load_registry

    reg = load_registry(root)
    return {name: getattr(c, "policy", "auto") for name, c in reg.classes.items() if c.custom}


class ApprovalRoutes:
    server: Any
    path: str

    def _approval_route_get(self, rt: Any) -> bool:
        if urlparse(self.path).path.rstrip("/") != _Q:
            return False
        if rt is None:
            self.send_error(409, "no play session")
            return True
        from neonrp.core import approvals

        self._send_json({"pending": approvals.pending(rt.root), "policies": _policies(rt.root), "choices": list(approvals.POLICIES)})
        return True

    def _approval_route_post(self, rt: Any) -> bool:
        route = urlparse(self.path).path.rstrip("/")
        if not (route == _POLICY or route.startswith(_Q + "/")):
            return False
        if rt is None:
            self.send_error(409, "no play session")
            return True
        from neonrp.core import approvals
        from neonrp.core.registry import RegisterError, register

        body = self._read_json_body() or {}
        if route == _POLICY:
            cls, policy = str(body.get("class") or ""), str(body.get("policy") or "")
            if cls not in _policies(rt.root):
                self._send_json({"ok": False, "error": f"unknown or built-in class {cls!r}"}, status=400)
                return True
            try:
                register(rt.root, "classes", cls, {"policy": policy})
            except RegisterError as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
                return True
            self._send_json({"ok": True, "policies": _policies(rt.root)})
            return True
        if not rt._busy.acquire(blocking=False):
            self._send_json({"ok": False, "error": "a turn is in progress"}, status=409)
            return True
        try:
            row = approvals.decide(rt.root, unquote(route[len(_Q) + 1:]), bool(body.get("approve")))
        except KeyError:
            self._send_json({"ok": False, "error": "no such open request"}, status=404)
            return True
        finally:
            rt._busy.release()
        self._send_json({"ok": True, "row": row})
        return True
