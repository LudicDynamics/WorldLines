"""Orchestration templates — the few shared ways a world runs, which a world names instead of carrying its own
(docs/planning/TEMPLATE-LAYERS-1019.md, stage A; niko 10-19: templates are few and shared, a world is content that uses
one). A template = one world orchestration (how a turn moves) + its parameters. How the characters present act in the
world's turn (the characters' orchestration: legacy · S-judge · S-direct · S-free) is a separate axis: the world picks it
in ``uses.soul``, the template only gives the default. A template carries no play contract and no rules pack — the world
picks those on its own.

A template is a folder ``<id>/orch.json`` (``worldlines.orch-template/1``)::

    {"id": "one_beat", "version": "1.0", "order": 20,
     "world": {"kind": "one_beat", "nodes": ["resolve"], "engine": {}},
     "soul": {"variant": "legacy"},
     "params": {"<name>": {"default": "<choice>", "choices": {"<choice>": {<engine settings>}}}},
     "aliases": {"<an old preset id>": {<its parameter choices>}}}

    world.nodes   the graph's core nodes it runs (``resolve`` · a node-kind plugin's node); a template whose node no
                  plugin brings is not offered (the open engine has the single beat only)
    world.engine  the engine settings the world orchestration stands for
    soul.variant  the default characters' orchestration (``turn.parallel.souls.default_variant``) when ``uses.soul`` is unset
    params        named choices laid over ``world.engine`` (a world picks one in ``uses.params``)
    aliases       the creation desk's preset ids from before templates (a draft may still carry one), read as this
                  template with those choices

Where templates come from (later wins, by id): the engine's ``neonrp/orchestrations/`` · the private layer's
``orchestrations/<id>/``. Their words are the ``orch_presets`` string table (``template.<id>``, ``param.<name>``).

A world names one in ``template.json`` ``uses: {template, version, soul?, params?}``. A run built from it keeps ``uses``
in its template record (``game/meta/template.json``); core/engine_config lays :func:`layer` between the play contract's
settings and the world's own (the ``orchestration`` layer). The template's settings are never copied into the save. A
template the engine does not have (a world made on a private one, played on the open engine) falls back to the first
open one, keeping the characters' orchestration the world named — the world still plays, on the plain turn.

A world without ``uses`` (an old package or an old save) plays as it always did: the official play contracts used to
turn on the orchestration the open engine calls :data:`LEGACY_CONTRACT`, so a world with a contract gets that world
orchestration's settings, one without gets none; neither gets a characters' part (the pack still says how they act).
Nothing here knows any world.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

SCHEMA = "worldlines.orch-template/1"
FILE = "orch.json"
_DIR = Path(__file__).resolve().parents[1] / "orchestrations"
VARIANT_KEY = "turn.parallel.souls.default_variant"
LEGACY_CONTRACT = "two_beat"   # the world orchestration a play contract stood for before templates (its private block)
_CACHE: dict[str, Any] = {}


def _read(p: Path) -> dict[str, Any] | None:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and d.get("id") else None


def _deep_merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(a)
    for k, v in (b or {}).items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def _dirs() -> list[Path]:
    from neonrp.core.paths import private_dir

    priv = private_dir("orchestrations")
    return [d for d in (_DIR, priv) if d is not None and d.is_dir()]


def _stamp(dirs: list[Path]) -> tuple[Any, ...]:
    out: list[Any] = []
    for d in dirs:
        for f in sorted(d.glob(f"*/{FILE}")):
            try:
                out.append((str(f), f.stat().st_mtime_ns))
            except OSError:
                pass
    return tuple(out)


def _norm(r: dict[str, Any], private: bool) -> dict[str, Any]:
    w = r.get("world") if isinstance(r.get("world"), dict) else {}
    s = r.get("soul") if isinstance(r.get("soul"), dict) else {}
    params: dict[str, Any] = {}
    for name, p in (r.get("params") or {}).items():
        if not isinstance(p, dict) or not isinstance(p.get("choices"), dict) or not p["choices"]:
            continue
        ch = {str(k): (dict(v) if isinstance(v, dict) else {}) for k, v in p["choices"].items()}
        dflt = str(p.get("default") or next(iter(ch)))
        params[str(name)] = {"default": dflt if dflt in ch else next(iter(ch)), "choices": ch}
    return {"id": str(r["id"]), "version": str(r.get("version") or "1.0"), "order": int(r.get("order") or 100),
            "world": {"kind": str(w.get("kind") or str(r["id"]).split(".")[0]), "nodes": [str(n) for n in w.get("nodes") or ["resolve"]],
                      "engine": dict(w["engine"]) if isinstance(w.get("engine"), dict) else {}},
            "soul": {"variant": str(s.get("variant") or "legacy")}, "params": params, "private": private,
            "aliases": {str(k): {str(a): str(b) for a, b in (v or {}).items()} for k, v in (r.get("aliases") or {}).items() if isinstance(v, (dict, type(None)))}}


def _all() -> dict[str, dict[str, Any]]:
    """Every template on disk, by id (the private layer's replace the engine's of the same id)."""
    dirs = _dirs()
    key = _stamp(dirs)
    if _CACHE.get("key") == key and _CACHE.get("dirs") == dirs:
        return _CACHE["by"]
    by: dict[str, dict[str, Any]] = {}
    for d in dirs:
        for f in sorted(d.glob(f"*/{FILE}")):
            r = _read(f)
            if r is not None:
                by[str(r["id"])] = _norm(r, d != _DIR)
    _CACHE.update(key=key, dirs=dirs, by=by)
    return by


def stamp() -> tuple[Any, ...]:
    """Changes whenever what :func:`layer` can answer changes: the template files, the node-kind plugins, the private
    switch (core/engine_config caches its layer on it)."""
    from neonrp.core import node_kinds

    dirs = _dirs()
    return (tuple(map(str, dirs)), _stamp(dirs), tuple(node_kinds.kinds()), os.environ.get("NEONRP_PRIVATE", ""))


def _core_nodes() -> set[str]:
    """The core nodes this engine can run: the Resolve, and each node-kind plugin's that brings a graph node."""
    from neonrp.core import node_kinds

    out = {"resolve"}
    for kind in node_kinds.kinds():
        g = node_kinds.call(kind, "graph", default=None)
        if isinstance(g, dict):
            out |= {str(k) for k in (g.get("nodes") or {})}
    return out


