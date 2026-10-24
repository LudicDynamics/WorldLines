"""How many runs (saves) of one world a player may keep (10-15).

    sandbox (a mystery / TRPG world)   guest · free 1 per world · Traveler 3 per world · Voyager no count limit
    open adventure                     guest · free 1 · Traveler / Voyager 1 main + 3 = 4 runs of that adventure

Only a NEW run is refused (``POST /api/v1/play/session {slug: "tpl--<id>"}``); carrying on with a run never is, and
runs already over the limit are left alone. The numbers are data, not code — the first that has them:

1. the platform: ``limits.saves_sandbox`` / ``limits.saves_adventure`` of billing ``GET /v1/me/entitlements?product=hub``
   (read when present; not there today — the next layer answers)
2. ``NEONRP_SAVE_LIMITS`` (a JSON file shaped like the packaged one; e2e)
3. the packaged ``schema/save_limits.json`` — by tier (billing's ``tier``: free · story = Traveler · vivid = Voyager)

Who is limited: a player on Worldlines in the browser build (the online Hub, the iOS app) — signed in, or a guest
whose token the browser build pushed in. The local edition (``worldlines`` / ``neonrp`` / the desktop app) has no
limit, signed in or not (lead 10-25); ``NEONRP_SAVE_LIMITS_ENFORCE=1`` turns the limit on there too (tests, hosted). The platform out of reach = no limit this
time (better one run too many than a player who cannot start); a token the platform refuses = free.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("neonrp.save_limits")

KINDS = ("sandbox", "adventure")
_CACHE: dict[str, tuple[float, dict[str, Any] | None]] = {}
TTL_S = 60.0


class SaveLimit(Exception):
    """A new run would go over the limit: what the page shows the player (status 409)."""

    def __init__(self, info: dict[str, Any]):
        super().__init__("save_limit")
        self.info = info

    def to_dict(self) -> dict[str, Any]:
        return {"error": "save_limit", **self.info}


def table() -> dict[str, Any]:
    """The tier → {sandbox, adventure} table (``NEONRP_SAVE_LIMITS`` file, else the packaged one)."""
    p = os.environ.get("NEONRP_SAVE_LIMITS", "").strip()
    src = Path(p) if p else Path(__file__).resolve().parents[1] / "schema" / "save_limits.json"
    try:
        d = json.loads(src.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        logger.warning("save limits: cannot read %s", src)
        return {}


def kind_of(tid: str) -> str:
    """``adventure`` for a template played under an open-adventure contract (its exit is a segment, a day), else sandbox."""
    try:
        from neonrp import template as TP
        from neonrp.template import contract as C

        found = TP.discover().get(tid)
        if not found:
            return "sandbox"
        ref = TP.load(found).play_contract
        c = C.load(ref) if ref else {}
        return "adventure" if str(((c or {}).get("exit") or {}).get("on") or "") == "segment" else "sandbox"
    except Exception:  # noqa: BLE001 — a template that does not load plays as a sandbox
        return "sandbox"


def _read(p: Path) -> dict[str, Any]:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def template_of(run: Path) -> str:
    rec = _read(run / "game" / "meta" / "template.json") or _read(run / ".neonrp" / "meta" / "template.json")
    t = str(rec.get("id") or rec.get("template") or "")
    if not t and run.name.startswith("tpl-"):
        t = run.name[4:].rsplit("-", 2)[0]
    return t


def runs_of(tid: str, plays: Path | None = None) -> list[dict[str, Any]]:
    """This world's runs on this machine / in this browser, newest first: {slug, turns, updated, ended}."""
    if plays is None:
        from neonrp.worlds import PLAYS_HOME as plays
    rows: list[dict[str, Any]] = []
    for d in plays.iterdir() if plays.is_dir() else []:
        if not d.is_dir() or template_of(d) != tid:
            continue
        rs = _read(d / "game" / "meta" / "run_state.json")
        st = d / "game" / "meta" / "run_state.json"
        try:
            mt = max(d.stat().st_mtime, st.stat().st_mtime if st.exists() else 0)
        except OSError:
            mt = 0
        rows.append({"slug": d.name, "turns": int(rs.get("turn_count") or 0), "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(mt)),
                     "ended": (d / "game" / "meta" / "settlement.json").is_file(), "_mt": mt})
    rows.sort(key=lambda r: r["_mt"], reverse=True)
    for r in rows:
        r.pop("_mt", None)
    return rows


def _entitlements(token: str) -> dict[str, Any] | None:
    """billing's {tier, limits} for this token (60 s cache); {"tier": "free"} when the platform refuses the token;
    None when it cannot be reached (no limit this time)."""
    hit = _CACHE.get(token)
    ttl = float(os.environ.get("NEONRP_SAVE_LIMITS_TTL_S") or TTL_S)   # e2e switches the fake platform's tier: 0
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    from neonrp.core import scene_art, worldlines_auth

    _ai, billing = scene_art._bases()
    out: dict[str, Any] | None
    try:
        st, body = scene_art._call("GET", f"{billing}/v1/me/entitlements?product={worldlines_auth.PRODUCT}", token, timeout=10)
    except Exception:  # noqa: BLE001
        st, body = 0, None
    if st == 200 and isinstance(body, dict):
        out = {"tier": str(body.get("tier") or body.get("plan") or "free"), "limits": body.get("limits") if isinstance(body.get("limits"), dict) else {}}
    elif st in (401, 403):
        out = {"tier": "free", "limits": {}}
    else:
        logger.info("save limits: billing unreachable (%s) — not limiting", st)
        out = None
    _CACHE[token] = (time.monotonic(), out)
    return out


def limit_for(kind: str) -> tuple[str | None, int | None]:
    """(tier, how many runs of one world) for whoever plays on this engine; (None, None) = no limit."""
    from neonrp.core import worldlines_auth

    if sys.platform != "emscripten" and os.environ.get("NEONRP_SAVE_LIMITS_ENFORCE", "").strip() != "1":
        return None, None  # the local edition: no limit, signed in or not (10-25)
    tok = worldlines_auth.access_token()
    if not tok or tok == "-":
        return None, None  # own key, not signed in (local)
    ent = _entitlements(tok)
    if ent is None:
        return None, None
    tier = ent["tier"]
    plat = (ent.get("limits") or {}).get(f"saves_{kind}")
    if isinstance(plat, int) or plat is None and f"saves_{kind}" in (ent.get("limits") or {}):
        return tier, plat
    row = table().get(tier) or table().get("free") or {}
    n = row.get(kind)
    return tier, (int(n) if isinstance(n, (int, float)) else None)


def check_new_run(tid: str, plays: Path | None = None) -> None:
    """Raise :class:`SaveLimit` when starting one more run of ``tid`` would go over the limit."""
    kind = kind_of(tid)
    tier, n = limit_for(kind)
    if n is None:
        return
    runs = runs_of(tid, plays)
    if len(runs) < n:
        return
    raise SaveLimit({"tier": tier, "kind": kind, "limit": n, "template": tid, "saves": runs})
