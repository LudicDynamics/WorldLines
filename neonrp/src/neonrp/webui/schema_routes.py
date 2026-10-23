"""Open / closed schema over HTTP (core/registry.py + core/ledger.py) — the web face of `neonrp schema`.

Play (bound run; read + subscribe, no writes — players propose, they don't register):
    GET  /api/v1/play/schema                          template + five tables (variables carry their value)
    GET  /api/v1/play/schema/history?var=player.gold  a variable's changes (pull)
    GET  /api/v1/play/schema/events?since=0&type=…    landed ledger events (pull)
    GET  /api/v1/play/schema/stream?pattern=…&since=  SSE: each new event matching pattern (push)

Workbench (world source open in the edit session; same reads + register):
    GET  /api/v1/create/session/edit-local/schema[/history|/events|/stream]
    POST /api/v1/create/session/edit-local/schema/register    {table, id, spec}
    POST /api/v1/create/session/edit-local/schema/unregister  {table, id}

Patterns are sdk.on's: ``*`` | ``<type>`` | ``<type>:<key>`` | ``<type>:*``.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

_PLAY = "/api/v1/play/schema"
_EDIT = "/api/v1/create/session/edit-local/schema"
_READ_SUBS = ("", "/history", "/events", "/stream")
SCHEMA_VERSION = 1


def _plain(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if is_dataclass(obj):
        return {k: v for k, v in asdict(obj).items() if not k.startswith("_")}
    return dict(obj)


_PLACE_LIKE = ("place", "level", "region", "town", "location", "world")


def schema_view(root: Path, *, entries: bool = True) -> dict[str, Any]:
    """The five tables as JSON. Entries are grouped by class (ids + names only)."""
    from neonrp.core.registry import load_registry

    from neonrp.core import engine_config

    reg = load_registry(root)
    out: dict[str, Any] = {
        # the HTTP shape's own version: bump on any breaking change so an older/newer UI can say so
        "schema_version": SCHEMA_VERSION,
        # v2b (world-agent tool loop) lands changes without the SDK → no ledger events to subscribe to
        "turn_mode": str(engine_config.get(root, "turn.mode", "v2b")),
        "template": reg.template,
        "variables": [{**v.to_dict(), "value": v.value} for v in reg.variables.values()],
        "classes": [{"name": k, **{kk: vv for kk, vv in _plain(c).items() if kk != "name"},
                     "count": sum(1 for e in reg.entries.values() if e.cls == k)} for k, c in reg.classes.items()],
        "actions": [_plain(a) for a in reg.actions.values()],
        "triggers": [t.to_dict() for t in reg.triggers.values()],
    }
    if entries:
        from neonrp.core import fallback_art

        by: dict[str, list[dict[str, Any]]] = {}
        for e in reg.entries.values():
            # a thing (not a person / place) carries its stand-in icon: the play screen draws what you carry from here (10-17)
            fb = {} if reg.is_person(e.cls) or e.cls in _PLACE_LIKE else {"icon_fallback": fallback_art.icon(e.props or {}, name=e.name)}
            by.setdefault(e.cls, []).append({"id": e.id, "name": e.name, "parent": e.parent, **fb})
        out["entries"] = by
    return out


class SchemaRoutes:
    server: Any
    path: str

    def _sq(self) -> dict[str, str]:
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items() if v}

    def _schema_root(self, rt: Any, base: str) -> Path | None:
        if base == _PLAY:
            return rt.root if rt is not None else None
        from neonrp.webui.http_util import web

        ert = web._try_rebind_edit_runtime(self.server)
        return ert.world_dir if ert is not None and (ert.world_dir / "game").is_dir() else None

    def _schema_split(self) -> tuple[str, str] | None:
        route = urlparse(self.path).path
        for base in (_PLAY, _EDIT):
            if route == base or route.startswith(base + "/"):
                return base, route[len(base):]
        return None

    # ── GET ──
    def _schema_route_get(self, rt: Any) -> bool:
        hit = self._schema_split()
        if hit is None or hit[1] not in _READ_SUBS:
            return False
        base, sub = hit
        root = self._schema_root(rt, base)
        if root is None:
            self.send_error(409, "no play session" if base == _PLAY else "no world edit session")
            return True
        q = self._sq()
        from neonrp.core import ledger

        if sub == "":
            # a player's read leaves the plot's triggers and the host's variable notes out (core/play_view, 10-15);
            # the bench reads it whole at /api/v1/play/engine/debug/schema
            from neonrp.core import play_view

            self._send_json(play_view.schema(schema_view(root), root) if base == _PLAY else schema_view(root))
        elif sub == "/history":
            var = q.get("var", "")
            if not var:
                self._send_json({"error": "var required"}, status=400)
            else:
                self._send_json(ledger.history(root, var, since_turn=int(q.get("since_turn", 0) or 0)))
        elif sub == "/events":
            self._send_json(ledger.events(root, since=int(q.get("since", 0) or 0), type=q.get("type") or None,
                                          limit=min(2000, int(q.get("limit", 200) or 200))))
        else:
            self._schema_stream(root, q.get("pattern", "*"), q.get("since"), float(q.get("timeout", 0) or 0))
        return True

    def _schema_stream(self, root: Path, pattern: str, since: str | None, timeout: float) -> None:
        """SSE tail of game/meta/events.jsonl. `timeout` > 0 ends the stream (tests)."""
        from neonrp.core import ledger

        seq = int(since) if since not in (None, "") else max((int(e.get("seq", 0)) for e in ledger.events(root, limit=10**9)), default=0)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self._cors_headers()
        self.end_headers()
        end = time.monotonic() + timeout if timeout > 0 else None
        last_beat = time.monotonic()
        try:
            self.wfile.write(f"event: hello\ndata: {json.dumps({'seq': seq, 'pattern': pattern})}\n\n".encode())
            self.wfile.flush()
            while True:
                for ev in ledger.events(root, since=seq, limit=10**9):
                    seq = max(seq, int(ev.get("seq", 0)))
                    if ledger._matches(pattern, ev):
                        self.wfile.write(f"id: {ev['seq']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n".encode())
                self.wfile.flush()
                now = time.monotonic()
                if end is not None and now >= end:
                    return
                if now - last_beat > 15:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    last_beat = now
                time.sleep(0.4)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    # ── POST (workbench only) ──
    def _schema_route_post(self) -> bool:
        hit = self._schema_split()
        if hit is None:
            return False
        base, sub = hit
        if sub not in ("/register", "/unregister"):
            return False
        if base == _PLAY:
            self._send_json({"error": "players propose; registering is the creator's (use the workbench)"}, status=403)
            return True
        root = self._schema_root(None, base)
        if root is None:
            self.send_error(409, "no world edit session")
            return True
        body = self._read_json_body() or {}
        from neonrp.core.registry import RegisterError, register

        try:
            spec = body.get("spec") if sub == "/register" else None
            if sub == "/register" and not isinstance(spec, dict):
                raise RegisterError("spec must be an object")
            res = register(root, str(body.get("table") or ""), str(body.get("id") or ""), spec,
                           replace=not body.get("no_replace"))
        except RegisterError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)
            return True
        self._send_json({"ok": True, **res, "schema": schema_view(root, entries=False)})
        return True
