"""One-click turn-engine mode (v2b ⇄ v3) for a world or a run — core/engine_config.py's `turn.mode`.

The switch writes the **world layer** (``game/meta/engine.json``) of the folder it is pointed at:
the world source in the workbench, or the bound run's own copy in play (so switching a save never
touches the world it came from). The env layer (``NEONRP_TURN_V3``) still wins over it — the
response says which layer the effective value came from, so a pinned env is visible, not silent.

    GET  /api/v1/play/engine/mode                          {mode, source, modes}
    POST /api/v1/play/engine/mode   {mode: "v2b"|"v3"}     the bound run
    GET  /api/v1/create/session/edit-local/engine/mode
    POST /api/v1/create/session/edit-local/engine/mode     the world source
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

MODES = ("v2b", "v3")
_PLAY = "/api/v1/play/engine/mode"
_EDIT = "/api/v1/create/session/edit-local/engine/mode"


def turn_mode(root: Path) -> dict[str, Any]:
    from neonrp.core import engine_config

    src = next((s for k, _v, s in engine_config.explain(root) if k == "turn.mode"), "builtin")
    return {"mode": str(engine_config.get(root, "turn.mode", "v2b")).lower(), "source": src, "modes": list(MODES)}


def set_turn_mode(root: Path, mode: str) -> dict[str, Any]:
    """Write turn.mode into <root>/game/meta/engine.json (other keys kept). Returns the effective state."""
    from neonrp.core.paths import get_data_dir_name

    mode = str(mode or "").lower()
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    p = root / get_data_dir_name(root) / "meta" / "engine.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    turn = data.get("turn") if isinstance(data.get("turn"), dict) else {}
    turn["mode"] = mode
    data["turn"] = turn
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**turn_mode(root), "file": str(p.relative_to(root))}


class ModeRoutes:
    server: Any
    path: str

    def _mode_root(self, rt: Any, route: str) -> Path | None:
        if route == _PLAY:
            return rt.root if rt is not None else None
        from neonrp.webui.http_util import web

        ert = web._try_rebind_edit_runtime(self.server)
        return ert.world_dir if ert is not None and (ert.world_dir / "game").is_dir() else None

    def _mode_route(self, rt: Any, method: str) -> bool:
        route = urlparse(self.path).path
        if route not in (_PLAY, _EDIT):
            return False
        root = self._mode_root(rt, route)
        if root is None:
            self.send_error(409, "no play session" if route == _PLAY else "no world edit session")
            return True
        if method == "GET":
            self._send_json(turn_mode(root))
            return True
        body = self._read_json_body() or {}
        try:
            self._send_json({"ok": True, **set_turn_mode(root, str(body.get("mode") or ""))})
        except ValueError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)
        return True
