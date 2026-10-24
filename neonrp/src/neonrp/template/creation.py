"""Limited creation + collection.

**What a template opens to creators.** A template's creation desk (Hub, iOS, the local workbench) never edits the
template; it adds data inside the layer the template opens. The template declares that layer::

    "creation": {
      "add":      ["soul", "plot", "ending", "clue", "rule"],         # what a creator may add
      "triggers": {"when": ["text", "flag", "entry"],                  # which trigger kinds (core/triggers.py) they may use
                   "then": ["narration", "soul", "flag", "end"]},
      "collect":  ["clear", "ending", "flag"]                          # how their souls may be collected
    }

No ``creation`` block = nothing is open. :func:`form` turns the block into the form a desk renders (an open schema in, a
form out); :func:`check` validates what a creator submitted against it.

**Who can be collected.** Only characters that live in the world. The world's author writes the rules in a plot::

    "collect": {"N201": {"on": "clear"},                     # any ending that is not a fail ending
                "艾琳娜": {"on": {"ending": "E1"}, "rarity": "rare"},
                "N202": {"on": {"flag": "joined.N202"}}}     # a trigger set the flag during play

The play contract only sets the floor (``"collect": {"souls": true, "min": 1}``). Settlement lists what this run granted
(:func:`granted`); the Hub hands it out. Nothing is taken back once collected.
"""
from __future__ import annotations

import copy

import json
from typing import Any

ADD = ("soul", "plot", "ending", "clue", "rule")
COLLECT_ON = ("clear", "ending", "flag")
RARITY = ("common", "rare", "epic")
FAIL_KINDS = ("fail",)
IMAGES = (("soul", "portrait"), ("ending", "art"), ("clue", "image"))   # the picture each added row may carry (optional)
WORK_PLOT = "mine"   # the web desk's one plot inside the creator's work (template/creation.save)


# ── the template's creation layer ────────────────────────────────────────────

def spec(t: Any) -> dict[str, Any]:
    """The template's creation block, normalised; everything closed when absent."""
    from neonrp.core.triggers import EMIT_TO, WHEN_KINDS

    raw = (getattr(t, "data", None) or {}).get("creation")
    raw = raw if isinstance(raw, dict) else {}
    tr = raw.get("triggers") if isinstance(raw.get("triggers"), dict) else {}
    return {"open": bool(raw),
            "add": [a for a in (raw.get("add") or []) if a in ADD],
            "triggers": {"when": [w for w in (tr.get("when") or []) if w in WHEN_KINDS],
                         "then": [x for x in (tr.get("then") or []) if x in EMIT_TO]},
            "collect": [c for c in (raw.get("collect") or []) if c in COLLECT_ON]}


def spec_problems(t: Any) -> list[tuple[str, str, str, str]]:
    """Unknown names in the template's creation block (they are dropped, so say so)."""
    from neonrp.core.triggers import EMIT_TO, WHEN_KINDS

    raw = (getattr(t, "data", None) or {}).get("creation")
    if raw is None:
        return []
    if not isinstance(raw, dict):
        return [("block", "creation.schema", "creation", "must be an object")]
    out: list[tuple[str, str, str, str]] = []
    tr = raw.get("triggers") if isinstance(raw.get("triggers"), dict) else {}
    for where, have, known in (("creation.add", raw.get("add") or [], ADD), ("creation.triggers.when", tr.get("when") or [], WHEN_KINDS),
                               ("creation.triggers.then", tr.get("then") or [], EMIT_TO), ("creation.collect", raw.get("collect") or [], COLLECT_ON)):
        for x in have:
            if x not in known:
                out.append(("warn", "creation.schema", where, f"unknown {x!r} (known: {', '.join(known)})"))
    return out


