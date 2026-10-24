"""「画这一幕」— a picture of one beat, drawn on demand (10-16; worldlines-platform docs/实时生图-1015.md).

The author's pictures come first and are free: a beat that already showed one (opening CG · a ``show`` · a stage CG · a
milestone's own CG) answers with that slot, and the front end shows it. Only a moment without a picture is drawn, by the
platform (ai ``POST /v1/images/generate``: Traveler / Voyager, paid in credits); the engine never draws on its own.

    mode(root)              the world's switch, template.json ``realtime_art``: off (left out) · scene_only · full —
                            off = nothing is drawn live (brief → {disabled: true, reason: realtime_art_off, cg}; the
                            generate door refuses), the author's pictures still show; scene_only = the place, nobody in it
    brief(root, reg, i)     what beat ``i`` (the turn record's index, as /traces lists it) would be drawn from:
                            {i, world_ref, kind, cg?, fields: {scene, caption, style, world_ref, kind, size}, extended}
                            ``fields`` = exactly what the platform takes today (scene ≤ 600 · caption ≤ 200 · style ≤ 200);
                            ``extended`` = the same moment, structured (place · characters with their look · the moment ·
                            the full style · reference pictures) — sent alongside, ignored until the platform reads it.
    listing / record / forget   the pictures this run drew: <data>/meta/scene_art.json {items: [{id, i, caption, …}]}
                            (+ ``cg``: the beats that already showed the author's picture)
                            (the image itself lives in the player's storage, hub:scene-image; one the platform could not
                            store comes back inline and is kept here: <data>/assets/scene-art/<id>.png)
    platform(op, …)         the local engine's door to ai / billing with its own Worldlines sign-in
                            (core/worldlines_auth); the browser build's page calls them itself (hub/play/boot.js)

What a picture may be made of is only what the player saw: the beat's lines as shown (player view, core/play_view.trace:
no host notes, no truths), the place they stand in, the people on stage with how they look (``character/profile.json``
``appearance``; a name only once met), the world's locked style (template ``ui.recipe.style`` > ``assets/art-style.md`` >
the engine's default — the same one the author's pictures were drawn with). Marks, ops (``[op …]`` / ``[~op …]``),
engine messages (``<…>``), out-of-character asides and the options are taken out. Reference pictures: each person's own
``portrait`` / ``sprite`` / ``base`` and the place's scene picture — never a ``-cNN`` candidate.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

LIMITS = {"scene": 600, "caption": 200, "style": 200}  # ai realtime.mjs today
SIZE = "1536x1024"
REF_STEMS = ("portrait", "sprite", "base")
MAX_REFS = 4
CANDIDATE = re.compile(r"-c\d+$", re.I)  # a pipeline's spare candidate (stand-c01.png): never a reference
_FILE = "scene_art.json"
_ID = re.compile(r"^si-[0-9a-f-]{36}$")

# what never goes into a picture's text
_MARK = re.compile(r"\d+|[-]")
_OPS = re.compile(r"\[\[[^\]]*\]\]|\[~?[a-z_][\w.-]*(?:\s[^\]]*)?\]")
_ENGINE = re.compile(r"<[^<>\n]{0,200}>")
_OOC: re.Pattern[str] | None = None  # built from the four tables (prompts/scene_art.*.json): an aside in any language


def _ooc() -> re.Pattern[str]:
    global _OOC
    if _OOC is None:
        from neonrp import prompts

        words = sorted({str(w) for lg in prompts.LANGS for w in prompts.strings("scene_art", lg).get("ooc") or [] if w}, key=len, reverse=True)
        _OOC = re.compile(r"[(\uff08\[\u3010]\s*(?:" + "|".join(map(re.escape, words)) + r")[^)\uff09\]\u3011]*[)\uff09\]\u3011]", re.I)
    return _OOC
_OPTION = re.compile(r"^\s*(?:[①-⑳]|\d+[.、)]|[-*•]\s|\[options)")
_DICE = re.compile(r"^\s*\[?(?:🎲|d\d+|\d+d\d+)", re.I)


def _meta(root: Path) -> Path:
    from neonrp.core.paths import get_data_dir_name

    return Path(root) / get_data_dir_name(root) / "meta"


def _j(p: Path, default: Any = None) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def clean(text: Any) -> str:
    """A line as a picture may use it: no marks, ops, engine messages, asides, options, dice."""
    s = _ooc().sub("", _ENGINE.sub("", _OPS.sub("", _MARK.sub("", str(text or "")))))
    keep = [ln.strip() for ln in s.splitlines() if ln.strip() and not _OPTION.match(ln) and not _DICE.match(ln)]
    return re.sub(r"\s+", " ", " ".join(keep)).strip()


def cut(text: str, n: int) -> str:
    """At most ``n`` characters, ended at a sentence (or a clause) when one is near."""
    text = (text or "").strip()
    if len(text) <= n:
        return text
    head = text[:n]
    for marks in ("。!?!?.」", ",,;;、 "):
        k = max(head.rfind(m) for m in marks)
        if k >= n * 0.6:
            return head[:k + 1].strip()
    return head.rstrip() + "…"


def _end(s: str) -> str:
    s = s.strip()
    return s if not s or s[-1] in "。.!?!?」』…" else s + "."


# ── the world's style ────────────────────────────────────────────────────

def style(root: Path) -> str:
    from neonrp.core import worldmap

    rec = _j(_meta(root) / "template.json", {}) or {}
    ui = rec.get("ui") if isinstance(rec.get("ui"), dict) else {}
    own = str(((ui.get("recipe") or {}) if isinstance(ui.get("recipe"), dict) else {}).get("style") or "").strip()
    return own or worldmap.art_style(Path(root))


def mode(root: Path) -> str:
    """The world's switch (template.json ``realtime_art``: off | scene_only | full; left out = off, 10-16)."""
    from neonrp.template import REALTIME_ART

    rec = _j(_meta(root) / "template.json", {}) or {}
    v = rec.get("realtime_art") if isinstance(rec, dict) else None
    return v if v in REALTIME_ART else "off"


