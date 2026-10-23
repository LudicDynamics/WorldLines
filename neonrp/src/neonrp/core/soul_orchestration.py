"""A character's own orchestration graph — the soul side of the orchestration bench (niko 10-16, PLATFORM-PLAY-RULES §3:
「角色编排台和世界编排台一体两面」). Same shape as the world's ``worldlines.orchestration/1`` (core/orchestration) with
``subject: "soul"``; the node kinds and the tools are the soul's own:

    chat      one message in → 1–5 bubbles out (the phone screen, core/soul_chat; today's behaviour = the default graph)
    tick      the character does one thing on its own between chats (the foreground tick, core/soul_tick; the player's switch,
              off by default); fields interval_min · daily_max · proactive_daily · prompt
    reflect   short-term memory folded into long-term after every N ticks (one cheap call, core/soul_tick.reflect); fields
              every (0 = off, the default) · keep
    in_world  the beat a world's turn asks of this character — not a node of this graph: the bench shows its real settings
              in the world (:func:`in_world`) and writes its variant into that world's engine settings

    edges     {id, from, to, on, when?}; on = {"chat": "message"} · {"tick": "<name>"} · {"idle": <minutes>}
    tools     sticker (chat) · memo.write (tick · reflect: they always write their memory; a chat writes none) ·
              image.generate (async ``[~image …]``, an interface only: off) · image.crop (off)

Where a graph comes from (later wins): the engine's default (:func:`default_graph`) · the soul folder's own
``agents/orchestration.json`` (the character library, or a world's soul folder) · the template's override
``prompts/souls/<sid>/orchestration.json`` (this world only). A file is a whole graph (``nodes`` + ``edges``) or a patch
``{nodes, remove, add}`` — core/orchestration's format. A graph declares the spec versions it was written for
(``targets: {soul_spec, world_spec}``); lint refuses one this engine cannot read and warns when the soul is older.

Memory is never in the graph: a new graph reads the same folder (soul.md · persona · memos) and the same thread, so an
edited graph never loses what the character remembers.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

SCHEMA = "worldlines.orchestration/1"
SUBJECT = "soul"
SOUL_SPEC = 1   # documents/spec/soul — bump on a change an old graph cannot read
WORLD_SPEC = 1  # documents/spec/world
FILE = "agents/orchestration.json"

NODE_KINDS: dict[str, dict[str, Any]] = {
    "chat": {"doc": "one message in, 1-5 bubbles out (the phone)", "tools": ["sticker", "image.generate", "image.crop"],
             "params": {"history": 24, "docs": ["soul.md", "persona", "background", "character/profile.json", "long-term-memo", "short-term-memo"],
                        "doc_cap": 9000, "max_bubbles": 5},
             "steps": [{"by": "engine", "id": "docs", "doc": "read its documents (docs · doc_cap)"},
                       {"by": "engine", "id": "history", "doc": "the last messages (history)"},
                       {"by": "llm", "id": "reply", "doc": "one model call answers"},
                       {"by": "engine", "id": "bubbles", "doc": "split into bubbles (max_bubbles) · stickers when the node has the tool"}]},
    "tick": {"doc": "one thing the character does on its own between chats (core/soul_tick; the player's switch, off by default)",
             "tools": ["memo.write"], "params": {"interval_min": 10, "daily_max": 24, "proactive_daily": 2, "prompt": ""},
             "steps": [{"by": "engine", "id": "ambient", "doc": "its simple world: the routine row for this time of day"},
                       {"by": "llm", "id": "doing", "doc": "one model call: one small thing it does (prompt; empty = the engine's)"},
                       {"by": "engine", "id": "memory", "doc": "write it into its own memory (trajectory/action_log.md · short-term-memo)"},
                       {"by": "engine", "id": "message", "doc": "maybe text the player (at most proactive_daily a day)"},
                       {"by": "hook", "id": "reflect", "doc": "every N ticks: the reflect node (when the graph has one switched on)"}]},
    "reflect": {"doc": "short-term memory folded into long-term (one cheap model call after every N ticks; every 0 = off)",
                "tools": ["memo.write"], "params": {"every": 0, "keep": 12},
                "steps": [{"by": "engine", "id": "read", "doc": "short-term-memo/recent_events.json + what it already reflected"},
                          {"by": "llm", "id": "fold", "doc": "one cheap model call (≤ 400 tokens): a few lines worth keeping"},
                          {"by": "engine", "id": "write", "doc": "append to long-term-memo/reflections.md · keep the last `keep` short-term events"}]},
    "in_world": {"doc": "the beat a world asks of this character (the world's engine settings; the variant is edited here, this world only)",
                 "tools": [], "params": {}, "readonly": True, "addable": False,
                 "steps": [{"by": "hook", "id": "called", "doc": "the world's turn calls on it by depth (silent · gesture · speak · act · away)"},
                           {"by": "llm", "id": "soul_step", "doc": "its turn under its variant (legacy · S-judge · S-direct · S-free)"},
                           {"by": "engine", "id": "settle", "doc": "the world settles it (verify · its memory)"}]},
}
TOOLS: dict[str, dict[str, Any]] = {
    "sticker": {"sync": True, "live": True, "kinds": ["chat"], "doc": "a line [sticker wl:<id>] / [sticker soul:<id>] sends a sticker"},
    "memo.write": {"sync": True, "live": True, "kinds": ["tick", "reflect"],
                   "doc": "its own memory: a tick writes what it did (trajectory · short-term), a reflect folds short-term into long-term; a chat writes none"},
    "image.generate": {"sync": False, "live": False, "kinds": [], "doc": "[~image <what>]: a picture drawn by the platform (interface only; off)"},
    "image.crop": {"sync": True, "live": False, "kinds": [], "doc": "a crop of one of its own finished pictures (portrait / CG)"},
}
# only the triggers the engine reads: chat (core/soul_chat) · tick / idle (core/soul_tick)
ON_KINDS = {"chat": "a message from the player", "tick": "the foreground tick (every interval_min)",
            "idle": "minutes without a message from the player (the phone open): one tick per quiet stretch"}
# a node's numbers: (low, high) — lint blocks a value out of range; the engine reads only in-range ints (core/soul_tick)
KNOB_RANGES: dict[str, dict[str, tuple[int, int]]] = {
    "chat": {"history": (0, 200), "doc_cap": (0, 60000), "max_bubbles": (1, 5)},
    "tick": {"interval_min": (1, 1440), "daily_max": (1, 288), "proactive_daily": (0, 20)},
    "reflect": {"every": (0, 100), "keep": (1, 40)},
}
PROMPT_MAX = 4000
IDLE_RANGE = (1, 1440)
# what node-kind plugins add (:func:`extend`; the private layer's phone orchestration) — hidden while NEONRP_PRIVATE=off
_EXT: dict[str, dict[str, Any]] = {"kinds": {}, "params": {}, "steps": {}, "ranges": {}, "on": {}}


def extend(*, kind: str, spec: dict[str, Any] | None = None, params: dict[str, Any] | None = None,
           ranges: dict[str, tuple[int, int]] | None = None, steps: list[dict[str, Any]] | None = None,
           on: dict[str, str] | None = None) -> None:
    """A plugin adds to the soul graph's vocabulary: a new node ``kind`` (``spec`` = {doc, tools, params, steps}), or
    more ``params`` / ``steps`` / int ``ranges`` on an existing kind, and triggers ``on`` an edge may use."""
    if spec is not None and kind not in NODE_KINDS:
        _EXT["kinds"][kind] = copy.deepcopy(spec)
    _EXT["params"].setdefault(kind, {}).update(copy.deepcopy(params or {}))
    _EXT["ranges"].setdefault(kind, {}).update(dict(ranges or {}))
    if steps:
        _EXT["steps"][kind] = [s for s in _EXT["steps"].get(kind, []) if s.get("id") not in {x.get("id") for x in steps}] + copy.deepcopy(steps)
    _EXT["on"].update(dict(on or {}))


def _plugins_on() -> bool:
    from neonrp.core import node_kinds

    node_kinds.kinds()  # loads the plugins (and with them what they extend)
    return not node_kinds._private_off()


def kinds() -> dict[str, dict[str, Any]]:
    """The node kinds this engine runs: :data:`NODE_KINDS` + what plugins extend."""
    out = copy.deepcopy(NODE_KINDS)
    if not _plugins_on():
        return out
    out.update(copy.deepcopy(_EXT["kinds"]))
    for k, v in out.items():
        v["params"] = {**(v.get("params") or {}), **copy.deepcopy(_EXT["params"].get(k) or {})}
        v["steps"] = [*(v.get("steps") or []), *copy.deepcopy(_EXT["steps"].get(k) or [])]
    return out


def knob_ranges() -> dict[str, dict[str, tuple[int, int]]]:
    out = {k: dict(v) for k, v in KNOB_RANGES.items()}
    if _plugins_on():
        for k, v in _EXT["ranges"].items():
            out.setdefault(k, {}).update(v)
    return out


def on_kinds() -> dict[str, str]:
    return {**ON_KINDS, **(_EXT["on"] if _plugins_on() else {})}


def node_params(n: dict[str, Any] | None, kind: str) -> dict[str, Any]:
    """A node's parameters as the engine runs them: the kind's defaults, overridden by the node's in-range values."""
    out = copy.deepcopy(kinds().get(kind, {}).get("params") or {})
    rng = knob_ranges()
    for k, v in (n or {}).items():
        if k in rng.get(kind, {}):
            lo, hi = rng[kind][k]
            if isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi:
                out[k] = v
        elif k == "prompt" and kind == "tick" and isinstance(v, str) and len(v) <= PROMPT_MAX:
            out[k] = v
    return out


