"""The player's collection on their Worldlines account (10-18, niko; docs/planning/COLLECTION-SYNC-1018.md): the cards a
world handed out, the runs finished, the characters taken home (with the template version), achievements and endings go
up to the platform's data service (``hub/collection``, hub manifest v9) and come back on every other device.

    GET  {data}/v1/records/hub/collection?scope=mine&limit=100[&cursor=]     all of mine, page by page
    POST {data}/v1/records:batch {product: hub, kind: collection, ops: [create | put | delete]}

- **only adds**: a sync never takes anything away from this machine or the account. Here and not there → up; there and
  not here → into the local record (core/player_data). The same thing on both → the newer ``updated`` wins (put with the
  record's rev; a rev that moved → read again next time)
- one record per thing, found by (type, world, key) — record ids are data's own. Two devices that created the same thing
  at once leave two records: the newest stays, the others are deleted
- pictures never go up: a card keeps its template slot (``image_slot``) and each device copies the picture from its own
  copy of the template (core/rewards); a template this machine does not have = a plain card until it does
- a character's memory stays on the device it was taken on; another device knows it is gained (and talks with it as the
  template wrote it)
- signed in = ``worldlines_auth.access_token()``; the token needs ``data:read data:write`` — an older session gets 403 and
  the state says ``relogin``. Not signed in, offline, the platform down: nothing happens, the local record stands

The state of the last sync (for the Hub's 「我的」): ``~/.worldlines/player-data/<player>.sync.json``
``{state: ok | relogin | offline | error | off, at, pulled, pushed, error?}``.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATA = os.environ.get("WORLDLINES_DATA_BASE", "https://data.worldlines.gg").rstrip("/")
PRODUCT, KIND = "hub", "collection"
LANGS = ("zh", "en", "ja", "ko")
DEBOUNCE_S = 10.0
PULL_EVERY_S = 60.0
_LOCK = threading.Lock()
_TIMER: dict[str, Any] = {"t": None}


def enabled() -> bool:
    return os.environ.get("WORLDLINES_COLLECTION_SYNC", "1").strip().lower() not in ("0", "off", "false", "no")


def _token() -> str | None:
    from neonrp.core import worldlines_auth

    tok = worldlines_auth.access_token()
    return tok if tok and tok != "-" else None


# ── the record on the platform ↔ the local record ────────────────────────────

def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _iso(v: Any) -> str:
    """A local ``at`` (``%Y-%m-%dT%H:%M:%S%z``) as RFC 3339 UTC; "" when it does not parse."""
    from datetime import datetime, timezone

    s = str(v or "")
    for f in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            d = datetime.strptime(s.replace("Z", "+0000") if f.endswith("%z") else s, f)
            return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    return ""


def _langs(v: Any, n: int) -> dict[str, str]:
    """A title / desc as the platform keeps it: {lang: text}, each cut to ``n``."""
    if isinstance(v, dict):
        return {str(k)[:8]: str(x)[:n] for k, x in list(v.items())[:8] if str(x).strip()}
    return {"und": str(v)[:n]} if str(v or "").strip() else {}


def _key(t: str, world: str, key: str, scope: str = "") -> tuple[str, str, str]:
    """The identity of a thing: a player-wide achievement is one whatever world it was earned in."""
    return (t, "" if scope == "player" else world, key)


def _ach_face(aid: str, world: str) -> dict[str, Any]:
    from neonrp.core import achievements

    out: dict[str, Any] = {"id": aid}
    for lg in LANGS:
        d = achievements.describe(aid, world, lg) or {}
        if d.get("title"):
            out.setdefault("title", {})[lg] = str(d["title"])[:120]
        if d.get("desc"):
            out.setdefault("desc", {})[lg] = str(d["desc"])[:400]
        if "points" in d:
            out["points"], out["scope"] = int(d.get("points") or 0), str(d.get("scope") or "world")
    return out


def local_items() -> dict[tuple[str, str, str], dict[str, Any]]:
    """Every thing in the local record as the platform's body, by its identity."""
    from neonrp.core import player_data

    pd = player_data.read()
    out: dict[tuple[str, str, str], dict[str, Any]] = {}

    def put(t: str, rec: dict[str, Any], key: str, extra: dict[str, Any], scope: str = "") -> None:
        world = str(rec.get("world") or "")
        if not world or not key:
            return
        at = _iso(rec.get("at")) or _now()
        body = {"v": 1, "type": t, "world": world[:128], "key": key[:160], "at": at, "updated": _iso(rec.get("updated")) or at,
                **({"version": str(rec["version"])[:32]} if rec.get("version") else {}), t: extra}
        out[_key(t, world, key, scope)] = body

    for c in pd["cards"]:
        put("card", c, str(c.get("id") or ""), {"kind": str(c.get("kind") or "card")[:32], "rarity": c.get("rarity") if c.get("rarity") in ("common", "rare", "epic") else "common",
                                                 "title": _langs(c.get("title"), 120), "desc": _langs(c.get("desc"), 400),
                                                 **({"image_slot": str(c["image_slot"])[:200]} if c.get("image_slot") else {}),
                                                 **({"source": str(c["source"])[:64]} if c.get("source") else {})})
    for r in pd["runs"]:
        put("run", r, str(r.get("run") or ""), {"run": str(r.get("run") or "")[:128], "exit": str(r.get("exit") or "ending")[:32] or "ending",
                                                **({"ending": str(r["ending"])[:64]} if r.get("ending") else {})})
    for c in pd["characters"]:
        put("character", c, str(c.get("sid") or ""), {"sid": str(c.get("sid") or "")[:128], "name": str(c.get("name") or "")[:80],
                                                      "how": str(c.get("how") or "")[:64], "memory": c.get("memory") if c.get("memory") in ("full", "fresh", "trial") else "full"})
    for a in pd["achievements"]:
        aid = str(a.get("id") or "")
        face = _ach_face(aid, str(a.get("world") or ""))
        put("achievement", a, aid, {**face, **({"source": str(a["source"])[:64]} if a.get("source") else {})}, str(face.get("scope") or ""))
    for e in pd["endings"]:
        put("ending", e, str(e.get("id") or ""), {"id": str(e.get("id") or "")[:64], "title": str(e.get("title") or "")[:120]})
    return out


