"""The orchestration graph — states and the transitions between them, as data (worldlines.orchestration/1).


A graph has **nodes** (a state: the Planning loop, the Resolve loop, a pack's mode layers, a phase of a phase variable)
and **edges** ``{id, from, to, on, when?, return?}``:

    on    what fires it — one of
          {"event": "external"}   an outside event that does not wait for the talk (a layer running, the template's seam)
          {"words": "commit"}     the player's commit word (plan_loop.COMMIT_RE); a list of words adds the author's own
          {"host": "advance"}     the host's ``next: advance``
          {"dm": true}            an @GM (@dm / @主持 alike) (the player's or a character's)
          {"judge": "settled"}    the judge says the talk is settled
          {"always": true}        unconditional (Resolve → Planning)
          {"op": "<op>", …}       an op landed (a mode switch tag, a layer's exit op, a phase op with its value)
          {"gate": true}          the template's gate seam forced a layer for this beat
          {"here_class": "<cls>"} the player stands at an entry of that class (a place-keyed layer)
          {"tick": "<name>"}      a pack's own rule (rpg: a room's encounter roll)
    when  optional guard: [{"var": name, "==" | "!=" | "<" | "<=" | ">" | ">=": value}] on the registry's variables
    return  entering pushes a return point; ``to: "@return"`` goes back to the layer it was entered from (a stack, O4)

Where the graph comes from (later wins): the engine's **default graph** generated from today's behaviour (the two
beats + the pack's modes / mode ops / exit ops / here_class / gate seam) · the **pack's** own ``orchestration``
(extra nodes and edges: phases, encounters) · the **template / run** override ``game/meta/orchestration.json``
(a whole graph with ``nodes`` + ``edges``, or a patch ``{"remove": [edge ids], "add": [edges]}``).

Behaviour is unchanged without an override: every switch the engine makes asks :func:`allows`, which refuses only what
the default graph allows and the effective graph took away; edges an override *adds* are honoured where the engine
looks for them (here-class layers, the player's words). Nothing here knows any world.
"""
from __future__ import annotations

import json

from neonrp.core import node_kinds as _node_kinds
from pathlib import Path
from typing import Any

SCHEMA = "worldlines.orchestration/1"
PLAN, RESOLVE, RETURN = "plan", "resolve", "@return"
_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}


def _edge(eid: str, frm: str, to: str, on: dict[str, Any], **kw: Any) -> dict[str, Any]:
    return {"id": eid, "from": frm, "to": to, "on": on, **kw}


_DEFAULT: dict[tuple[str, int], dict[str, Any]] = {}


def default_graph(root: Path) -> dict[str, Any]:
    """The graph today's engine runs, generated from the pack (no override): the two beats and the pack's layers."""
    from neonrp.packs import resolve as resolve_pack

    try:
        pk = resolve_pack(root)
    except Exception:  # noqa: BLE001 — no pack: the two beats only
        pk = None
    key = (str(Path(root).resolve()), id(pk), _private_stamp(pk), tuple(_node_kinds.kinds()))  # private graph / plugins change → rebuilt
    if key not in _DEFAULT:
        if len(_DEFAULT) > 64:
            _DEFAULT.clear()
        _DEFAULT[key] = _build_default(pk)
    return _DEFAULT[key]


