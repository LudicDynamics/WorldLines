"""What the player played, told to chronicle (chronicle.worldlines.gg, 10-15 lead · sns-platform): the run opened
(``playthrough.ensure``), a world was opened (``world.open``), an ending landed (``ending.reached``). The SNS reads it to
know the player really played a world (a replay of a curated world shows on iOS only then); achievement attachments
point at the endings.

    POST <CHRONICLE>/v1/events:batch {product: "hub", events: [...]}       the player's own token (via=user)

``world_ref`` is ``hub/template/<template id>`` (core/replay_export.world_ref_of_run — the same address replays carry),
``local:<run>`` for a run not built from a template. ``save_id`` = the run folder's name.

Every event goes to a local spool first (``~/.worldlines/chronicle/spool.jsonl``) and is sent from there: offline or a
server error → it stays and goes with the next one. Each event is bound to the account that played it (the token's
``sub``) and only ever sent with that account's token — never put on someone who signs in later on the same machine
(sns-platform 10-15: the SNS and billing read it as "this person played this world"). Nobody signed in, or a guest
(``anon`` in the token — chronicle does not take guests) → the event is not kept at all. Kept at most :data:`SPOOL_MAX`. Per-event results: created / duplicated /
conflict / rejected → done (never retried), except ``rejected: unknown_ref`` (what it points at has not arrived yet) →
kept; a 410 (account deleted) drops the spool. ``NEONRP_CHRONICLE=off`` turns it off.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BASE = os.environ.get("WORLDLINES_CHRONICLE_BASE", "https://chronicle.worldlines.gg")
SPOOL = Path.home() / ".worldlines" / "chronicle" / "spool.jsonl"
SPOOL_MAX = 2000
SPOOL_DAYS = 30   # an account that never comes back: its events leave the spool after this (sns-platform 10-15)
BATCH = 500
_LOCK = threading.Lock()
_FLUSHING = threading.Lock()
_THREADS: list[threading.Thread] = []


def enabled() -> bool:
    return os.environ.get("NEONRP_CHRONICLE", "").strip().lower() not in ("off", "0", "false", "no")


CLIENTS = ("web", "local", "seat", "app")   # chronicle's own list (worldlines-platform services/chronicle/src/events.mjs)


def client() -> str:
    """Where this engine runs: ``WORLDLINES_CLIENT`` when the shell says so (the iOS app's embedded engine sets ``app``,
    ios4 10-21), else the browser engine (Pyodide) = web, else local."""
    env = os.environ.get("WORLDLINES_CLIENT", "").strip().lower()
    if env in CLIENTS:
        return env
    return "web" if sys.platform == "emscripten" else "local"


def _token() -> str | None:
    from neonrp.core import worldlines_auth

    tok = worldlines_auth.access_token()
    return tok if tok and tok != "-" else None   # the browser build sets "-" when nobody is signed in and no guest token yet


def _claims(token: str) -> dict[str, Any]:
    """The access token's payload, read (not verified — chronicle verifies): who and whether a guest. A PAT is not a JWT."""
    import base64

    parts = token.split(".")
    if len(parts) != 3:
        return {}
    try:
        c = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
        return c if isinstance(c, dict) else {}
    except (ValueError, TypeError):
        return {}


def account(token: str | None = None) -> str | None:
    """Whose events these are: the token's ``sub`` (a PAT: a hash of it); None = nobody signed in, or a guest. Offline
    with an expired session, the stored token still says who it is."""
    from neonrp.core import worldlines_auth

    tok = token or _token()
    if tok is None:
        try:
            tok = str(json.loads(worldlines_auth.store_path().read_text(encoding="utf-8")).get("access_token") or "") or None
        except (OSError, ValueError, AttributeError):
            tok = None
    if not tok:
        return None
    c = _claims(tok)
    if c:
        return None if c.get("anon") else (str(c["sub"]) if c.get("sub") else None)
    import hashlib

    return "pat:" + hashlib.sha256(tok.encode()).hexdigest()[:16]


