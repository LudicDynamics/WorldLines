"""Share a run's replay to the platform (10-15 lead · sns-platform, worldlines-platform docs/玩家分享SNS-1015.md §4.1):
the replay is registered and uploaded through the ordinary works channel with the player's own token, published in the
open zone, then posted as a moment.

    POST /api/v1/local/replay/share {session_id?, text?, lang?}
    → 200 {replay_id, ref: "hub/replay/<id>", world_ref?, moment_id, moment_url, zone, notice?, moment_error?, message?}
      (moment_error: sns_share_unavailable = the replay is published; posting is not open for this sign-in yet —
      ``message`` says so in the player's language)
      401 not_signed_in · 403 insufficient_scope (sign in again: the token needs resources:write storage:write
      sns:share) · 404 no such run · 422 nothing to replay / refused · 429 replay quota · 502 a platform step failed

1. auth   POST /v1/resources {product: hub, kind: replay, id, title, meta: {world_ref}}
2. auth   POST /v1/resources/hub/replay/<id>/lease → lease_id
3. storage POST /v1/objects/hub/replay/<id>/upload-url {leaseId, files: [{path, size, sha256}]} → PUT each url with its
          headers exactly
4. storage POST /v1/objects/hub/replay/<id>/complete {leaseId, title, meta}      (meta carries world_ref again)
5. auth   POST /v1/resources/hub/replay/<id>/publish {zone: "open"}
6. sns    POST /v1/moments {text?, attachments: [{type: replay, ref: hub/replay/<id>}]} (Idempotency-Key = the id)

What goes up is the replay bundle's whitelist (core/replay_export.pack_replay): replay.json · timeline.json
(worldlines.replay/1) · story.md · feed.jsonl · cover.png · assets/… (the run's pictures the replay shows: scenes,
portraits, the ending's art) — the raw turn trace stays home. ``world_ref`` (``hub/template/<id>``) comes from replay.json unchanged; a run not
built from a template has none and the SNS treats it as the open zone. The browser build uploads the same files (its XHR
bridge sends bytes as base64, hub/play/wlweb._body).
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

STORAGE = os.environ.get("WORLDLINES_STORAGE_BASE", "https://storage.worldlines.gg")
SNS = os.environ.get("WORLDLINES_SNS_BASE", "https://sns.worldlines.gg/api")
SCOPES_NEEDED = ("resources:write", "storage:write", "sns:share")
TEXT_MEMBERS = ("replay.json", "timeline.json", "story.md", "feed.jsonl")


class ShareError(Exception):
    def __init__(self, status: int, code: str, message: str = "", extra: dict[str, Any] | None = None):
        super().__init__(message or code)
        self.status, self.code, self.extra = status, code, extra or {}

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.code, "message": str(self), **self.extra}


def _issuer() -> str:
    from neonrp.core import worldlines_auth

    return worldlines_auth.ISSUER.rstrip("/")


UPLOAD_FLOOR_BPS = 64 * 1024   # the slowest upload speed a timeout still allows for (bytes / s)
UPLOAD_TIMEOUT_MAX = 900


def _call(method: str, url: str, token: str | None, body: Any = None, *, headers: dict[str, str] | None = None,
          raw: bytes | None = None, step: str = "", platform: bool = True) -> tuple[int, dict[str, Any]]:
    """``platform=False``: a signed storage URL — only its own signed headers go with it."""
    from neonrp.core import worldlines_auth

    h = {**(worldlines_auth.headers() if platform else {}), **(headers or {})}
    if token:
        h["Authorization"] = f"Bearer {token}"
    data = raw
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    # a big upload gets time for its size (≥ 64 KB/s on top of the minute; the browser engine's XHR is synchronous, so the
    # timeout is all it has), and a signed PUT — the same bytes to the same URL — is tried once more when it times out
    tmo = min(UPLOAD_TIMEOUT_MAX, 60 + len(data or b"") / UPLOAD_FLOOR_BPS)
    for attempt in range(2 if raw is not None and not platform else 1):
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=tmo) as r:
                txt = r.read()
                return r.status, (json.loads(txt) if txt and txt[:1] in (b"{", b"[") else {})
        except urllib.error.HTTPError as e:
            try:
                out = json.loads(e.read() or b"{}")
            except ValueError:
                out = {}
            return e.code, out if isinstance(out, dict) else {}
        except (urllib.error.URLError, OSError) as e:
            if attempt == 0 and raw is not None and not platform and "timed out" in str(e).lower():
                continue
            raise ShareError(502, "unreachable", f"{step}: {e}", {"step": step}) from e
    raise ShareError(502, "unreachable", f"{step}: timed out", {"step": step})


def _check(status: int, body: dict[str, Any], step: str, ok: tuple[int, ...] = (200, 201)) -> dict[str, Any]:
    if status in ok:
        return body
    detail = {"step": step, "status": status, **({"detail": body} if body else {})}
    if status == 401:
        raise ShareError(401, "not_signed_in", "sign in to Worldlines first", detail)
    if status == 403:
        raise ShareError(403, "insufficient_scope", "sign in again: sharing needs " + " ".join(SCOPES_NEEDED), detail)
    if status == 429:
        raise ShareError(429, str(body.get("error") or "quota"), "replay quota reached", detail)
    if status == 422:
        raise ShareError(422, str(body.get("error") or "refused"), str(body.get("message") or "refused"), detail)
    raise ShareError(502, "platform_error", f"{step} failed ({status})", detail)


def _token() -> str:
    from neonrp.core import worldlines_auth

    tok = worldlines_auth.access_token()
    if not tok or tok == "-":
        raise ShareError(401, "not_signed_in", "sign in to Worldlines first")
    return tok


def _files(run_dir: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    """(replay.json, {path: bytes}) — the bundle's whitelist, packed in memory (core/replay_export.pack_replay)."""
    from neonrp.core.replay_export import ReplayExportError, pack_replay

    try:
        return pack_replay(run_dir, source="local-play")
    except ReplayExportError as exc:
        raise ShareError(422, "nothing_to_replay", str(exc)) from exc