def _build_default(pk: Any) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {
        RESOLVE: {"kind": "loop", "title": "resolve", "prompt": "narrate", "tools": "@pack.actions",
                  "steps": [],  # filled from core/turn_steps below
                  "state": "pseudo"},  # how this beat writes state — a parameter the author sets (STATE_MODES)
    }
    edges: list[dict[str, Any]] = []
    start = RESOLVE  # the engine's own graph: the plain turn, again and again (10-08: no beat is built in)
    for kind in _node_kinds.kinds():  # node-kind plugins (the planning beat …) bring their nodes, edges and start
        g = _node_kinds.call(kind, "graph", default=None)
        if isinstance(g, dict):
            nodes.update({k: dict(v) for k, v in (g.get("nodes") or {}).items() if isinstance(v, dict)})
            edges += [dict(e) for e in g.get("edges") or [] if isinstance(e, dict)]
            start = str(g.get("start") or start)
    from neonrp.core import turn_steps  # 10-17 S1: a node's steps are the step catalog's (what the beat really runs)

    for nid in turn_steps.nodes():
        if nid in nodes:
            nodes[nid]["steps"] = turn_steps.ids(nid)
    if pk is None:
        return {"schema": SCHEMA, "id": "default", "start": start, "nodes": nodes, "edges": edges}
    modes = dict(getattr(pk, "modes", {}) or {})
    switch_ops = {a.op: a for a in pk.actions if a.kind == "mode" and a.enabled}
    call_ops = {a.op for a in pk.actions if a.kind == "tool" and a.enabled}  # a one-shot node called by its tool, from wherever the beat is
    has_gate = str((pk.mechanics or {}).get("gate") or "builtin:none") != "builtin:none"
    for name, spec in modes.items():
        if not isinstance(spec, dict):
            continue
        kind = "one_shot" if spec.get("one_shot") else ("place" if spec.get("here_class") else "mode")
        _t = spec.get("title")
        _t = (_t.get("zh") or next(iter(_t.values()), "")) if isinstance(_t, dict) else _t  # a {lang: text} title: the graph keeps one name
        nodes[name] = {"kind": kind, "mode": name, "title": str(_t or name),
                       **({"here_class": spec["here_class"]} if spec.get("here_class") else {}),
                       **({"exit": spec["exit"]} if spec.get("exit") else {}),
                       "tools": list(spec.get("ops") or [])}
    place_layers = [n for n, s in modes.items() if isinstance(s, dict) and s.get("here_class")]
    for name, spec in modes.items():
        if not isinstance(spec, dict):
            continue
        if name in switch_ops:  # a switch tag in the prose: from the Resolve, and from a place layer (layer_ops lets it)
            edges.append(_edge(f"resolve>{name}:op", RESOLVE, name, {"op": name}, **{"return": True}))
            for pl in place_layers:
                if pl != name:
                    edges.append(_edge(f"{pl}>{name}:op", pl, name, {"op": name}, **{"return": True}))
        if spec.get("one_shot"):  # 10-18: the Resolve calls it and it returns within the beat — never a state the world is in
            if name in call_ops:
                edges.append(_edge(f"resolve>{name}:call", RESOLVE, name, {"op": name}, **{"return": True}))
                for pl in place_layers:  # a place layer is the Resolve's prompt where the player stands (a dungeon room)
                    edges.append(_edge(f"{pl}>{name}:call", pl, name, {"op": name}, **{"return": True}))
            continue
        if spec.get("here_class"):
            edges.append(_edge(f"*>{name}:here", "*", name, {"here_class": str(spec["here_class"])}, **{"return": True}))
        if has_gate and not spec.get("here_class"):
            edges.append(_edge(f"*>{name}:gate", "*", name, {"gate": True}, **{"return": True}))
        if spec.get("exit"):
            edges.append(_edge(f"{name}>@return:{spec['exit']}", name, RETURN, {"op": str(spec["exit"])}))
    extra = getattr(pk, "orchestration", None) or {}
    g = {"schema": SCHEMA, "id": f"{pk.name}-default", "start": start, "nodes": nodes, "edges": edges}
    g = _patch(g, {"add": list(extra.get("edges") or []), "nodes": dict(extra.get("nodes") or {})})
    for p in _private_pack_graphs(pk):  # 10-08: our own pack orchestration, over the pack's public graph
        g = _patch(g, p)
    return g


def _private_files(pk: Any) -> list[Path]:
    from neonrp.core.paths import private_dir

    priv = private_dir("packs")
    if priv is None or pk is None:
        return []
    names = [str(getattr(pk, "base", "") or ""), str(pk.name or "").split("+")[0]]
    return [priv / n / "orchestration.json" for n in dict.fromkeys(x for x in names if x)]


def _private_stamp(pk: Any) -> tuple[tuple[str, float], ...]:
    out = []
    for f in _private_files(pk):
        try:
            out.append((str(f), f.stat().st_mtime))
        except OSError:
            continue
    return tuple(out)


def _private_pack_graphs(pk: Any) -> list[dict[str, Any]]:
    """The private layer's ``packs/<pack>/orchestration.json`` patches (base pack's first, then the pack's own) —
    ``{"add": [edges], "remove": [edge ids], "nodes": {...}}``, the same shape as a template override."""
    out: list[dict[str, Any]] = []
    for f in _private_files(pk):
        try:
            d = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None
        except (OSError, ValueError):
            d = None
        if isinstance(d, dict):
            out.append(d)
    return out


