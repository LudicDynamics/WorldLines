"""The turn's step catalog (10-17 batch 4 · S1 · niko: the orchestration bench is a real editor; step names may show).

What a beat actually runs, step by step, as data: each step's id · the node it belongs to · its backend (python / llm /
jev) · the engine settings it owns (their dotted ``turn.*`` keys and defaults) · the mechanics seam whose handler it calls
(swappable) · what it needs and gives (requires / provides) · whether it may be left out. The orchestration graph's node
``steps`` are generated from here, and the editor draws them from :func:`describe` with each setting's value and where
that value came from.

S1 is read-only: the turn still runs its fixed order (core/conversation · core/turn_v3); later steps of the plan bind the
params to the graph (S2) and run the turn off the node's steps (S3–S5). Nothing here knows a world.

A node-kind plugin brings its own node's steps with :func:`register` (the private planning beat registers ``plan``).
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any


def _p(name: str, key: str, default: Any, doc: str, **kw: Any) -> dict[str, Any]:
    return {"name": name, "key": key, "default": default, "type": type(default).__name__, "doc": doc, **kw}


# The Resolve beat as it runs today (engine v3: conversation._run_multi_agent_turn → turn_v3.solve_turn), in order.
RESOLVE: list[dict[str, Any]] = [
    {"id": "clock", "backend": "python", "title": "World clock", "doc": "The world's time moves one step before the turn, so everyone sees the same time"},
    {"id": "scene_route", "backend": "python", "title": "Who is here", "doc": "Finds the characters at the player's place by location (only those present act)", "provides": ["active_souls"]},
    {"id": "s1_plan", "backend": "jev", "title": "S1 forecast (Jev)", "provides": ["plan"],
     "doc": "One Jev judgment: what the player means · whether each character moves and how deeply · the mood; without Jev, the fallback plan (everyone present acts)",
     "params": [_p("backend", "turn.plan.backend", "auto", "Who judges", choices=["auto", "jev", "llm", "off"]),
                _p("confidence", "turn.plan.confidence", 0.7, "How sure a judgment must be", min=0, max=1),
                _p("react", "turn.plan.react", 0.6, "When a character counts as moved", min=0, max=1),
                _p("fallback_depth", "turn.plan.fallback_depth", "act", "How deeply characters act when unsure",
                   choices=["silent", "gesture", "speak", "act"])]},
    {"id": "player_gate", "backend": "llm", "title": "The player's line", "provides": ["gate"],
     "doc": "The player's words as an attempt: what they try · whether they can know what they mention (runs before the characters act)",
     "params": [_p("mode", "turn.player_gate", "auto", "On / off", choices=["auto", "on", "off"])]},
    {"id": "s2_souls", "backend": "llm", "title": "S2 characters act in parallel", "parallel": True, "seam": "soul_turn",
     "requires": ["plan", "active_souls"], "provides": ["soul_reports"],
     "doc": "Characters present act at the same time at the depth S1 gave (silent / gesture / speak / act); those away take a beat where they are",
     "params": [_p("default_variant", "turn.parallel.souls.default_variant", "legacy", "How characters act",
                   choices=["legacy", "S-judge", "S-direct", "S-free"]),
                _p("max_workers", "turn.parallel.souls.max_workers", 8, "How many act at once", min=1, max=32),
                _p("timeout_s", "turn.parallel.souls.timeout_s", 20, "How long one character may think (s)", min=1, max=120),
                _p("escalate_at", "turn.parallel.souls.escalate_at", 0.8, "When a character thinks one more round", min=0, max=1),
                _p("escalate_turns", "turn.parallel.souls.escalate_turns", 3, "At most how many extra rounds", min=1, max=10),
                _p("heavy_at", "turn.parallel.souls.heavy_at", 0.4, "When the heavy path is taken", min=0, max=1),
                _p("decide_conf", "turn.parallel.souls.decide_conf", 0.5, "How sure a character must be to decide alone", min=0, max=1),
                _p("adjudicate", "turn.parallel.souls.adjudicate", 1, "Rule on persuasion (1 / 0)", min=0, max=1)]},
    {"id": "followups", "backend": "jev", "title": "S1 follow-up", "requires": ["soul_reports"],
     "doc": "After the characters answer, one more judgment: does the host still need to ask anyone (if not, the ask tools are put away)"},
    {"id": "pack", "backend": "python", "title": "Pack the world", "seam": "pack_hints", "provides": ["pack"],
     "doc": "The world the narrator reads, in one pack (places · people · state · recent events)",
     "params": [_p("budget", "turn.plan.pack_budget", 0, "Pack size cap in characters (0 = engine default)", min=0)]},
    {"id": "understand", "backend": "python", "title": "Read the line", "seam": "understand",
     "doc": "What the world says about each thing the player mentions (nobody vouches for what is not there)"},
    {"id": "gate", "backend": "python", "title": "Pre-ruling / enter a layer", "seam": "gate",
     "doc": "The rules rule this beat in advance (a referee) · force a layer when needed (an ambush on the road → combat) · fire async tools itself"},
    {"id": "mode_layer", "backend": "python", "title": "Layer", "doc": "Inside a layer (combat · a dungeon) the whole prompt is the layer's, plus the layer's state"},
    {"id": "solve", "backend": "llm", "title": "Narration call", "seam": "contract", "requires": ["pack"], "provides": ["proposal"],
     "doc": "One model call writes the beat, calling tools as it goes (dice · map …) and waiting for the engine's answer before it goes on",
     "params": [_p("max_ops", "turn.solve.max_ops", 24, "At most how many changes per beat", min=1, max=200),
                _p("history", "turn.solve.history", 4, "How many rounds of history", min=0, max=40),
                _p("sections", "turn.solve.sections", "xml", "How output sections are marked", choices=["xml", "divider", "fence"]),
                _p("async_mark", "turn.solve.async_mark", "tilde", "How async tools are marked", choices=["tilde", "angle"])]},
    {"id": "verify", "backend": "python", "title": "Verify", "requires": ["proposal"], "provides": ["verdict"],
     "doc": "Each proposed change is checked against the registry and the rules; fixable ones go back for a rewrite (a few times at most)",
     "params": [_p("max_loops", "turn.verify.gate.max_loops", 1, "At most how many rewrites", min=0, max=5),
                _p("l2", "turn.verify.l2", "auto", "Semantic check", choices=["auto", "on", "off"]),
                _p("grounded_min", "turn.verify.grounded_min", 0.5, "How grounded a change must be", min=0, max=1),
                _p("missed_min", "turn.verify.missed_min", 0.6, "When something counts as missed", min=0, max=1)]},
    {"id": "apply", "backend": "python", "title": "Apply", "required": True, "requires": ["verdict"], "provides": ["applied"],
     "doc": "The changes that passed are written into the world (state · files)",
     "params": [_p("writers", "turn.apply.writers", "on", "Write by ownership", choices=["on", "off"])]},
    {"id": "deferred_fire", "backend": "python", "title": "Async tools", "requires": ["applied"],
     "doc": "Tools that are not waited for (map · panels) are drawn after the beat lands (so they show where things ended up)"},
    {"id": "settle", "backend": "llm", "title": "Characters settle", "seam": "settle", "requires": ["applied"],
     "doc": "What each character present remembers after the beat (written into their own memory)"},
    {"id": "after_turn", "backend": "python", "title": "After the turn", "seam": "after_turn", "requires": ["applied"],
     "doc": "Wrap-up after the turn (pictures for new things · triggers)"},
    {"id": "ticks", "backend": "python", "title": "Background units", "requires": ["applied"],
     "doc": "The economy · effect countdowns · characters elsewhere · the pack's own rules, each within its declared writes"},
    {"id": "land", "backend": "python", "title": "Commit", "required": True, "requires": ["applied"],
     "doc": "The turn is committed as a version and its beat events go to the front ends"},
]

_NODES: dict[str, list[dict[str, Any]]] = {"resolve": RESOLVE}


def register(node: str, steps: list[dict[str, Any]]) -> None:
    """A node-kind plugin's own node steps (the planning beat's ``plan``): same shape as :data:`RESOLVE`."""
    _NODES[str(node)] = [dict(s) for s in steps]


def steps_of(node: str) -> list[dict[str, Any]]:
    from neonrp.core import node_kinds

    node_kinds.kinds()  # loads the plugins (and with them their steps)
    return copy.deepcopy(_NODES.get(node) or [])


def nodes() -> list[str]:
    """The nodes with steps: the Resolve, and each node-kind plugin's that is on (``NEONRP_PRIVATE=off`` hides ``plan``)."""
    from neonrp.core import node_kinds

    on = set(node_kinds.kinds())
    return [n for n in _NODES if n == "resolve" or n in on]


