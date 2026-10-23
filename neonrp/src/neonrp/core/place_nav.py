"""Town navigation — feed a soul the REAL map it already lives on (surgical).

The canonical sub-location graph already exists in
``game/towns/<TID>/town_map.json`` (each node has ``id``, ``name``, ``links``).
Nothing was feeding it to souls, so a soul that decided to "walk into the guild"
had no node id to put in ``moved_to`` and invented ids that matched nothing
(``north-gate`` vs canonical ``gate_north``) — its move never committed.

This module resolves a soul's current node → its town_map entry → adjacent
exits (id + display name), so the soul's perception can list exactly where it
may go this turn, and ``moved_to`` can carry a valid canonical id.

A richer world ontology (Place objects, scoped ids, multi-hop pathing,
occupants) is deferred to the next version — this is the down payment that uses
the data already on disk.
"""

from __future__ import annotations

import json
import logging
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Legacy id drift → canonical town_map id. The gate is the only node whose
# routing `node` ("north-gate") diverged from its town_map id ("gate_north");
# guild/inn/main_street already agree. Normalizing on read lets old saves and a
# habit-drifting world-agent still resolve while seeds move to canonical ids.
_ALIASES = {"north-gate": "gate_north"}

# A town/region id is a short uppercase-prefixed code: T001, D001, R003. Used to
# tell a town-level address (the whole town) from a bare sub-location node id
# (guild, main_street) that needs a town to be unambiguous.
_TOWN_ID_RE = re.compile(r"^[A-Z]{1,3}\d{2,4}$")


def canonical_node(node: str | None) -> str | None:
    """Map a (possibly legacy) node id to its canonical town_map id."""
    if not isinstance(node, str) or not node:
        return node
    return _ALIASES.get(node, node)


# --- scoped addresses -------------------------------------------------------
# THE problem these solve: sub-location ids (guild, main_street, shop_general)
# are reused across towns, so a bare id can't say which town it's in. The
# router/map then had to GUESS (prefer the player's town, else first match),
# and the guess flip-flopped as context changed — characters appeared to
# "jump" between towns. A scoped address carries its town: "T004/guild" (a
# spot in 碧石镇) or "T004" (the town itself). qualify_location() is the single
# normalization boundary: every stored/emitted location passes through it.


def split_location(loc: str | None) -> tuple[str | None, str | None]:
    """Split an address into (town, node).

    "T004/guild" → ("T004","guild"); "T004" → ("T004", None);
    "guild" → (None,"guild"); "" → (None, None). Node ids are canonicalized.
    """
    s = str(loc or "").strip()
    if not s:
        return (None, None)
    if "/" in s:
        town, _, node = s.partition("/")
        return (town.strip() or None, canonical_node(node.strip()) or None)
    if _TOWN_ID_RE.match(s):
        return (s, None)
    return (None, canonical_node(s))


def _canon(root: Path, node: str, town: str | None) -> str:
    """Another id a place folder lists in its ``aliases`` (riverlamp-inn for inn) → the place's own id."""
    from neonrp.core.place_tree import canonical

    return canonical(root, node, town) or node


def join_location(town: str | None, node: str | None) -> str:
    """Inverse of split_location: ("T004","guild") → "T004/guild"."""
    if town and node:
        return f"{town}/{node}"
    return town or node or ""


def _town_dirs(root: Path) -> list[Path]:
    towns = root / "game" / "towns"
    return sorted(d for d in towns.iterdir() if d.is_dir()) if towns.is_dir() else []


def town_of_node(
    root: Path, node: str | None, *, prefer_town: str | None = None
) -> str | None:
    """Which town's town_map contains this bare sub-node id.

    `prefer_town` wins if it contains the node (default-stay-in-town); else the
    first town that contains it; else None (wilderness / unknown node).
    """
    node = canonical_node(node)
    if not node:
        return None
    from neonrp.core.place_tree import canonical

    node = canonical(root, node, prefer_town)
    found: list[str] = []
    for tid, data in _town_maps(root).items():
        if any(isinstance(n, dict) and n.get("id") == node for n in data.get("nodes", [])):
            found.append(tid)
    if not found:
        return None
    if prefer_town and prefer_town in found:
        return prefer_town
    return found[0]