def form(t: Any) -> dict[str, Any]:
    """The form a limited creation desk renders: one section per thing the template lets creators add.
    Field types: text · longtext · id · enum · list · trigger. The desk supplies the labels (four languages)."""
    s = spec(t)
    sections: list[dict[str, Any]] = []
    if "soul" in s["add"]:
        sections.append({"key": "soul", "fields": [
            {"name": "name", "type": "text", "required": True},
            {"name": "persona", "type": "longtext", "required": True},
            {"name": "appearance", "type": "longtext"},
            *([{"name": "collect", "type": "enum", "options": s["collect"]},
               {"name": "collect_ending", "type": "id", "ref": "ending", "when": {"collect": "ending"}},
               {"name": "collect_flag", "type": "text", "when": {"collect": "flag"}},
               {"name": "rarity", "type": "enum", "options": list(RARITY)}] if s["collect"] else [])]})
    if "plot" in s["add"]:
        sections.append({"key": "plot", "fields": [
            {"name": "title", "type": "text", "required": True},
            {"name": "stages", "type": "list", "of": "text"},
            {"name": "prompt", "type": "longtext"}]})
    if "clue" in s["add"]:
        sections.append({"key": "clue", "fields": [
            {"name": "name", "type": "text", "required": True},
            {"name": "summary", "type": "longtext", "required": True},
            {"name": "where", "type": "id", "ref": "place"}]})
    if "ending" in s["add"]:
        sections.append({"key": "ending", "fields": [
            {"name": "title", "type": "text", "required": True},
            {"name": "kind", "type": "enum", "options": ["true", "alt", "fail"], "required": True},
            {"name": "text", "type": "longtext"}]})
    if "rule" in s["add"] and s["triggers"]["when"] and s["triggers"]["then"]:
        sections.append({"key": "rule", "fields": [
            {"name": "doc", "type": "text"},
            {"name": "trigger", "type": "trigger", "when": s["triggers"]["when"], "then": s["triggers"]["then"], "required": True}]})
    keys, need = {x["key"] for x in sections}, _needs(t)
    images = [{"for": "card", "name": "cover", "required": True}] if s["open"] else []
    images += [{"for": k, "name": n, **({"required": True} if (k, n) in need["images"] else {})} for k, n in IMAGES if k in keys]
    return {"schema": "worldlines.creation-form/1", "template": getattr(t, "id", ""), "open": s["open"], "sections": sections,
            "card": ["title", "pitch"] if s["open"] else [], "images": images,
            **({"reveal": {"required": need["reveal"] == "always" or ("ending" in keys), **({"template": rv} if (rv := template_reveal(t)) else {})}}
               if s["open"] and need["reveal"] else {}),
            **_quiz().form_part(t), **({"orchestration": _orch_options(t)} if s["open"] else {})}


def template_reveal(t: Any) -> dict[str, str]:
    """The truth the template itself wrote (its first plot with a ``reveal``), per language — the desk starts its own
    reveal from it (lead 10-23: the desk opens with the template's words, the template itself is never changed).
    A plain string is the template's source language; ``i18n/<lang>/plots/<id>/plot.json`` fills the languages it lacks."""
    d = getattr(t, "dir", None)
    if d is None:
        return {}
    src = str(((getattr(t, "data", None) or {}).get("card") or {}).get("lang") or "zh")
    for rel in getattr(t, "plots", None) or []:
        try:
            raw = json.loads((d / rel / "plot.json").read_text(encoding="utf-8")).get("reveal")
        except (OSError, ValueError, AttributeError):
            continue
        out = {k: str(v).strip() for k, v in raw.items() if str(v or "").strip()} if isinstance(raw, dict) else ({src: raw.strip()} if isinstance(raw, str) and raw.strip() else {})
        if not out:
            continue
        for lg_dir in (d / "i18n").iterdir() if (d / "i18n").is_dir() else []:
            try:
                tr = json.loads((lg_dir / rel / "plot.json").read_text(encoding="utf-8")).get("reveal")
            except (OSError, ValueError, AttributeError):
                continue
            if isinstance(tr, str) and tr.strip():
                out.setdefault(lg_dir.name, tr.strip())
        return out
    return {}


def _orch_options(t: Any) -> dict[str, Any]:
    """The orchestration templates the desk offers (core/orch_presets · core/orch_templates, 10-18 / 10-19): pick
    one (the Default Zone's author may switch it any time), never edit it."""
    from neonrp.core import orch_presets

    return orch_presets.options(t)


def _quiz() -> Any:
    from neonrp.template import creation_quiz   # the 「真相三问」 part (§11)

    return creation_quiz