def absorb(body: dict[str, Any]) -> bool:
    """One record from the platform into the local record: a thing missing here is added, a newer one replaces the
    fields that change (a card's face, a character's version / memory). True = something changed here."""

    t, world, key = str(body.get("type") or ""), str(body.get("world") or ""), str(body.get("key") or "")
    x = body.get(t) if isinstance(body.get(t), dict) else {}
    at, upd, ver = str(body.get("at") or _now()), str(body.get("updated") or body.get("at") or ""), str(body.get("version") or "")
    if t == "card":
        rec = {"id": key, "world": world, "kind": x.get("kind") or "card", "title": x.get("title") or key, "desc": x.get("desc") or "",
               "rarity": x.get("rarity") or "common", "version": ver, "source": x.get("source") or "account", "at": at, "updated": upd,
               **({"image_slot": x["image_slot"]} if x.get("image_slot") else {})}
        return _merge("cards", rec, ("id", "world"), upd, pictured=True)
    if t == "run":
        return _merge("runs", {"world": world, "run": key, "exit": x.get("exit") or "ending", **({"ending": x["ending"]} if x.get("ending") else {}),
                               "version": ver, "at": at}, ("world", "run"), upd)
    if t == "character":
        return _merge("characters", {"sid": key, "name": x.get("name") or key, "world": world, "how": x.get("how") or "",
                                     "memory": x.get("memory") or "full", "version": ver, "at": at, "updated": upd}, ("sid", "world"), upd)
    if t == "achievement":
        scope = str(x.get("scope") or "")
        return _merge("achievements", {"id": key, "world": world, "source": x.get("source") or "account", "at": at},
                      ("id",) if scope == "player" else ("id", "world"), upd)
    if t == "ending":
        return _merge("endings", {"id": key, "title": x.get("title") or "", "world": world, "at": at}, ("id", "world"), upd)
    return False


_UPDATABLE = {"cards": ("kind", "title", "desc", "rarity", "version", "image_slot", "updated"),
              "characters": ("name", "how", "memory", "version", "updated")}


def _merge(kind: str, rec: dict[str, Any], key: tuple[str, ...], upd: str, *, pictured: bool = False) -> bool:
    from neonrp.core import player_data

    with player_data._LOCK:
        d = player_data.read()
        hit = next((r for r in d[kind] if all(r.get(k) == rec.get(k) for k in key)), None)
        if hit is None:
            d[kind].append(rec)
        elif kind in _UPDATABLE and upd and upd > (_iso(hit.get("updated")) or _iso(hit.get("at"))):
            hit.update({k: rec[k] for k in _UPDATABLE[kind] if k in rec})
        else:
            return False
        player_data._save(d)
    if pictured:
        _picture(rec)
    return True


def _picture(rec: dict[str, Any]) -> None:
    """A card that came from the account: its picture from this machine's copy of the template (never from the platform)."""
    from neonrp.core import player_data, rewards

    name = rewards._picture(rec["world"], {"id": rec["id"], **({"slot": rec["image_slot"]} if rec.get("image_slot") else {})},
                            rewards.card_dir(rec["world"]))
    if name:
        player_data.update("cards", {"id": rec["id"], "world": rec["world"]}, {"image": name})


# ── the wire ─────────────────────────────────────────────────────────────────

class SyncError(Exception):
    def __init__(self, state: str, msg: str = ""):
        super().__init__(msg or state)
        self.state = state


