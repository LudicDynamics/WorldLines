"""Usage events for the platform console (docs/planning/USAGE-DATA-CONTRACT-1025.md — 10-25: console showed nothing for
NeonRP, the engine had only ever sent the four play records of ``/v1/events:batch``).

    POST <chronicle>/v1/events   {product: "hub", session_id, app_version, locale?, events: [{name, at, world_id?, props?}]}
    X-Worldlines-Client: local | web | ios     Authorization: Bearer <signed-in or guest token>   (optional: none = anonymous)

What is sent: ``app_open`` (a cold start: once per session) · ``lobby_view`` · ``world_enter {resumed, tracked: true}`` ·
``session_turn {n, place?}`` on the first turn of each band (n = 1, 2, 3, 6, 11, 21, 51, 101, …) · ``world_leave {turns,
place?}`` (another world, sign-out of the page, exit) · ``first_turn`` (a save's very first turn) · ``ending_reached
{ending?}``. Props are short words, small integers and booleans only — never text from the game.

- one session per process (16 random bytes, never derived from the device or the account); a browser tab hands its own
  (``WORLDLINES_USAGE_SESSION``), and then the page has already said ``app_open``;
- events wait in a small spool next to the session file (≤ 500, ≤ 24 h) and go every 10 s or at 20, and at exit;
  429 → after ``Retry-After``; 5xx / offline → back off 30 s doubling to 10 min; 400 / 413 → dropped;
- the token: the account's (renewed when it has under a minute left — core/worldlines_auth), the browser's guest token
  when that is what the page has; no token → anonymous. A 401 never happens here (chronicle takes a bad token as none).
``NEONRP_USAGE=off`` (or the setting ``usage_data: false``, :func:`set_enabled`) stops it and empties the spool."""
from __future__ import annotations

import atexit
import base64
import json
import logging
import os
import re
import secrets
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

FLUSH_EVERY_S = 10.0
FLUSH_AT = 20
BATCH = 50
SPOOL_MAX = 500
SPOOL_AGE_S = 24 * 3600
TIMEOUT = 3.0 if sys.platform == "emscripten" else 8.0  # the browser engine sends inline (sync XHR): never hold a turn long
_SID_OK = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
_WORLD_OK = re.compile(r"^[A-Za-z0-9._:/@-]{1,128}$")
_PLACE_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
_WORD_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
_lock = threading.RLock()
_S: dict[str, Any] = {"sid": None, "inherited": False, "opened": False, "world": None, "turns": 0, "place": None,
                      "last_flush": 0.0, "retry_at": 0.0, "backoff": 0.0, "thread": None, "atexit": False}


def base() -> str:
    return (os.environ.get("WORLDLINES_USAGE_BASE") or os.environ.get("WORLDLINES_CHRONICLE_BASE")
            or "https://chronicle.worldlines.gg").rstrip("/")


def _settings_file() -> Path:
    from neonrp.core import worldlines_auth

    return worldlines_auth.store_path().with_name("usage.json")


def enabled() -> bool:
    if os.environ.get("NEONRP_USAGE", "").strip().lower() in ("off", "0", "false", "no"):
        return False
    try:
        return json.loads(_settings_file().read_text(encoding="utf-8")).get("usage_data", True) is not False
    except (OSError, ValueError, AttributeError):
        return True


def set_enabled(on: bool) -> None:
    """The player's switch (「发送使用数据」, default on). Off also empties what waits."""
    p = _settings_file()
    try:
        p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        p.write_text(json.dumps({"usage_data": bool(on)}), encoding="utf-8")
    except OSError:
        pass
    if not on:
        with _lock:
            _write([])


def session_id() -> str:
    with _lock:
        if _S["sid"] is None:
            given = os.environ.get("WORLDLINES_USAGE_SESSION", "").strip()
            if _SID_OK.match(given):  # a browser tab's session; the page says whether its app_open went out already
                _S.update(sid=given, inherited=True, opened=os.environ.get("WORLDLINES_USAGE_OPENED") == "1")
            else:
                _S["sid"] = base64.urlsafe_b64encode(secrets.token_bytes(16)).decode("ascii").rstrip("=")
        return str(_S["sid"])


def new_session() -> None:
    """Sign-out / another account: a new session from here on (contract §3)."""
    with _lock:
        leave()
        _S.update(sid=None, inherited=False, opened=False)