def _uploadable(name: str) -> bool:
    """The bundle's text members and its pictures (cover · assets/…) — the browser build too: its XHR bridge carries
    bytes as base64 (hub/play/wlweb._body, 10-18)."""
    return name in TEXT_MEMBERS or name == "cover.png" or name.startswith("assets/")


def _new_id(slug: str) -> str:
    base = "".join(c if c.isalnum() or c in "-_." else "-" for c in slug).strip("-.") or "replay"
    return f"{base[:80]}-{time.strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(2)}"


def share(run_dir: Path, *, text: str = "", lang: str | None = None) -> dict[str, Any]:
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise ShareError(404, "no_such_run", str(run_dir.name))
    _token()
    meta, files = _files(run_dir)
    return share_files(meta, files, text=text, lang=lang, fallback_id=run_dir.name)


def share_files(meta: dict[str, Any], files: dict[str, bytes], *, text: str = "", lang: str | None = None,
                fallback_id: str = "replay") -> dict[str, Any]:
    """Steps 1–6 for a bundle already built — a run just packed, or a replay kept on this machine (core/replay_library)."""
    token = _token()
    files = {k: v for k, v in files.items() if _uploadable(k)}
    world = meta.get("world") or {}
    rid = _new_id(str(world.get("slug") or fallback_id))
    ref = f"hub/replay/{rid}"
    title = f"{world.get('name') or world.get('slug') or rid} · replay"[:200]
    rmeta = {k: meta[k] for k in ("world_ref",) if meta.get(k)} | {"turns": meta.get("turns", 0), "lang": lang or meta.get("lang")}
    rmeta = {k: v for k, v in rmeta.items() if v is not None}
    auth = _issuer()
    _check(*_call("POST", f"{auth}/v1/resources", token, {"product": "hub", "kind": "replay", "id": rid, "title": title, "meta": rmeta},
                  step="register"), "register")
    lease = _check(*_call("POST", f"{auth}/v1/resources/{ref}/lease", token, {}, step="lease"), "lease")
    lease_id = str(lease.get("lease_id") or lease.get("leaseId") or "")
    if not lease_id:
        raise ShareError(502, "platform_error", "lease: no lease_id", {"step": "lease"})
    try:
        want = [{"path": p, "size": len(b), "sha256": hashlib.sha256(b).hexdigest()} for p, b in files.items()]
        up = _check(*_call("POST", f"{STORAGE}/v1/objects/{ref}/upload-url", token, {"leaseId": lease_id, "files": want},
                           step="upload-url"), "upload-url")
        for u in up.get("uploads") or []:
            p = str(u.get("path") or "")
            if p not in files:
                continue
            st, body = _call(str(u.get("method") or "PUT"), str(u["url"]), None, headers=dict(u.get("headers") or {}),
                             raw=files[p], step=f"put {p}", platform=False)
            _check(st, body, f"put {p}", ok=(200, 201, 204))
        _check(*_call("POST", f"{STORAGE}/v1/objects/{ref}/complete", token, {"leaseId": lease_id, "title": title, "meta": rmeta},
                      step="complete"), "complete")
    except ShareError:
        _call("DELETE", f"{auth}/v1/resources/{ref}/lease/{lease_id}", token, step="release")
        raise
    pub = _check(*_call("POST", f"{auth}/v1/resources/{ref}/publish", token, {"zone": "open"}, step="publish"), "publish",
                 ok=(200, 202))
    moment_error, mom = None, {}
    if not _may_share(token):   # signed in without sns:share (identity before 0016): the replay is up, the post waits
        moment_error = "sns_share_unavailable"
    else:
        st, mom = _call("POST", f"{SNS.rstrip('/')}/v1/moments", token,
                        {**({"text": text.strip()[:2000]} if text.strip() else {}), "attachments": [{"type": "replay", "ref": ref}],
                         **({"lang": _sns_lang(lang)} if _sns_lang(lang) else {})},
                        headers={"Idempotency-Key": rid}, step="moment")
        if st in (401, 403):
            moment_error, mom = "sns_share_unavailable", {}
        else:
            mom = _check(st, mom, "moment")
    return {"replay_id": rid, "ref": ref, **({"world_ref": rmeta["world_ref"]} if rmeta.get("world_ref") else {}),
            "published": (pub.get("resource") or {}).get("status") or "published",
            "moment_id": mom.get("id"), "moment_url": mom.get("url"), "zone": mom.get("zone"),
            **({"notice": mom["notice"]} if mom.get("notice") else {}),
            **({"moment_error": moment_error, "message": _not_open(lang)} if moment_error else {})}


def _not_open(lang: str | None) -> str:
    from neonrp.core.output_lang import normalize_prompt_lang
    from neonrp.prompts import strings

    return str(strings("replay_share", normalize_prompt_lang(lang) if lang else "en").get("share_not_open") or "")


def _may_share(token: str) -> bool:
    """The token says it may post (``scope`` has sns:share); a token that names no scopes (a PAT, a plain session) is
    let through and the SNS answers for itself."""
    from neonrp.core.chronicle import _claims

    c = _claims(token)
    return "scope" not in c or "sns:share" in str(c.get("scope") or "").split()


def _sns_lang(lang: str | None) -> str | None:
    return {"zh": "zh-CN", "en": "en", "ja": "ja", "ko": "ko"}.get(str(lang or ""))