def _runnable(t: dict[str, Any], have: set[str]) -> bool:
    if t["private"] and os.environ.get("NEONRP_PRIVATE", "").strip().lower() in ("off", "0", "false", "no"):
        return False
    return set(t["world"]["nodes"]) <= have


def templates() -> list[dict[str, Any]]:
    """Every template this engine can run, in order (copies)."""
    have = _core_nodes()
    return [copy.deepcopy(t) for t in sorted(_all().values(), key=lambda t: (t["order"], t["id"])) if _runnable(t, have)]


def get(tid: str) -> dict[str, Any] | None:
    """The template ``tid`` when this engine can run it, else None."""
    t = _all().get(str(tid or ""))
    return copy.deepcopy(t) if t is not None and _runnable(t, _core_nodes()) else None


def resolve(tid: str) -> dict[str, Any] | None:
    """The template a world naming ``tid`` plays: ``tid`` itself, else (an orchestration this engine does not have) the
    first open one, else the first one; None when the engine has none."""
    t = get(tid)
    if t is not None:
        return t
    ts = templates()
    return next((r for r in ts if not r["private"]), ts[0] if ts else None)


# ── a world's choice ─────────────────────────────────────────────────────────

def parse_uses(u: Any) -> dict[str, Any] | None:
    """``template.json`` ``uses`` → ``{template, version, soul, params}`` (``soul`` '' = the template's default); None when
    absent or not one."""
    if isinstance(u, str) and u.strip():
        u = {"template": u.strip()}
    if not isinstance(u, dict) or not str(u.get("template") or "").strip():
        return None
    params = u.get("params") if isinstance(u.get("params"), dict) else {}
    return {"template": str(u["template"]).strip(), "version": str(u.get("version") or ""), "soul": str(u.get("soul") or ""),
            "params": {str(k): str(v) for k, v in params.items()}}


def ref(u: dict[str, Any] | None) -> str:
    """A choice as one string (what the creation desk passes around): ``<id>`` or ``<id>?<param>=<choice>&…``."""
    if not u:
        return ""
    t = get(u["template"]) or {}
    ps = [(k, v) for k, v in sorted((u.get("params") or {}).items()) if ((t.get("params") or {}).get(k) or {}).get("default") != v]
    return str(u["template"]) + ("?" + "&".join(f"{k}={v}" for k, v in ps) if ps else "")