def _needs(t: Any) -> dict[str, Any]:
    """What the template's mode and play contract ask of every plot (so the form asks for it, not the lint afterwards):
    ``reveal`` = "always" (mode.reveal: every plot carries the truth) · "endings" (the contract reveals it at an ending) · "";
    ``images`` = {(section, picture)} that must be there (rewards.player ending_cg → every ending's art)."""
    from neonrp.template import contract as _c

    mode = getattr(t, "mode", None) or {}
    c: dict[str, Any] = {}
    if getattr(t, "play_contract", ""):
        try:
            c = _c.load(t.play_contract)
        except Exception:  # noqa: BLE001 — an unknown contract is the lint's to report
            c = {}
    reveal = "always" if mode.get("reveal") else "endings" if (c.get("exit") or {}).get("reveal") == "required" else ""
    images = {("ending", "art")} if "ending_cg" in ((c.get("rewards") or {}).get("player") or []) else set()
    return {"reveal": reveal, "images": images}


def check(t: Any, addition: dict[str, Any], *, reg: Any = None) -> list[str]:
    """Problems with what a creator submitted (empty = ok). ``addition`` = {"soul": [...], "plot": [...], "clue": [...],
    "ending": [...], "rule": [...]} as the form produced it. ``reg`` (a built run's registry) also checks references."""
    from neonrp.core import triggers as T

    s = spec(t)
    if not s["open"]:
        return ["this template does not open anything to creators"]
    out: list[str] = []
    rv = form(t).get("reveal")
    if "reveal" in (addition or {}) and not rv:
        out.append("the template does not ask for a reveal")
    elif rv and rv.get("required") and not str((addition or {}).get("reveal") or "").strip():
        out.append("reveal: required")
    out += _quiz().check(t, (addition or {}).get("truth_quiz"))
    oid = (addition or {}).get("orchestration")
    if oid not in (None, ""):
        from neonrp.core import orch_presets

        why = orch_presets.check(t, str(oid)) if isinstance(oid, str) else "must be a template id"
        if why:
            out.append(f"orchestration: {why}")
    for key, rows in (addition or {}).items():
        if key in ("reveal", "truth_quiz", "orchestration"):
            continue
        if key not in ADD:
            out.append(f"unknown section {key!r}")
            continue
        if key not in s["add"]:
            out.append(f"the template does not let creators add {key!r}")
            continue
        sec = next((x for x in form(t)["sections"] if x["key"] == key), {"fields": []})
        for i, row in enumerate(rows if isinstance(rows, list) else []):
            where = f"{key}[{i}]"
            if not isinstance(row, dict):
                out.append(f"{where}: must be an object")
                continue
            for f in sec["fields"]:
                if f.get("required") and f["type"] != "trigger" and not str(row.get(f["name"]) or "").strip():
                    out.append(f"{where}.{f['name']}: required")
                if f["type"] == "enum" and row.get(f["name"]) not in (None, "") and row[f["name"]] not in f["options"]:
                    out.append(f"{where}.{f['name']}: must be one of {', '.join(f['options'])}")
            if key == "rule":
                tr = row.get("trigger")
                if not isinstance(tr, dict):
                    out.append(f"{where}.trigger: required")
                    continue
                n = T.normalize(tr)
                kinds = [k for k in T.WHEN_KINDS if k in (n.get("when") or {})]
                if kinds and kinds[0] not in s["triggers"]["when"]:
                    out.append(f"{where}.trigger.when: {kinds[0]!r} is not open (open: {', '.join(s['triggers']['when'])})")
                for e in [*(n.get("then") or []), *(n.get("else") or [])]:
                    if isinstance(e, dict) and e.get("to") not in s["triggers"]["then"]:
                        out.append(f"{where}.trigger.then: {e.get('to')!r} is not open (open: {', '.join(s['triggers']['then'])})")
                out += [f"{where}.trigger: {p}" for p in T.validate(reg, tr)]
    return out