def qualify_location(
    root: Path, raw: str | None, *, current_town: str | None = None
) -> str:
    """Normalize any location to a self-describing scoped address.

    Returns "T###/node" (a sub-location) or "T###" (a whole town). A bare node
    id resolves to `current_town` when that town has it (the default
    stay-in-town rule — only an explicit town/qualified id moves towns), else
    the first town that contains it. An id in no town_map (wilderness) is
    returned canonicalized but unscoped. Empty in → empty out.
    """
    town, node = split_location(raw)
    if node:
        node = _canon(root, node, town or current_town)
    if town and node:
        return join_location(town, node)        # already scoped
    if town and not node:
        return town                             # town-level address
    if node and not town:
        t = town_of_node(root, node, prefer_town=current_town)
        return join_location(t, node) if t else node
    return ""


def resolve_move_target(
    root: Path,
    target: str | None,
    *,
    current_location: str | None,
    cross_town: bool = False,
) -> str | None:
    """Resolve a MOVE target to a scoped address, refusing cross-town teleports.

    Unlike :func:`qualify_location` (which always returns *something* and, for a
    bare id absent from the current town, falls back to the first town that has
    it — fine for display, fatal for movement), this is the mover's gate:

    - Explicit qualified target (``T001/gate_north`` or ``T001``) → honored.
    - Bare node the current town HAS → scoped to the current town.
    - Bare node the current town does NOT have but ANOTHER town does → ``None``
      (rejected). Cross-town travel must be an explicit ``T###/node``. This is
      what stops a hallucinated ``north-gate`` (aliased to T001's ``gate_north``)
      from teleporting a T004 soul into T001.
    - Bare node in no town_map (wilderness) → returned unscoped (leave town).
    - No current town yet (first placement) → falls back to qualify_location.

    ``cross_town=True`` trusts the caller (the authoritative world-agent, which
    owns movement and knows the map): a bare node in another town is then scoped
    to that town instead of rejected. The soul path keeps the default (False) as
    an anti-hallucination guard — though souls no longer author moves at all.
    """
    cur_town, _ = split_location(current_location)
    t_town, t_node = split_location(target)
    if t_node:
        t_node = _canon(root, t_node, t_town or cur_town)
        target = join_location(t_town, t_node)
    if t_town:                                    # explicit town / qualified id
        return qualify_location(root, target, current_town=cur_town)
    if not t_node:
        return None
    if not cur_town:                              # no town context — legacy resolve
        return qualify_location(root, target, current_town=None)
    home = town_of_node(root, t_node, prefer_town=cur_town)
    if home == cur_town:
        return join_location(cur_town, t_node)    # a real node in this town
    if home is None:
        return t_node                             # wilderness — leave town, unscoped
    # node belongs to another town: reject for souls (anti-teleport), but honor
    # it when the authoritative world-agent says so.
    return join_location(home, t_node) if cross_town else None


def _load_town_map(town_dir: Path) -> dict[str, Any] | None:
    path = town_dir / "town_map.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def town_node_view(
    root: Path, node: str | None, *, prefer_town: str | None = None
) -> dict[str, Any] | None:
    """Resolve ``node`` to a town_map entry with named exits, or None.

    Returns ``{"town", "id", "name", "exits": [{"id","name"}, ...]}``.

    Town disambiguation (some local ids like ``guild``/``main_street`` exist in
    several towns): if ``prefer_town`` contains the node it wins; otherwise the
    first town that contains it. Souls of interest share the player's town, so
    passing the player's town as ``prefer_town`` is correct for v1. A node in
    no town_map (wilderness, e.g. ``north-cliff``) returns None — callers
    degrade gracefully (no exits listed).
    """
    node = canonical_node(node)
    if not node:
        return None
    from neonrp.core.place_tree import canonical

    node = canonical(root, node, prefer_town)
    candidates: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for town_id, data in _town_maps(root).items():
        for entry in data.get("nodes", []):
            if isinstance(entry, dict) and entry.get("id") == node:
                candidates[town_id] = (data, entry)
                break
    if not candidates:
        return None

    if prefer_town and prefer_town in candidates:
        town_id = prefer_town
    else:
        town_id = next(iter(candidates))
    data, entry = candidates[town_id]

    by_id = {
        n.get("id"): n for n in data.get("nodes", []) if isinstance(n, dict)
    }
    exits = []
    for link in entry.get("links", []) or []:
        exits.append({"id": link, "name": by_id.get(link, {}).get("name", link)})

    return {
        "town": town_id,
        "id": node,
        "name": entry.get("name", node),
        "exits": exits,
    }