# ── the spool ────────────────────────────────────────────────────────────────

def _spool() -> Path:
    from neonrp.core import worldlines_auth

    return worldlines_auth.store_path().with_name("usage-spool.jsonl")


def pending() -> list[dict[str, Any]]:
    try:
        rows = [json.loads(x) for x in _spool().read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError):
        return []
    now = time.time() * 1000
    return [r for r in rows if isinstance(r, dict) and now - float((r.get("ev") or {}).get("at") or 0) < SPOOL_AGE_S * 1000]


def _write(rows: list[dict[str, Any]]) -> None:
    p = _spool()
    try:
        if not rows:
            p.unlink(missing_ok=True)
            return
        p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows[-SPOOL_MAX:]), encoding="utf-8")
        tmp.replace(p)
    except OSError:
        pass


def _clean_props(props: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (props or {}).items():
        if isinstance(v, bool):
            out[k] = v
        elif isinstance(v, int) and 0 <= v <= 100000:
            out[k] = v
        elif isinstance(v, str) and _WORD_OK.match(v):
            out[k] = v
    return out


def emit(name: str, *, world_id: str | None = None, props: dict[str, Any] | None = None) -> None:
    """Queue one event (never raises, never waits on the network)."""
    try:
        if not enabled():
            return
        with _lock:
            if name != "app_open" and not _S["opened"]:
                app_open()
            ev: dict[str, Any] = {"name": name, "at": int(time.time() * 1000)}
            if world_id and _WORLD_OK.match(world_id):
                ev["world_id"] = world_id
            p = _clean_props(props)
            if p:
                ev["props"] = p
            rows = pending()
            rows.append({"sid": session_id(), "ev": ev})
            _write(rows)
            n = len(rows)
        _schedule(now=n >= FLUSH_AT)
    except Exception:  # noqa: BLE001 — counting never breaks a turn
        logger.debug("usage event not queued", exc_info=True)


def app_open(launch: str = "cold") -> None:
    with _lock:
        session_id()
        if _S["opened"]:
            return
        _S["opened"] = True
    emit("app_open", props={"launch": launch})


def lobby_view() -> None:
    emit("lobby_view")


_BANDS = {1, 2, 3}


def is_band_start(n: int) -> bool:
    """1, 2, 3, 6, 11, 21, 51, 101, 201, 501, 1001, … — the first turn of each band."""
    if n in _BANDS:
        return True
    m = n - 1
    while m >= 10 and m % 10 == 0:
        m //= 10
    return n > 3 and m in (1, 2, 5)


def world_enter(world_id: str, *, resumed: bool = False) -> None:
    with _lock:
        if _S["world"] is not None:
            leave()
        _S.update(world=world_id, turns=0, place=None, save_turn=None)
    emit("world_enter", world_id=world_id, props={"resumed": bool(resumed), "tracked": True})


def turn(world_id: str, save_turn: int | None = None, place: str | None = None) -> None:
    """One turn played in ``world_id`` (``save_turn`` = the save's own turn number)."""
    if not save_turn or save_turn < 1:  # an apply outside a numbered turn (setup, a background write) is not a turn
        return
    with _lock:
        if _S["world"] != world_id:  # a turn without a bind we saw (the TUI, a reconnect): the world is entered now
            world_enter(world_id, resumed=save_turn > 1)
        if _S.get("save_turn") == save_turn:  # several applies land in one turn (player action, approvals, the beat)
            return
        _S["save_turn"] = save_turn
        _S["turns"] += 1
        n = int(_S["turns"])
        _S["place"] = place if place and _PLACE_OK.match(str(place)) else _S["place"]
        pl = _S["place"]
    if save_turn == 1:
        emit("first_turn", world_id=world_id)
    if is_band_start(n):
        emit("session_turn", world_id=world_id, props={"n": n, **({"place": pl} if pl else {})})


def ending(world_id: str, ending_id: str | None = None) -> None:
    emit("ending_reached", world_id=world_id, props={"ending": ending_id} if ending_id else None)


def leave() -> None:
    with _lock:
        w, turns, pl = _S["world"], int(_S["turns"]), _S["place"]
        _S.update(world=None, turns=0, place=None)
    if w:
        emit("world_leave", world_id=w, props={"turns": min(turns, 100000), **({"place": pl} if pl else {})})


# ── sending ──────────────────────────────────────────────────────────────────

def _token() -> str | None:
    try:
        from neonrp.core import worldlines_auth

        tok = worldlines_auth.access_token()
    except Exception:  # noqa: BLE001
        return None
    return tok if tok and tok != "-" else None


def _app_version() -> str:
    try:
        from neonrp import __version__ as v
    except Exception:  # noqa: BLE001
        v = "0"
    return re.sub(r"[^A-Za-z0-9._+-]", "", str(v))[:40] or "0"


def _locale() -> str | None:
    loc = (os.environ.get("NEONRP_LOCALE") or "").strip().replace("_", "-")
    return loc if re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})?", loc) else None