def to_plot(addition: dict[str, Any], pid: str, *, title: str = "") -> dict[str, Any]:
    """What a creator submitted (checked) as one plot.json: souls → NPC entries, clues → clue entries, endings, rules →
    triggers, souls' collect fields → the plot's collect rules. The template itself is never touched."""
    ends = [e for e in (addition.get("ending") or []) if isinstance(e, dict)]
    ids = [str(e.get("id") or f"{pid}_E{i}") for i, e in enumerate(ends, 1)]

    def ref(x: Any) -> str:  # the desk names an ending of this submission as "#<n>" (it does not know the ids yet)
        x = str(x or "")
        return ids[int(x[1:]) - 1] if x.startswith("#") and x[1:].isdigit() and 0 < int(x[1:]) <= len(ids) else x

    plot_rows = addition.get("plot") or []
    head = plot_rows[0] if plot_rows and isinstance(plot_rows[0], dict) else {}
    out: dict[str, Any] = {"id": pid, "title": str(head.get("title") or title or pid), "entries": {}, "endings": {}, "triggers": {},
                           "collect": {}, "created_by": "creation"}
    if head.get("stages"):
        out["stages"] = [x if isinstance(x, dict) else str(x) for x in head["stages"]]  # a name, or {name, goal} (10-15)
    if head.get("prompt"):
        out["prompt"] = str(head["prompt"])
    if str(addition.get("reveal") or "").strip():   # the truth behind this plot (mode.reveal / the contract's reveal)
        out["reveal"] = str(addition["reveal"]).strip()
    if isinstance(addition.get("truth_quiz"), dict) and _quiz().to_plot(addition["truth_quiz"]):
        out["truth_quiz"] = _quiz().to_plot(addition["truth_quiz"])
    for i, s in enumerate(addition.get("soul") or [], 1):
        eid = f"{pid}_N{i:02d}"
        out["entries"][eid] = {"class": "npc", "name": str(s.get("name") or ""),
                               "props": {k: str(s[k]) for k in ("persona", "appearance") if s.get(k)}}
        on = s.get("collect")
        if on == "clear":
            out["collect"][eid] = {"on": "clear"}
        elif on == "ending" and s.get("collect_ending"):
            out["collect"][eid] = {"on": {"ending": ref(s["collect_ending"])}}
        elif on == "flag" and s.get("collect_flag"):
            out["collect"][eid] = {"on": {"flag": str(s["collect_flag"])}}
        if eid in out["collect"]:
            out["collect"][eid]["rarity"] = str(s.get("rarity") or "common")
    for i, c in enumerate(addition.get("clue") or [], 1):
        out["entries"][f"{pid}_C{i:02d}"] = {"class": "clue", "name": str(c.get("name") or ""),
                                              **({"parent": str(c["where"])} if c.get("where") else {}),
                                              "props": {"summary": str(c.get("summary") or "")}}
    clues = [c for c in (addition.get("clue") or []) if isinstance(c, dict)]
    if clues:   # the built-in classes are item / place / npc: a plot that adds clues declares the class itself
        out["classes"] = {"clue": {"required": ["name"], "render": "- {id} {name}: {summary}", "clue": True,
                                   "scope": "place" if all(c.get("where") for c in clues) else "world"}}
    for eid, e in zip(ids, ends):
        out["endings"][eid] = {"title": str(e.get("title") or ""), "kind": str(e.get("kind") or "alt"),
                                                             **({"text": str(e["text"])} if e.get("text") else {})}
    for i, r in enumerate(addition.get("rule") or [], 1):
        tr = json.loads(json.dumps(r.get("trigger") or {}))
        for e in [*(tr.get("then") or []), *(tr.get("else") or [])]:
            if isinstance(e, dict) and e.get("to") == "end":
                e["ending"] = ref(e.get("ending"))
        out["triggers"][f"{pid}_R{i:02d}"] = {**tr, **({"doc": str(r["doc"])} if r.get("doc") else {})}
    return {k: v for k, v in out.items() if v not in ({}, [])}


# ── the creator's work (the web Hub desk, PLATFORM-PLAY-RULES-1015 §2) ────────
# A work is a copy of the template in the write store: ``<template id>-mine`` by default, more of them on one template as
# ``<template id>-mine-<6 hex>`` (the desk passes the id; lead 10-23) — each names its template in ``forked_from``
# with what the creator added as one plot (WORK_PLOT) and the card they wrote. Saving again rewrites that plot and card;
# the template's own files are copied, never edited. Copying for creation is allowed whenever the template opens a
# creation layer — also for an official world that is not forkable (forking copies it to change it freely; this only adds).