# --- the movement judge --------------------------------------------------
# resolve_move_target trusts the world-agent completely (cross_town=True), so
# nothing ever consulted the `links` graphs the maps already carry — a soul
# could legally cross the world in one turn (the Rowan teleport). judge_move
# is the deterministic post-process referee for that trusted path: intra-town
# movement is free (a town is one scene locality), a town TRANSITION is the
# budgeted action (one per turn, through a gate), and everything it can't
# reason about (name-only worlds, wilderness, unmapped towns) stays permissive
# so it introduces ZERO false rejections. Pure graph walks — no LLM, no I/O
# beyond reading the maps already on disk.


@dataclass
class MoveVerdict:
    """Outcome of judging one world-agent move.

    - allowed=True  → persist ``resolved`` (the move as asked, canonical).
    - allowed=False + ``clamped_to`` → persist ``clamped_to`` (partial travel
      beat; ``reason`` explains the itinerary for the world-agent).
    - allowed=False + no ``clamped_to`` → refuse the move; soul stays put.
    """

    allowed: bool
    resolved: str | None = None
    clamped_to: str | None = None
    reason: str | None = None
    tier: str = "unmapped"  # "intra" | "cross" | "unmapped"

    @property
    def final(self) -> str | None:
        """The address to persist, or None to keep the current location."""
        return self.resolved if self.allowed else self.clamped_to


def _town_maps(root: Path) -> dict[str, dict[str, Any]]:
    """All town maps keyed by town_id — old town_map.json files and folder trees alike (place_tree)."""
    from neonrp.core.place_tree import town_docs

    return town_docs(root)


def _map_nodes(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(n.get("id")): n
        for n in data.get("nodes", [])
        if isinstance(n, dict) and n.get("id")
    }


def _gate_of(data: dict[str, Any]) -> str | None:
    """A town's deterministic travel gate: first gate node by id (a node with
    type=="gate", falling back to an id that starts with "gate")."""
    nodes = _map_nodes(data)
    gates = sorted(
        nid
        for nid, n in nodes.items()
        if n.get("type") == "gate" or nid.startswith("gate")
    )
    return gates[0] if gates else None


def _R(root: Path) -> dict[str, str]:
    """The verdict texts in the run's language (prompts/place_nav.<lang>.json, 10-06)."""
    from neonrp import prompts
    from neonrp.core.output_lang import prompt_lang

    return prompts.strings("place_nav", prompt_lang(root))


def _entered(town: str, node: str, root: Path) -> str:
    return _R(root)["entered"].format(town=town, node=node)


def _route_between(world_map: dict[str, Any] | None, a: str | None, b: str | None) -> str | None:
    """The id of the world route joining places ``a`` and ``b`` (either direction), if one is declared."""
    if not world_map or not a or not b:
        return None
    for r in world_map.get("routes") or []:
        if isinstance(r, dict) and r.get("id") and {str(r.get("from")), str(r.get("to"))} == {a, b}:
            return str(r["id"])
    return None


def _landing(root: Path, town: str, data: dict[str, Any] | None, edge: str | None) -> str | None:
    """Where a parent-level edge meets this level (MAP-SCALES-1005 G1): the node whose ``ports.up`` names the edge,
    else the level's ``entry``, else the old deterministic gate. Worlds without ports / entry behave as before."""
    if not data:
        return None
    from neonrp.core.place_tree import level_entry, port_node

    nodes = _map_nodes(data)
    p = port_node(data, edge)
    if p and p in nodes:
        return p
    e = level_entry(root, town)
    if e and e in nodes:
        return e
    return _gate_of(data)


