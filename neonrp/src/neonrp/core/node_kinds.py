"""Node kinds — the turn's plugin seam (10-08: open engine · private orchestration).

The engine runs an orchestration graph; what a node *does* beyond the plain turn (roll → people → narrate → verify →
land → tick) comes from a node-kind plugin. A game that needs none of them (werewolf, a murder mystery, a galgame, the
public fallback) plays on the plain turn alone — the engine knows no particular beat by name.

A plugin is any object with the hooks below (all optional except ``kind``); it is registered by kind:

    kind: str                                         "plan" …
    active(root, user_text) -> bool                   this node takes the turn now (its world stands still meanwhile)
    take_turn(session, *, user_text, trace, run_id, on_chunk) -> dict | ConversationTurnResult | None
        a ConversationTurnResult ends the turn here (the node replied, nothing landed);
        a dict is the context the plain turn below carries (facts / head lines / trace record);
        None = nothing to add
    facts(ctx, root) -> str                           text the narrator gets before it writes
    head_lines(ctx, root) -> list[str]                lines shown before what happened (dice …)
    trace_beat(ctx, out) -> dict                      the beat record kept in the turn's trace
    carry(ctx, root, who) -> ...                      what a person present carries out from the node
    check_edge(frm, to, on_kind) -> None | str | False  lint: fine · why it never runs · not this plugin's trigger
    check_node(nid, node) -> None | str               lint for a node of this kind: fine · why it never runs

Seams outside the turn's node loop (:func:`call_all` — every plugin that has the hook, results not None). A plugin that
only answers seams and brings no node of the world's graph registers with :func:`register_seams` (it is not a node kind:
no world orchestration lists it — the phone orchestration, 10-21):

    before_turn(root)                                 a turn is about to read the world (after the inbox, before intake)
    chat_system(c, node, lang) -> str                 text added to a phone chat's system prompt (core/soul_chat)
    greet_system(c, lang) -> str                      … to the system prompt of a character's first line (soul_chat.greet)
    tick_system(c, lang) -> str                       … to a tick's system prompt (core/soul_tick)
    chat_reply(c, node, raw, lang) -> (raw, [msg])    a chat reply before it is split into bubbles: the plugin's own
                                                      lines taken out, its messages appended
    chat_sent(c, node, saved, adapter=, lang=)        after a chat reply was kept
    soul_ticked(c, out, adapter=, lang=) -> dict      after a character's tick landed (core/soul_tick): merged into its answer
    chat_online(c, state, rt=, lang=) -> [msg]        the player is on the phone with her (soul_chat.presence): her messages
    tick_context(c, lang) -> str                      where she is now, instead of her simple world (core/soul_tick)
    tick_owns_message(c) -> bool                      the plugin sends a tick's message itself, after its step
                                                      (``soul_ticked`` → ``message``: text or {text, attach})
    phone_subscription(c, body, lang=) -> dict        GET / POST /api/v1/chat/subscription: the plugin's answer
    phone_catchup(c, lang=, rt=) -> dict              POST /api/v1/chat/catchup: the plugin's answer
    phone_row(c) -> dict                              its word on a character's row of the phone's list (``phone``)
    phone_orch_bench(op, body) -> dict                the local desk's /api/v1/phone/orchestration (get · lint · save · reset)

The engine registers three generic kinds of its own — ``opening`` (core/opening: the world's authored opening, in any
orchestration), ``player_action`` (core/player_action: a front end's structured inspect / pick; called ``act`` before
10-19 — the old name still reads, see :data:`ALIASES`) and ``interaction`` (core/interaction_node: a game client's
interaction graphs). Plugins come from the private layer (``neonrp.core.paths.private_dir("nodes")/*.py``, each module
calling ``register``) or any code that registers one. The open engine ships no others. ``NEONRP_PRIVATE=off`` hides the
private ones.

Which active node takes a turn first: :func:`turn_order` (a plugin's ``order``, default 100, then its kind) — the
player's own structured move (``player_action``, order 0) always before any talk.
"""
from __future__ import annotations

import importlib.util
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)

_REG: dict[str, Any] = {}
_LOADED: set[str] = set()
# old kind names that still read (10-19: the world's ``act`` became ``player_action`` — a character's ``act`` on the
# phone is another thing, core/soul_orchestration)
ALIASES: dict[str, str] = {"act": "player_action"}


def canonical(kind: str) -> str:
    """The kind a (possibly old) name stands for."""
    return ALIASES.get(str(kind or ""), str(kind or ""))


def register(plugin: Any) -> Any:
    """Register a node-kind plugin under its ``kind`` (a later one replaces an earlier one of the same kind)."""
    kind = str(getattr(plugin, "kind", "") or "")
    if not kind:
        raise ValueError("a node-kind plugin needs a kind")
    _REG[kind] = plugin
    return plugin


def unregister(kind: str) -> None:
    _REG.pop(kind, None)
    _SEAMS.pop(kind, None)


_SEAMS: dict[str, Any] = {}  # plugins that answer seams only (not node kinds of a world's graph)