def ids(node: str) -> list[str]:
    return [s["id"] for s in steps_of(node)]


def describe(root: Path | None = None, lang: str | None = None) -> dict[str, Any]:
    """Every node's steps for the editor: the catalog (titles and docs in ``lang``, prompts/turn_steps.<lang>.json; a
    plugin's own steps carry their own), and with a run each setting's value now and where it came from (``default`` ·
    a layer of core/engine_config: ``builtin`` · ``pack`` · ``contract`` · ``engine.json`` · ``playthrough`` · ``env``)."""
    from neonrp.prompts import strings

    if lang is None and root is not None:
        from neonrp.core.output_lang import prompt_lang

        lang = prompt_lang(root)
    try:
        tr = strings("turn_steps", lang or "zh")
    except KeyError:
        tr = {}
    src: dict[str, str] = {}
    if root is not None:
        from neonrp.core import engine_config

        src = {k: s for k, _v, s in engine_config.explain(root)}
    out: dict[str, Any] = {"schema": "worldlines.turn-steps/1", "nodes": {}}
    for node in nodes():
        rows = []
        for st in steps_of(node):
            if node == "resolve":
                st.update((tr.get("steps") or {}).get(st["id"]) or {})
            for p in st.get("params") or []:
                if node == "resolve" and (tr.get("params") or {}).get(p["key"]):
                    p["doc"] = tr["params"][p["key"]]
                if root is not None:
                    from neonrp.core import engine_config

                    p["value"] = engine_config.get(root, p["key"], p["default"])
                    p["source"] = src.get(p["key"], "default")
            rows.append(st)
        out["nodes"][node] = rows
    return out