def from_ref(s: str) -> dict[str, Any] | None:
    """:func:`ref` back → ``{template, version, soul: "", params}`` (version = the template's), None for an empty string.
    An old preset id (a template's ``aliases``) is read as that template with the alias's choices."""
    s = str(s or "").strip()
    if not s:
        return None
    tid, _, q = s.partition("?")
    params: dict[str, str] = {}
    if get(tid) is None:
        owner = next((t for t in templates() if tid in t["aliases"]), None)
        if owner is not None:
            tid, params = owner["id"], dict(owner["aliases"][tid])
    for part in q.split("&") if q else []:
        k, _, v = part.partition("=")
        if k:
            params[k] = v
    t = get(tid)
    return {"template": tid, "version": str((t or {}).get("version") or ""), "soul": "", "params": params}


def check_ref(s: str) -> str | None:
    """Why ``s`` is not a template choice this engine offers (None = fine)."""
    u = from_ref(s)
    if u is None:
        return None
    t = get(u["template"])
    if t is None:
        return f"must be one of {', '.join(r['id'] for r in templates())}"
    for k, v in u["params"].items():
        p = t["params"].get(k)
        if p is None:
            return f"{u['template']}: no parameter {k!r}"
        if v not in p["choices"]:
            return f"{u['template']}: {k} must be one of {', '.join(p['choices'])}"
    return None


def engine_of(t: dict[str, Any], params: dict[str, str] | None = None, *, soul: str | None = "") -> dict[str, Any]:
    """The engine settings template ``t`` stands for: its world orchestration's, the chosen parameters' over them, and
    how the characters present act (``soul``; '' = the template's default; None = leave it to the layers below)."""
    eng = copy.deepcopy(t["world"]["engine"])
    for name, p in t["params"].items():
        choice = str((params or {}).get(name) or p["default"])
        eng = _deep_merge(eng, p["choices"].get(choice) or p["choices"][p["default"]])
    if soul is not None:
        eng = _deep_merge(eng, {"turn": {"parallel": {"souls": {"default_variant": soul or t["soul"]["variant"]}}}})
    return eng


def layer(uses: Any, *, contract: bool) -> dict[str, Any]:
    """The ``orchestration`` engine layer: the named template's settings with the world's characters' orchestration
    (core/engine_config); without ``uses`` the settings the world used to get from its play contract (``contract``: it
    has one) — the world orchestration only."""
    u = parse_uses(uses)
    if u is not None:
        t = resolve(u["template"])
        if t is None:
            return {}
        return engine_of(t, u["params"] if t["id"] == u["template"] else None, soul=u["soul"])
    if not contract:
        return {}
    t = next((r for r in templates() if r["world"]["kind"] == LEGACY_CONTRACT), None)
    return engine_of(t, soul=None) if t is not None else {}


def owned_keys() -> set[str]:
    """Every dotted engine setting some template decides (a world's own ``pack.engine`` copy of one would override the
    template it switches to)."""
    out = {VARIANT_KEY}
    for t in _all().values():
        out |= set(_flat(t["world"]["engine"]))
        for p in t["params"].values():
            for ch in p["choices"].values():
                out |= set(_flat(ch))
    return out


def _get(d: dict[str, Any], dotted: str) -> Any:
    cur: Any = d
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _flat(d: dict[str, Any], pre: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (d or {}).items():
        if isinstance(v, dict) and v:
            out.update(_flat(v, f"{pre}{k}."))
        else:
            out[f"{pre}{k}"] = v
    return out


def without_owned(eng: dict[str, Any]) -> dict[str, Any]:
    """``eng`` with every template-owned setting taken out (empty dicts dropped)."""
    owned = owned_keys()

    def walk(d: dict[str, Any], pre: str) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in d.items():
            key = f"{pre}{k}"
            if key in owned:
                continue
            if isinstance(v, dict):
                sub = walk(v, key + ".")
                if sub or not v:
                    out[k] = sub
            else:
                out[k] = copy.deepcopy(v)
        return out

    return walk(eng or {}, "")


def matches(eng: dict[str, Any], t: dict[str, Any], params: dict[str, str] | None = None) -> bool:
    """Does an effective engine settings dict play as template ``t`` (each of its world orchestration's settings;
    ``plan_loop`` off when absent)? The characters' orchestration is the world's own axis, not compared."""
    have = _flat(eng)
    for k, v in _flat(engine_of(t, params, soul=None)).items():
        cur = have.get(k, "off" if k == "turn.plan_loop" else None)
        if str(cur).lower() != str(v).lower():
            return False
    return True