def default_graph() -> dict[str, Any]:
    """What every character runs without a graph of its own: the phone's chat node, as core/soul_chat behaved on 10-15."""
    return {"schema": SCHEMA, "subject": SUBJECT, "id": "soul-default", "targets": {"soul_spec": SOUL_SPEC, "world_spec": WORLD_SPEC},
            "start": "chat",
            "nodes": {"chat": {"kind": "chat", "title": "chat", "tools": ["sticker"], **copy.deepcopy(NODE_KINDS["chat"]["params"])}},
            "edges": [{"id": "chat>chat:message", "from": "chat", "to": "chat", "on": {"chat": "message"}}]}


def _read(p: Path) -> dict[str, Any] | None:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def _layer(g: dict[str, Any], d: dict[str, Any] | None) -> dict[str, Any]:
    if not d:
        return g
    if isinstance(d.get("nodes"), dict) and isinstance(d.get("edges"), list) and not (d.get("add") or d.get("remove")):
        nodes = {k: v for k, v in d["nodes"].items() if isinstance(v, dict)}  # a whole graph replaces
        return {**g, **{k: v for k, v in d.items() if k not in ("nodes", "edges")}, "nodes": nodes, "edges": [e for e in d["edges"] if isinstance(e, dict)]}
    from neonrp.core.orchestration import _patch

    out = _patch(g, d)
    for k in ("start", "targets", "id"):
        if d.get(k):
            out[k] = d[k]
    return out