def _call(method: str, path: str, token: str, body: Any = None) -> tuple[int, dict[str, Any]]:
    from neonrp.core import worldlines_auth

    h = {**worldlines_auth.headers(), "Authorization": f"Bearer {token}", "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{DATA}{path}", data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            txt = r.read()
            return r.status, (json.loads(txt) if txt else {})
    except urllib.error.HTTPError as e:
        try:
            out = json.loads(e.read() or b"{}")
        except ValueError:
            out = {}
        if e.code in (401, 403):
            raise SyncError("relogin", f"{e.code} {out.get('error') or ''}".strip()) from e
        return e.code, out if isinstance(out, dict) else {}
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise SyncError("offline", str(e)) from e


def _pull(token: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cursor = ""
    for _ in range(100):  # 100 pages × 100 = the 5000 a player may keep
        st, body = _call("GET", f"/v1/records/{PRODUCT}/{KIND}?scope=mine&limit=100" + (f"&cursor={cursor}" if cursor else ""), token)
        if st != 200:
            raise SyncError("error", f"pull {st} {body.get('error') or ''}".strip())
        rows += [r for r in body.get("records") or [] if isinstance(r, dict) and isinstance(r.get("body"), dict)]
        cursor = str(body.get("next_cursor") or "")
        if not cursor:
            break
    return rows


def _batch(token: str, ops: list[dict[str, Any]]) -> int:
    ok = 0
    for i in range(0, len(ops), 100):
        st, body = _call("POST", "/v1/records:batch", token, {"product": PRODUCT, "kind": KIND, "ops": ops[i:i + 100]})
        if st != 200:
            raise SyncError("error", f"batch {st} {body.get('error') or ''}".strip())
        ok += int((body.get("counts") or {}).get("ok") or 0)
    return ok


def sync() -> dict[str, Any]:
    """Pull, merge, push. Never raises; the state is written for the Hub."""
    if not enabled():
        return _state({"state": "off"})
    token = _token()
    if not token:
        return _state({"state": "signed_out"})
    with _LOCK:
        try:
            remote = _pull(token)
            by: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
            for r in remote:
                b = r["body"]
                scope = str((b.get("achievement") or {}).get("scope") or "") if b.get("type") == "achievement" else ""
                by.setdefault(_key(str(b.get("type")), str(b.get("world")), str(b.get("key")), scope), []).append(r)
            ops: list[dict[str, Any]] = []
            pulled = 0
            for recs in by.values():
                recs.sort(key=lambda r: (str(r["body"].get("updated") or ""), int(r.get("rev") or 0)), reverse=True)
                for dup in recs[1:]:  # two devices created the same thing at once: keep the newest
                    ops.append({"op": "delete", "id": dup["id"]})
                if absorb(recs[0]["body"]):
                    pulled += 1
            mine = local_items()
            for k, body in mine.items():
                have = by.get(k)
                if not have:
                    ops.append({"op": "create", "body": body})
                elif body["updated"] > str(have[0]["body"].get("updated") or ""):
                    ops.append({"op": "put", "id": have[0]["id"], "rev": int(have[0].get("rev") or 1), "body": body})
            pushed = _batch(token, ops) if ops else 0
            return _state({"state": "ok", "pulled": pulled, "pushed": pushed, "remote": len(remote)})
        except SyncError as e:
            return _state({"state": e.state, "error": str(e)[:200]})
        except Exception as e:  # noqa: BLE001 — a sync never breaks play
            logger.warning("collection sync failed: %s", e, exc_info=True)
            return _state({"state": "error", "error": str(e)[:200]})


def _state_path() -> Path:
    from neonrp.core import player_data

    return player_data.HOME / f"{player_data.player_id()}.sync.json"


def _state(d: dict[str, Any]) -> dict[str, Any]:
    d = {**d, "at": _now(), "t": time.time()}
    try:
        p = _state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d), encoding="utf-8")
    except OSError:
        pass
    return d


def state() -> dict[str, Any]:
    try:
        d = json.loads(_state_path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _maybe_signed_in() -> bool:
    """Cheap (no network, no token refresh): a PAT, or a session file. :func:`sync` asks for the real token."""
    from neonrp.core import worldlines_auth

    return bool(os.environ.get("WORLDLINES_API_KEY", "").strip()) or worldlines_auth.store_path().is_file()


def schedule(delay: float = DEBOUNCE_S) -> None:
    """Something changed in the local record: sync once, shortly (calls within ``delay`` fold into one). Never under a
    test run (a timer outliving the test would reach the developer's own account); the browser engine (one thread,
    threads run when the turn is done) syncs then, without waiting."""
    import sys

    if not enabled() or os.environ.get("PYTEST_CURRENT_TEST") or not _maybe_signed_in():
        return
    t = _TIMER.get("t")
    if t is not None and t.is_alive():
        return
    th = threading.Thread(target=sync, daemon=True) if sys.platform == "emscripten" else threading.Timer(delay, sync)
    th.daemon = True
    _TIMER["t"] = th
    th.start()


def maybe_pull() -> None:
    """The Hub opened 「我的」: when the last sync is older than a minute, sync now in the background."""
    if time.time() - float(state().get("t") or 0) >= PULL_EVERY_S:
        schedule(0.0)