def _post(body: dict[str, Any], token: str | None) -> tuple[int, dict[str, str]]:
    from neonrp.core import worldlines_auth

    hdrs = {"Content-Type": "application/json", **worldlines_auth.client_header(), **({"Authorization": f"Bearer {token}"} if token else {})}
    req = urllib.request.Request(f"{base()}/v1/events", data=json.dumps(body).encode("utf-8"), method="POST", headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 — our own chronicle
            r.read()
            return r.status, dict(r.headers or {})
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {})
    except (OSError, ValueError):
        return 0, {}


def flush(force: bool = False) -> dict[str, int]:
    """Send what waits, by session, ≤ :data:`BATCH` per request. → {sent, kept, dropped}."""
    out = {"sent": 0, "kept": 0, "dropped": 0}
    if not enabled():
        return out
    with _lock:
        if not force and time.monotonic() < _S["retry_at"]:
            out["kept"] = len(pending())
            return out
        _S["last_flush"] = time.monotonic()
        rows = pending()
    if not rows:
        return out
    token = _token()
    done: set[int] = set()
    for sid in dict.fromkeys(r["sid"] for r in rows):
        idx = [i for i, r in enumerate(rows) if r["sid"] == sid]
        for k in range(0, len(idx), BATCH):
            part = idx[k:k + BATCH]
            body = {"product": "hub", "session_id": sid, "app_version": _app_version(),
                    **({"locale": loc} if (loc := _locale()) else {}), "events": [rows[i]["ev"] for i in part]}
            st, hdrs = _post(body, token)
            if st in (200, 202, 204) or st in (400, 413):  # 204 = switched off server-side; 400 / 413 = ours, never resent
                done.update(part)
                out["sent" if st < 300 else "dropped"] += len(part)
                with _lock:
                    _S["backoff"] = 0.0
                continue
            with _lock:
                if st == 429:
                    try:
                        wait = float(hdrs.get("Retry-After") or hdrs.get("retry-after") or 30)
                    except ValueError:
                        wait = 30.0
                else:  # 5xx / offline
                    wait = min(600.0, max(30.0, _S["backoff"] * 2))
                    _S["backoff"] = wait
                _S["retry_at"] = time.monotonic() + wait
            break
        else:
            continue
        break
    with _lock:  # drop what is done; what was added meanwhile stays
        sent = {json.dumps(rows[i], sort_keys=True) for i in done}
        left = [r for r in pending() if json.dumps(r, sort_keys=True) not in sent]
        _write(left)
        out["kept"] = len(left)
    return out


def _loop() -> None:
    while True:
        time.sleep(FLUSH_EVERY_S)
        try:
            if pending():
                flush()
        except Exception:  # noqa: BLE001
            logger.debug("usage flush failed", exc_info=True)


def _at_exit() -> None:
    try:
        leave()
        flush(force=True)
    except Exception:  # noqa: BLE001
        pass


def _schedule(*, now: bool = False) -> None:
    with _lock:
        if not _S["atexit"]:
            atexit.register(_at_exit)
            _S["atexit"] = True
        if sys.platform == "emscripten":  # no threads in the browser engine: send inline, every 10 s at most
            due = now or time.monotonic() - _S["last_flush"] >= FLUSH_EVERY_S
        else:
            if _S["thread"] is None:
                _S["thread"] = threading.Thread(target=_loop, daemon=True, name="usage-flush")
                _S["thread"].start()
            due = now
    if due:
        if sys.platform == "emscripten":
            flush()
        else:
            threading.Thread(target=flush, daemon=True, name="usage-flush-now").start()


def _reset() -> None:
    """Tests."""
    with _lock:
        _S.update(sid=None, inherited=False, opened=False, world=None, turns=0, place=None, last_flush=0.0, retry_at=0.0, backoff=0.0)