def sources(folder: Path | None, template_dir: Path | None = None, sid: str = "") -> list[tuple[str, Path]]:
    """The files a character's graph is layered from, in order: its own folder's, then the template's override."""
    out: list[tuple[str, Path]] = []
    if folder is not None:
        out.append(("soul", Path(folder) / FILE))
    if template_dir is not None and sid:
        out.append(("template", Path(template_dir) / "prompts" / "souls" / sid / "orchestration.json"))
    return out


def graph(folder: Path | None, template_dir: Path | None = None, sid: str = "") -> dict[str, Any]:
    """The effective graph: default · the soul folder's · the template's override (this world only)."""
    g = default_graph()
    for _, p in sources(folder, template_dir, sid):
        g = _layer(g, _read(p))
    g["schema"], g["subject"] = SCHEMA, SUBJECT
    return g


def chat_node(g: dict[str, Any]) -> dict[str, Any]:
    """The node that answers a message: the target of the ``{chat: message}`` edge from the start (or from anywhere),
    else the start itself when it is a chat node; its params fall back to the chat kind's defaults."""
    nodes = g.get("nodes") or {}
    start = str(g.get("start") or "")
    to = next((str(e.get("to")) for e in g.get("edges") or [] if isinstance(e, dict) and (e.get("on") or {}).get("chat") == "message"
               and str(e.get("from")) in (start, "*") and str(e.get("to")) in nodes), "")
    nid = to or (start if (nodes.get(start) or {}).get("kind") == "chat" else "")
    if not nid or (nodes.get(nid) or {}).get("kind") != "chat":
        return {}
    return {"id": nid, **copy.deepcopy(kinds()["chat"]["params"]), **{k: v for k, v in nodes[nid].items()}}