def load_world_map(root: Path) -> dict[str, Any] | None:
    """game/world/world_map.json (towns + roads + links), or None. Tree-form worlds: the top place folders are the
    nodes (place_tree.level_doc)."""
    from neonrp.core.place_tree import WORLD, level_doc

    return level_doc(root, WORLD)


def _world_route(
    world_map: dict[str, Any] | None, src: str, dst: str
) -> tuple[str, list[str]]:
    """Route between two towns over the world graph.

    Returns (status, towns_on_path) where towns_on_path lists the town
    vertices from src to dst inclusive. Real maps are sloppy — links name
    road ids that are never declared as nodes — so every link target is a
    vertex too (an undeclared shared road still connects its towns).

    status: "ok" (path found) | "noroute" (both towns are meaningfully wired
    into the graph yet share no path — positive evidence of separation) |
    "unknown" (no world map / town undeclared / town isolated: the map simply
    doesn't encode its roads, so the judge stays permissive).
    """
    if not world_map:
        return "unknown", []
    declared = {
        str(n.get("id")): n
        for n in world_map.get("nodes", [])
        if isinstance(n, dict) and n.get("id")
    }
    if src not in declared or dst not in declared:
        return "unknown", []
    towns = {
        nid for nid, n in declared.items() if n.get("type") in ("town", "city", "village")
    }
    adj: dict[str, set[str]] = {}
    for nid, n in declared.items():
        for link in n.get("links", []) or []:
            link = str(link)
            adj.setdefault(nid, set()).add(link)
            adj.setdefault(link, set()).add(nid)

    def _bfs(start: str, goal: str | None) -> tuple[list[str] | None, bool]:
        """Shortest path start→goal; also reports whether ANY other town is
        reachable from start (isolation probe when goal is None/missed)."""
        prev: dict[str, str] = {}
        seen = {start}
        queue = deque([start])
        reaches_a_town = False
        while queue:
            cur = queue.popleft()
            for nxt in adj.get(cur, ()):
                if nxt in seen:
                    continue
                seen.add(nxt)
                prev[nxt] = cur
                if nxt in towns and nxt != start:
                    reaches_a_town = True
                if goal is not None and nxt == goal:
                    path = [nxt]
                    while path[-1] != start:
                        path.append(prev[path[-1]])
                    return list(reversed(path)), True
                queue.append(nxt)
        return None, reaches_a_town

    path, _ = _bfs(src, dst)
    if path is not None:
        return "ok", [p for p in path if p in towns]
    # No path. Distinguish "the map separates them" from "the map never wired
    # this town up at all" (dangling road refs — common in authored worlds).
    _, src_reaches = _bfs(src, None)
    _, dst_reaches = _bfs(dst, None)
    if src_reaches and dst_reaches:
        return "noroute", []
    return "unknown", []