def save(t: Any, addition: dict[str, Any], *, work_id: str, card: dict[str, dict[str, str]] | None = None) -> Any:
    """Check ``addition`` against ``t``'s creation layer, then write it into the creator's work ``work_id`` (made on the
    first save). ``card`` = {lang: {title, pitch}} — the source language goes into template.json, the others into their
    i18n layer. → the work (Template). Raises TemplateError with the problems."""
    from neonrp import template as TP
    from neonrp.template import author

    probs = check(t, addition)
    if probs:
        raise TP.TemplateError("; ".join(probs))
    found = TP.discover()
    if work_id in found:
        w = TP.load(found[work_id])
        if not author.writable(w) or str((w.data.get("forked_from") or {}).get("id") or "") != t.id:
            raise TP.TemplateError(f"{work_id}: not a work made from {t.id}")
    else:
        w = author.fork(t, work_id, creation=True)
    rel = f"plots/{WORK_PLOT}"
    target = w.dir / rel / "plot.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(to_plot(addition, WORK_PLOT), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    d = json.loads((w.dir / "template.json").read_text(encoding="utf-8"))
    if rel not in (d.get("plots") or []):
        d["plots"] = [*(d.get("plots") or []), rel]
    _write_card(w, d, card or {})
    _write_orch(t, d, str((addition or {}).get("orchestration") or ""))
    (w.dir / "template.json").write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    from neonrp.template import v3

    v3.forget(w)   # the new plot's entries are class slots: the next look sees them at once
    return TP.load(w.dir)


def _write_orch(t: Any, d: dict[str, Any], oid: str) -> None:
    """The chosen orchestration template as the work's ``uses`` (10-19 stage A; none chosen = the world's own). Computed
    from the world every time, so switching never leaves an earlier choice behind: the work's ``pack.engine`` is the
    world's, less what a template decides when the work plays another one than the world (stoneford-town's own
    ``plan_loop: off`` would otherwise keep a work on the two beats single-beat)."""
    from neonrp.core import orch_presets, orch_templates

    own_eng = dict((getattr(t, "pack", None) or {}).get("engine") or {})
    mine = orch_presets.normalize(t, oid)
    u = orch_presets.uses_for(t, mine) if mine and mine != orch_presets.default_for(t) else None
    if u is not None:
        own_eng = orch_templates.without_owned(own_eng)
        # the characters' orchestration stays the world's (an old package without uses: what its pack makes them do)
        soul = (getattr(t, "uses", None) or {}).get("soul") or str(orch_templates._get(orch_presets._effective(t), orch_templates.VARIANT_KEY) or "")
        d["uses"] = {"template": u["template"], "version": u["version"], **({"soul": soul} if soul else {}),
                     **({"params": u["params"]} if u["params"] else {})}
    elif "uses" in (t.data or {}):
        d["uses"] = copy.deepcopy(t.data["uses"])
    else:
        d.pop("uses", None)
    pack = d.setdefault("pack", {})
    if own_eng:
        pack["engine"] = own_eng
    else:
        pack.pop("engine", None)