def lint(g: dict[str, Any], soul_spec: int | None = None) -> list[dict[str, str]]:
    """block = this engine will not run it as drawn; warn = it runs, but not all of it does something yet."""
    out: list[dict[str, str]] = []

    def add(level: str, code: str, msg: str) -> None:
        out.append({"level": level, "code": code, "msg": msg})

    if g.get("subject", SUBJECT) != SUBJECT:
        add("block", "orch.subject", f"subject: {g.get('subject')} is not a soul graph")
    tg = g.get("targets") or {}
    for key, have in (("soul_spec", SOUL_SPEC), ("world_spec", WORLD_SPEC)):
        want = tg.get(key)
        if want is None:
            continue
        if not isinstance(want, int) or want > have:
            add("block", "orch.spec_mismatch", f"targets.{key}: {want} — this engine reads {key} {have}")
    if soul_spec is not None and isinstance(tg.get("soul_spec"), int) and soul_spec < tg["soul_spec"]:
        add("warn", "orch.spec_mismatch", f"targets.soul_spec: {tg['soul_spec']} — the character's folder is spec {soul_spec}")
    nodes = g.get("nodes") or {}
    KINDS, RANGES, ON = kinds(), knob_ranges(), on_kinds()
    if not isinstance(nodes, dict) or not nodes:
        add("block", "orch.empty", "no nodes")
        return out
    if str(g.get("start") or "") not in nodes:
        add("block", "orch.start", f"start: {g.get('start')} is not a node")
    for nid, n in nodes.items():
        kind = str((n or {}).get("kind") or "")
        if kind not in KINDS:
            add("block", "orch.node_kind", f"{nid}: kind {kind or '—'} is not a soul node kind ({' · '.join(KINDS)})")
            continue
        for t in (n or {}).get("tools") or []:
            if t not in TOOLS:
                add("warn", "orch.tool_unknown", f"{nid}: tool {t} is not registered")
            elif t not in KINDS[kind]["tools"]:
                add("warn", "orch.tool_unknown", f"{nid}: tool {t} is not one a {kind} node can call")
            elif not TOOLS[t]["live"] or kind not in TOOLS[t]["kinds"]:
                add("warn", "orch.tool_off", f"{nid}: tool {t} is not live yet — drawn, not called")
        for k, (lo, hi) in RANGES.get(kind, {}).items():
            v = (n or {}).get(k)
            if v is not None and (not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi):
                add("block", "orch.param_range", f"{nid}: {k} = {v!r} — a whole number from {lo} to {hi}")
        if kind == "tick" and (n or {}).get("prompt") is not None and (not isinstance(n["prompt"], str) or len(n["prompt"]) > PROMPT_MAX):
            add("block", "orch.param_range", f"{nid}: prompt — text up to {PROMPT_MAX} characters")
        if kind == "reflect" and not node_params(n, kind)["every"]:
            add("warn", "orch.node_off", f"{nid}: every = 0 — the reflect node is off (set every ≥ 1 to fold memory after that many ticks)")
    for e in g.get("edges") or []:
        eid = str((e or {}).get("id") or f"{(e or {}).get('from')}>{(e or {}).get('to')}")
        if not isinstance(e, dict) or not isinstance(e.get("on"), dict):
            add("block", "orch.edge", f"{eid}: an edge needs from / to / on")
            continue
        if (e.get("from") != "*" and e.get("from") not in nodes) or e.get("to") not in nodes:
            add("block", "orch.edge", f"{eid}: points at a node that does not exist")
        for k in e["on"]:
            if k not in ON:
                add("warn", "orch.on_unknown", f"{eid}: trigger {k} is not one a soul graph knows ({' · '.join(ON)})")
            elif k in ("tick", "idle") and (nodes.get(str(e.get("to"))) or {}).get("kind") != "tick":
                add("warn", "orch.on_target", f"{eid}: {k} only starts a tick node")
        v = e["on"].get("idle")
        if "idle" in e["on"] and (not isinstance(v, int) or isinstance(v, bool) or not IDLE_RANGE[0] <= v <= IDLE_RANGE[1]):
            add("block", "orch.param_range", f"{eid}: idle = {v!r} — minutes, a whole number from {IDLE_RANGE[0]} to {IDLE_RANGE[1]}")
    if not chat_node(g):
        add("warn", "orch.no_chat", "no chat node answers {chat: message} — the phone falls back to the default chat")
    return out


def describe() -> dict[str, Any]:
    """What the bench draws with — only what this engine runs: node kinds (each with its real steps, parameters and
    their ranges) · tools (``live`` + the kinds that call them) · triggers · the spec versions this engine reads."""
    ks, rng = kinds(), knob_ranges()
    for k, v in ks.items():
        v["ranges"] = {p: list(r) for p, r in rng.get(k, {}).items()}
        v.setdefault("addable", True)
        v.setdefault("readonly", False)
    return {"schema": "worldlines.orchestration-hooks/1", "subject": SUBJECT, "specs": {"soul_spec": SOUL_SPEC, "world_spec": WORLD_SPEC},
            "node_kinds": ks, "tools": copy.deepcopy(TOOLS), "on": on_kinds(), "idle_range": list(IDLE_RANGE)}