def world_ref(root: Path) -> str:
    rec = _j(_meta(root) / "template.json", {}) or {}
    tid = str(rec.get("id") or "") if isinstance(rec, dict) else ""
    return f"hub/template/{tid}" if tid else f"local/{Path(root).name}"[:200]


# ── one beat ─────────────────────────────────────────────────────────────

def _beat_lines(pv: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(narration, speech) of a beat as the player saw it."""
    ap = pv.get("apply") or {}
    beat = ap.get("beat") if isinstance(ap.get("beat"), dict) else {}
    narr: list[str] = []
    said: list[str] = []
    script = beat.get("script") if isinstance(beat.get("script"), list) else []
    for x in script:
        if not isinstance(x, dict) or x.get("role") == "player":
            continue
        (narr if x.get("role") in ("host", "handoff", None) else said).append(clean(x.get("text")))
    if not script:
        narr.append(clean(ap.get("narration_plain") or ((ap.get("proposals") or [{}])[-1] or {}).get("narration")))
        said += [clean(s.get("speech")) for s in pv.get("souls") or [] if isinstance(s, dict)]
    return [x for x in narr if x], [x for x in said if x]


def _addr(root: Path, tree: dict[str, Any], loc: str | None) -> str:
    loc = str(loc or "")
    nodes = tree.get("nodes") or {}
    if not loc or loc in nodes:
        return loc
    try:
        from neonrp.core.place_nav import qualify_location

        q = qualify_location(Path(root), loc)
        if q in nodes:
            return q
    except Exception:  # noqa: BLE001
        pass
    return next((a for a in nodes if a.endswith("/" + loc)), loc)


def _place(root: Path, tree: dict[str, Any], addr: str) -> dict[str, Any]:
    n = (tree.get("nodes") or {}).get(addr) or {}
    detail = n.get("detail") if isinstance(n.get("detail"), dict) else {}
    text = str(n.get("summary") or detail.get("description") or "")
    if not text and "/" in addr:  # the place's own file (what the player sees standing there)
        town, node = addr.split("/", 1)
        text = str((_j(Path(root) / "game" / "locations" / town / node / "location.json", {}) or {}).get("summary") or "")
    par = (tree.get("nodes") or {}).get(str(n.get("parent") or "")) or {}
    return {"addr": addr, "name": str(n.get("name") or ""), "parent": str(par.get("name") or ""), "summary": clean(text)}


def _ref_file(d: Path | None) -> list[Path]:
    if d is None or not (d / "assets").is_dir():
        return []
    out = []
    for stem in REF_STEMS:
        for p in sorted((d / "assets").glob(f"{stem}.*")):
            if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") and not CANDIDATE.search(p.stem):
                out.append(p)
                break
    return out


def _ref(root: Path, p: Path, kind: str, slot: str, name: str = "") -> dict[str, Any]:
    try:
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        sha = ""
    return {"kind": kind, "slot": slot, "name": name, "path": p.relative_to(root).as_posix(), "sha256": sha}


def _cast(root: Path, reg: Any, pv: dict[str, Any], latest: bool) -> list[dict[str, Any]]:
    """The people on stage in this beat, as the player knows them: the ones the beat judged, and (the newest beat) everyone
    standing with the player now."""
    from neonrp.core import people as P
    from neonrp.core.play_view import _present

    try:
        known = {str(r["id"]): r for r in P.people(root)["people"]}
    except Exception:  # noqa: BLE001
        known = {}
    on = list(dict.fromkeys([*_present(pv.get("apply") or {}), *(i for i, r in known.items() if latest and r.get("here"))]))
    dirs = P._soul_dirs(Path(root))
    out = []
    for iid in on:
        r = known.get(iid) or {}
        e = reg.entries.get(iid) if reg is not None else None
        d = dirs.get(iid)
        prof = (_j(d / "character" / "profile.json", {}) or {}) if d else {}
        props = (e.props or {}) if e is not None else {}
        look = clean(prof.get("appearance") or props.get("appearance") or props.get("look") or "")
        sid = str(r.get("sid") or (_j(d / "soul.json", {}) or {}).get("sid") or iid) if d else str(r.get("sid") or iid)
        out.append({"iid": iid, "sid": sid, "kind": str(r.get("kind") or (e.cls if e is not None else "")),
                    "name": str(r.get("name") or ""),  # empty = not met: drawn, never named
                    "role": str(r.get("role_label") or ""), "look": look,
                    "refs": [_ref(root, p, "character", f"soul.{p.stem}:{sid}", str(r.get("name") or "")) for p in _ref_file(d)]})
    return out[:4]


def _cg(root: Path, t: dict[str, Any]) -> dict[str, Any] | None:
    """The author's picture this beat already put on screen (free)."""
    from neonrp.core import beat_events

    try:
        evs, _ = beat_events.from_traces([t], root=root)
    except Exception:  # noqa: BLE001
        return None
    for k, d in evs:
        if k == "show" and d.get("slot"):
            return {"slot": str(d["slot"]), "label": d.get("label") or d.get("caption") or "", "by": "show"}
        if k == "stage.changed" and isinstance(d.get("cg"), dict) and d["cg"].get("slot"):
            return {"slot": str(d["cg"]["slot"]), "label": d["cg"].get("caption") or d.get("name") or "", "by": "stage"}
        if k == "milestone" and isinstance(d.get("art"), dict) and d["art"].get("kind") == "cg" and d["art"].get("slot"):
            return {"slot": str(d["art"]["slot"]), "label": d.get("label") or "", "by": "milestone"}
        if k == "plan.beat" and d.get("opening") and isinstance(d.get("cg"), list) and d["cg"]:
            c = d["cg"][-1]
            return {"slot": str(c.get("slot") or ""), "label": c.get("caption") or "", "by": "opening"} if c.get("slot") else None
    return None


def brief(root: Path, reg: Any = None, i: int | None = None, *, branch: str | None = None, kind: str | None = None,
          caption: str | None = None) -> dict[str, Any]:
    from neonrp.core import play_view, worldmap
    from neonrp.core.orchestration_trace import read_turn_traces
    from neonrp.core.registry import load_registry

    root = Path(root)
    reg = reg if reg is not None else load_registry(root)
    trs = read_turn_traces(root, branch)
    if not trs:
        raise LookupError("no beats yet")
    i = len(trs) - 1 if i is None else int(i)
    if not 0 <= i < len(trs):
        raise LookupError(f"no beat {i}")
    t = trs[i]
    art = mode(root)
    if art == "off":  # the world draws nothing live: only the author's picture of this beat, if it has one
        return {"i": i, "latest": i == len(trs) - 1, "realtime_art": "off", "disabled": True, "reason": "realtime_art_off", "cg": _cg(root, t)}
    pv = play_view.trace(t)
    latest = i == len(trs) - 1
    try:
        tree = worldmap.build_map_tree(root)
    except Exception:  # noqa: BLE001
        tree = {"nodes": {}}
    # where the beat left the player: the next record's start, or (the newest) where they stand now
    loc = reg.player_location if latest else (trs[i + 1].get("world_location") or t.get("world_location"))
    place = _place(root, tree, _addr(root, tree, loc))
    cast = _cast(root, reg, pv, latest) if art == "full" else []  # scene_only: the place, nobody in it
    narr, said = _beat_lines(pv)
    st = style(root)
    kind = kind if kind in ("place", "milestone") else "place"

    who = "; ".join(f"{p['name'] or p['role'] or 'someone'}: {cut(p['look'], 90)}" if p["look"] else (p["name"] or p["role"] or "someone")
                    for p in cast)
    bits = [f"Place: {place['name']}" + (f" ({place['parent']})" if place["parent"] else "") + (f" — {cut(place['summary'], 150)}" if place["summary"] else ""),
            f"People: {cut(who, 230)}" if who else ("No people in the picture" if art == "scene_only" else "")]
    head = " ".join(_end(b) for b in bits if b.strip())
    moment = cut(" ".join(narr) or " ".join(said), max(80, LIMITS["scene"] - len(head) - 10))
    scene = cut(f"{head} Moment: {moment}" if moment else head, LIMITS["scene"]) or (place["name"] or "a quiet moment")
    cap = cut(clean(caption) if caption else (said[0] if said and art == "full" else ""), LIMITS["caption"]) or None
    refs = [r for p in cast for r in p["refs"][:1]]
    sp = worldmap.scene_image_path(root, place["addr"]) if place["addr"] else None
    if sp is not None and not CANDIDATE.search(sp.stem):
        refs.insert(0, _ref(root, sp, "place", f"place.scene:{place['addr']}", place["name"]))
    fields = {"scene": scene, "style": cut(st, LIMITS["style"]), "world_ref": world_ref(root), "kind": kind, "size": SIZE}
    if cap:
        fields["caption"] = cap
    return {
        "i": i, "latest": latest, "realtime_art": art, "disabled": False, "world_ref": fields["world_ref"], "kind": kind, "cg": _cg(root, t),
        "fields": fields,
        "extended": {
            "place": {"name": place["name"], "parent": place["parent"], "summary": cut(place["summary"], 300)},
            "characters": [{"name": p["name"], "role": p["role"] if not p["name"] else "", "look": cut(p["look"], 200),
                            "ref": (p["refs"][0]["slot"] if p["refs"] else None)} for p in cast],
            "moment": cut(" ".join(narr), 600), "lines": [cut(x, 120) for x in said[:3]],
            "style_full": cut(st, 800), "style_locked": True, "references": refs[:MAX_REFS], "people": art == "full",
        },
    }


# ── this run's pictures ──────────────────────────────────────────────────

def _store(root: Path) -> dict[str, Any]:
    d = _j(_meta(root) / _FILE, {}) or {}
    return {"items": [x for x in d.get("items") or [] if isinstance(x, dict) and x.get("id")]}


def _save(root: Path, d: dict[str, Any]) -> None:
    p = _meta(root) / _FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _inline(root: Path, iid: str) -> Path:
    from neonrp.core.paths import get_data_dir_name

    return Path(root) / get_data_dir_name(root) / "assets" / "scene-art" / f"{iid}.png"


def listing(root: Path, branch: str | None = None) -> dict[str, Any]:
    """The pictures drawn so far, and the beats that already have the author's picture (``cg``: {i: {slot, label}})."""
    from neonrp.core.orchestration_trace import read_turn_traces

    items = _store(root)["items"]
    cg = {}
    for i, t in enumerate(read_turn_traces(Path(root), branch)):
        c = _cg(Path(root), t)
        if c:
            cg[str(i)] = c
    return {"items": [{**x, "local": _inline(root, x["id"]).is_file()} for x in items], "cg": cg, "realtime_art": mode(Path(root))}


def record(root: Path, body: dict[str, Any]) -> dict[str, Any]:
    """Keep a drawn picture with the beat it belongs to. ``b64_png`` (the platform could not store it) is kept here."""
    iid = str(body.get("id") or "")
    b64 = body.get("b64_png")
    if not _ID.match(iid):
        if not b64:
            raise ValueError("id")
        iid = f"si-{uuid.uuid4()}"  # stored: false — our own id for the copy kept in the run
    try:
        i = int(body.get("i"))
    except (TypeError, ValueError):
        raise ValueError("i") from None
    if b64:
        raw = base64.b64decode(str(b64), validate=True)
        if not raw.startswith(b"\x89PNG") or len(raw) > 12 * 1024 * 1024:
            raise ValueError("b64_png")
        f = _inline(root, iid)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(raw)
    d = _store(root)
    d["items"] = [x for x in d["items"] if x["id"] != iid]
    row = {"id": iid, "i": i, "kind": str(body.get("kind") or "place")[:20], "caption": str(body.get("caption") or "")[:200],
           "size": str(body.get("size") or SIZE)[:20], "stored": not b64, "credits": body.get("credits"),
           "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    d["items"].append(row)
    _save(root, d)
    return {**row, "local": bool(b64)}


def forget(root: Path, iid: str) -> bool:
    d = _store(root)
    n = len(d["items"])
    d["items"] = [x for x in d["items"] if x["id"] != iid]
    f = _inline(root, iid)
    if f.is_file():
        f.unlink()
    if len(d["items"]) != n:
        _save(root, d)
        return True
    return False


def inline_file(root: Path, iid: str) -> Path | None:
    f = _inline(root, iid)
    return f if _ID.match(iid) and f.is_file() else None


# ── the platform (local engine: its own sign-in) ─────────────────────────

def _bases() -> tuple[str, str]:
    from neonrp.core import worldlines_auth as A

    ai = re.sub(r"/v1/?$", "", A.API_BASE.rstrip("/"))  # API_BASE is the OpenAI-style base (…/v1)
    billing = os.environ.get("WORLDLINES_BILLING_BASE", "https://billing.worldlines.gg").rstrip("/")
    return ai, billing


def _call(method: str, url: str, token: str, body: Any = None, timeout: float = 30) -> tuple[int, Any]:
    import urllib.error
    import urllib.request

    from neonrp.core import worldlines_auth as A

    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "authorization": f"Bearer {token}", "accept": "application/json", **A.headers(),
        **({"content-type": "application/json"} if data is not None else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — our own platform URL
            raw = r.read().decode("utf-8")
            st = r.status
    except urllib.error.HTTPError as e:
        raw, st = e.read().decode("utf-8", "replace"), e.code
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return 0, {"error": {"code": "unreachable", "message": str(e)}}
    try:
        return st, json.loads(raw) if raw else {}
    except ValueError:
        return st, {"error": {"code": "bad_answer", "message": raw[:200]}}


def platform(op: str, body: dict[str, Any] | None = None, iid: str | None = None) -> tuple[int, Any]:
    """status · generate · url · delete — with the engine's Worldlines sign-in. → (http status, json)"""
    from neonrp.core import worldlines_auth as A

    tok = A.access_token()
    if not tok:
        return (200, {"signed_in": False, "available": False, "reason": "signin"}) if op == "status" else (401, {"error": {"code": "signin", "message": "Sign in to Worldlines first."}})
    ai, billing = _bases()
    if op == "status":
        st, bal = _call("GET", f"{billing}/v1/me/balance?product={A.PRODUCT}", tok)
        if st != 200:
            return 200, {"signed_in": True, "available": False, "reason": "billing_unavailable" if st in (0, 502, 503) else ("signin" if st == 401 else "plan_required")}
        f = ((bal or {}).get("features") or {}).get("realtime_images") or {}
        out: dict[str, Any] = {"signed_in": True, "available": bool(f.get("available")), "reason": f.get("reason"), "upgrade_url": f.get("upgrade_url")}
        if out["available"]:
            st, pr = _call("GET", f"{ai}/v1/images/generate/price", tok)
            if st == 200:
                out["price"] = pr
            elif isinstance(pr, dict) and (pr.get("error") or {}).get("code") in ("users_only", "insufficient_scope"):
                out.update(available=False, reason=pr["error"]["code"])
        return 200, out
    if op == "generate":
        return _call("POST", f"{ai}/v1/images/generate", tok, body or {}, timeout=240)
    if op in ("url", "delete") and iid and _ID.match(iid):
        return _call("GET" if op == "url" else "DELETE", f"{ai}/v1/images/scenes/{iid}", tok)
    return 404, {"error": {"code": "not_found", "message": op}}