# ── S2 (10-17): the graph is where a beat's settings live — node ``step_params: {step id: {param name: value}}`` ──────

def param_of(node: str, step: str, name: str) -> dict[str, Any] | None:
    st = next((x for x in steps_of(node) if x["id"] == step), None)
    return next((p for p in (st or {}).get("params") or [] if p["name"] == name), None)


def coerce(p: dict[str, Any], v: Any) -> Any:
    """``v`` as the setting's own type (the editor sends text); ValueError(why) when it does not fit."""
    t = p.get("type")
    if t == "bool":
        if isinstance(v, bool):
            return v
        if str(v).strip().lower() in ("1", "true", "on", "yes"):
            return True
        if str(v).strip().lower() in ("0", "false", "off", "no"):
            return False
        raise ValueError(f"{p['name']}: {v!r} is not on / off")
    if t in ("int", "float"):
        try:
            x = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"{p['name']}: {v!r} is not a number") from None
        if t == "int":
            if x != int(x):
                raise ValueError(f"{p['name']}: {v!r} is not a whole number")
            x = int(x)
        if p.get("min") is not None and x < p["min"] or p.get("max") is not None and x > p["max"]:
            raise ValueError(f"{p['name']}: {v} is outside {p.get('min')}–{p.get('max')}")
        return x
    v = str(v)
    if p.get("choices") and v not in p["choices"]:
        raise ValueError(f"{p['name']}: {v!r} is not one of {' · '.join(p['choices'])}")
    return v


def check_params(graph: dict[str, Any]) -> list[str]:
    """Why a graph's ``step_params`` would not run as written (unknown step / setting · a value that does not fit)."""
    out: list[str] = []
    for nid, n in ((graph or {}).get("nodes") or {}).items():
        sp = (n or {}).get("step_params") if isinstance(n, dict) else None
        if sp is None:
            continue
        if not isinstance(sp, dict):
            out.append(f"{nid}: step_params needs {{step: {{setting: value}}}}")
            continue
        for step, vals in sp.items():
            if not isinstance(vals, dict):
                out.append(f"{nid}.{step}: needs {{setting: value}}")
                continue
            for name, v in vals.items():
                p = param_of(str(nid), str(step), str(name))
                if p is None:
                    out.append(f"{nid}.{step}.{name}: no such setting")
                    continue
                try:
                    coerce(p, v)
                except ValueError as exc:
                    out.append(f"{nid}.{step}.{exc}")
    return out


def graph_layer(graph: dict[str, Any]) -> dict[str, Any]:
    """A graph's ``step_params`` as an engine_config layer (``{"turn": {...}}`` by each setting's dotted key); a setting
    that does not fit is left out (lint says why)."""
    from neonrp.core.engine_config import _set_path

    out: dict[str, Any] = {}
    for nid, n in ((graph or {}).get("nodes") or {}).items():
        sp = (n or {}).get("step_params") if isinstance(n, dict) else None
        for step, vals in (sp or {}).items() if isinstance(sp, dict) else ():
            for name, v in (vals or {}).items() if isinstance(vals, dict) else ():
                p = param_of(str(nid), str(step), str(name))
                if p is None:
                    continue
                try:
                    _set_path(out, p["key"], coerce(p, v))
                except ValueError:
                    continue
    return out