def patch_of(base: dict[str, Any], g: dict[str, Any]) -> dict[str, Any]:
    """What to store: the edit as a patch on ``base`` (template/author.graph_patch's format) + start / targets when changed."""
    from neonrp.template.author import graph_patch

    p = graph_patch(base, g)
    for k in ("start", "targets"):
        if g.get(k) and g.get(k) != base.get(k):
            p[k] = g[k]
    return p


def check(g: Any) -> dict[str, Any]:
    """The shape every write needs; raises ValueError(why)."""
    if not isinstance(g, dict) or not isinstance(g.get("nodes"), dict) or not isinstance(g.get("edges"), list):
        raise ValueError("graph needs nodes (object) and edges (list)")
    blocks = [x for x in lint({**g, "subject": g.get("subject", SUBJECT)}) if x["level"] == "block"]
    if blocks:
        raise ValueError("; ".join(x["msg"] for x in blocks))
    return g


# ── the bench (Local only): who can be opened · read a graph · write it back ─────────────────────────────────────────

def split_ref(ref: str) -> tuple[str, str]:
    """``lib:<folder>`` → (``lib:<folder>``, "") · ``tpl:<template>/<sid>`` (or ``<template>/<sid>``) → (template, sid)."""
    ref = str(ref or "")
    if ref.startswith("lib:"):
        return ref, ""
    body = ref[4:] if ref.startswith("tpl:") else ref
    tpl, _, sid = body.partition("/")
    return tpl, sid


def ref_of(tpl: str, sid: str) -> str:
    return tpl if tpl.startswith("lib:") else f"tpl:{tpl}/{sid}"


def catalog(lang: str | None = None) -> dict[str, Any]:
    """Every character the bench can open and the phone can talk to (niko 10-16, hybrid), one row per copy:
    ① the library's own (``library``; ``independent`` when no world links it) · ② a world's ``standalone`` · ③ a world's
    ``takeable``. A row: ref · kinds · worlds · chat (library | standalone | obtained | locked) · edit (where a graph is
    written: the library folder, or the template — this world only) · the card."""
    from neonrp import template as TP
    from neonrp.core import soul_chat as C
    from neonrp.template import author

    rows: list[dict[str, Any]] = []
    for name in C.library_souls():
        c = C.resolve(C.LIB + name, "")
        lg = C._lang(lang, c["lang"])
        try:
            worlds = TP.bindings_of(name)
        except Exception:  # noqa: BLE001
            worlds = []
        rows.append({"ref": c["tpl"], "kinds": ["library", *([] if worlds else ["independent"])], "worlds": worlds, "chat": "library",
                     "edit": {"to": "library", "id": name, "writable": True}, **_card(C, c, lg)})
    for (tpl, sid), src in sorted(C.template_souls().items()):
        take = src["t"].take.get(sid)
        if not (src["standalone"] or take is not None):
            continue
        c = C.resolve(tpl, sid)
        lg = C._lang(lang, src["lang"])
        rows.append({"ref": ref_of(tpl, sid), "kinds": [*(["standalone"] if src["standalone"] else []), *(["takeable"] if take is not None else [])],
                     "take_when": take, "worlds": [{"template": tpl, "title": C.world_title(c, lg), "sid": sid}], "chat": c["access"],
                     "zone": src["t"].zone, "edit": {"to": "template", "id": tpl, "writable": author.writable(src["t"])}, **_card(C, c, lg)})
    return {"souls": rows, "specs": {"soul_spec": SOUL_SPEC, "world_spec": WORLD_SPEC}}


def _card(C: Any, c: dict[str, Any], lg: str) -> dict[str, Any]:
    card = C.soul_card(c, lg)
    return {k: card[k] for k in ("tpl", "sid", "name", "avatar_url", "avatar_thumb_url", "portrait_fallback", "tagline", "world")}


def _soul_spec(folder: Path) -> int:
    sj = _read(Path(folder) / "soul.json") or {}
    v = sj.get("spec_version", sj.get("schema_version", 1))
    return int(v) if isinstance(v, int) else 1