def judge_move(
    root: Path, *, current_location: str | None, target: str | None
) -> MoveVerdict:
    """Judge a world-agent move against the maps. Deterministic; zero LLM.

    Policy: intra-town movement is free (only the node must exist); a
    cross-town TRANSITION is the one budgeted travel action per turn and goes
    through gates — this turn you walk out by your gate and land in the (next)
    town (one beat, 10-19); multi-leg routes advance one town per turn; no route on the world graph → refused.
    Anything the maps can't describe stays allowed (tier "unmapped")."""
    maps = _town_maps(root)
    if not maps:
        return MoveVerdict(allowed=True, resolved=None, tier="unmapped")

    resolved = resolve_move_target(
        root, target, current_location=current_location, cross_town=True
    )
    if resolved is None:
        return MoveVerdict(
            allowed=False, reason=_R(root)["unresolved"], tier="unmapped"
        )

    cur_town, cur_node = split_location(current_location)
    t_town, t_node = split_location(resolved)

    # Wilderness / unscoped target, or a soul not currently in any town:
    # out-of-town space is the world-agent's narrative domain.
    if not t_town or not cur_town:
        return MoveVerdict(allowed=True, resolved=resolved, tier="unmapped")

    # ── intra-town: free movement, the node just has to exist.
    if t_town == cur_town:
        town_map = maps.get(t_town)
        if town_map is None or t_node is None:
            return MoveVerdict(allowed=True, resolved=resolved, tier="unmapped")
        nodes = _map_nodes(town_map)
        if t_node in nodes:
            return MoveVerdict(allowed=True, resolved=resolved, tier="intra")
        some = ", ".join(sorted(nodes)[:5])
        return MoveVerdict(
            allowed=False,
            reason=_R(root)["no_node"].format(town=t_town, node=t_node, some=some),
            tier="intra",
        )

    # ── cross-town: one town transition per turn, through gates (ports, 10-05 G1).
    world_map = load_world_map(root)
    cur_map = maps.get(cur_town)
    if cur_map is None:
        # Current place unmapped (a dungeon, the wilds) — can't stage travel beats; stay permissive. A bare town target
        # still lands somewhere real: the node bound to the route in (ports.up), else the town's entry (G1).
        dst_map = maps.get(t_town)
        if t_node is None and dst_map is not None:
            land = _landing(root, t_town, dst_map, _route_between(world_map, cur_town, t_town))
            if land:
                return MoveVerdict(allowed=False, clamped_to=join_location(t_town, land),
                                   reason=_entered(t_town, land, root), tier="cross")
        return MoveVerdict(allowed=True, resolved=resolved, tier="unmapped")

    status, town_path = _world_route(world_map, cur_town, t_town)
    if status == "noroute":
        return MoveVerdict(
            allowed=False,
            reason=_R(root)["no_route"].format(a=cur_town, b=t_town),
            tier="cross",
        )
    # Next town on the itinerary (multi-leg routes advance one town a turn).
    next_town = t_town
    if status == "ok" and len(town_path) > 2:
        next_town = town_path[1]

    leg = _route_between(world_map, cur_town, next_town)  # the world edge this turn's leg walks
    own_gate = _landing(root, cur_town, cur_map, leg)  # leave by the node bound to it (ports.up), else entry / gate
    if own_gate is None:
        # A gateless town can't stage the two-beat travel; don't trap the soul.
        return MoveVerdict(allowed=True, resolved=resolved, tier="cross")

    # One beat walks out through the gate and arrives (niko 10-19: 「重点不是我是否能到北门,而是这中间发生的经过和结果」 —
    # the old first beat stopped the player at their own gate while the prose had them arrive). The road's referee
    # (packs/rpg/travel) still decides whether a journey of days arrives this beat.
    if next_town != t_town:
        # Multi-leg: advance to the next town's gate, journey continues.
        nxt_map = maps.get(next_town)
        nxt_gate = _landing(root, next_town, nxt_map, leg) if nxt_map else None
        landing = join_location(next_town, nxt_gate) if nxt_gate else next_town
        return MoveVerdict(
            allowed=False,
            clamped_to=landing,
            reason=_R(root)["via"].format(town=t_town, next=next_town, landing=landing),
            tier="cross",
        )
    dst_map = maps.get(t_town)
    if dst_map is None:
        return MoveVerdict(allowed=True, resolved=resolved, tier="cross")
    dst_nodes = _map_nodes(dst_map)
    if t_node is not None and t_node in dst_nodes:
        # The transition is the budgeted action; landing anywhere in the
        # target town is fine (intra-town movement is free).
        return MoveVerdict(allowed=True, resolved=resolved, tier="cross")
    dst_gate = _landing(root, t_town, dst_map, leg)  # arrive at the node bound to the route in, else entry / gate
    if dst_gate is None:
        return MoveVerdict(allowed=True, resolved=resolved, tier="cross")
    if t_node is None:
        # Town-level target — land at its gate.
        return MoveVerdict(
            allowed=False,
            clamped_to=join_location(t_town, dst_gate),
            reason=_entered(t_town, dst_gate, root),
            tier="cross",
        )
    some = ", ".join(sorted(dst_nodes)[:5])
    return MoveVerdict(
        allowed=False,
        clamped_to=join_location(t_town, dst_gate),
        reason=(
            _R(root)["no_node_gate"].format(town=t_town, node=t_node, gate=dst_gate, some=some)
        ),
        tier="cross",
    )