def register_seams(plugin: Any) -> Any:
    """Register a plugin that only answers seams (:func:`call_all`), under its ``kind`` as a name — never listed by
    :func:`kinds`, so no world orchestration offers it as a node."""
    name = str(getattr(plugin, "kind", "") or "")
    if not name:
        raise ValueError("a seam plugin needs a kind (its name)")
    _SEAMS[name] = plugin
    return plugin


def seams() -> list[str]:
    """The seam-only plugins' names (a private one hidden while ``NEONRP_PRIVATE=off``)."""
    _load_builtin()
    _load_private()
    off = _private_off()
    return sorted(k for k in _SEAMS if not (off and k in _PRIVATE_SEAMS))


def _load_private() -> None:
    from neonrp.core.paths import private_dir

    d = private_dir("nodes")
    key = str(d) if d is not None else ""
    if not key or key in _LOADED:
        return
    _LOADED.add(key)
    for f in sorted(d.glob("*.py")):  # type: ignore[union-attr]
        if f.name.startswith("_"):
            continue
        name = f"neonrp_private_nodes.{f.stem}"
        try:
            before, before_s = set(_REG), set(_SEAMS)
            spec = importlib.util.spec_from_file_location(name, f)
            mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            sys.modules[name] = mod
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            _PRIVATE_KINDS.update(set(_REG) - before)
            _PRIVATE_SEAMS.update(set(_SEAMS) - before_s)
        except Exception:  # noqa: BLE001 — a broken private plugin never stops the public engine
            logger.warning("private node plugin %s failed to load", f, exc_info=True)


_PRIVATE_KINDS: set[str] = set()  # kinds registered while loading the private layer
_PRIVATE_SEAMS: set[str] = set()  # seam plugins registered while loading it


def _private_off() -> bool:
    import os

    return os.environ.get("NEONRP_PRIVATE", "").strip().lower() in ("off", "0", "false", "no")


_BUILTIN = False


def _load_builtin() -> None:
    """The engine's own generic node kinds — only what every orchestration shares (the world's authored opening)."""
    global _BUILTIN
    if _BUILTIN:
        return
    _BUILTIN = True
    from neonrp.core import interaction_node, opening, player_action

    if "opening" not in _REG:
        register(opening._OpeningNode())
    if "player_action" not in _REG:  # the player's structured action from a front end (inspect / pick, 10-14)
        register(player_action._PlayerActionNode())
    if "interaction" not in _REG:  # a game client's interaction graphs (move · examine · talk · approach · encounter, 10-19)
        register(interaction_node._InteractionNode())


def get(kind: str) -> Any | None:
    """The plugin for ``kind``, or None (the plain turn). A private plugin is hidden while ``NEONRP_PRIVATE=off``."""
    _load_builtin()
    _load_private()
    kind = canonical(kind)
    if kind in _PRIVATE_KINDS and _private_off():
        return None
    return _REG.get(kind)


def kinds() -> list[str]:
    _load_builtin()
    _load_private()
    off = _private_off()
    return sorted(k for k in _REG if not (off and k in _PRIVATE_KINDS))


def turn_order() -> list[str]:
    """:func:`kinds` in the order their nodes may take a turn: each plugin's ``order`` (default 100), then its kind."""
    return sorted(kinds(), key=lambda k: (int(getattr(_REG.get(k), "order", 100) or 0), k))


def module_of(kind: str) -> Any | None:
    """The module a plugin lives in (tests and the graph runner stub its model calls there), or None."""
    p = get(kind)
    if p is None and kind in seams():
        p = _SEAMS.get(kind)
    return sys.modules.get(type(p).__module__) if p is not None else None


def call(kind: str, hook: str, *args: Any, default: Any = None, **kwargs: Any) -> Any:
    """``plugin.hook(*args, **kwargs)`` when the plugin and the hook exist, else ``default``."""
    p = get(kind)
    fn = getattr(p, hook, None) if p is not None else None
    return fn(*args, **kwargs) if callable(fn) else default


def hooks(hook: str) -> list[tuple[str, Any]]:
    """(name, callable) of every plugin (node kinds, then seam plugins) that has ``hook`` — for a caller that chains
    them (each one gets what the one before it gave back)."""
    out: list[tuple[str, Any]] = []
    for kind, p in [*((k, _REG.get(k)) for k in kinds()), *((k, _SEAMS.get(k)) for k in seams())]:
        fn = getattr(p, hook, None)
        if callable(fn):
            out.append((kind, fn))
    return out


def call_all(hook: str, *args: Any, **kwargs: Any) -> list[Any]:
    """``hook(*args, **kwargs)`` of every plugin that has it, in kind order; the results that are not None. A plugin that
    raises is logged and skipped — a seam never breaks its caller. No plugin with the hook = ``[]`` (the open engine)."""
    out: list[Any] = []
    for kind, fn in hooks(hook):
        try:
            r = fn(*args, **kwargs)
        except Exception:  # noqa: BLE001
            logger.warning("node plugin %s: %s failed", kind, hook, exc_info=True)
            continue
        if r is not None:
            out.append(r)
    return out