def bench(ref: str, lang: str | None = None, world: str | None = None) -> dict[str, Any]:
    """What the bench shows for one character: the effective graph · the graph without this world's override · each layer
    (which file, there or not) · lint · the hooks to draw with · where a save goes · ``in_world``: its real settings in
    its world (:func:`in_world`; a library character: ``world``, else the first world that links it; None = no world)."""
    from neonrp.core import soul_chat as C
    from neonrp.template import author

    tpl, sid = split_ref(ref)
    c = C.resolve(tpl, sid)
    t = c.get("t")
    g = C.graph_of(c)
    base = graph(Path(c["dir"])) if t is not None else default_graph()
    layers = [{"scope": s, "path": str(p), "exists": p.is_file()} for s, p in sources(Path(c["dir"]), Path(t.dir) if t is not None else None, c["sid"])]
    edit = {"to": "template", "id": t.id, "writable": author.writable(t)} if t is not None else {"to": "library", "id": tpl[4:], "writable": True}
    return {"ref": ref_of(c["tpl"], c["sid"]), "name": C._name(c["sj"], C._lang(lang, c["lang"])), "graph": g, "base": base, "default": default_graph(),
            "layers": layers, "lint": lint(g, _soul_spec(Path(c["dir"]))), "hooks": describe(), "edit": edit, "in_world": in_world(c, world, lang)}


def save(ref: str, g: Any) -> dict[str, Any]:
    """Write a graph back where it belongs: a library character → its folder's ``agents/orchestration.json``; a world's
    character → the template's override (author op ``set_soul_orchestration``; a built-in template is read-only).
    Stored as a patch on what it gets without that file. ValueError(why) / PermissionError(why) when refused."""
    from neonrp.core import soul_chat as C

    tpl, sid = split_ref(ref)
    c = C.resolve(tpl, sid)
    g = check(g)
    if c.get("t") is None:
        p = Path(c["dir"]) / FILE
        patch = patch_of(default_graph(), g)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(patch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"ok": True, "to": "library", "path": str(p), "patch": patch, "graph": C.graph_of(c)}
    from neonrp.template import author

    if not author.writable(c["t"]):
        raise PermissionError(f"template {c['t'].id} is built in (read-only): copy it into your own templates first")
    out = author.apply_ops(c["t"], [{"op": "set_soul_orchestration", "sid": c["sid"], "graph": g}])
    if not out.get("ok"):
        raise ValueError("; ".join(str(x.get("why")) for x in out.get("refused") or []) or "refused")
    return {"ok": True, "to": "template", "id": c["t"].id, "applied": out.get("applied"), "graph": C.graph_of(C.resolve(tpl, sid))}


# ── in_world: the beat a world asks of this character — its real settings in that world (niko 10-17, 工作台去 mock 3.2) ──

LEGACY = "legacy"
VARIANT_KEY = "turn.parallel.souls.per_soul"
# what each path of a soul's world turn reads from the prompt tables — names only: the text stays in the engine and the
# private layer (the open bench never shows it)
STEP_PROMPTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "S-judge": ("soul_step", ("q_asked", "q_costly", "q_why", "q_willingness", "q_attitude", "q_register", "q_urgency", "q_confides",
                              "q_follow", "q_stay", "q_want_move", "q_free", "q_move_to", "judged", "act_rule", "no_explain",
                              "keep_decision", "decide_yourself", "GESTURES")),
    "S-direct": ("soul_step", ("act_rule", "direct_fmt", "silent_line")),
    "S-free": ("soul_step", ("act_rule", "no_explain", "q_attitude", "q_register", "q_urgency", "q_follow", "q_stay", "q_move_to", "silent_line")),
    LEGACY: ("conversation", ("respond_or_do",)),
}


def variants() -> tuple[str, ...]:
    from neonrp.packs.rpg.soul_step import VARIANTS

    return (LEGACY, *VARIANTS)


def _template_layers(t: Any) -> list[tuple[str, dict[str, Any]]]:
    """The engine settings a run built from ``t`` starts with, layer by layer (core/engine_config order): builtin · the
    pack's loop · the play contract's engine block (+ the private layer's) · the orchestration template the world uses
    (core/orch_templates) · the world data's game/meta/engine.json · the template's ``pack.engine`` (merged over it at
    build) · env."""
    from neonrp.core import engine_config as E
    from neonrp.template import world_dir

    out: list[tuple[str, dict[str, Any]]] = [("builtin", E.DEFAULTS)]
    try:
        from neonrp import packs

        loop = packs.load(t.pack_name).loop
    except Exception:  # noqa: BLE001
        loop = {}
    out.append(("pack", loop if isinstance(loop, dict) else {}))
    ce: dict[str, Any] = {}
    if t.data.get("play_contract"):
        try:
            from neonrp.template import contract as K

            k = K.load(str(t.data["play_contract"]))
            ce = E._deep_merge(k.get("engine") if isinstance(k.get("engine"), dict) else {}, E._private_contract_engine(str(k.get("id") or "")))
        except Exception:  # noqa: BLE001
            ce = {}
    out.append(("contract", ce))
    from neonrp.core import orch_templates

    out.append(("orchestration", orch_templates.layer(t.data.get("uses"), contract=bool(t.data.get("play_contract")))))
    wd = world_dir(t)
    out.append(("world", E._read_json(wd / "game" / "meta" / "engine.json") if wd else {}))
    eng = t.pack.get("engine")
    out.append(("template", eng if isinstance(eng, dict) else {}))
    out.append(("env", E.env_layer()))
    return out


