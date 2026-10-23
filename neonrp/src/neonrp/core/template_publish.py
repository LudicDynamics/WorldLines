"""Publish a template to the Hub's free zone with the author's Worldlines account (niko 10-16 · PLATFORM-PLAY-RULES-1015 §1:
Local creation desk → submit with the account → fields complete and the checks pass = public in the free zone at once,
moderated after; the author may later ask for the default zone). worldlines-platform docs/审核与分区-1015.md is the
platform side: ``hub:template`` is a work (storage files, publishable); ``publish {zone: "open"}`` runs the automatic
checks (``meta.lint``, no secrets in title / meta) and makes it public, or answers 422 checks_failed. The engine says
reviewed / open, the platform curated / open.

    POST /api/v1/local/templates/<id>/publish {lang?}   → 200 {id, ref, zone, status, revision, source, review?}
    GET  /api/v1/local/templates/<id>/publish?lang=     → {checks: {ok, problems}, work, signed_in}   (the dry run)
    POST /api/v1/local/templates/<id>/publish {zone: "curated", lang?}  → the default zone's review queue (the web desk)
    GET  /api/v1/local/hub/mine · POST …/hub/unpublish {id} · …/hub/submit {id} · …/hub/withdraw {id}   the author's own works
    GET  /api/v1/local/hub/open · …/hub/cover?id=      the free zone (no credential) · a work's cover
    POST /api/v1/local/hub/fetch {id} · …/hub/report {id, reason}   download to play locally · report a work
    errors: 401 not_signed_in · 403 insufficient_scope / anonymous · 404 · 409 taken_down / zone_locked ·
            422 checks_failed {problems} · 429 · 502 platform_error / unreachable — ``message`` in the author's language

Before anything goes up the engine runs the same three checks the Hub gate always had (core/hub_publish): no
key-shaped string or credential file in what ships (the template and every library soul it links), lint publishable
(no block), title + pitch in zh / en / ja / ko (the card, and the i18n layers' cards) — plus a cover. No play
certificate is asked for (lead 10-16).

Upload = the ordinary works channel (core/replay_share): register → lease → storage upload-url → PUT → complete →
publish. Files: ``package.zip`` (template/package.export_template: the template folder + the linked library souls,
「link 的角色复制进包」) and ``cover.<ext>``. The work id is ``<template id>-<6 hex>`` (official template ids stay the
officials'); publishing the same template again finds the author's work by ``meta.source`` and adds a revision.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from neonrp.core import replay_share as _rs

PRODUCT, KIND = "hub", "template"
LANGS = ("zh", "en", "ja", "ko")
META_MAX = 4000            # identity caps meta at 4096 bytes
ID_BASE_MAX = 41           # template ids are ≤ 48 (template/author.ID_RE); "-" + 6 hex fits
ZONE_IN = {"curated": "reviewed", "open": "open"}   # platform → engine
_COVER_CACHE: dict[tuple[str, int], tuple[bytes, str]] = {}
_COVER_CACHE_MAX = 64


class PublishError(_rs.ShareError):
    pass


def _msg(code: str, lang: str | None, **kw: Any) -> str:
    from neonrp.core.output_lang import normalize_prompt_lang
    from neonrp.prompts import strings

    s = str(strings("template_publish", normalize_prompt_lang(lang) if lang else "zh").get(code) or "")
    try:
        return s.format(**kw) if kw else s
    except (KeyError, IndexError):
        return s


def _fail(http: int, code: str, lang: str | None, extra: dict[str, Any] | None = None, **kw: Any) -> PublishError:
    return PublishError(http, code, _msg(code, lang, **kw) or code, extra)


def _auth() -> str:
    return _rs._issuer()


def _storage() -> str:
    return _rs.STORAGE.rstrip("/")


def _token(lang: str | None) -> str:
    from neonrp.core import worldlines_auth

    tok = worldlines_auth.access_token()
    if not tok or tok == "-":
        raise _fail(401, "not_signed_in", lang)
    return tok


def _call(method: str, url: str, token: str | None, body: Any = None, *, lang: str | None, step: str, **kw: Any) -> tuple[int, dict]:
    try:
        return _rs._call(method, url, token, body, step=step, **kw)
    except _rs.ShareError as e:
        raise _fail(502, "unreachable", lang, e.extra) from e


def _check(status: int, body: dict[str, Any], step: str, lang: str | None, ok: tuple[int, ...] = (200, 201)) -> dict[str, Any]:
    if status in ok:
        return body
    err = str(body.get("error") or "")
    detail = {"step": step, "status": status, **({"detail": body} if body else {})}
    if status == 401:
        raise _fail(401, "not_signed_in", lang, detail)
    if status == 403:
        raise _fail(403, "anonymous" if err == "anonymous_forbidden" else "insufficient_scope", lang, detail)
    if status == 404:
        raise _fail(404, "not_found", lang, detail)
    if status == 409 and err in ("taken_down", "published", "busy"):
        raise _fail(409, {"published": "zone_locked"}.get(err, err), lang, detail)
    if status == 422:
        fails = body.get("failures") if isinstance(body.get("failures"), list) else []
        probs = [{"code": f"platform.{f.get('check')}", "message": str(f.get("detail") or "")} for f in fails if isinstance(f, dict)]
        raise _fail(422, "checks_failed", lang, {**detail, "problems": probs})
    if status == 429:
        raise _fail(429, "rate_limited", lang, detail)
    raise _fail(502, "platform_error", lang, detail, step=step, status=status)


# ── the checks (nothing leaves the machine before they pass) ─────────────────

def _layer_card(t: Any, lg: str) -> dict[str, Any]:
    from neonrp.template import i18n as _i18n

    if lg == _i18n.source_lang(t):
        return dict(t.card)
    d = _i18n.layer_dir(t, lg)
    try:
        over = json.loads((d / "template.json").read_text(encoding="utf-8")) if d else {}
    except (OSError, ValueError):
        over = {}
    return dict((over or {}).get("card") or {}) if isinstance(over, dict) else {}


def cards(t: Any) -> dict[str, dict[str, Any]]:
    """{lang: the card as that language's players read it} — only what is really written in that language."""
    from neonrp.template import i18n as _i18n

    out = {}
    for lg in LANGS:
        own = _layer_card(t, lg)
        if own:
            out[lg] = own if lg == _i18n.source_lang(t) else _i18n.card(t, lg)
            out[lg]["_own"] = own
    return out


def _cover(t: Any) -> Path | None:
    c = str(t.card.get("cover") or "")
    p = (t.dir / c).resolve() if c else None
    return p if p and p.is_file() and p.is_relative_to(t.dir.resolve()) else None


def preflight(t: Any, *, lang: str | None = None, lint: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Every reason this template may not go public yet → [{code, message, where?}] (empty = it may)."""
    from neonrp import template as TP
    from neonrp.core.hub_publish import scan_for_secrets
    from neonrp.template import library_dir
    from neonrp.template.package import _linked

    out: list[dict[str, Any]] = []
    links = _linked(t)
    missing = [n for n in links if not (library_dir(n) / "soul.json").is_file()]
    if missing:
        out.append({"code": "souls", "message": _msg("p_souls", lang, names=", ".join(missing))})
    hits = [(f"{t.id}/{h.path}", h) for h in scan_for_secrets(t.dir)]
    for n in links:
        if n not in missing:
            hits += [(f"souls-lib/{n}/{h.path}", h) for h in scan_for_secrets(library_dir(n))]
    for where, h in hits[:20]:
        out.append({"code": "secret", "where": f"{where}:{h.line}", "message": _msg("p_secret", lang, where=f"{where}:{h.line}", kind=h.kind)})
    lint = lint if lint is not None else TP.lint(t)
    blocks = [p for p in lint.get("problems") or [] if p.get("level") == "block"]
    if not lint.get("publishable", not blocks):
        out.append({"code": "lint", "message": _msg("p_lint", lang, n=len(blocks)),
                    "items": [{"code": p.get("code"), "where": p.get("where"), "message": p.get("message")} for p in blocks[:8]]})
    cs = cards(t)
    gaps = [lg for lg in LANGS if not (str((cs.get(lg) or {}).get("_own", {}).get("title") or "").strip()
                                       and str((cs.get(lg) or {}).get("_own", {}).get("pitch") or "").strip())]
    if gaps:
        out.append({"code": "langs", "message": _msg("p_langs", lang, langs=" / ".join(gaps)), "langs": gaps})
    if _cover(t) is None:
        out.append({"code": "cover", "message": _msg("p_cover", lang)})
    return out


# ── what the listing carries (identity meta, ≤ 4 KB) ─────────────────────────

def _cut(s: Any, n: int) -> str:
    s = str(s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def listing_meta(t: Any, *, lint: dict[str, Any], cover_name: str | None, size: int, author: str = "") -> dict[str, Any]:
    from neonrp import __version__
    from neonrp.template import i18n as _i18n

    cs = cards(t)
    pc = str(getattr(t, "play_contract", "") or "")
    meta: dict[str, Any] = {
        "lint": {"errors": int((lint.get("counts") or {}).get("block") or 0), "warnings": int((lint.get("counts") or {}).get("warn") or 0)},
        "source": t.id, "version": str(t.version or ""), "engine": __version__,
        "lang": _i18n.source_lang(t), "langs": _i18n.langs(t),
        "title": {lg: _cut(c.get("title"), 80) for lg, c in cs.items()},
        "pitch": {lg: _cut(c.get("pitch"), 200) for lg, c in cs.items()},
        "tags": {lg: [_cut(x, 16) for x in (c.get("tags") or [])[:5] if isinstance(x, str)] for lg, c in cs.items() if isinstance(c.get("tags"), list)},
        **({"play_contract": pc} if pc else {}),
        "ending": str((t.mode or {}).get("ending") or ""),
        "cast": [_cut(n, 24) for n in _cast(t)][:8],
        **({"author": _cut(author, 40)} if author.strip() else {}),   # the web Hub labels community works with it (identity hides owner ids)
        "package": "package.zip", "size": size,
        **({"cover": cover_name} if cover_name else {}),
    }
    for shrink in (lambda m: m.pop("tags", None), lambda m: m.update(cast=m["cast"][:3]),
                   lambda m: m.update(pitch={k: _cut(v, 90) for k, v in m["pitch"].items()}), lambda m: m.pop("cast", None)):
        if len(json.dumps(meta, ensure_ascii=False).encode("utf-8")) <= META_MAX:
            break
        shrink(meta)
    return meta


def _cast(t: Any) -> list[str]:
    names: list[str] = []
    for p in t.soul_files():
        try:
            sj = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(sj, dict) and sj.get("name") and str(sj["name"]) not in names:
            names.append(str(sj["name"]))
    return names


# ── the author's works ───────────────────────────────────────────────────────

def _row(r: dict[str, Any]) -> dict[str, Any]:
    """An identity resource row as the screens read it (zone in the engine's words)."""
    rv = r.get("review") if isinstance(r.get("review"), dict) else {}
    return {"id": r.get("id"), "ref": f"{PRODUCT}/{KIND}/{r.get('id')}", "title": r.get("title"), "meta": r.get("meta") or {},
            "status": r.get("status"), "zone": ZONE_IN.get(str(r.get("zone") or ""), r.get("zone")),
            "revision": r.get("revision"), "published_revision": r.get("published_revision"),
            "published_at": r.get("published_at"), "updated_at": r.get("updated_at"),
            "review": {"state": rv.get("state") or "none", "note": rv.get("note"),   # autopass_at / held: the quick review (platform 86cb3f4)
                       **{k: rv[k] for k in ("autopass_at", "held") if rv.get(k) is not None}} if rv else None,
            "takedown": r.get("takedown"), "source": (r.get("meta") or {}).get("source")}


def _author(token: str, lang: str | None) -> str:
    """The name the author shows under (identity /v1/me display_name); "" when it cannot be read — never fatal."""
    try:
        st, body = _call("GET", f"{_auth()}/v1/me", token, lang=lang, step="me")
    except PublishError:
        return ""
    u = body.get("user") if st == 200 and isinstance(body.get("user"), dict) else {}
    return str(u.get("display_name") or "").strip()


def mine(*, lang: str | None = None, token: str | None = None) -> list[dict[str, Any]]:
    token = token or _token(lang)
    q = urllib.parse.urlencode({"scope": "mine", "product": PRODUCT, "kind": KIND, "limit": 100})
    body = _check(*_call("GET", f"{_auth()}/v1/resources?{q}", token, lang=lang, step="mine"), "mine", lang, ok=(200,))
    return [_row(r) for r in body.get("resources") or [] if isinstance(r, dict)]


def work_of(tid: str, works: list[dict[str, Any]]) -> dict[str, Any] | None:
    hits = [w for w in works if w.get("source") == tid]
    return sorted(hits, key=lambda w: str(w.get("updated_at") or ""))[-1] if hits else None


def new_id(tid: str) -> str:
    return f"{tid[:ID_BASE_MAX].rstrip('-')}-{secrets.token_hex(3)}"


def status(t: Any, *, lang: str | None = None, lint: dict[str, Any] | None = None) -> dict[str, Any]:
    """The dry run: what the checks say, and the author's work made from this template (when signed in)."""
    from neonrp.core import worldlines_auth

    probs = preflight(t, lang=lang, lint=lint)
    tok = worldlines_auth.access_token()
    work, err = None, None
    if tok and tok != "-":
        try:
            work = work_of(t.id, mine(lang=lang, token=tok))
        except PublishError as e:
            err = e.to_dict()
    signed = bool(tok and tok != "-")
    return {"checks": {"ok": not probs, "problems": probs}, "work": work, "signed_in": signed,
            "official": official_account(token=tok, lang=lang) if signed else False,   # 10-17: 「发布为官方」 shows
            **({"account_error": err} if err else {})}


def publish(t: Any, *, lang: str | None = None, lint: dict[str, Any] | None = None, zone: str = "open") -> dict[str, Any]:
    """Up as the author's work. ``zone="open"`` (the local desk): public in the free zone once the platform's checks pass.
    ``zone="curated"`` (the web Hub desk, PLATFORM-PLAY-RULES-1015 §1–2): into the default zone's review queue (202
    pending); a work already approved there keeps its approved version online while the new one waits."""
    from neonrp.template import TemplateError
    from neonrp.template.package import export_template

    probs = preflight(t, lang=lang, lint=lint)
    if probs:
        raise _fail(422, "checks_failed", lang, {"problems": probs})
    token = _token(lang)
    prev = work_of(t.id, mine(lang=lang, token=token))
    wid = str(prev["id"]) if prev else new_id(t.id)
    try:
        pkg = export_template(t, any_zone=True)   # the work goes up as the author's; downloads stay refused for the default zone
    except TemplateError as e:
        raise _fail(422, "checks_failed", lang, {"problems": [{"code": "package", "message": str(e)}]}) from e
    pkg = _with_builtin(pkg, t)
    files = {"package.zip": pkg}
    cov = _cover(t)
    cover_name = None
    if cov is not None:
        cover_name = f"cover{cov.suffix.lower()}"
        files[cover_name] = cov.read_bytes()
    from neonrp import template as TP

    lint = lint if lint is not None else TP.lint(t)
    meta = listing_meta(t, lint=lint, cover_name=cover_name, size=len(pkg), author=_author(token, lang))
    title = _cut(meta["title"].get(meta["lang"]) or next(iter(meta["title"].values()), "") or t.id, 200)
    auth = _auth()
    for attempt in range(2):
        st, body = _call("POST", f"{auth}/v1/resources", token, {"product": PRODUCT, "kind": KIND, "id": wid, "title": title, "meta": meta},
                         lang=lang, step="register")
        if st == 409 and str(body.get("error")) == "owned" and not prev and attempt == 0:
            wid = new_id(t.id)   # someone else holds that id: draw again
            continue
        _check(st, body, "register", lang)
        break
    ref = f"{PRODUCT}/{KIND}/{wid}"
    done = _upload(ref, token, files, title, meta, lang)
    # a work already in the default zone stays there: publishing it again is a review request (202; the approved version
    # stays online). A published work never changes zone by publish — moving up is `submit` (identity §4)
    keep = prev and prev.get("zone") == "reviewed"
    up = bool(zone == "curated" and prev and not keep and prev.get("status") == "published")
    if up:   # public in the free zone: ask to move up (it stays public there while it waits)
        st, pub = _call("POST", f"{auth}/v1/resources/{ref}/submit", token, {}, lang=lang, step="submit")
    else:
        body = {} if keep else {"zone": "curated" if zone == "curated" else "open"}
        st, pub = _call("POST", f"{auth}/v1/resources/{ref}/publish", token, body, lang=lang, step="publish")
    pub = _check(st, pub, "publish", lang, ok=(200, 202))
    r = pub.get("resource") or {}
    rev = (done.get("manifest") or {}).get("revision") or r.get("revision")
    want = "curated" if zone == "curated" else "open"
    msg = ("submitted" if up else "published_open" if st == 200 else "published_review" if keep and prev.get("status") == "published"
           else "submitted_curated")
    return {"id": wid, "ref": ref, "source": t.id, "zone": ZONE_IN.get(str(r.get("zone") or ""), "open" if up or want == "open" else "reviewed"),
            "status": r.get("status") or ("published" if st == 200 else "draft"), "revision": rev, "updated": bool(prev),
            **({"review": pub["review"]} if pub.get("review") else {}),
            "message": _msg(msg, lang)}


def _upload(ref: str, token: str, files: dict[str, bytes], title: str, meta: dict[str, Any], lang: str | None) -> dict[str, Any]:
    """lease → storage upload-url → PUT each file → complete (a new revision); the lease is released when it fails."""
    auth = _auth()
    lease = _check(*_call("POST", f"{auth}/v1/resources/{ref}/lease", token, {}, lang=lang, step="lease"), "lease", lang)
    lease_id = str(lease.get("lease_id") or lease.get("leaseId") or "")
    if not lease_id:
        raise _fail(502, "platform_error", lang, {"step": "lease"}, step="lease", status=200)
    try:
        want = [{"path": p, "size": len(b), "sha256": hashlib.sha256(b).hexdigest()} for p, b in files.items()]
        up = _check(*_call("POST", f"{_storage()}/v1/objects/{ref}/upload-url", token, {"leaseId": lease_id, "files": want},
                           lang=lang, step="upload-url"), "upload-url", lang)
        for u in up.get("uploads") or []:
            p = str(u.get("path") or "")
            if p in files:
                st, body = _call(str(u.get("method") or "PUT"), str(u["url"]), None, headers=dict(u.get("headers") or {}),
                                 raw=files[p], lang=lang, step=f"put {p}", platform=False)
                _check(st, body, f"put {p}", lang, ok=(200, 201, 204))
        done = _check(*_call("POST", f"{_storage()}/v1/objects/{ref}/complete", token, {"leaseId": lease_id, "title": title, "meta": meta},
                             lang=lang, step="complete"), "complete", lang)
    except PublishError:
        _call("DELETE", f"{auth}/v1/resources/{ref}/lease/{lease_id}", token, lang=lang, step="release")
        raise
    return done


def _with_builtin(pkg: bytes, t: Any) -> bytes:
    """A template on a built-in world (``world.builtin``) carries that world as ``_builtin/<name>/``: the browser engine
    has no built-in worlds of its own (hub/play/worker.js lays them in, as it does for a world pack); a local import
    ignores the folder (template/package.import_package reads the template and souls-lib only)."""
    import io
    import zipfile

    from neonrp import template as TP

    name = str((t.world or {}).get("builtin") or "")
    d = TP.world_dir(t) if name else None
    if d is None or not d.is_dir():
        return pkg
    buf = io.BytesIO(pkg)
    with zipfile.ZipFile(buf, "a", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(d.rglob("*")):
            if f.is_file() and not f.is_symlink() and "__pycache__" not in f.parts and f.name != ".DS_Store":
                z.write(f, f"_builtin/{name}/{f.relative_to(d).as_posix()}")
    return buf.getvalue()


def _owned(wid: str, lang: str | None) -> str:
    from neonrp.template.author import ID_RE

    if not wid or not ID_RE.match(wid):
        raise _fail(400, "bad_id", lang)
    return wid


def unpublish(wid: str, *, lang: str | None = None) -> dict[str, Any]:
    wid, token = _owned(wid, lang), _token(lang)
    body = _check(*_call("POST", f"{_auth()}/v1/resources/{PRODUCT}/{KIND}/{wid}/unpublish", token, {}, lang=lang, step="unpublish"),
                  "unpublish", lang, ok=(200,))
    return {"ok": True, "work": _row(body.get("resource") or {"id": wid}), "message": _msg("unpublished", lang)}


def withdraw(wid: str, *, lang: str | None = None) -> dict[str, Any]:
    """Take back a version waiting in the default zone's review (an approved version stays online)."""
    wid, token = _owned(wid, lang), _token(lang)
    body = _check(*_call("POST", f"{_auth()}/v1/resources/{PRODUCT}/{KIND}/{wid}/withdraw", token, {}, lang=lang, step="withdraw"),
                  "withdraw", lang, ok=(200,))
    return {"ok": True, "work": _row(body.get("resource") or {"id": wid}), "message": _msg("withdrawn", lang)}


def submit(wid: str, *, lang: str | None = None) -> dict[str, Any]:
    """Ask for the default zone: the review queue; the work stays public in the free zone while it waits."""
    wid, token = _owned(wid, lang), _token(lang)
    body = _check(*_call("POST", f"{_auth()}/v1/resources/{PRODUCT}/{KIND}/{wid}/submit", token, {}, lang=lang, step="submit"),
                  "submit", lang, ok=(200, 202))
    return {"ok": True, "review": body.get("review"), "work": _row(body.get("resource") or {"id": wid}), "message": _msg("submitted", lang)}


def _reader() -> str | None:
    """The signed-in player's token for a public listing (identity then leaves out the authors they blocked), or None."""
    from neonrp.core import worldlines_auth

    tok = worldlines_auth.access_token()
    return tok if tok and tok != "-" else None


# ── blocking an author (App Store 1.2 · identity feat/block-owner 32a8aab): by one of their works; the owner id never shows ──

def block(wid: str, *, lang: str | None = None) -> dict[str, Any]:
    wid, token = _owned(wid, lang), _token(lang)
    body = _check(*_call("POST", f"{_auth()}/v1/resources/{PRODUCT}/{KIND}/{wid}/block-owner", token, {}, lang=lang, step="block"),
                  "block", lang, ok=(200, 201))
    return {"ok": True, "block": body.get("block"), "created": bool(body.get("created")), "message": _msg("blocked", lang)}


def unblock(wid: str, *, lang: str | None = None) -> dict[str, Any]:
    wid, token = _owned(wid, lang), _token(lang)
    body = _check(*_call("DELETE", f"{_auth()}/v1/resources/{PRODUCT}/{KIND}/{wid}/block-owner", token, lang=lang, step="unblock"),
                  "unblock", lang, ok=(200,))
    return {"ok": True, "unblocked": bool(body.get("unblocked")), "message": _msg("unblocked", lang)}


def blocks(*, lang: str | None = None) -> list[dict[str, Any]]:
    token = _token(lang)
    body = _check(*_call("GET", f"{_auth()}/v1/me/blocks?product={PRODUCT}", token, lang=lang, step="blocks"), "blocks", lang, ok=(200,))
    return [b for b in body.get("blocks") or [] if isinstance(b, dict)]


def report(wid: str, reason: str, *, lang: str | None = None) -> dict[str, Any]:
    wid, token = _owned(wid, lang), _token(lang)
    reason = str(reason or "").strip()[:500]
    if not reason:
        raise _fail(400, "no_reason", lang)
    body = _check(*_call("POST", f"{_auth()}/v1/resources/{PRODUCT}/{KIND}/{wid}/report", token, {"reason": reason}, lang=lang,
                         step="report"), "report", lang)
    return {"ok": True, "created": bool(body.get("created")), "message": _msg("reported", lang)}


# ── the free zone, read without a credential ─────────────────────────────────

def open_works(*, client: str = "local", lang: str | None = None) -> list[dict[str, Any]]:
    """The free zone's templates (``client=ios`` never gets them — identity's rule, not ours)."""
    q = urllib.parse.urlencode({"product": PRODUCT, "kind": KIND, "zones": "open", "client": client, "limit": 100})
    body = _check(*_call("GET", f"{_auth()}/v1/public/resources?{q}", _reader(), lang=lang, step="open"), "open", lang, ok=(200,))
    return [_row(r) for r in body.get("resources") or [] if isinstance(r, dict) and r.get("zone") == "open"]


def _public_files(wid: str, lang: str | None) -> dict[str, Any]:
    wid = _owned(wid, lang)
    return _check(*_call("GET", f"{_storage()}/v1/public/objects/{PRODUCT}/{KIND}/{wid}/download-url", None, lang=lang, step="download-url"),
                  "download-url", lang, ok=(200,))


def _get(url: str, lang: str | None, limit: int = 300 * 1024 * 1024) -> bytes:
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=120) as r:
            data = r.read(limit + 1)
    except Exception as e:  # noqa: BLE001
        raise _fail(502, "unreachable", lang, {"step": "download"}) from e
    if len(data) > limit:
        raise _fail(422, "too_large", lang)
    return data


def cover(wid: str) -> tuple[bytes, str] | None:
    """The published cover's bytes + content type (kept in memory per revision; the signed URLs expire in minutes)."""
    try:
        d = _public_files(wid, None)
    except PublishError:
        return None
    key = (wid, int(d.get("revision") or 0))
    if key in _COVER_CACHE:
        return _COVER_CACHE[key]
    f = next((f for f in d.get("files") or [] if str(f.get("path") or "").startswith("cover.")), None)
    if not f:
        return None
    try:
        data = _get(str(f["url"]), None, limit=16 * 1024 * 1024)
    except PublishError:
        return None
    ct = _sniff(data) or {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(
        str(f["path"]).rsplit(".", 1)[-1].lower(), "application/octet-stream")   # what the bytes are (a .png may be a JPEG)
    if len(_COVER_CACHE) >= _COVER_CACHE_MAX:
        _COVER_CACHE.pop(next(iter(_COVER_CACHE)))
    _COVER_CACHE[key] = (data, ct)
    return data, ct


def _sniff(b: bytes) -> str | None:
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    return None


def fetch(wid: str, *, lang: str | None = None) -> dict[str, Any]:
    """Download a public work and install it as a local template (template/package.import_package: checked, never
    run). It lands under the work id; a taken id gets the next free ``-2`` …; it is marked as a free-zone work."""
    from neonrp import template as TP
    from neonrp.template import TemplateError
    from neonrp.template.author import write_root
    from neonrp.template.package import _free, import_package

    d = _public_files(wid, lang)
    f = next((f for f in d.get("files") or [] if f.get("path") == "package.zip"), None)
    if not f:
        raise _fail(404, "not_found", lang)
    data = _get(str(f["url"]), lang)
    if f.get("sha256") and hashlib.sha256(data).hexdigest() != f["sha256"]:
        raise _fail(502, "platform_error", lang, {"step": "download"}, step="download", status="sha256")
    root = write_root()
    if root is None:
        raise _fail(409, "no_store", lang)
    found = TP.discover()
    tid = _free(wid[:48], lambda n: n in found or (root / f"{n}.template").exists())
    try:
        out = import_package(data, new_id=tid)
    except TemplateError as e:
        raise _fail(422, "bad_package", lang, {"detail": str(e)}) from e
    if out.get("kind") != "template":
        raise _fail(422, "bad_package", lang)
    tj = root / f"{out['id']}.template" / "template.json"
    try:
        d2 = json.loads(tj.read_text(encoding="utf-8"))
        d2["zone"] = "open"
        d2["hub_ref"] = f"{PRODUCT}/{KIND}/{wid}"
        tj.write_text(json.dumps(d2, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError):
        pass
    return {"ok": True, "id": out["id"], "ref": f"{PRODUCT}/{KIND}/{wid}", "revision": d.get("revision"), "title": out.get("title"),
            "souls": out.get("souls") or [], **({"renamed_from": wid} if out["id"] != wid else {}), "message": _msg("fetched", lang)}


# ── official worlds (niko 10-17) ─────────────────────────────────────────────
# The local edition ships two worlds; every other official world goes up from the official account's local creation
# desk to the default zone (identity: curated) and comes down to signed-in local players. Its work id is the template id
# itself (no hex suffix): what a player fetches, a replay cites and a character link names stays the same id. Who is
# official is identity's answer (/v1/me user.official — ID_OFFICIAL_OWNERS, platform P2); NEONRP_OFFICIAL_PUBLISH=1
# shows the desk's button before that lands (the platform still decides: without P2 a curated publish waits for review).

def official_account(*, token: str | None = None, lang: str | None = None) -> bool:
    import os

    if os.environ.get("NEONRP_OFFICIAL_PUBLISH", "").strip() == "1":
        return True
    from neonrp.core import worldlines_auth

    tok = token or worldlines_auth.access_token()
    if not tok or tok == "-":
        return False
    try:
        st, body = _call("GET", f"{_auth()}/v1/me", tok, lang=lang, step="me")
    except PublishError:
        return False
    return st == 200 and isinstance(body.get("user"), dict) and body["user"].get("official") is True


def _ver(v: str) -> tuple[int, ...] | None:
    parts = str(v or "").strip().split(".")
    return tuple(int(x) for x in parts) if parts and all(x.isdigit() for x in parts) else None


def _next_ver(v: str) -> str:
    t = _ver(v)
    return ".".join(map(str, (*t[:-1], t[-1] + 1))) if t else "1.0"


def _as_official(t: Any) -> Any:
    """The template as the default zone sees it (in memory): zone reviewed, so the lint grades it the way it is graded there."""
    from neonrp import template as TP

    t2 = TP.load(t.dir)
    t2.data = {**t2.data, "zone": "reviewed"}
    return t2


def _retag(pkg: bytes, tid: str, patch: dict[str, Any], drop: tuple[str, ...]) -> bytes:
    """The package's template.json with ``patch`` laid over and ``drop`` taken out (the source folder is not touched)."""
    import io
    import zipfile

    name = f"{tid}.template/template.json"
    src = zipfile.ZipFile(io.BytesIO(pkg))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i in src.infolist():
            data = src.read(i)
            if i.filename == name:
                d = json.loads(data)
                for k in drop:
                    d.pop(k, None)
                d.update(patch)
                data = (json.dumps(d, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            z.writestr(i, data)
    return buf.getvalue()


def publish_official(t: Any, *, lang: str | None = None, lint: dict[str, Any] | None = None) -> dict[str, Any]:
    """「发布为官方」: the official account puts this template up as ``hub/template/<template id>`` in the default zone —
    a new revision each time; the version must go up. → {id, ref, zone, status, revision, version, message}."""
    from neonrp import template as TP
    from neonrp.template import TemplateError
    from neonrp.template.author import ID_RE
    from neonrp.template.package import export_template

    if not ID_RE.match(t.id or ""):
        raise _fail(400, "bad_id", lang)
    t2 = _as_official(t)
    lint = lint if lint is not None and t.zone == "reviewed" else TP.lint(t2)
    probs = preflight(t2, lang=lang, lint=lint)
    if probs:
        raise _fail(422, "checks_failed", lang, {"problems": probs})
    token = _token(lang)
    if not official_account(token=token, lang=lang):
        raise _fail(403, "official_only", lang)
    prev = next((w for w in mine(lang=lang, token=token) if w.get("id") == t.id), None)
    pv = str(((prev or {}).get("meta") or {}).get("version") or "")
    if prev and pv:
        a, b = _ver(t.version), _ver(pv)
        if not (a > b if a is not None and b is not None else t.version and t.version != pv):
            raise _fail(409, "official_version", lang, {"previous": pv}, prev=pv, next=_next_ver(pv))
    try:
        pkg = export_template(t, any_zone=True)
    except TemplateError as e:
        raise _fail(422, "checks_failed", lang, {"problems": [{"code": "package", "message": str(e)}]}) from e
    pkg = _with_builtin(_retag(pkg, t.id, {"zone": "reviewed"}, ("official", "hub_ref", "hub_revision")), t)
    files = {"package.zip": pkg}
    cov = _cover(t)
    cover_name = None
    if cov is not None:
        cover_name = f"cover{cov.suffix.lower()}"
        files[cover_name] = cov.read_bytes()
    meta = {**listing_meta(t2, lint=lint, cover_name=cover_name, size=len(pkg)), "official": True}
    title = _cut(meta["title"].get(meta["lang"]) or next(iter(meta["title"].values()), "") or t.id, 200)
    auth, ref = _auth(), f"{PRODUCT}/{KIND}/{t.id}"
    st, body = _call("POST", f"{auth}/v1/resources", token, {"product": PRODUCT, "kind": KIND, "id": t.id, "title": title, "meta": meta},
                     lang=lang, step="register")
    if st == 409 and str(body.get("error")) == "owned":
        raise _fail(409, "official_id_taken", lang, {"id": t.id}, id=t.id)
    _check(st, body, "register", lang)
    done = _upload(ref, token, files, title, meta, lang)
    st, pub = _call("POST", f"{auth}/v1/resources/{ref}/publish", token, {"zone": "curated"}, lang=lang, step="publish")
    pub = _check(st, pub, "publish", lang, ok=(200, 202))
    r = pub.get("resource") or {}
    rev = (done.get("manifest") or {}).get("revision") or r.get("revision")
    live = st == 200
    return {"id": t.id, "ref": ref, "source": t.id, "zone": "reviewed", "official": True, "version": t.version, "revision": rev,
            "status": "published" if live else "pending", "updated": bool(prev),
            **({"review": pub["review"]} if pub.get("review") else {}),
            "message": _msg("official_live" if live else "official_review", lang, rev=rev)}


def _installed() -> dict[str, dict[str, Any]]:
    """template id → what this machine has of it: where (builtin · source · official · store), version, revision."""
    from neonrp import template as TP
    from neonrp.core.paths import official_dir
    from neonrp.template import author

    off = official_dir()
    out: dict[str, dict[str, Any]] = {}
    for tid, d in TP.discover().items():
        try:
            t = TP.load(d)
        except TP.TemplateError:
            continue
        where = ("official" if off is not None and d.parent == off else "store" if author.writable(t)
                 else "builtin" if t.builtin else "source")
        out[tid] = {"where": where, "version": t.version, "revision": t.data.get("hub_revision"), "zone": t.zone}
    return out


def official_works(*, lang: str | None = None) -> dict[str, Any]:
    """The default zone's worlds for the local Hub (niko 10-17): signed out → nothing (only what this machine has);
    signed in → every published default-zone template, the official ones marked, each with what is installed here and
    whether a newer revision is up. → {signed_in, works: [row + installed? + update + official]}."""
    from neonrp.core import worldlines_auth

    tok = worldlines_auth.access_token()
    if not tok or tok == "-":
        return {"signed_in": False, "works": []}
    q = urllib.parse.urlencode({"product": PRODUCT, "kind": KIND, "zones": "curated", "client": "local", "limit": 100})
    body = _check(*_call("GET", f"{_auth()}/v1/public/resources?{q}", tok, lang=lang, step="official"), "official", lang, ok=(200,))   # with the token: authors I blocked are left out
    have = _installed()
    works = []
    for r in body.get("resources") or []:
        if not isinstance(r, dict) or r.get("zone") != "curated":
            continue
        w = _row(r)
        w["official"] = r.get("official") is True   # identity's mark (P2); meta.official is only the publisher's word
        w["version"] = str((w.get("meta") or {}).get("version") or "")
        h = have.get(str(w["id"]))
        w["installed"] = h
        rev = int(w.get("published_revision") or r.get("revision") or 0)
        w["update"] = bool(h and h["where"] == "official" and rev > int(h.get("revision") or 0))
        works.append(w)
    return {"signed_in": True, "works": works}


def _is_official(wid: str, token: str, lang: str | None) -> bool:
    """Is this default-zone work the official account's (identity's mark on the listing)? A community work fetched to play
    (niko 10-21: iOS plays approved community works) must not come down labelled official. Unknown = False."""
    q = urllib.parse.urlencode({"product": PRODUCT, "kind": KIND, "zones": "curated", "client": "local", "limit": 100})
    try:
        st, body = _call("GET", f"{_auth()}/v1/public/resources?{q}", token, lang=lang, step="official")
    except PublishError:
        return False
    return st == 200 and any(isinstance(r, dict) and r.get("id") == wid and r.get("official") is True for r in body.get("resources") or [])


def fetch_official(wid: str, *, lang: str | None = None, busy: Any = None) -> dict[str, Any]:
    """「获取」/「更新」a default-zone world into the official cache under its own id (a newer copy swaps the old one out
    whole; runs already started are copies and stay as they were). Signed-in full accounts only — storage hands the
    curated package to our apps' tokens (platform P1). ``busy(tid)`` → True while a turn of a run on it is in flight."""
    from neonrp import template as TP
    from neonrp.core.paths import official_dir
    from neonrp.template import TemplateError
    from neonrp.template.package import import_package

    wid = _owned(wid, lang)
    token = _token(lang)
    root = official_dir()
    if root is None:
        raise _fail(409, "no_store", lang)
    if busy is not None and busy(wid):
        raise _fail(409, "official_running", lang)
    d = _check(*_call("GET", f"{_storage()}/v1/objects/{PRODUCT}/{KIND}/{wid}/download-url?revision=published", token, lang=lang,
                      step="download-url"), "download-url", lang, ok=(200,))
    f = next((f for f in d.get("files") or [] if f.get("path") == "package.zip"), None)
    if d.get("limited") or not f:
        raise _fail(403, "official_locked", lang)
    data = _get(str(f["url"]), lang)
    if f.get("sha256") and hashlib.sha256(data).hexdigest() != f["sha256"]:
        raise _fail(502, "platform_error", lang, {"step": "download"}, step="download", status="sha256")
    had = (root / f"{wid}.template").is_dir()
    rev = d.get("published_revision") or d.get("revision")
    try:
        out = import_package(data, new_id=wid, into=root, replace=True,
                             patch={"zone": "reviewed", "official": _is_official(wid, token, lang), "hub_ref": f"{PRODUCT}/{KIND}/{wid}", "hub_revision": rev})
    except TemplateError as e:
        raise _fail(422, "bad_package", lang, {"detail": str(e)}) from e
    if out.get("kind") != "template":
        raise _fail(422, "bad_package", lang)
    hit = TP.discover().get(wid)
    shadowed = hit is not None and hit.parent != root
    msg = _msg("official_updated" if had else "official_fetched", lang)
    if shadowed and _installed().get(wid, {}).get("where") == "store":
        msg += " " + _msg("official_shadowed", lang, id=wid)
    return {"ok": True, "id": wid, "ref": f"{PRODUCT}/{KIND}/{wid}", "revision": rev, "updated": had, "title": out.get("title"),
            "souls": out.get("souls") or [], **({"shadowed": True} if shadowed else {}), "message": msg}
