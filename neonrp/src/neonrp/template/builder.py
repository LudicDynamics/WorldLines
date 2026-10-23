"""Player builder — the player makes their own character before the run opens (niko 10-14, 面板玩家).

**The template declares the sheet; the screen renders it; the engine checks and writes it.** No builder block = the run
opens as before. ``template.json``::

    "player": {"builder": {
      "title": {"zh": "…", "en": "…"},
      "fields": [
        {"id": "name",   "kind": "text",   "required": true, "max": 24, "to": "player/profile.json:name", "random": ["…"]},
        {"id": "origin", "kind": "choice", "required": true, "to": "player/profile.json:origin",
         "options": [{"id": "a", "label": "…", "desc": "…",
                      "grants": {"set":    {"meta/run_state.json:location": {"node_id": "T001", "subnode_id": "x"}},
                                 "append": {"player/stats.json:skills": [{"name": "…", "value": 40}]},
                                 "add":    {"player/stats.json:attributes.dex": 1}}}]},
        {"id": "traits", "kind": "multi",  "min": 0, "max": 2, "options": [...], "to": "player/profile.json:traits"},
        {"id": "attrs",  "kind": "points", "total": 20, "min": 1, "max": 8, "exact": true,
         "stats": [{"id": "str", "label": "…"}, …], "to": "player/stats.json:attributes", "var": "player.attr"},
        {"id": "face",   "kind": "portrait", "options": [{"id": "a", "src": "assets/player/a.png"}]}
      ],
      "companion": {"from": ["cast"], "role": "companion", "pick": 1, "required": true,
                    "cards": {"<sid>": {"title": "…", "tier": "…", "blurb": "…", "<more>": "…"}},
                    "rows": [{"key": "<more>", "label": "…"}]},
      "steps": [{"id": "who", "title": "…"}, {"id": "pick", "title": "…"}, {"id": "go", "title": "…"}]
    }}

``derive`` (optional) — values computed from the points after every grant (linear, floor division)::

    "derive": [{"to": "player/stats.json:hp.current", "also": ["player/stats.json:hp.max"], "base": 6, "per": {"体": 2},
                "label": "…"},
               {"to": "player/stats.json:resonance", "base": 2, "per": {"魂": 1}, "div": 3}]     # 2 + floor(魂 / 3)

A text field with ``"generate": true`` (or a prompt string) gets a "generate" button: the configured model writes it
(``generate()``), the field's ``example`` texts stand in when no model is set up (stub). Free text is the player's own:
a 生平 is not bound by the world's setting — it is written as this run's reality.

``labels`` (optional) names what a grant's ``add`` raises when it is not one of the points stats::

    "labels": {"player/stats.json:attributes.int": {"zh": "智力", "en": "INT"}}     # or by the dotted key / its last part

so the option card says "brings 智力 +1", never a raw key (an unnamed one is warned by lint).

``steps`` (optional) groups the screen: a field's ``step`` / ``companion.step`` names its step; a step with nothing in
it is the confirm-and-open page. ``companion.rows`` labels the extra keys of ``cards``.

Every text may be a string or ``{zh, en, ja, ko}``. ``to`` = ``<file under the game dir>:<dotted key>`` — the engine
writes there and knows no world's words. ``choice`` / ``multi`` options may carry ``grants`` (set · append · add, same
addressing). ``points`` with ``var`` registers ``<var>.<stat>`` int variables bound to the same file. ``portrait`` copies
the chosen image to ``game/player/assets/portrait.<ext>`` (the play screen's player avatar). The whole filled sheet is
always written to ``game/player/card.json`` (values + the declaration), which the play screen's panel reads.

``companion``: candidates are the template's ``souls`` rows with that role (``from`` may add ``"library"``: every soul
in the character library). Candidates not picked do not enter the run.

A draft the screen sends: ``{"fields": {"<id>": value}, "companion": "<sid>" | [sid, …]}`` — text → str, choice /
portrait → option id, multi → [ids], points → {stat: int}.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
from pathlib import Path
from typing import Any

KINDS = ("text", "choice", "multi", "points", "portrait")
GRANTS = ("set", "append", "add")
FROM = ("cast", "library")
CARD = "player/card.json"  # under the game dir
CARD_SCHEMA = "worldlines.player-card/1"
TEXT_MAX = 4000  # a long free text (生平) fits; a field's own max is lower
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")


class BuilderError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def raw(t: Any) -> Any:
    p = (getattr(t, "data", None) or {}).get("player")
    return p.get("builder") if isinstance(p, dict) else None


def declared(t: Any) -> bool:
    return isinstance(raw(t), dict) and bool(raw(t).get("fields") or raw(t).get("companion"))


def _fields(b: dict[str, Any]) -> list[dict[str, Any]]:
    return [f for f in b.get("fields") or [] if isinstance(f, dict)]


def _opts(f: dict[str, Any]) -> list[dict[str, Any]]:
    return [o for o in f.get("options") or [] if isinstance(o, dict)]


def _int(v: Any, default: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


# ── addressing: "<file under the game dir>:<dotted key>" ─────────────────────

def parse_target(to: Any) -> tuple[str, str] | None:
    """``player/profile.json:name`` → (``player/profile.json``, ``name``); anything outside the game dir → None."""
    if not isinstance(to, str) or ":" not in to:
        return None
    path, _, key = to.partition(":")
    parts = path.split("/")
    if not path.endswith(".json") or path.startswith("/") or "\\" in path or any(p in ("", ".", "..") for p in parts) or not key.strip("."):
        return None
    return path, key


def _get(d: Any, key: str) -> Any:
    for k in key.split("."):
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _set(d: dict[str, Any], key: str, v: Any) -> None:
    ks = key.split(".")
    for k in ks[:-1]:
        if not isinstance(d.get(k), dict):
            d[k] = {}
        d = d[k]
    d[ks[-1]] = v


# ── the declaration ──────────────────────────────────────────────────────────

def problems(t: Any) -> list[tuple[str, str, str, str]]:
    """What is wrong with the declaration itself: (level, code, where, msg). Code ``player.builder``."""
    b = raw(t)
    if b is None:
        return []
    out: list[tuple[str, str, str, str]] = []
    bad = lambda w, m: out.append(("block", "player.builder", w, m))  # noqa: E731
    if not isinstance(b, dict):
        return [("block", "player.builder", "player.builder", "must be an object")]
    if b.get("fields") is not None and not isinstance(b.get("fields"), list):
        bad("player.builder.fields", "must be a list")
    steps = [str(s.get("id") or "") for s in b.get("steps") or [] if isinstance(s, dict)]
    if b.get("steps") is not None and (not isinstance(b.get("steps"), list) or "" in steps or len(set(steps)) != len(steps)):
        bad("player.builder.steps", "a list of {id, title}, each id distinct")
    for i, f in enumerate(b.get("fields") or []):
        if isinstance(f, dict) and f.get("step") is not None and str(f["step"]) not in steps:
            bad(f"player.builder.fields[{i}].step", f"no step {f['step']!r} in steps")
    c0 = b.get("companion")
    if isinstance(c0, dict) and c0.get("step") is not None and str(c0["step"]) not in steps:
        bad("player.builder.companion.step", f"no step {c0['step']!r} in steps")
    seen: set[str] = set()
    for i, f in enumerate(b.get("fields") or []):
        w = f"player.builder.fields[{i}]"
        if not isinstance(f, dict):
            bad(w, "must be an object")
            continue
        fid, kind = str(f.get("id") or ""), f.get("kind")
        if not fid:
            bad(w, "needs an id")
        elif fid in seen:
            bad(w, f"duplicate id {fid!r}")
        seen.add(fid)
        w = f"player.builder.fields.{fid or i}"
        if kind not in KINDS:
            bad(w, f"unknown kind {kind!r} (known: {', '.join(KINDS)})")
            continue
        if f.get("to") is not None and parse_target(f.get("to")) is None:
            bad(f"{w}.to", f"{f.get('to')!r}: write '<file under the game dir>.json:<key>' (no .., no absolute path)")
        if kind in ("choice", "multi", "portrait"):
            opts = _opts(f)
            if not opts:
                bad(w, "needs options")
            ids = [str(o.get("id") or "") for o in opts]
            if "" in ids or len(set(ids)) != len(ids):
                bad(f"{w}.options", "every option needs a distinct id")
            for o in opts:
                g = o.get("grants")
                if g is None:
                    continue
                if not isinstance(g, dict) or any(k not in GRANTS for k in g):
                    bad(f"{w}.options.{o.get('id')}.grants", f"grants is {{{', '.join(GRANTS)}}}")
                    continue
                for how, m in g.items():
                    if not isinstance(m, dict):
                        bad(f"{w}.options.{o.get('id')}.grants.{how}", "must be an object of target → value")
                        continue
                    for to, v in m.items():
                        if parse_target(to) is None:
                            bad(f"{w}.options.{o.get('id')}.grants.{how}", f"bad target {to!r}")
                        elif how == "add" and not isinstance(v, (int, float)):
                            bad(f"{w}.options.{o.get('id')}.grants.add", f"{to}: add takes a number")
            if kind == "portrait":
                for o in opts:
                    src = _option_image(t, o)
                    if src is None:
                        bad(f"{w}.options.{o.get('id')}.src", "image not found inside the template (png · jpg · webp)")
                if f.get("default") is not None and str(f["default"]) not in {str(o.get("id")) for o in opts}:
                    bad(f"{w}.default", f"{f['default']!r} is not one of the options")
            if kind == "multi":
                lo, hi = _int(f.get("min"), 0), _int(f.get("max"), len(opts))
                if lo > hi or hi > len(opts):
                    bad(w, f"min {lo} / max {hi} do not fit {len(opts)} options")
        if kind == "points":
            stats = [s for s in f.get("stats") or [] if isinstance(s, dict)]
            sids = [str(s.get("id") or "") for s in stats]
            if not stats or "" in sids or len(set(sids)) != len(sids):
                bad(f"{w}.stats", "needs stats, each with a distinct id")
            total, lo, hi = _int(f.get("total"), -1), _int(f.get("min"), 0), _int(f.get("max"), 10 ** 6)
            if total < 0:
                bad(f"{w}.total", "needs a total (int ≥ 0)")
            elif stats and (lo * len(stats) > total or (f.get("exact") and hi * len(stats) < total)):
                bad(w, f"{len(stats)} stats in {lo}..{hi} cannot spend {total} points")
            if f.get("var") is not None and (not isinstance(f["var"], str) or not f["var"].strip(".") or parse_target(f.get("to")) is None):
                bad(f"{w}.var", "var needs a name and the field needs a 'to'")
    stat_ids = {str(s.get("id")) for f in _fields(b) if f.get("kind") == "points" for s in f.get("stats") or [] if isinstance(s, dict)}
    for f in _fields(b):
        if f.get("generate") and f.get("kind") != "text":
            bad(f"player.builder.fields.{f.get('id')}.generate", "only a text field can be generated")
    if b.get("derive") is not None and not isinstance(b.get("derive"), list):
        bad("player.builder.derive", "must be a list")
    for i, dv in enumerate(b.get("derive") or [] if isinstance(b.get("derive"), list) else []):
        w = f"player.builder.derive[{i}]"
        if not isinstance(dv, dict):
            bad(w, "must be an object")
            continue
        if parse_target(dv.get("to")) is None or any(parse_target(x) is None for x in dv.get("also") or []):
            bad(f"{w}.to", "to / also are '<file under the game dir>.json:<key>'")
        per = dv.get("per") if isinstance(dv.get("per"), dict) else None
        if per is None or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in per.values()):
            bad(f"{w}.per", "per is {stat id: number}")
        elif [k for k in per if k not in stat_ids]:
            bad(f"{w}.per", f"no points stat {', '.join(k for k in per if k not in stat_ids)}")
        if not isinstance(dv.get("base", 0), (int, float)) or _int(dv.get("div"), 1) < 1:
            bad(w, "base is a number, div an int ≥ 1")
    if b.get("labels") is not None and not isinstance(b.get("labels"), dict):
        bad("player.builder.labels", "must be an object of target → label")
    for f in _fields(b):
        for o in _opts(f):
            for x in brings(b, o.get("grants")):
                if x.get("add") is not None and x.get("label") is None:
                    out.append(("warn", "player.builder", f"player.builder.fields.{f.get('id')}.options.{o.get('id')}.grants.add",
                                f"{x['key']!r} has no label: name it in player.builder.labels (the card would show the raw key)"))
    c = b.get("companion")
    if c is not None:
        if not isinstance(c, dict):
            bad("player.builder.companion", "must be an object")
        else:
            src = c.get("from") or ["cast"]
            src = [src] if isinstance(src, str) else src
            if any(s not in FROM for s in src):
                bad("player.builder.companion.from", f"from is a list of {', '.join(FROM)}")
            pick = _int(c.get("pick"), 1)
            cands = companions(t)
            if pick < 1:
                bad("player.builder.companion.pick", "pick ≥ 1")
            elif "library" not in src and pick > len(cands):
                bad("player.builder.companion", f"pick {pick} but {len(cands)} candidate(s) with role {c.get('role') or 'companion'!r} in souls")
    return out


def _option_image(t: Any, o: dict[str, Any]) -> Path | None:
    src = o.get("src")
    if not isinstance(src, str) or not src:
        return None
    root = Path(os.path.abspath(t.dir))
    p = Path(os.path.normpath(root / src))  # inside the folder by path: a localized copy links its images to the original
    return p if p.is_file() and p.is_relative_to(root) and p.suffix.lower() in IMAGE_EXTS else None


def option_image(t: Any, field_id: str, option_id: str) -> Path | None:
    b = raw(t) if declared(t) else {}
    f = next((x for x in _fields(b) if str(x.get("id")) == field_id), None)
    o = next((x for x in _opts(f or {}) if str(x.get("id")) == option_id), None)
    return _option_image(t, o) if o else None


# ── companions ───────────────────────────────────────────────────────────────

def _companion_spec(t: Any) -> dict[str, Any] | None:
    c = (raw(t) or {}).get("companion") if isinstance(raw(t), dict) else None
    return c if isinstance(c, dict) else None


def _soul_card(sd: Path | None, over: Path | None = None) -> dict[str, Any]:
    """Name / intro / portrait of a soul folder; ``over`` = the same soul inside the template's world-overlay (its art)."""
    sj: dict[str, Any] = {}
    if sd is not None:
        try:
            sj = json.loads((sd / "soul.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            sj = {}
    port = next((d / "assets" / f"portrait{e}" for d in (over, sd) if d is not None for e in IMAGE_EXTS if (d / "assets" / f"portrait{e}").is_file()), None)
    return {"name": sj.get("name_local") or sj.get("name") or (sd.name if sd else ""), "name_en": sj.get("name") or "",
            "intro": sj.get("intro_i18n") or sj.get("intro") or "", "tags": sj.get("tags") or [],
            "portrait": port is not None, "_portrait": port}


def companions(t: Any, *, with_paths: bool = False) -> list[dict[str, Any]]:
    """The candidates the screen shows: ``{sid, from, name, intro, portrait, tier, blurb}``."""
    from neonrp import template as TP

    c = _companion_spec(t)
    if c is None:
        return []
    role = str(c.get("role") or "companion")
    src = c.get("from") or ["cast"]
    src = [src] if isinstance(src, str) else list(src)
    cards = c.get("cards") if isinstance(c.get("cards"), dict) else {}
    wdir = TP.world_dir(t)
    out: list[dict[str, Any]] = []
    if "cast" in src:
        for s in t.souls:
            if s.get("pool") is not None or str(s.get("role") or "npc") != role or not s.get("sid") and not s.get("lib"):
                continue
            sd = TP.soul_dir(t, s, wdir)
            sid = str(s.get("sid") or s.get("lib"))
            ov = TP.overlay_dir(t)
            over = ov / "souls" / sd.name if ov is not None and sd is not None and wdir is not None and sd.is_relative_to(wdir) else None
            out.append({"sid": sid, "from": "cast", **_soul_card(sd, over), **(cards.get(sid) or {})})
    if "library" in src:
        from neonrp.core import souls as _souls

        lib = Path(_souls.SOUL_HOME)
        have = {o["sid"] for o in out}
        for d in sorted(lib.iterdir()) if lib.is_dir() else []:
            if not (d.is_dir() and (d / "soul.json").is_file()):
                continue
            try:
                sid = str(json.loads((d / "soul.json").read_text(encoding="utf-8")).get("sid") or d.name)
            except (OSError, ValueError):
                sid = d.name
            if sid not in have:
                have.add(sid)
                out.append({"sid": sid, "from": "library", "lib": d.name, **_soul_card(d), **(cards.get(sid) or {})})
    if not with_paths:
        for o in out:
            o.pop("_portrait", None)
    return out


def companion_image(t: Any, sid: str) -> Path | None:
    hit = next((o for o in companions(t, with_paths=True) if o["sid"] == sid), None)
    return hit.get("_portrait") if hit else None


def brings(b: dict[str, Any], grants: Any) -> list[dict[str, Any]]:
    """What a picked option brings, for its card: ``{label, key, add}`` per number it raises, ``{label}`` per thing it adds
    to a list (its ``name`` / ``title``). A number's label: ``labels`` (the target, its dotted key or the key's last part)
    → the points stat the target lands on → None (the screen falls back to the key)."""
    if not isinstance(grants, dict):
        return []
    names = b.get("labels") if isinstance(b.get("labels"), dict) else {}
    stats: dict[str, Any] = {}  # "<file>:<key>.<stat id>" → the stat's label
    for f in _fields(b):
        tgt = parse_target(f.get("to"))
        if f.get("kind") == "points" and tgt is not None:
            for st in f.get("stats") or []:
                if isinstance(st, dict) and st.get("id") is not None:
                    stats[f"{tgt[0]}:{tgt[1]}.{st['id']}"] = st.get("label") or str(st["id"])
    out: list[dict[str, Any]] = []
    for to, v in (grants.get("add") or {}).items() if isinstance(grants.get("add"), dict) else []:
        tgt = parse_target(to)
        key = tgt[1] if tgt else str(to)
        last = key.split(".")[-1]
        label = next((names[k] for k in (to, key, last) if names.get(k)), None) or stats.get(str(to))
        out.append({"label": label, "key": last, "add": v})
    for v in (grants.get("append") or {}).values() if isinstance(grants.get("append"), dict) else []:
        for x in v if isinstance(v, list) else [v]:
            if isinstance(x, dict) and (x.get("name") or x.get("title")):
                out.append({"label": x.get("name") or x.get("title")})
    return out


def view(t: Any) -> dict[str, Any]:
    """What the screen renders (``GET /api/v1/local/templates/<id>/builder``): the declaration + resolved candidates."""
    if not declared(t):
        return {"declared": False}
    b = copy.deepcopy(raw(t))
    for f in _fields(b):
        for o in _opts(f):
            if o.get("grants"):
                o["brings"] = brings(b, o["grants"])
        if f.get("kind") == "portrait":
            for o in _opts(f):
                o["image"] = _option_image(t, o) is not None
                o.pop("src", None)
    c = _companion_spec(t)
    return {"declared": True, "template": t.id, "builder": b,
            "companion": ({**{k: v for k, v in c.items() if k != "cards"}, "pick": _int(c.get("pick"), 1),
                           "required": c.get("required", True) is not False, "candidates": companions(t)} if c else None),
            "problems": [{"level": lv, "where": w, "msg": m} for lv, _c, w, m in problems(t)]}


# ── a draft: check, then write ───────────────────────────────────────────────

def check(t: Any, draft: Any) -> tuple[list[str], dict[str, Any]]:
    """Validate a draft against the declaration. Returns (errors, normalised draft)."""
    if not declared(t):
        return ["this template declares no player builder"], {}
    decl = [f"{w}: {m}" for lv, _c, w, m in problems(t) if lv == "block"]
    if decl:
        return decl, {}
    draft = draft if isinstance(draft, dict) else {}
    vals = draft.get("fields") if isinstance(draft.get("fields"), dict) else {}
    errs: list[str] = []
    norm: dict[str, Any] = {}
    for f in _fields(raw(t)):
        fid, kind, req = str(f["id"]), f["kind"], bool(f.get("required"))
        v = vals.get(fid)
        if kind == "text":
            s = str(v or "").strip() if isinstance(v, (str, int, float)) or v is None else None
            if s is None:
                errs.append(f"{fid}: must be text")
                continue
            if req and not s:
                errs.append(f"{fid}: required")
            if len(s) > min(_int(f.get("max"), TEXT_MAX), TEXT_MAX):
                errs.append(f"{fid}: longer than {min(_int(f.get('max'), TEXT_MAX), TEXT_MAX)} characters")
            if s:
                norm[fid] = s
        elif kind in ("choice", "portrait"):
            ids = [str(o["id"]) for o in _opts(f)]
            if v in (None, ""):
                if req:
                    errs.append(f"{fid}: required")
                continue
            if str(v) not in ids:
                errs.append(f"{fid}: {v!r} is not an option ({', '.join(ids)})")
                continue
            norm[fid] = str(v)
        elif kind == "multi":
            ids = [str(o["id"]) for o in _opts(f)]
            got = [str(x) for x in v] if isinstance(v, list) else ([] if v in (None, "") else None)
            if got is None:
                errs.append(f"{fid}: must be a list of option ids")
                continue
            lo, hi = _int(f.get("min"), 1 if req else 0), _int(f.get("max"), len(ids))
            unknown = [x for x in got if x not in ids]
            if unknown:
                errs.append(f"{fid}: not options: {', '.join(unknown)}")
            if len(set(got)) != len(got):
                errs.append(f"{fid}: an option picked twice")
            if not lo <= len(got) <= hi:
                errs.append(f"{fid}: pick {lo}..{hi}, got {len(got)}")
            if got:
                norm[fid] = got
        elif kind == "points":
            stats = [str(s["id"]) for s in f.get("stats") or [] if isinstance(s, dict)]
            got = v if isinstance(v, dict) else {}
            lo, hi, total = _int(f.get("min"), 0), _int(f.get("max"), 10 ** 6), _int(f.get("total"), 0)
            alloc: dict[str, int] = {}
            for s in stats:
                x = got.get(s, lo)
                if isinstance(x, bool) or not isinstance(x, int):
                    errs.append(f"{fid}.{s}: must be a whole number")
                    continue
                if not lo <= x <= hi:
                    errs.append(f"{fid}.{s}: {x} is outside {lo}..{hi}")
                alloc[s] = x
            extra = [k for k in got if k not in stats]
            if extra:
                errs.append(f"{fid}: unknown stats {', '.join(map(str, extra))}")
            spent = sum(alloc.values())
            if spent > total:
                errs.append(f"{fid}: {spent} points spent, only {total}")
            elif f.get("exact") and spent != total:
                errs.append(f"{fid}: spend all {total} points ({spent} spent)")
            norm[fid] = alloc
    c = _companion_spec(t)
    if c is not None:
        pick = _int(c.get("pick"), 1)
        got = draft.get("companion")
        got = [got] if isinstance(got, str) and got else ([str(x) for x in got] if isinstance(got, list) else [])
        cands = {o["sid"]: o for o in companions(t)}
        unknown = [x for x in got if x not in cands]
        if unknown:
            errs.append(f"companion: not a candidate: {', '.join(unknown)}")
        elif len(set(got)) != len(got):
            errs.append("companion: picked twice")
        elif len(got) > pick:
            errs.append(f"companion: pick at most {pick}")
        elif c.get("required", True) is not False and len(got) < pick:
            errs.append(f"companion: pick {pick}")
        norm["__candidates"] = sorted(cands)
        norm["__companion"] = [{"sid": x, "from": cands[x]["from"], **({"lib": cands[x]["lib"]} if cands[x].get("lib") else {})}
                               for x in got if x in cands]
    return errs, norm


def select_cast(t: Any, norm: dict[str, Any]) -> Any:
    """The template with its companion candidates narrowed to the ones picked (library picks join as links)."""
    c = _companion_spec(t)
    if c is None or "__companion" not in norm:
        return t
    role = str(c.get("role") or "companion")
    picked = norm["__companion"]
    keep = {p["sid"] for p in picked}
    t2 = copy.copy(t)
    rows = []
    for s in t.souls:
        if s.get("pool") is None and str(s.get("role") or "npc") == role and str(s.get("sid") or s.get("lib")) not in keep:
            continue
        rows.append(s)
    rows += [{"sid": p["sid"], "lib": p["lib"], "role": role} for p in picked if p["from"] == "library"]
    t2.souls = rows
    return t2


def apply(t: Any, run: Path, norm: dict[str, Any]) -> dict[str, Any]:
    """Write a checked draft into a built run: each field's ``to``, each picked option's grants, the variables, the
    portrait, and the whole sheet to ``game/player/card.json``. Returns the card."""
    from neonrp.core.paths import get_data_dir_name

    run = Path(run)
    g = get_data_dir_name(run)
    game = run / g
    files: dict[str, Any] = {}

    def doc(path: str) -> dict[str, Any]:
        if path not in files:
            try:
                d = json.loads((game / path).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                d = {}
            files[path] = d if isinstance(d, dict) else {}
        return files[path]

    b = raw(t)
    labels: dict[str, Any] = {}
    grants: list[dict[str, Any]] = []
    new_vars: dict[str, Any] = {}
    portrait: Path | None = None
    for f in _fields(b):
        fid, kind = str(f["id"]), f["kind"]
        if fid not in norm:
            continue
        v = norm[fid]
        opts = {str(o["id"]): o for o in _opts(f)}
        if kind in ("choice", "portrait"):
            labels[fid] = opts[v].get("label")
            grants.append(opts[v].get("grants") or {})
            if kind == "portrait":
                portrait = _option_image(t, opts[v])
        elif kind == "multi":
            labels[fid] = [opts[x].get("label") for x in v]
            grants += [opts[x].get("grants") or {} for x in v]
        tgt = parse_target(f.get("to"))
        if tgt is None:
            continue
        path, key = tgt
        if kind == "points":
            cur = _get(doc(path), key)
            merged = {**(cur if isinstance(cur, dict) else {}), **v}
            _set(doc(path), key, merged)
            if isinstance(f.get("var"), str) and f["var"].strip("."):
                for s in f.get("stats") or []:
                    sid = str(s.get("id"))
                    new_vars[f"{f['var'].strip('.')}.{sid}"] = {"type": "int", "path": f"{g}/{path}", "key": f"{key}.{sid}",
                                                                 "min": 0, "doc": _plain(s.get("label")) or sid}
        else:
            _set(doc(path), key, v)
    for gr in grants:
        for to, v in (gr.get("set") or {}).items():
            p, k = parse_target(to)  # type: ignore[misc] — checked by problems()
            _set(doc(p), k, copy.deepcopy(v))
        for to, v in (gr.get("append") or {}).items():
            p, k = parse_target(to)  # type: ignore[misc]
            cur = _get(doc(p), k)
            _set(doc(p), k, [*(cur if isinstance(cur, list) else []), *(copy.deepcopy(v) if isinstance(v, list) else [copy.deepcopy(v)])])
        for to, v in (gr.get("add") or {}).items():
            p, k = parse_target(to)  # type: ignore[misc]
            cur = _get(doc(p), k)
            _set(doc(p), k, (cur if isinstance(cur, (int, float)) and not isinstance(cur, bool) else 0) + v)
    derived = _derive(b, lambda path: doc(path))
    for dv, val in derived:
        for to in [dv["to"], *(dv.get("also") or [])]:
            p, k = parse_target(to)  # type: ignore[misc] — checked by problems()
            _set(doc(p), k, val)
    card = {"schema": CARD_SCHEMA, "template": t.id, "values": {k: v for k, v in norm.items() if not k.startswith("__")},
            "labels": labels, "companion": [p["sid"] for p in norm.get("__companion") or []], "builder": copy.deepcopy(b),
            "derived": {str(dv["to"]): val for dv, val in derived}}
    files[CARD] = card
    for path, d in files.items():
        (game / path).parent.mkdir(parents=True, exist_ok=True)
        (game / path).write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _bench(run, norm)
    if new_vars:
        vp = game / "meta" / "variables.json"
        try:
            cur = json.loads(vp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cur = {}
        vp.write_text(json.dumps({**(cur if isinstance(cur, dict) else {}), **new_vars}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if portrait is None and not any((game / "player" / "assets" / f"portrait{e}").is_file() for e in IMAGE_EXTS):
        portrait = default_portrait(t)  # no picture picked and none in the world: the field's default (10-15)
    if portrait is not None:
        _put_portrait(game, portrait)
    return card


def default_portrait(t: Any) -> Path | None:
    """The image of the first portrait field's ``default`` option (the face a run gets when the player picks none — a
    run started without the builder, or a draft that left it out); None when no field names one."""
    for f in _fields(raw(t) or {}):
        if f.get("kind") == "portrait" and f.get("default"):
            o = next((x for x in _opts(f) if str(x.get("id")) == str(f["default"])), None)
            if o is not None:
                return _option_image(t, o)
    return None


def _put_portrait(game: Path, portrait: Path) -> None:
    adir = game / "player" / "assets"
    adir.mkdir(parents=True, exist_ok=True)
    for e in IMAGE_EXTS:
        (adir / f"portrait{e}").unlink(missing_ok=True)
    shutil.copy2(portrait, adir / f"portrait{portrait.suffix.lower()}")


def apply_default(t: Any, run: Path) -> bool:
    """A run started without the builder: the player's portrait is the portrait field's ``default`` — unless the world
    already gives the player one. True = written."""
    from neonrp.core.paths import get_data_dir_name

    if not declared(t):
        return False
    game = Path(run) / get_data_dir_name(Path(run))
    if any((game / "player" / "assets" / f"portrait{e}").is_file() for e in IMAGE_EXTS):
        return False
    p = default_portrait(t)
    if p is None:
        return False
    _put_portrait(game, p)
    return True


def _bench(run: Path, norm: dict[str, Any]) -> None:
    """Candidates not picked leave the run's disk too: the cast list already drops them, but anything that scans
    ``souls/`` (the map, the play screen's @-chips) would still meet them. The template keeps its copy."""
    picked = {p["sid"] for p in norm.get("__companion") or []}
    try:
        pt = json.loads((run / "playthrough.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pt = {}
    cast = {str(r.get("sid")) for r in pt.get("souls") or [] if isinstance(r, dict)}
    for sid in norm.get("__candidates") or []:
        if sid in picked or sid in cast:
            continue
        for d in (run / "souls").glob(f"{sid}-*") if (run / "souls").is_dir() else []:
            sj = d / "soul.json"
            try:
                own = str(json.loads(sj.read_text(encoding="utf-8")).get("sid") or "") if sj.is_file() else ""
            except (OSError, ValueError):
                own = ""
            if d.is_dir() and own in ("", sid):
                shutil.rmtree(d, ignore_errors=True)


def _derive(b: dict[str, Any], doc: Any) -> list[tuple[dict[str, Any], int | float]]:
    """``base + floor(Σ stat × per / div)`` from the stats as written (allocation + every grant)."""
    stats: dict[str, Any] = {}
    for f in _fields(b):
        tgt = parse_target(f.get("to"))
        if f.get("kind") == "points" and tgt is not None:
            cur = _get(doc(tgt[0]), tgt[1])
            stats.update(cur if isinstance(cur, dict) else {})
    out = []
    for dv in b.get("derive") or [] if isinstance(b.get("derive"), list) else []:
        if not isinstance(dv, dict) or parse_target(dv.get("to")) is None:
            continue
        acc = sum((stats.get(k) or 0) * m for k, m in (dv.get("per") or {}).items() if isinstance(stats.get(k) or 0, (int, float)))
        div = max(1, _int(dv.get("div"), 1))
        val = (dv.get("base") or 0) + (acc // div if div > 1 else acc)
        out.append((dv, int(val) if float(val).is_integer() else val))
    return out


def _by_lang(key: str) -> dict[str, str]:
    from neonrp.prompts import by_lang

    return by_lang("builder", key)


# the "generate" button's model brief and its no-model stand-in (prompts/builder.<lang>.json, 10-15)
GEN_SYSTEM = _by_lang("gen_system")
EXAMPLE = _by_lang("example")


def generate(t: Any, field_id: str, draft: Any = None, *, lang: str = "zh", adapter: Any = None) -> dict[str, Any]:
    """Write one text field for the player (the "generate" button): the configured model, or — no model set up / the
    stub — the field's ``example`` (else a neutral sample). Context = what the player already filled in; the world's
    lore is left out on purpose (the player's own life is free). Returns ``{text, source: model|example}``."""
    import random

    if not declared(t):
        raise BuilderError(["this template declares no player builder"])
    f = next((x for x in _fields(raw(t)) if str(x.get("id")) == field_id), None)
    if f is None or f.get("kind") != "text" or not f.get("generate"):
        raise BuilderError([f"{field_id}: not a generated text field"])
    lang = lang if lang in GEN_SYSTEM else "zh"
    cap = min(_int(f.get("max"), TEXT_MAX), TEXT_MAX)

    def example() -> dict[str, Any]:
        ex = f.get("example")
        pool = ex if isinstance(ex, list) else ([ex] if ex else [])
        pick = random.choice(pool) if pool else EXAMPLE
        txt = pick.get(lang) or _plain(pick) if isinstance(pick, dict) else str(pick)
        return {"text": txt[:cap], "source": "example"}

    if adapter is None:
        try:
            from neonrp.core.hub_publish import adapter_for_preset

            adapter = adapter_for_preset(None)
        except Exception:  # noqa: BLE001 — no model configured: the example stands in
            return example()
    if type(adapter).__name__ == "StubAdapter":
        return example()
    vals = ((draft or {}).get("fields") or {}) if isinstance(draft, dict) else {}
    known = []
    for g in _fields(raw(t)):
        v = vals.get(str(g.get("id")))
        if g is f or g.get("kind") == "portrait" or v in (None, "", [], {}):
            continue
        if g.get("kind") == "choice":
            v = next((_label(o.get("label"), lang) for o in _opts(g) if str(o.get("id")) == str(v)), v)
        elif g.get("kind") == "multi":
            v = "、".join(_label(o.get("label"), lang) for o in _opts(g) if str(o.get("id")) in v)
        elif g.get("kind") == "points":
            v = " ".join(f"{_label(s.get('label'), lang) or s.get('id')}{v.get(str(s.get('id')))}" for s in g.get("stats") or [] if isinstance(s, dict))
        known.append(f"{_label(g.get('label'), lang) or g.get('id')}: {v}")
    ask = f.get("generate") if isinstance(f.get("generate"), (str, dict)) else ""
    user = "\n".join([f"[{_label(f.get('label'), lang) or field_id}] ≤ {cap}", _label(ask, lang) if ask else _label(f.get("hint"), lang), *known])
    try:
        out = adapter.generate(GEN_SYSTEM[lang], user)
        txt = "" if getattr(out, "error", None) else str(getattr(out, "raw_output", "") or getattr(out, "proposal_text", "") or "").strip()
    except Exception:  # noqa: BLE001 — a model error must not block making a character
        return example()
    return {"text": txt[:cap], "source": "model"} if txt else example()


def _label(v: Any, lang: str) -> str:
    if isinstance(v, dict):
        return str(v.get(lang) or v.get("zh") or v.get("en") or next(iter(v.values()), "") or "")
    return str(v or "")


def _plain(v: Any) -> str:
    if isinstance(v, dict):
        return str(v.get("zh") or v.get("en") or next(iter(v.values()), "") or "")
    return str(v or "")


def run_card(run: Path) -> dict[str, Any] | None:
    """The run's player card with the current values read back from where they were written (play changes them)."""
    from neonrp.core.paths import get_data_dir_name

    game = Path(run) / get_data_dir_name(Path(run))
    try:
        card = json.loads((game / CARD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(card, dict):
        return None
    live: dict[str, Any] = {}
    cache: dict[str, Any] = {}
    for f in _fields(card.get("builder") or {}):
        tgt = parse_target(f.get("to"))
        if tgt is None:
            continue
        if tgt[0] not in cache:
            try:
                cache[tgt[0]] = json.loads((game / tgt[0]).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                cache[tgt[0]] = {}
        v = _get(cache[tgt[0]], tgt[1])
        if f.get("kind") == "points" and isinstance(v, dict):
            v = {str(s.get("id")): v.get(str(s.get("id"))) for s in f.get("stats") or [] if isinstance(s, dict)}
        if v is not None:
            live[str(f.get("id"))] = v
    for dv in (card.get("builder") or {}).get("derive") or []:
        tgt = parse_target(dv.get("to")) if isinstance(dv, dict) else None
        if tgt is None or not dv.get("label"):
            continue
        if tgt[0] not in cache:
            try:
                cache[tgt[0]] = json.loads((game / tgt[0]).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                cache[tgt[0]] = {}
        live.setdefault("__derived", {})[str(dv["to"])] = _get(cache[tgt[0]], tgt[1])
    card["live"] = live
    cc: dict[str, Any] = {}
    for sid in card.get("companion") or []:  # the run's own copy of the soul (souls/<sid>-<instance>/)
        sd = next((d for d in sorted((Path(run) / "souls").glob(f"{sid}-*")) if (d / "soul.json").is_file()), None)
        if sd is not None:
            sc = _soul_card(sd)
            cc[str(sid)] = {"name": sc["name"], "portrait": sc["portrait"]}
    card["companion_cards"] = cc
    card["portrait"] = any((game / "player" / "assets" / f"portrait{e}").is_file() for e in IMAGE_EXTS)
    return card