def _pick(layers: list[tuple[str, dict[str, Any]]], dotted: str, default: Any = None) -> tuple[Any, str]:
    from neonrp.core.engine_config import _get_path

    val, src = default, "builtin"
    for name, layer in layers:
        v = _get_path(layer, dotted, None)
        if v is not None:
            val, src = v, name
    return val, src


def _private_keys(table: str, keys: tuple[str, ...], lang: str) -> list[str]:
    """Which of ``keys`` the private layer's ``prompts/<table>.<lang>.json`` replaces — names only."""
    from neonrp.core.paths import private_dir

    d = private_dir("prompts")
    have = (_read(d / f"{table}.{lang}.json") or {}) if d is not None else {}
    return [k for k in keys if k in have]


def _world_of(c: dict[str, Any], world: str | None = None) -> tuple[Any, str] | None:
    """(template, sid in it) — a world's character: its template; a library character: the world asked for among the
    ones that link it, else the first (None when no world links it)."""
    if c.get("t") is not None:
        return c["t"], c["sid"]
    from neonrp import template as TP

    try:
        rows = TP.bindings_of(str(c["tpl"])[4:])
    except Exception:  # noqa: BLE001
        rows = []
    row = next((r for r in rows if r["template"] == world), rows[0] if rows else None)
    if row is None:
        return None
    d = TP.discover().get(row["template"])
    return (TP.load(d), str(row["sid"])) if d is not None else None


def in_world(c: dict[str, Any], world: str | None = None, lang: str | None = None) -> dict[str, Any] | None:
    """What the world's turn really does with this character (the in_world node): the turn mode · its variant
    (``turn.parallel.souls.per_soul[sid]``, else ``default_variant``; legacy whenever the world is not v3) and which
    layer said so · the depth rules (core/conversation's S2 block) · the prompt names its path reads (the private layer's
    marked, never their text) · whether this world can be written."""
    from neonrp.core import engine_config as E
    from neonrp.template import author

    w = _world_of(c, world)
    if w is None:
        return None
    t, sid = w
    lg = str(lang or t.card.get("lang") or "zh")
    layers = _template_layers(t)
    mode, mode_src = _pick(layers, "turn.mode", "v2b")
    v3 = str(mode).lower() == "v3"
    dflt, dflt_src = _pick(layers, "turn.parallel.souls.default_variant", LEGACY)
    per_all: dict[str, Any] = {}
    for _n, layer in layers:   # deep-merged like the run's config: every layer's per_soul rows, later wins
        per_all.update(E._get_path(layer, VARIANT_KEY, None) or {})
    per_src = next((n for n, layer in reversed(layers) if sid in (E._get_path(layer, VARIANT_KEY, None) or {})), "")
    mine = per_all.get(sid)
    variant = (str(mine) if mine else str(dflt)) if v3 else LEGACY
    src = ("per_soul@" + per_src if mine else "default_variant@" + dflt_src) if v3 else "turn.mode@" + mode_src
    sj = variant in ("S-judge", "S-direct", "S-free")
    esc_turns, _ = _pick(layers, "turn.parallel.souls.escalate_turns", 3)
    esc_at, _ = _pick(layers, "turn.parallel.souls.escalate_at", 0.8)
    depth = [
        {"depth": "silent", "path": "skipped: no model call"},
        {"depth": "gesture", "path": "a small gesture from the register table (no model call)" if sj else "heartbeat: one line, no model call"},
        {"depth": "speak", "path": f"soul_step {variant}" if sj else "ask_soul: one question, one answer"},
        {"depth": "act", "path": f"soul_step {variant} (escalates to its agent loop when needs_free_action ≥ {esc_at})" if sj
         else f"engage loop: up to {esc_turns} model turns"},
        {"depth": "away", "path": "off the player's screen: soul_step S-direct, one call (whatever the variant)" if v3 else "—"},
    ]
    prompts = []
    for v in dict.fromkeys([variant, *(["S-direct"] if v3 else [])]):
        table, keys = STEP_PROMPTS[v]
        prompts.append({"for": "away" if v != variant else variant, "table": table, "keys": list(keys), "private": _private_keys(table, keys, lg)})
    return {"template": t.id, "title": str(t.card.get("title") or t.id), "sid": sid, "mode": mode, "v3": v3, "variant": variant,
            "source": src, "per_soul": mine, "default_variant": dflt, "variants": list(variants()), "depth": depth, "prompts": prompts,
            "key": f"{VARIANT_KEY}.{sid}", "writable": author.writable(t)}