def _patch(g: dict[str, Any], p: dict[str, Any]) -> dict[str, Any]:
    out = {**g, "nodes": {**g.get("nodes", {})}, "edges": list(g.get("edges") or [])}
    if isinstance(p.get("nodes"), dict):
        for k, v in p["nodes"].items():
            if v is None:
                out["nodes"].pop(k, None)
            elif isinstance(v, dict):
                out["nodes"][k] = {**out["nodes"].get(k, {}), **v}
    gone = {str(x) for x in p.get("remove") or []}
    out["edges"] = [e for e in out["edges"] if str(e.get("id")) not in gone]
    have = {str(e.get("id")) for e in out["edges"]}
    for e in p.get("add") or []:
        if isinstance(e, dict) and e.get("from") and e.get("to") and isinstance(e.get("on"), dict):
            e = {**e, "id": str(e.get("id") or f"{e['from']}>{e['to']}:{'+'.join(sorted(e['on']))}")}
            out["edges"] = [x for x in out["edges"] if str(x.get("id")) != e["id"]] if e["id"] in have else out["edges"]
            out["edges"].append(e)
    return out


def override_path(root: Path) -> Path:
    from neonrp.core.paths import get_data_dir_name

    return Path(root) / get_data_dir_name(root) / "meta" / "orchestration.json"


