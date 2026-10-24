"""Orchestration presets — what a limited creation desk lets a creator pick from (10-18: the web Hub's Default Zone and
the iOS desk offer a few orchestrations; the chosen one is drawn as a read-only graph that explains what a turn does — the
local orchestration bench stays the only editor).

A world's choices are the orchestration templates (core/orch_templates, 10-19 stage A: a template = one world
orchestration + the orchestration its characters' beat uses; the desk picks a template, the work names it in
``template.json`` ``uses``). A choice travels as one string, :func:`orch_templates.ref` — ``<template id>`` or
``<template id>?<param>=<choice>`` (the two beats' quick pace is such a parameter, no longer a preset of its own).

A character's presets (``subject: soul``) are data (``worldlines.orchestration-presets/1``) from the engine's
``core/orch_presets.json`` and the private layer's ``orchestrations/presets.json`` (later wins, by id).

Their words are the ``orch_presets`` string table (four languages; the private layer adds its templates' and nodes'
entries). The read-only view (:func:`views`) carries names and one-line explanations only — never a prompt, a tool list
or a setting's value, except the settings a template's own parameter choices change (shown on the node they belong
to, so two choices look different). Nothing here knows any world.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

SCHEMA = "worldlines.orchestration-presets/1"
VIEW = "worldlines.orchestration-view/1"
_FILE = Path(__file__).with_name("orch_presets.json")
_LAYER_KINDS = ("mode", "place", "one_shot", "phase")


def _read(p: Path | None) -> list[dict[str, Any]]:
    try:
        d = json.loads(p.read_text(encoding="utf-8")) if p is not None and p.is_file() else {}
    except (OSError, ValueError):
        return []
    rows = d.get("presets") if isinstance(d, dict) else None
    return [r for r in rows or [] if isinstance(r, dict) and r.get("id")]


def _deep_merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(a)
    for k, v in (b or {}).items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def presets(subject: str = "world") -> list[dict[str, Any]]:
    """Every choice this engine can run for ``subject`` (``world``: the orchestration templates · ``soul``), in order."""
    if subject == "world":
        from neonrp.core import orch_templates as OT

        return [{"id": t["id"], "subject": "world", "order": t["order"], "nodes": list(t["world"]["nodes"]),
                 "engine": OT.engine_of(t), "params": {k: list(p["choices"]) for k, p in t["params"].items()}}
                for t in OT.templates()]
    from neonrp.core.paths import private_dir

    priv = private_dir("orchestrations")
    by: dict[str, dict[str, Any]] = {}
    for r in _read(_FILE) + _read(priv / "presets.json" if priv is not None else None):
        if str(r.get("subject") or "world") != subject:
            continue
        p = {"id": str(r["id"]), "subject": subject, "order": int(r.get("order") or 100),
             "graph": copy.deepcopy(r["graph"]) if isinstance(r.get("graph"), dict) else {}}
        by[p["id"]] = p
    return sorted((p for p in by.values() if _soul_runnable(p)), key=lambda p: (p["order"], p["id"]))


def get(pid: str, subject: str = "world") -> dict[str, Any] | None:
    """A choice by id — for a world, a template's (a :func:`orch_templates.ref` names its template)."""
    pid = str(pid or "").partition("?")[0] if subject == "world" else str(pid or "")
    return next((p for p in presets(subject) if p["id"] == pid), None)


def _effective(t: Any) -> dict[str, Any]:
    """The turn settings a world plays with: the template layers a run built from it starts with (no env)."""
    from neonrp.core import soul_orchestration as SO

    eng: dict[str, Any] = {}
    for name, layer in SO._template_layers(t):
        if name != "env":
            eng = _deep_merge(eng, layer)
    return eng


def default_for(t: Any) -> str:
    """The choice a world plays as untouched (a :func:`orch_templates.ref`): the template it names (or the one it falls
    back to on this engine); a world naming none (an old package) — the template its settings match best, else the first."""
    from neonrp.core import orch_templates as OT

    u = OT.parse_uses(getattr(t, "data", {}).get("uses"))
    if u is not None:
        r = OT.resolve(u["template"])
        if r is None:
            return ""
        return OT.ref(u if r["id"] == u["template"] else {"template": r["id"], "params": {}})
    ts = OT.templates()
    eff = _effective(t)
    hit = [r for r in ts if OT.matches(eff, r)]
    hit.sort(key=lambda r: (-len(OT._flat(r["world"]["engine"])), r["order"]))
    return hit[0]["id"] if hit else (ts[0]["id"] if ts else "")