def _write_card(w: Any, d: dict[str, Any], card: dict[str, Any]) -> None:
    from neonrp.template import i18n as _i18n

    src = _i18n.source_lang(w)
    for lg, c in card.items():
        if lg not in _i18n.LANGS or not isinstance(c, dict):
            continue
        patch = {k: str(c[k]).strip() for k in ("title", "pitch") if str(c.get(k) or "").strip()}
        if not patch:
            continue
        if lg == src:
            d.setdefault("card", {}).update(patch)
            continue
        f = w.dir / _i18n.DIR / lg / "template.json"
        try:
            over = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
        except (OSError, ValueError):
            over = {}
        over = over if isinstance(over, dict) else {}
        over.setdefault("card", {}).update(patch)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(over, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def slots(w: Any) -> list[dict[str, Any]]:
    """The pictures of the creator's work the desk shows: the cover (required) and one per added soul / ending / clue,
    each with the form row it belongs to (``row: {sec, i}``) so an upload lands on the right slot."""
    from neonrp import template as TP

    pre = f"plot:plots/{WORK_PLOT}:"
    kinds = {"N": "soul", "E": "ending", "C": "clue"}
    pic = {"card": "cover", **dict(IMAGES)}
    req = {(i["for"], i["name"]) for i in form(w)["images"] if i.get("required")}
    out = []
    for s in TP.asset_slots(w, classes=False):
        row = None
        if s["slot"] == "card:cover":
            row = {"sec": "card", "i": 0}
        elif s["slot"].startswith(pre) and "@" not in s["slot"]:
            eid = s["slot"].rsplit(":", 1)[-1]
            tail = eid[len(WORK_PLOT) + 1:] if eid.startswith(WORK_PLOT + "_") else ""
            if tail[:1] in kinds and tail[1:].isdigit():
                row = {"sec": kinds[tail[0]], "i": int(tail[1:]) - 1}
        if row is not None:
            out.append({k: s.get(k) for k in ("slot", "cls", "label", "have", "path")}
                       | {"name": pic[row["sec"]], "need": bool(s.get("need")) or (row["sec"], pic[row["sec"]]) in req, "row": row})
    return out


# ── collection ───────────────────────────────────────────────────────────────

def rules(plot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """A plot's collect rules, normalised: {who: {"on": "clear" | {"ending": id} | {"flag": key}, "rarity": …}}."""
    raw = plot.get("collect") if isinstance(plot, dict) else None
    out: dict[str, dict[str, Any]] = {}
    for who, r in (raw.items() if isinstance(raw, dict) else []):
        r = {"on": r} if isinstance(r, str) else dict(r or {})
        on = r.get("on", "clear")
        out[str(who)] = {"on": on, "rarity": str(r.get("rarity") or "common")}
    return out


def _world_names(t: Any, plots: list[dict[str, Any]], wdir: Any) -> set[str]:
    """Every name / id a character in the world goes by: the template's cast, the world's souls, the plots' NPC entries."""
    from neonrp.template import _world_souls

    names: set[str] = set()
    for s in getattr(t, "souls", None) or []:
        for r in [{"sid": x} if isinstance(x, str) else x for x in s.get("pool")] if isinstance(s.get("pool"), list) else [s]:
            names.update(str(r.get(k)) for k in ("sid", "name") if r.get(k))
    if wdir is not None:
        for sid, s in _world_souls(wdir).items():
            names.update(x for x in (sid, str(s.get("name") or ""), str(s.get("instance_id") or "")) if x)
    for p in plots:
        for eid, e in (p.get("entries") or {}).items():
            if isinstance(e, dict) and str(e.get("class") or "") in ("npc", "soul", "character"):
                names.update(x for x in (str(eid), str(e.get("name") or "")) if x)
    return names


def lint(t: Any, plots: list[dict[str, Any]], wdir: Any, c: dict[str, Any] | None) -> list[tuple[str, str, str, str]]:
    """(level, code, where, msg): collect rules point at characters in the world and at endings that exist;
    the contract's collect floor is met."""
    out = list(spec_problems(t))
    names = _world_names(t, plots, wdir)
    endings = {str(e) for p in plots for e in (p.get("endings") or {})}
    n = 0
    for p in plots:
        for who, r in rules(p).items():
            where = f"{p.get('id')}.collect.{who}"
            n += 1
            if who not in names:
                out.append(("block", "collect.who", where, "only characters that live in the world can be collected"))
            on = r["on"]
            kind = on if isinstance(on, str) else next((k for k in ("ending", "flag") if isinstance(on, dict) and k in on), "")
            if kind not in COLLECT_ON:
                out.append(("block", "collect.on", where, f"`on` must be one of {', '.join(COLLECT_ON)}"))
            elif kind == "ending" and str(on["ending"]) not in endings:
                out.append(("block", "collect.on", where, f"no ending {on['ending']!r}"))
            if r["rarity"] not in RARITY:
                out.append(("warn", "collect.rarity", where, f"rarity must be one of {', '.join(RARITY)}"))
    floor = (c or {}).get("collect") if isinstance((c or {}).get("collect"), dict) else {}
    if floor.get("souls") is False and n:
        out.append(("block", "collect.contract", "collect", "the contract does not reward souls; drop the collect rules"))
    if int(floor.get("min") or 0) > n:
        out.append(("block", "collect.contract", "collect.min", f"the contract needs ≥ {floor['min']} collectable characters, has {n}"))
    return out


def granted(plots: list[dict[str, Any]], *, ending: dict[str, Any] | None, flags: dict[str, bool]) -> list[dict[str, Any]]:
    """Who this run lets the player collect: [{who, plot, rarity, why}]. ``ending`` = the ending the run reached (or None)."""
    out: list[dict[str, Any]] = []
    eid = str((ending or {}).get("id") or "")
    cleared = bool(ending) and str((ending or {}).get("kind") or "") not in FAIL_KINDS
    for p in plots:
        for who, r in rules(p).items():
            on, why = r["on"], None
            if on == "clear" and cleared:
                why = f"clear:{eid}"
            elif isinstance(on, dict) and "ending" in on and eid and str(on["ending"]) == eid:
                why = f"ending:{eid}"
            elif isinstance(on, dict) and "flag" in on and flags.get(str(on["flag"])):
                why = f"flag:{on['flag']}"
            if why:
                out.append({"who": who, "plot": p.get("id"), "rarity": r["rarity"], "why": why})
    return out