def set_in_world(ref: str, variant: Any, world: str | None = None) -> dict[str, Any]:
    """Write this character's variant into its world's engine settings (the template's ``pack.engine``; author op
    ``set_engine_setting``; "" / None = follow the world's default_variant). A built-in template is read-only."""
    from neonrp.core import soul_chat as C
    from neonrp.template import author

    tpl, sid = split_ref(ref)
    c = C.resolve(tpl, sid)
    w = _world_of(c, world)
    if w is None:
        raise ValueError("this character is in no world")
    t, wsid = w
    if not author.writable(t):
        raise PermissionError(f"template {t.id} is built in (read-only): copy it into your own templates first")
    out = author.apply_ops(t, [{"op": "set_engine_setting", "key": f"{VARIANT_KEY}.{wsid}", "value": variant or None}])
    if not out.get("ok"):
        raise ValueError("; ".join(str(x.get("why")) for x in out.get("refused") or []) or "refused")
    return {"ok": True, "id": t.id, "applied": out.get("applied"), "in_world": in_world(C.resolve(tpl, sid), world)}


# ── the character's own stickers (S5): pictures + what each one means (stickers/stickers.json, four languages) ─────────

STICKER_MAX = 2 * 1024 * 1024
_STICKER_ID = __import__("re").compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def _sticker_target(ref: str) -> tuple[dict[str, Any], Path]:
    from neonrp.core import soul_chat as C

    tpl, sid = split_ref(ref)
    c = C.resolve(tpl, sid)
    if c.get("t") is not None:
        from neonrp.template import author

        if not author.writable(c["t"]):
            raise PermissionError(f"template {c['t'].id} is built in (read-only): copy it into your own templates first")
    return c, Path(c["dir"]) / "stickers"


def stickers(ref: str) -> dict[str, Any]:
    """The bench's sticker page: every picture with its meaning in all four languages and when to send it."""
    from neonrp.core import soul_chat as C

    tpl, sid = split_ref(ref)
    c = C.resolve(tpl, sid)
    d = C.sticker_dir(c)
    meta = C.sticker_meta(d)
    rows = [{"id": p.stem, "label": (meta.get(p.stem) or {}).get("label") or {}, "when": (meta.get(p.stem) or {}).get("when") or "",
             "url": next((s["url"] for s in C.soul_stickers(c) if s["id"] == f"soul:{p.stem}"), "")} for p in sorted(d.glob("*.png"))] if d.is_dir() else []
    try:
        _sticker_target(ref)
        writable = True
    except PermissionError:
        writable = False
    return {"ref": ref_of(c["tpl"], c["sid"]), "stickers": rows, "writable": writable}


def sticker_put(ref: str, sid_sticker: str, data: bytes) -> dict[str, Any]:
    if not _STICKER_ID.match(sid_sticker or ""):
        raise ValueError("a sticker id is 1-32 of a-z 0-9 _ -")
    if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > STICKER_MAX:
        raise ValueError("a sticker is a PNG up to 2 MB")
    _, d = _sticker_target(ref)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sid_sticker}.png").write_bytes(data)
    return stickers(ref)


def sticker_meta_set(ref: str, sid_sticker: str, label: Any = None, when: Any = None) -> dict[str, Any]:
    from neonrp.core import soul_chat as C

    _, d = _sticker_target(ref)
    if not (d / f"{sid_sticker}.png").is_file():
        raise ValueError(f"no sticker {sid_sticker}")
    meta = C.sticker_meta(d)
    m = dict(meta.get(sid_sticker) or {})
    if isinstance(label, dict):
        m["label"] = {k: str(v).strip()[:24] for k, v in label.items() if k in ("zh", "en", "ja", "ko") and str(v or "").strip()}
    if when is not None:
        m["when"] = str(when).strip()[:120]
    meta[sid_sticker] = {k: v for k, v in m.items() if v}
    (d / "stickers.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return stickers(ref)


def sticker_remove(ref: str, sid_sticker: str) -> dict[str, Any]:
    from neonrp.core import soul_chat as C

    _, d = _sticker_target(ref)
    p = d / f"{sid_sticker}.png"
    if _STICKER_ID.match(sid_sticker or "") and p.is_file():
        p.unlink()
        meta = C.sticker_meta(d)
        if meta.pop(sid_sticker, None) is not None:
            (d / "stickers.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return stickers(ref)