def normalize(t: Any, choice: str) -> str:
    """A desk's choice as a ref (an old preset id read as the template it now is; '' stays '')."""
    from neonrp.core import orch_templates as OT

    return OT.ref(OT.from_ref(choice)) if str(choice or "").strip() else ""


def check(t: Any, choice: str) -> str | None:
    """Why ``choice`` is not one the desk offers for ``t`` (None = fine; '' = the world's own)."""
    from neonrp.core import orch_templates as OT

    return OT.check_ref(normalize(t, choice)) if str(choice or "").strip() else None


def uses_for(t: Any, choice: str) -> dict[str, Any] | None:
    """The ``uses`` a work made from ``t`` stores for ``choice`` (a ref; '' = the world's own)."""
    from neonrp.core import orch_templates as OT

    return OT.from_ref(normalize(t, choice) or default_for(t))


# ── words (four languages) ───────────────────────────────────────────────────

def _langs() -> tuple[str, ...]:
    from neonrp.prompts import LANGS

    return LANGS


def _tables() -> dict[str, dict[str, Any]]:
    from neonrp.prompts import strings

    return {lg: strings("orch_presets", lg) for lg in _langs()}


def _word(tb: dict[str, dict[str, Any]], key: str, field: str, fallback: str = "", **fmt: Any) -> dict[str, str]:
    out = {}
    for lg, d in tb.items():
        v = d.get(key)
        s = v.get(field) if isinstance(v, dict) else (v if field == "" else None)
        s = str(s if s is not None else fallback)
        try:
            out[lg] = s.format(**fmt) if fmt else s
        except (KeyError, IndexError, ValueError):
            out[lg] = s
    return out


def _params(tb: dict[str, dict[str, Any]], p: dict[str, Any]) -> list[dict[str, Any]]:
    """A template's parameters for the form: names and each choice's words (never the settings behind them)."""
    from neonrp.core import orch_templates as OT

    t = OT.get(p["id"]) or {"params": {}}
    return [{"id": name, "default": spec["default"], "title": _word(tb, f"param.{name}", "title", name),
             "choices": [{"id": ch, "title": _word(tb, f"param.{name}.{ch}", "title", ch),
                          "summary": _word(tb, f"param.{name}.{ch}", "summary")} for ch in spec["choices"]]}
            for name, spec in t["params"].items()]


def options(t: Any) -> dict[str, Any]:
    """The creation form's orchestration part: ``{default, options: [{id, title, summary, params?}]}`` (texts by
    language); ``default`` is a ref (a template id, with a parameter choice when the world picked one)."""
    tb = _tables()
    out = []
    for p in presets():
        o = {"id": p["id"], "title": _word(tb, f"template.{p['id']}", "title", p["id"]),
             "summary": _word(tb, f"template.{p['id']}", "summary")}
        ps = _params(tb, p)
        out.append({**o, "params": ps} if ps else o)
    return {"default": default_for(t), "options": out}


# ── the read-only view ───────────────────────────────────────────────────────