def _read_override(root: Path) -> dict[str, Any]:
    try:
        d = json.loads(override_path(root).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def graph(root: Path) -> dict[str, Any]:
    """The effective graph for this run: default + pack's own + the run / template override."""
    p = override_path(root)
    try:
        mt = p.stat().st_mtime
    except OSError:
        mt = 0.0
    try:
        from neonrp.packs import resolve as resolve_pack

        pk = resolve_pack(root)
        pname = str(pk.name)
    except Exception:  # noqa: BLE001
        pk, pname = None, ""
    key = (str(Path(root).resolve()), pname, mt, _private_stamp(pk), tuple(_node_kinds.kinds()))
    if key in _CACHE:
        return {**_CACHE[key], "state": _state_of(_CACHE[key])}
    g = default_graph(root)
    ov = _read_override(root)
    if ov.get("nodes") is not None and ov.get("edges") is not None and not ov.get("remove") and not ov.get("add"):
        g = {"schema": SCHEMA, "id": str(ov.get("id") or "override"), "start": str(ov.get("start") or default_graph(root).get("start") or RESOLVE),
             "nodes": dict(ov["nodes"]), "edges": [e for e in ov["edges"] if isinstance(e, dict)]}
    elif ov:
        g = _patch(g, ov)
    g = _prune(g)  # a node deleted in the editor (the planning beat …) takes its edges with it; start falls back to resolve
    g = {**g, "units": units(root)}  # O7: the background units (ticks, characters elsewhere) and what each may write
    g["lint"] = lint_units(g["units"]) + lint_runnable(root, g) + lint_step_params(root, g)
    _CACHE.clear() if len(_CACHE) > 64 else None
    _CACHE[key] = g
    return {**g, "state": _state_of(g)}  # not cached: it follows whether Jev answers


def _prune(g: dict[str, Any]) -> dict[str, Any]:
    nodes = g.get("nodes") or {}
    ok = set(nodes) | {RETURN, "*"}
    edges = [e for e in g.get("edges") or [] if e.get("from") in ok and e.get("to") in ok]
    start = g.get("start") if g.get("start") in nodes else (RESOLVE if RESOLVE in nodes else next(iter(nodes), RESOLVE))
    return {**g, "edges": edges, "start": start}


def node_kind_live(root: Path, kind: str) -> bool:
    """Does a node-kind plugin still have a node in this run's graph? Deleting its nodes in the orchestration editor
    (``game/meta/orchestration.json`` ``{"nodes": {"plan": null}}``, or a whole graph without them) turns it off —
    the planning beat is decoupled by deleting its node. A plugin that brings no graph is always live."""
    own = _node_kinds.call(kind, "graph", default=None)
    mine = set((own or {}).get("nodes") or {}) if isinstance(own, dict) else set()
    if not mine:
        return True
    return bool(mine & set(graph(root).get("nodes") or {}))


# How the Resolve beat turns its prose into state — a parameter of the Resolve node the author sets (decision
# D-20261011-state-param), both open:
#   pseudo  the prose, then one model call writes the changes as pseudo-code lines → parsed to the JSON changes (default)
#   jev     the prose ends with the changes in plain words (same call); Jev fills our registered tools' JSON line by
#           line, and only the lines it is unsure of go to the pseudo-code call
# The graph is the one source: ``nodes.resolve.state``, set in the orchestration editor (game/meta/orchestration.json
# ``{"nodes": {"resolve": {"state": "jev"}}}``). ``jev`` without a fast Jev runs ``pseudo``.
# Benchmarks only: NEONRP_STATE overrides the node; NEONRP_V3_SOLVE pins a raw solve shape (experiment arms).
STATE_MODES: dict[str, str] = {"pseudo": "narrate", "jev": "jevjson-inline"}
DEFAULT_STATE = "pseudo"


def _state_of(g: dict[str, Any]) -> dict[str, Any]:
    import os

    node = (g.get("nodes") or {}).get(RESOLVE) or {}
    asked = (os.environ.get("NEONRP_STATE", "").strip().lower() or str(node.get("state") or "").strip().lower() or DEFAULT_STATE)
    if asked not in STATE_MODES:
        return {"mode": DEFAULT_STATE, "asked": asked, "why": "unknown"}
    if asked == "jev":
        from neonrp.core import system_one as _s1

        if not _s1.fast_judge_available():
            return {"mode": DEFAULT_STATE, "asked": asked, "why": "no_fast_jev"}
    return {"mode": asked, "asked": asked, "why": ""}


def state_mode(root: Path) -> dict[str, Any]:
    """``{"mode": what runs, "asked": what the graph says, "why": why they differ}`` for this run's Resolve beat."""
    return graph(root)["state"]


def solve_structured(root: Path) -> str:
    """The solve shape the Resolve beat runs: an experiment's NEONRP_V3_SOLVE, else the state mode's."""
    import os

    raw = os.environ.get("NEONRP_V3_SOLVE", "").strip()
    return raw or STATE_MODES[state_mode(root)["mode"]]


def _match_on(edge_on: dict[str, Any], on: dict[str, Any]) -> bool:
    for k, v in edge_on.items():
        if k == "words" and isinstance(v, list):  # an author's own words: the caller passes the player's text
            if not any(str(w) and str(w) in str(on.get("text") or "") for w in v):
                return False
            continue
        if k not in on or on[k] != v:
            return False
    return True


def _when_ok(reg: Any, when: Any) -> bool:
    if not when:
        return True
    conds = when if isinstance(when, list) else [when]
    for c in conds:
        if not isinstance(c, dict) or "var" not in c:
            continue
        spec = getattr(reg, "variables", {}).get(str(c["var"])) if reg is not None else None
        val = spec.value if spec is not None else None
        for opn, ref in c.items():
            if opn == "var":
                continue
            try:
                ok = {"==": val == ref, "!=": val != ref, "<": val < ref, "<=": val <= ref, ">": val > ref, ">=": val >= ref}.get(opn, True)
            except TypeError:
                ok = False
            if not ok:
                return False
    return True


def edges_for(g: dict[str, Any], frm: str, on: dict[str, Any], to: str | None = None, reg: Any = None) -> list[dict[str, Any]]:
    out = []
    for e in g.get("edges") or []:
        if e.get("from") not in (frm, "*") or (to is not None and e.get("to") != to):
            continue
        if not isinstance(e.get("on"), dict) or not _match_on(e["on"], on):
            continue
        if not _when_ok(reg, e.get("when")):
            continue
        out.append(e)
    return out


def allows(root: Path, frm: str, on: dict[str, Any], to: str | None = None, reg: Any = None) -> bool:
    """Whether the run's graph lets this transition happen. Refuses only what the default graph allows and the
    effective one removed — so a run without an override behaves exactly as before."""
    eff = graph(root)
    if edges_for(eff, frm, on, to, reg):
        return True
    return not edges_for(default_graph(root), frm, on, to, reg)


def current(root: Path, reg: Any = None) -> str:
    """The node the world is in right now: a running layer · a place-keyed layer · a phase · else the Resolve (this is
    asked while a beat runs)."""
    try:
        from neonrp.core.modes import read_mode

        m = read_mode(root)
        if m and m.get("name"):
            return str(m["name"])
    except Exception:  # noqa: BLE001
        pass
    if reg is not None:
        hl = here_layer(root, reg)
        if hl:
            return hl
        ph = phase_node(root, reg)
        if ph:
            return ph
    return RESOLVE


def phase_node(root: Path, reg: Any) -> str | None:
    """A node keyed by a phase variable (``{"kind": "phase", "var": …, "value": …}``) whose value the world holds now."""
    for nid, n in (graph(root).get("nodes") or {}).items():
        if isinstance(n, dict) and n.get("kind") == "phase" and n.get("var"):
            spec = getattr(reg, "variables", {}).get(str(n["var"]))
            if spec is not None and str(spec.value) == str(n.get("value")):
                return nid
    return None


def here_layer(root: Path, reg: Any) -> str | None:
    """The place-keyed layer for where the player stands, read off the graph's ``here_class`` edges (so an override can
    add or take one away)."""
    here = reg.entries.get(reg.player_location or "") if getattr(reg, "player_location", None) else None
    if here is None:
        return None
    for e in graph(root).get("edges") or []:
        on = e.get("on") if isinstance(e.get("on"), dict) else {}
        if "here_class" in on and here.cls == str(on["here_class"]) and _when_ok(reg, e.get("when")):
            return str(e.get("to"))
    return None


def op_on(op: dict[str, Any]) -> dict[str, Any]:
    """The trigger an op makes: its name, plus the fields an edge may key on (a phase op's value)."""
    on = {"op": str(op.get("op") or "")}
    for k in ("value", "outcome"):
        if op.get(k) is not None:
            on[k] = op[k]
    return on


def refuses_op(root: Path, reg: Any, op: dict[str, Any]) -> str | None:
    """Why this op may not land from the current node (an override removed its edge), or None. Only ops some edge of
    the default graph keys on are judged; every other op is not the graph's business."""
    on = op_on(op)
    dflt = default_graph(root)
    keyed = [e for e in dflt.get("edges") or [] if isinstance(e.get("on"), dict) and e["on"].get("op") == on["op"]]
    if not keyed:
        return None
    frm = current(root, reg)
    if allows(root, frm, on, reg=reg):
        return None
    return f"orchestration: no edge from {frm!r} on op {on['op']!r}"


def describe(g: dict[str, Any]) -> str:
    """The graph as text (``neonrp engine graph``)."""
    st = g.get("state") or {}
    st_txt = f" · state={st.get('mode')}" + (f" (asked {st['asked']}: {st['why']})" if st.get("why") else "") if st else ""
    lines = [f"{g.get('schema')} · {g.get('id')} · start={g.get('start')}{st_txt}", "", "nodes:"]
    for nid, n in (g.get("nodes") or {}).items():
        extra = " ".join(f"{k}={n[k]}" for k in ("mode", "here_class", "exit", "var", "value") if isinstance(n, dict) and n.get(k))
        lines.append(f"  {nid:<12} {str((n or {}).get('kind') or ''):<9} {extra}".rstrip())
    lines += ["", "edges:"]
    for e in g.get("edges") or []:
        on = " ".join(f"{k}={v}" for k, v in (e.get("on") or {}).items())
        tail = (" when=" + json.dumps(e["when"], ensure_ascii=False) if e.get("when") else "") + (" return" if e.get("return") else "")
        lines.append(f"  {e.get('from'):>10} → {e.get('to'):<10} on {on}{tail}   [{e.get('id')}]")
    if g.get("units"):
        lines += ["", "units (background):"]
        for u in g["units"]:
            lines.append(f"  {u['name']:<16} on={u.get('on')}{' llm' if u.get('llm') else ''}  writes: {', '.join(u.get('writes') or []) or '(undeclared)'}")
    for x in g.get("lint") or []:
        lines.append(f"  ! {x['code']}: {x['msg']}")
    return "\n".join(lines)


# ── O5 (10-06): what an editor may pick from — never write ──────────────────────────────────────────────────────────
ON_KINDS: dict[str, str] = {  # the engine's own triggers; a node-kind plugin adds its own (on_kinds())
    "always": "unconditional",
    "op": "an op landed (a mode switch, a layer's exit op, a phase op)",
    "gate": "the template's gate seam forced a layer",
    "here_class": "the player stands at an entry of that class",
    "tick": "a pack's own rule",
}


def beat_kinds(root: Path) -> dict[str, Any]:
    """How this run's beats are shown (R2/R3, 10-09): ``{"start": …, "kinds": {node: {label, tone, …}}}`` — each
    node-kind plugin's ``ui_beats()`` for the nodes this run's graph has, then the run's template / pack ``ui.beats``
    over it. Nothing declared → ``{"kinds": {}}`` (the screen falls back to node names, neutral style)."""
    out: dict[str, Any] = {"kinds": {}}
    try:
        nodes = set((graph(root).get("nodes") or {}))
    except Exception:  # noqa: BLE001
        nodes = set()
    try:
        from neonrp.core.output_lang import prompt_lang

        lang = prompt_lang(Path(root))
    except Exception:  # noqa: BLE001
        lang = "zh"
    for kind in _node_kinds.kinds():
        d = _node_kinds.call(kind, "ui_beats", lang, default=None)
        if not isinstance(d, dict) or kind not in nodes:
            continue
        for k, v in (d.get("kinds") or {}).items():
            if k in nodes and isinstance(v, dict):
                out["kinds"][k] = {**out["kinds"].get(k, {}), **v}
        if d.get("start") and str(d["start"]) in nodes:
            out["start"] = str(d["start"])
    try:  # the run's own presentation (template record: pack + mixins < template) may override
        from neonrp.core.paths import get_data_dir_name

        rec = json.loads((Path(root) / get_data_dir_name(Path(root)) / "meta" / "template.json").read_text(encoding="utf-8"))
        ub = ((rec.get("ui") or {}).get("beats") or {}) if isinstance(rec, dict) else {}
    except (OSError, ValueError):
        ub = {}
    if isinstance(ub, dict):
        for k, v in (ub.get("kinds") or {}).items():
            if isinstance(v, dict):
                out["kinds"][str(k)] = {**out["kinds"].get(str(k), {}), **v}
        if ub.get("start"):
            out["start"] = str(ub["start"])
    return out


def on_kinds() -> dict[str, str]:
    """Every trigger an edge may use: the engine's, then each node-kind plugin's (``on_kinds``)."""
    out = dict(ON_KINDS)
    for kind in _node_kinds.kinds():
        out.update(_node_kinds.call(kind, "on_kinds", default={}) or {})
    return out


def judges() -> list[str]:
    out: list[str] = []
    for kind in _node_kinds.kinds():
        out += [str(x) for x in _node_kinds.call(kind, "judges", default=()) or ()]
    return out


def hooks(root: Path) -> dict[str, Any]:
    """The registered pieces an orchestration editor chooses from (O5): mechanic seams and the handler each uses now,
    every handler name it could use, the edge trigger kinds and judges, the pack's ops (with kind / waits), modes and
    ticks. Read from the registry and the pack — nothing to configure here."""
    from neonrp.core import handlers, mechanics
    from neonrp.core.registry import load_registry

    out: dict[str, Any] = {"schema": "worldlines.orchestration-hooks/1", "on": on_kinds(), "judges": judges()}
    try:
        cur = mechanics.spec(root)
    except Exception:  # noqa: BLE001
        cur = {}
    out["seams"] = {s: cur.get(s, mechanics.DEFAULTS.get(s, "")) for s in mechanics.SEAMS}
    names = set(f"builtin:{k}" for k in handlers.BUILTIN)
    try:
        from neonrp.packs import resolve as _resolve_pack

        pk = _resolve_pack(root)
        names |= {str(v) for v in (getattr(pk, "mechanics", {}) or {}).values() if v}
        out["ticks"] = list(getattr(pk, "ticks", []) or [])
        out["modes"] = {k: {kk: v.get(kk) for kk in ("enter", "exit", "here_class", "one_shot") if v.get(kk) is not None}
                        for k, v in (getattr(pk, "modes", {}) or {}).items()}
        out["pack"] = str(getattr(pk, "name", ""))
    except Exception:  # noqa: BLE001
        out.setdefault("ticks", [])
        out.setdefault("modes", {})
    out["handlers"] = sorted(names)
    try:
        reg = load_registry(root)
        out["ops"] = {k: {"kind": a.kind, "waits": bool(a.waits()) if hasattr(a, "waits") else False,
                          **({"enabled": False} if getattr(a, "enabled", True) is False else {})}
                      for k, a in sorted(reg.actions.items())}
    except Exception:  # noqa: BLE001
        out["ops"] = {}
    return out


# ── O7 (10-06): background units — the ticks and the off-stage characters as declared units of the graph ──────────────
CORE_UNITS: list[dict[str, Any]] = [
    {"name": "effects", "tick": "core:effects", "on": "apply", "llm": False, "writes": ["var:*", "op:patch", "op:remove"],
     "doc": "status effects count down and apply their per-resolve change (the world's own variables: any)"},
    {"name": "souls_elsewhere", "tick": "core:souls_elsewhere", "on": "resolve", "llm": True, "writes": ["op:move_to"],
     "doc": "characters away from the player take their own turn (LLM); only their own moves land"},
]


def unit_of(name: str) -> dict[str, Any] | None:
    """A pack tick's declared unit (``tick.unit`` on the function), or None when it declares nothing."""
    try:
        from neonrp.core.handlers import resolve

        u = getattr(resolve(name), "unit", None)
    except Exception:  # noqa: BLE001
        return None
    return dict(u) if isinstance(u, dict) else None


def units(root: Path) -> list[dict[str, Any]]:
    out = [dict(u) for u in CORE_UNITS]
    try:
        from neonrp.packs import resolve as _resolve_pack

        ticks = list(getattr(_resolve_pack(root), "ticks", []) or [])
    except Exception:  # noqa: BLE001
        ticks = []
    for t in ticks:
        u = unit_of(t) or {}
        out.append({"name": t.partition(":")[0].rsplit(".", 1)[-1], "tick": t, "on": u.get("on", "apply"), "llm": bool(u.get("llm", False)),
                    "writes": list(u.get("writes") or []), **({"undeclared": True} if not u else {})})
    return out


def _overlap(a: str, b: str) -> bool:
    if a.endswith(":*") or b.endswith(":*"):
        return False  # a wildcard unit writes whatever the world declared (effects) — not a conflict by itself
    ka, _, pa = a.partition(":")
    kb, _, pb = b.partition(":")
    if ka != kb:
        return False
    if ka == "op":
        return False  # several units may each use an op (new / remove) on their own entries
    sa, sb = pa.rstrip("*"), pb.rstrip("*")
    return pa == pb or (pa.endswith("*") and pb.startswith(sa)) or (pb.endswith("*") and pa.startswith(sb))


def lint_units(us: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Two units declaring the same variable (or overlapping patterns) → ``orch.unit_conflict``; a pack tick that declares
    nothing → ``orch.unit_undeclared`` (it may write anything). Both warn."""
    out: list[dict[str, str]] = []
    for i, a in enumerate(us):
        if a.get("undeclared"):
            out.append({"code": "orch.unit_undeclared", "level": "warn", "msg": f"{a['name']}: no declared write scope"})
        for b in us[i + 1:]:
            hit = [f"{x}" for x in a.get("writes") or [] for y in b.get("writes") or [] if _overlap(x, y)]
            if hit:
                out.append({"code": "orch.unit_conflict", "level": "warn", "msg": f"{a['name']} × {b['name']}: both write {', '.join(sorted(set(hit)))}"})
    return out


# ── what a drawn graph can actually run (10-06: the visual editor can draw edges the engine never reads) ──────────────

def _ekey(e: dict[str, Any]) -> tuple[str, str, str]:
    return (str(e.get("from")), str(e.get("to")), json.dumps(e.get("on") or {}, sort_keys=True, ensure_ascii=False))


def _edge_unrunnable(e: dict[str, Any], nodes: dict[str, Any], modes: dict[str, Any], mode_ops: set[str],
                     has_gate: bool, classes: set[str] | None) -> str | None:
    """Why the engine would never take this edge, or None. The engine reads the graph in four places: planning → resolve
    (plan_loop), a place-keyed layer (modes.here_layer), a layer switch / exit op (modes.enter, sdk.refuses_op) and a
    phase variable (phase_node); an edge anywhere else is drawn but dead."""
    on = e.get("on") if isinstance(e.get("on"), dict) else {}
    frm, to = str(e.get("from") or ""), str(e.get("to") or "")
    if not on:
        return "no trigger (on)"
    known = on_kinds()
    kind = next((k for k in on if k in known), None)
    if kind is None:
        return f"unknown trigger {sorted(on)} — one of {', '.join(known)}"
    if frm != "*" and frm not in nodes:
        return f"from {frm!r}: no such node"
    if to != RETURN and to not in nodes:
        return f"to {to!r}: no such node"
    if kind not in ON_KINDS or kind == "always":  # a plugin's trigger (and where it reads 'always'): the plugin judges the edge
        for nk in _node_kinds.kinds():
            why = _node_kinds.call(nk, "check_edge", frm, to, kind, default=False)
            if why is not False:
                return why
        if kind == "always":  # the engine itself never reads 'always' — only a node kind that claims the edge does (10-17)
            return "'always' is read only where a node kind takes it (the planning beat: resolve → plan)"
        return f"{kind!r}: no node kind reads it"
    if kind == "here_class":
        if to not in modes:
            return f"here_class leads only into a pack layer; {to!r} has none"
        if classes is not None and str(on["here_class"]) not in classes:
            return f"class {on['here_class']!r} is not registered"
        return None
    if kind == "op":
        op = str(on.get("op") or "")
        exits = {str(s.get("exit")) for s in modes.values() if isinstance(s, dict) and s.get("exit")}
        if to == RETURN:
            return None if op in exits else f"op {op!r} is no layer's exit op — only an exit op returns"
        if (nodes.get(to) or {}).get("kind") == "phase":
            return None
        if to in modes and op == to and op in mode_ops:
            return None
        if to in modes and op == to and (modes.get(to) or {}).get("one_shot"):  # a one-shot node, called by its own tool
            return None
        return f"op {op!r} does not switch into {to!r} — a layer is entered by its own switch op ({', '.join(sorted(mode_ops)) or 'none'})"
    if kind == "gate":
        return None if has_gate and to in modes else "no gate seam in this pack, or the target is not a layer"
    if kind == "tick":
        return None if to in modes else f"a pack rule can only enter a pack layer; {to!r} has none"
    return None


def lint_runnable(root: Path, g: dict[str, Any]) -> list[dict[str, str]]:
    """Nodes and edges the effective graph has beyond the default one that the engine cannot run: a node with no layer
    behind it (``orch.node_no_impl``), a phase node on an unregistered variable (``orch.phase_var``), an edge in a place
    the engine never reads the graph (``orch.edge_unrunnable``). All warn — the run still plays; the editor shows them."""
    try:
        dflt = default_graph(root)
        from neonrp.packs import resolve as resolve_pack

        pk = resolve_pack(root)
    except Exception:  # noqa: BLE001
        return []
    modes = {k: v for k, v in (getattr(pk, "modes", {}) or {}).items() if isinstance(v, dict)}
    mode_ops = {a.op for a in getattr(pk, "actions", []) or [] if a.kind == "mode" and a.enabled}
    has_gate = str((getattr(pk, "mechanics", None) or {}).get("gate") or "builtin:none") != "builtin:none"
    try:
        from neonrp.core.registry import load_registry

        reg = load_registry(root)
        classes: set[str] | None = set(reg.classes)
        variables: set[str] | None = set(reg.variables)
    except Exception:  # noqa: BLE001
        classes = variables = None
    nodes = g.get("nodes") or {}
    plugin_kinds = set(_node_kinds.kinds())
    out: list[dict[str, str]] = []
    for nid, n in nodes.items():
        if nid in (dflt.get("nodes") or {}):
            continue
        n = n if isinstance(n, dict) else {}
        if n.get("kind") == "phase":
            if variables is not None and n.get("var") and str(n["var"]) not in variables:
                out.append({"code": "orch.phase_var", "level": "warn", "msg": f"{nid}: phase variable {n['var']!r} is not registered"})
        elif _node_kinds.canonical(str(n.get("kind") or "")) in plugin_kinds:  # a node-kind plugin's own node (a game client's interaction …): it judges
            why = _node_kinds.call(str(n["kind"]), "check_node", nid, n, default=None)
            if why:
                out.append({"code": "orch.node_no_impl", "level": "warn", "msg": f"{nid}: {why}"})
        elif nid not in modes:
            out.append({"code": "orch.node_no_impl", "level": "warn",
                        "msg": f"{nid}: no pack layer behind this node — the engine has nothing to run there"})
    dkeys = {_ekey(e) for e in dflt.get("edges") or [] if isinstance(e, dict)}
    for e in g.get("edges") or []:
        if not isinstance(e, dict) or _ekey(e) in dkeys:
            continue
        why = _edge_unrunnable(e, nodes, modes, mode_ops, has_gate, classes)
        if why:
            out.append({"code": "orch.edge_unrunnable", "level": "warn", "msg": f"{e.get('id') or _ekey(e)}: {why}"})
    return out


def lint_step_params(root: Path, g: dict[str, Any]) -> list[dict[str, str]]:
    """The graph's step settings (10-17 S2): one that names no setting or does not fit → ``orch.step_param`` (left out
    when the turn runs); one the world's engine.json also sets → ``orch.legacy_turn_config`` (the graph wins — the old
    key can go, ``neonrp engine migrate-turn``)."""
    from neonrp.core import turn_steps
    from neonrp.core.engine_config import _read_json
    from neonrp.core.paths import get_data_dir_name

    out = [{"code": "orch.step_param", "level": "warn", "msg": m} for m in turn_steps.check_params(g)]

    def keys(d: Any, pre: str = "") -> set[str]:
        if not isinstance(d, dict):
            return {pre}
        return set().union(*(keys(v, f"{pre}.{k}" if pre else k) for k, v in d.items())) if d else set()

    mine = keys(turn_steps.graph_layer(g)) - {""}
    old = keys(_read_json(Path(root) / get_data_dir_name(Path(root)) / "meta" / "engine.json")) - {""}
    for k in sorted(mine & old):
        out.append({"code": "orch.legacy_turn_config", "level": "warn", "msg": f"{k}: set in the graph and in engine.json — the graph wins"})
    return out


def in_scope(unit: dict[str, Any] | None, op: dict[str, Any]) -> bool:
    """Does this op stay inside the unit's declared writes? An undeclared unit may write anything (behaviour unchanged)."""
    if not unit or not unit.get("writes"):
        return True
    import fnmatch

    var = op.get("var")
    for w in unit["writes"]:
        k, _, pat = str(w).partition(":")
        if k == "var" and var and fnmatch.fnmatchcase(str(var), pat):
            return True
        if k == "op" and not var and fnmatch.fnmatchcase(str(op.get("op")), pat):
            return True
    return False