def world_ref(root: Path) -> str:
    from neonrp.core.replay_export import derive_world_slug, world_ref_of_run

    return world_ref_of_run(root) or f"local:{derive_world_slug(root)}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _meta(root: Path) -> dict[str, Any]:
    from neonrp.core.paths import get_data_dir_name

    try:
        t = json.loads((Path(root) / get_data_dir_name(Path(root)) / "meta" / "template.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(t, dict):
        return {}
    out = {"template_id": t.get("id"), "template_version": t.get("version"), "pack": t.get("pack"),
           "world_title": (t.get("card") or {}).get("title") if isinstance(t.get("card"), dict) else t.get("title")}
    return {k: str(v) for k, v in out.items() if v}


# ── what is told ─────────────────────────────────────────────────────────────

def ensure(root: Path) -> None:
    """This run exists (idempotent: chronicle keys it by save_id)."""
    emit({"type": "playthrough.ensure", "save_id": Path(root).name, "world_ref": world_ref(root), **({"meta": m} if (m := _meta(root)) else {})})


def opened(root: Path) -> None:
    """The player opened this run's world (bound it to play) — and the model calls from now on say which world
    (X-Worldlines-World, core/worldlines_auth)."""
    _bind_world(root)
    ensure(root)
    emit({"type": "world.open", "world_ref": world_ref(root), "open_id": uuid.uuid4().hex, "client": client()})


def ending(root: Path, ended: dict[str, Any]) -> None:
    eid = str(ended.get("id") or "")
    if not eid:
        return
    ensure(root)   # a run played without the web bind (TUI / headless) still has its playthrough first
    emit({"type": "ending.reached", "save_id": Path(root).name, "ending_id": eid,
          **{k: str(ended[k]) for k in ("title", "kind") if ended.get(k)}})


def _bind_world(root: Path) -> None:
    from neonrp.core import worldlines_auth

    ref = world_ref(root)
    worldlines_auth.set_world(ref.split("/", 2)[2] if ref.startswith("hub/template/") else None)


def reward(root: Path, *, ref: str, points: int, source: str, score: int | None = None, total: int | None = None) -> str:
    """A settled run's points, told to chronicle (``settlement.reward``, 2026-10-21) — chronicle hands it to billing, which
    pays only on its own facts (billed calls of this world during the run). → what happened: reported · own_key (the
    player's own model key: billing sees no calls, nothing is sent) · local (not a published template's world) ·
    free_zone · guest (nobody signed in / a guest: chronicle takes no guests) · none (0 points) · off."""
    from neonrp.core import player_data, worldlines_auth

    if not enabled():
        return "off"
    if points <= 0:
        return "none"
    if not world_ref(root).startswith("hub/template/"):
        return "local"
    if player_data.free_zone(root):
        return "free_zone"
    if not worldlines_auth.bills_run(root):
        return "own_key"
    if account() is None:
        return "guest"
    ensure(root)
    emit({"type": "settlement.reward", "save_id": Path(root).name, "ref": str(ref).lower()[:100], "source": source, "points": int(points),
          **({"score": int(score)} if score is not None else {}), **({"total": int(total)} if total is not None else {})})
    return "reported"


# ── the spool ────────────────────────────────────────────────────────────────

def emit(ev: dict[str, Any], *, send: bool = True) -> None:
    if not enabled():
        return
    who = account()
    if who is None:   # not signed in / a guest: chronicle would not take it, and no one else may inherit it
        return
    rec = {**ev, "occurred_at": ev.get("occurred_at") or _now(), "_uid": who}
    with _LOCK:
        SPOOL.parent.mkdir(parents=True, exist_ok=True)
        lines = pending()
        lines.append(rec)
        _write(lines)
    if send:
        flush_soon()


def pending() -> list[dict[str, Any]]:
    try:
        return [json.loads(x) for x in SPOOL.read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError):
        return []


def _fresh(ev: dict[str, Any], now: float) -> bool:
    try:
        t = datetime.fromisoformat(str(ev.get("occurred_at") or "").replace("Z", "+00:00")).timestamp()
    except ValueError:
        return False
    return now - t < SPOOL_DAYS * 86400


def _write(rows: list[dict[str, Any]]) -> None:
    """The spool as given, minus events older than SPOOL_DAYS, the newest SPOOL_MAX at most (first in, first out)."""
    now = time.time()
    rows = [r for r in rows if _fresh(r, now)][-SPOOL_MAX:]
    tmp = SPOOL.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    tmp.replace(SPOOL)


def flush_soon() -> None:
    """Send in the background — never hold a turn or a bind on the network."""
    th = threading.Thread(target=flush, daemon=True, name="chronicle-flush")
    _THREADS[:] = [t for t in _THREADS if t.is_alive()] + [th]
    th.start()


def _post(body: dict[str, Any], token: str) -> tuple[int, dict[str, Any]]:
    import urllib.error
    import urllib.request

    from neonrp.core import worldlines_auth

    req = urllib.request.Request(f"{BASE.rstrip('/')}/v1/events:batch", data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}", **worldlines_auth.headers()})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def flush() -> dict[str, int]:
    """Send what waits, oldest first, in batches. → {sent, kept, dropped}."""
    out = {"sent": 0, "kept": 0, "dropped": 0}
    if not enabled() or not _FLUSHING.acquire(blocking=False):
        return out
    try:
        token = _token()
        who = account(token) if token else None
        if token is None or who is None:
            out["kept"] = len(pending())
            return out
        from neonrp.core import worldlines_auth

        while True:
            with _LOCK:
                mine = [(i, ev) for i, ev in enumerate(pending()) if ev.get("_uid") == who][:BATCH]
            batch = [ev for _, ev in mine]
            if not batch:
                out["kept"] = len(pending())
                return out
            try:
                status, res = _post({"product": worldlines_auth.PRODUCT,
                                     "events": [{k: v for k, v in ev.items() if not k.startswith("_")} for ev in batch]}, token)
            except Exception as exc:  # noqa: BLE001 — offline: everything stays for the next time
                logger.debug("chronicle offline: %s", exc)
                out["kept"] = len(pending())
                return out
            if status == 410:   # the account is gone: what waits is for no one
                keep: list[dict[str, Any]] = []
                out["dropped"] += len(batch)
            elif status != 200:
                out["kept"] = len(pending())
                return out
            else:
                results = {int(r.get("index", -1)): r for r in res.get("results") or [] if isinstance(r, dict)}
                keep = [ev for i, ev in enumerate(batch) if (results.get(i) or {}).get("code") == "unknown_ref"]
                out["sent"] += len(batch) - len(keep)
            sent = {json.dumps(ev, sort_keys=True) for ev in batch} - {json.dumps(ev, sort_keys=True) for ev in keep}
            with _LOCK:   # drop what is done; everything else (other accounts', added meanwhile) stays in its order
                _write([ev for ev in pending() if json.dumps(ev, sort_keys=True) not in sent])
            if keep:   # unknown_ref: wait for the next flush rather than spin on it
                out["kept"] = len(pending())
                return out
    finally:
        _FLUSHING.release()


def _wait(timeout: float = 5.0) -> None:
    """Tests: wait until a background flush is done."""
    t0 = time.monotonic()
    while _THREADS:
        _THREADS.pop().join(max(0.0, timeout - (time.monotonic() - t0)))