def _steps(node: str, tb: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """A core node's steps: id · who does it (engine / model / judge) · title · one line, in every language. Never a
    prompt or a setting."""
    from neonrp.core import turn_steps
    from neonrp.prompts import strings

    cat = {lg: (strings("turn_steps", lg).get("steps") or {}) for lg in _langs()} if node == "resolve" else {}
    own = {lg: (d.get(f"steps.{node}") or {}) for lg, d in tb.items()}
    out = []
    for st in turn_steps.steps_of(node):
        sid = str(st["id"])
        title, doc = {}, {}
        for lg in _langs():
            w = (cat.get(lg) or {}).get(sid) or own[lg].get(sid) or {}
            title[lg] = str(w.get("title") or st.get("title") or sid)
            doc[lg] = str(w.get("doc") or st.get("doc") or "")
        out.append({"id": sid, "by": str(st.get("backend") or "python"), "title": title, "doc": doc,
                    **({"parallel": True} if st.get("parallel") else {}), **({"required": True} if st.get("required") else {})})
    return out


def _layer_title(pk: Any, nid: str, n: dict[str, Any]) -> dict[str, str]:
    spec = (getattr(pk, "modes", None) or {}).get(nid) if pk is not None else None
    t = spec.get("title") if isinstance(spec, dict) else n.get("title")
    if isinstance(t, dict):
        first = str(next(iter(t.values()), "") or nid)
        return {lg: str(t.get(lg) or t.get("en") or first) for lg in _langs()}
    return {lg: str(t or nid) for lg in _langs()}


def _label(tb: dict[str, dict[str, Any]], on: dict[str, Any], ret: bool = False) -> dict[str, str]:
    """An edge's trigger in words (the ``on.*`` entries of the table)."""
    if ret:
        return _word(tb, "on.return", "", "", v=str(on.get("op") or ""))
    kind = next(iter(on), "always") if isinstance(on, dict) and on else "always"
    v = on.get(kind) if isinstance(on, dict) else True
    if kind == "op" and "value" in on:
        kind, v = "phase", on["value"]
    return _word(tb, f"on.{kind}", "", kind, v="" if v is True else str(v))


def _pack_of(t: Any) -> Any:
    from neonrp import packs
    from neonrp.template import world_dir

    try:
        return packs.load(t.pack_name, world_dir(t))
    except Exception:  # noqa: BLE001 — a pack that does not load: the core nodes only
        return None


def _combos(params: dict[str, Any]) -> list[dict[str, str]]:
    """Every combination of a template's parameter choices (the default combination first)."""
    out: list[dict[str, str]] = [{}]
    for name, spec in params.items():
        chs = [spec["default"], *[c for c in spec["choices"] if c != spec["default"]]]
        out = [{**o, name: c} for o in out for c in chs]
    return out


def _value_words(tb: dict[str, dict[str, Any]], v: Any) -> dict[str, str]:
    if isinstance(v, bool):
        return _word(tb, "value.on" if v else "value.off", "", "on" if v else "off")
    if str(v).lower() in ("on", "off"):
        return _word(tb, f"value.{str(v).lower()}", "", str(v).lower())
    return {lg: str(v) for lg in _langs()}


def _settings(tid: str, params: dict[str, str], node: str, tb: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """The settings of ``node`` that the template's parameter choices change, as this combination sets them (pace:
    quick → how many rounds the host takes …): id (its place on the node, the same in every choice) · title · a short
    form for the graph · how it reads now (``shows``) · changed (vs the template's default choices). Never the setting's
    engine key — only these, and the rest of a node's settings stay out of the read-only view."""
    from neonrp.core import orch_templates as OT, turn_steps

    t = OT.get(tid)
    if t is None or not t["params"]:
        return []
    keys = {k for p in t["params"].values() for ch in p["choices"].values() for k in OT._flat(ch)}
    mine = {p["key"]: p for st in turn_steps.steps_of(node) for p in st.get("params") or [] if p.get("key") in keys}
    if not mine:
        return []
    now, base = OT._flat(OT.engine_of(t, params, soul=None)), OT._flat(OT.engine_of(t, None, soul=None))
    out = []
    for i, (key, p) in enumerate(mine.items(), 1):
        v, d = now.get(key, p.get("default")), base.get(key, p.get("default"))
        val = _value_words(tb, v)
        out.append({"id": f"{node}.{i}", "title": _word(tb, f"setting.{key}", "title", str(p.get("doc") or i)),
                    "short": {lg: _word(tb, f"setting.{key}", "short", "{v}")[lg].replace("{v}", val[lg]) for lg in _langs()},
                    "shows": val, **({"changed": True} if v != d else {})})
    return out


def view(t: Any, pid: str, *, pk: Any = None, tb: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """What a turn of ``t`` does under preset ``pid``, as a read-only graph: the preset's core nodes with their steps, the
    template's own layers (a fight, a dungeon, a phase …) and how a turn moves between them — titles and one-line
    explanations in every language, nothing an editor could change."""
    from neonrp.core import orchestration

    from neonrp.core import orch_templates as OT

    p = get(pid)
    if p is None:
        raise KeyError(pid)
    u = OT.from_ref(pid) or {"params": {}}
    tpl = OT.get(p["id"]) or {"params": {}}
    params = {name: str(u["params"].get(name) or spec["default"]) for name, spec in tpl["params"].items()}
    pid = p["id"]
    tb = tb or _tables()
    pk = pk if pk is not None else _pack_of(t)
    full = orchestration._build_default(pk)
    core = list(p["nodes"])
    nodes: list[dict[str, Any]] = []
    for nid in core:
        st = _settings(pid, params, nid, tb)
        nodes.append({"id": nid, "kind": "core", "title": _word(tb, f"node.{nid}", "title", nid),
                      "summary": _word(tb, f"node.{nid}", "summary"), "steps": _steps(nid, tb), **({"settings": st} if st else {})})
    layers = {nid: n for nid, n in (full.get("nodes") or {}).items()
              if isinstance(n, dict) and n.get("kind") in _LAYER_KINDS and nid not in core}
    for nid, n in layers.items():
        k = str(n.get("kind"))
        nodes.append({"id": nid, "kind": k, "title": _layer_title(pk, nid, n), "summary": _word(tb, f"kind.{k}", "")})
    have = {n["id"] for n in nodes}
    hub = "resolve" if "resolve" in have else core[0]
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for e in full.get("edges") or []:
        frm, to = str(e.get("from") or ""), str(e.get("to") or "")
        ret = to == orchestration.RETURN
        frm = hub if frm == "*" else frm
        to = hub if ret else to
        if frm not in have or to not in have or (frm == to and not ret):
            continue
        key = (frm, to)
        m = merged.setdefault(key, {"from": frm, "to": to, "labels": []})
        lab = _label(tb, e.get("on") or {}, ret)
        if lab not in m["labels"]:
            m["labels"].append(lab)
    for nid, n in layers.items():   # a place layer is left by walking out, a one-off one after its beat: no edge says so
        back = {"place": "on.leave", "one_shot": "on.done"}.get(str(n.get("kind")))
        if back and (nid, hub) not in merged:
            merged[(nid, hub)] = {"from": nid, "to": hub, "labels": [_word(tb, back, "")]}
    edges = list(merged.values())
    if not any(e["from"] == hub and e["to"] == hub for e in edges) and core == [hub]:
        edges.append({"from": hub, "to": hub, "labels": [_word(tb, "on.next", "")]})   # the plain turn, line after line
    start = str(full.get("start") or hub)
    return {"schema": VIEW, "template": str(getattr(t, "id", "")), "preset": pid, "readonly": True,
            **({"ref": OT.ref({"template": pid, "params": params}), "choice": params} if params else {}),
            "title": _word(tb, f"template.{pid}", "title", pid), "summary": _word(tb, f"template.{pid}", "summary"),
            "start": start if start in core else core[0], "nodes": nodes, "edges": edges}


def views(t: Any) -> dict[str, Any]:
    """Every preset's view for ``t`` plus the form's part (the desk switches presets without asking again). A template
    with parameters gets one view per combination of their choices, keyed by its ref (``two_beat`` = the default
    choices, ``two_beat?pace=quick`` …; 10-23: the two paces looked the same), each node carrying the settings that
    choice changes."""
    from neonrp.core import orch_templates as OT

    tb, pk = _tables(), _pack_of(t)
    out: dict[str, Any] = {}
    for p in presets():
        tpl = OT.get(p["id"]) or {"params": {}}
        for combo in _combos(tpl["params"]):
            r = OT.ref({"template": p["id"], "params": combo})
            out[r] = view(t, r, pk=pk, tb=tb)
    return {"schema": VIEW, "template": str(getattr(t, "id", "")), **options(t), "views": out}


# ── soul presets (subject: soul) ─────────────────────────────────────────────
# A soul preset carries the graph itself (core/soul_orchestration's shape, structure only: no parameter values — the
# node kinds give the defaults). Not offered anywhere for now (10-19: an orchestration is one system of the
# template — world and characters together — not a pick per character; the creation desk's per-row picker is gone).
SOUL_DEFAULT = "chat_only"


def _so_kinds() -> dict[str, Any]:
    """core/soul_orchestration's node kinds (with what plugins extend, where that engine has it)."""
    from neonrp.core import soul_orchestration as SO

    return SO.kinds() if hasattr(SO, "kinds") else copy.deepcopy(SO.NODE_KINDS)


def _soul_runnable(p: dict[str, Any]) -> bool:

    nodes = (p.get("graph") or {}).get("nodes") or {}
    kinds = _so_kinds()
    return bool(nodes) and all(isinstance(n, dict) and n.get("kind") in kinds for n in nodes.values())


def _soul_node(n: dict[str, Any]) -> dict[str, Any]:
    """A preset node as the engine runs it: the kind's defaults and its live tools (a preset carries structure only)."""
    from neonrp.core import soul_orchestration as SO

    k = str(n["kind"])
    spec = _so_kinds().get(k) or {}
    tools = n.get("tools") if isinstance(n.get("tools"), list) else [x for x in spec.get("tools") or [] if (SO.TOOLS.get(x) or {}).get("live")]
    return {"kind": k, "title": k, "tools": [str(x) for x in tools], **SO.node_params({}, k)}


def soul_graph(pid: str) -> dict[str, Any]:
    """The file a chosen soul preset writes: a whole ``worldlines.orchestration/1`` graph with ``subject: soul``."""
    from neonrp.core import soul_orchestration as SO

    p = get(pid, "soul")
    if p is None:
        raise KeyError(pid)
    g = copy.deepcopy(p["graph"])
    return {"schema": SO.SCHEMA, "subject": SO.SUBJECT, "id": f"preset:{pid}", "targets": {"soul_spec": SO.SOUL_SPEC, "world_spec": SO.WORLD_SPEC},
            "start": str(g.get("start") or next(iter(g.get("nodes") or {}), "chat")),
            "nodes": {k: _soul_node(v) for k, v in (g.get("nodes") or {}).items()},
            "edges": [dict(e) for e in g.get("edges") or [] if isinstance(e, dict)]}


def _sw(d: dict[str, Any], own: dict[str, Any], kind: str, sid: str) -> dict[str, Any]:
    """A soul step's words: ``soul.steps.<kind>`` {id: …}, or the flat ``soul.steps.<kind>.<id>`` a plugin adds for a
    step it extends a kind with (the private layer's table merges key by key, so it cannot add inside the kind's dict)."""
    w = d.get(f"soul.steps.{kind}.{sid}")
    return w if isinstance(w, dict) else (own.get(sid) if isinstance(own.get(sid), dict) else {})


def _txt(x: Any) -> str:
    """A table entry as text: a string, or ``{"title": …}``."""
    return str(x.get("title") or "") if isinstance(x, dict) else str(x or "")


def soul_view(pid: str, *, tb: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """A soul preset as a read-only graph (the same view shape as :func:`view`): each node's kind, title, one line and
    steps (id · who does it, words from the table — never a parameter or a prompt), edges with their trigger in words."""

    tb = tb or _tables()
    g, kinds = soul_graph(pid), _so_kinds()
    nodes = []
    for nid, n in g["nodes"].items():
        k = n["kind"]
        own = {lg: (d.get(f"soul.steps.{k}") or {}) for lg, d in tb.items()}
        steps = [{"id": str(st["id"]), "by": {"engine": "python", "hook": "python"}.get(str(st.get("by")), str(st.get("by") or "python")),
                  "title": {lg: str(_sw(tb[lg], own[lg], k, st["id"]).get("title") or st["id"]) for lg in _langs()},
                  "doc": {lg: str(_sw(tb[lg], own[lg], k, st["id"]).get("doc") or "") for lg in _langs()}}
                 for st in (kinds.get(k) or {}).get("steps") or [] if isinstance(st, dict) and st.get("id")]
        nodes.append({"id": nid, "kind": "core", "soul_kind": k, "title": _word(tb, f"soul.node.{k}", "title", k),
                      "summary": _word(tb, f"soul.node.{k}", "summary"), "steps": steps})
    edges: dict[tuple[str, str], dict[str, Any]] = {}
    for e in g["edges"]:
        on = e.get("on") if isinstance(e.get("on"), dict) else {}
        kind = next(iter(on), "always")
        v = on.get(kind)
        lab = {lg: _txt(d.get(f"soul.on.{kind}")) or _txt(d.get(f"on.{kind}")) or kind for lg, d in tb.items()}
        lab = {lg: (x.replace("{v}", "" if v is True else str(v))) for lg, x in lab.items()}
        m = edges.setdefault((str(e.get("from")), str(e.get("to"))), {"from": str(e.get("from")), "to": str(e.get("to")), "labels": []})
        if lab not in m["labels"]:
            m["labels"].append(lab)
    return {"schema": VIEW, "subject": "soul", "preset": pid, "readonly": True,
            "title": _word(tb, f"preset.{pid}", "title", pid), "summary": _word(tb, f"preset.{pid}", "summary"),
            "start": g["start"], "nodes": nodes, "edges": list(edges.values())}


def soul_options() -> dict[str, Any]:
    tb = _tables()
    ps = presets("soul")
    return {"default": SOUL_DEFAULT if any(p["id"] == SOUL_DEFAULT for p in ps) else (ps[0]["id"] if ps else ""),
            "options": [{"id": p["id"], "title": _word(tb, f"preset.{p['id']}", "title", p["id"]),
                         "summary": _word(tb, f"preset.{p['id']}", "summary")} for p in ps]}


def soul_views() -> dict[str, Any]:
    tb = _tables()
    return {"schema": VIEW, "subject": "soul", **soul_options(), "views": {p["id"]: soul_view(p["id"], tb=tb) for p in presets("soul")}}
