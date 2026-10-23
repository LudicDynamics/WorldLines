"""M18 §3 scene-understanding — the deterministic routing step (M22-extended).

The router half of the file-as-router turn pipeline. Pure code, no LLM. It
runs once at the top of a turn, BEFORE any soul thinks:

1. read every soul's node (``souls/<sid>-<iid>/run_state.json`` location) and
   the player's node (``game/meta/run_state.json`` location.node);
2. decide the LIVE set = souls co-located with the player ∪ souls already
   active (a soul in play keeps living its own scene when it walks away);
3. partition the live set by location (M22 双视角):
   - player's node (or no location on disk) → **primary group**, integrated
     by the primary world-agent;
   - any other node → a **location group**, one per node, capped at
     ``MAX_LOCATION_GROUPS`` — destined for that location's world-agent
     (M22 Phase C); groups beyond the cap are deactivated this turn
     (off-stage memo keeps their memory continuous);
4. write the decision to ``playthrough.json``: ``active_souls`` (who runs)
   AND ``integrations`` (who integrates whom, where) — file-as-router for
   integrators;
5. build each active soul's **perspective ScenePacket** (M22 双视角 feed):
   its OWN location's scene label, its OWN location's last narration, and no
   player-onboarding fields — a soul never receives the player's viewpoint.

``broadcast`` is the execution half: pure code publishing each active soul's
packet to its request topic over the bus.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from neonrp.core import topics
from neonrp.core.player_controller import (
    ScenePacket,
    read_last_narration,
    strip_choice_block,
)
from neonrp.core.playthrough import set_active_souls

# M22 cost ceiling: at most this many away-from-player location groups stay
# live per turn; groups beyond it are deactivated (off-stage memo path).
MAX_LOCATION_GROUPS = 2

PRIMARY_WORLD_AGENT = "world-agent"


@dataclass(frozen=True)
class SceneUnderstanding:
    """The turn's routing decision — the ``playthrough.json`` diff, in memory.

    ``active_iids`` is what runs; ``integrations`` is who integrates whom
    (primary entry first, then location groups); ``reasons`` covers EVERY
    soul so the trace shows why each was or wasn't reached;
    ``per_soul_packets`` carries each active soul's perspective packet.
    """

    player_node: str | None
    active_iids: tuple[str, ...]
    reasons: dict[str, str] = field(default_factory=dict)
    per_soul_packets: dict[str, ScenePacket] = field(default_factory=dict)
    integrations: tuple[dict[str, Any], ...] = ()
    # True when a live soul was kept active away from the player (it lives in
    # a location group rather than the player's scene).
    fallback_used: bool = False
    # Every soul physically NOT at the player's node — (iid, scoped_node).
    # The hard truth the primary world-agent needs in its prompt so it won't
    # let the player pull a far-away soul into the scene by cueing it.
    away_roster: tuple[tuple[str, str], ...] = ()


def scene_state_path(root: Path, node: str) -> Path:
    """场景层状态文件(场景拍写权白名单;原地点裁判遗产)。"""
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in node)
    return root / "game" / "locations" / safe / "scene_state.json"


def understand_scene(
    root: Path, playthrough: Any, scene_packet: ScenePacket
) -> SceneUnderstanding:
    """Decide the active set + integration routing and write the manifest."""
    from neonrp.core.place_nav import qualify_location

    location = scene_packet.location if isinstance(scene_packet.location, dict) else {}
    _player_town = location.get("node_id")
    _player_raw = location.get("node") or location.get("node_id")
    # Resolve to a scoped address ("T###/node" | "T###") so co-location is
    # decided on the full address, not a bare node id that two towns share.
    # The player's own town is the context for a bare node (stay-in-town).
    player_node = (
        qualify_location(
            root,
            str(_player_raw),
            current_town=str(_player_town) if _player_town else None,
        )
        or None
    ) if _player_raw else None

    prior_active = set(playthrough.active_souls)
    reasons: dict[str, str] = {}
    primary: list[str] = []
    loc_groups: dict[str, list[str]] = {}  # node -> [iid...] (insertion order)
    away: list[tuple[str, str]] = []  # (iid, node) for every soul NOT at player_node

    for soul in playthrough.souls:
        iid = soul.instance_id
        # Scoped address: a soul that already moved carries its town
        # ("T004/guild"); a legacy bare id falls back to first-match. Either
        # way co-location is now an exact address comparison, not a guess.
        node = qualify_location(root, _soul_node(root, soul)) or None
        # Physical truth for the world-agent: any soul with a known node that
        # isn't the player's is NOT here — regardless of active/inactive.
        if node is not None and node != player_node:
            away.append((iid, node))
        live = (player_node is not None and node == player_node) or iid in prior_active
        if not live:
            reasons[iid] = (
                f"inactive · elsewhere ('{node}', player at '{player_node}')"
                if node
                else "inactive · no location on disk"
            )
            continue
        if node is None or (player_node is not None and node == player_node):
            primary.append(iid)
            reasons[iid] = (
                f"active · co-located at '{player_node}'"
                if node
                else "active · no location on disk (kept with player)"
            )
        else:
            loc_groups.setdefault(node, []).append(iid)

    # Cap the location groups (cost ceiling); overflow groups go off-stage.
    kept_groups = list(loc_groups.items())[:MAX_LOCATION_GROUPS]
    dropped_groups = list(loc_groups.items())[MAX_LOCATION_GROUPS:]
    for node, iids in kept_groups:
        for iid in iids:
            reasons[iid] = f"active · location group '{node}' (away from player)"
    for node, iids in dropped_groups:
        for iid in iids:
            reasons[iid] = (
                f"inactive · beyond location-group cap ({MAX_LOCATION_GROUPS}) at '{node}'"
            )

    active_iids = tuple(primary) + tuple(
        iid for _node, iids in kept_groups for iid in iids
    )

    integrations: list[dict[str, Any]] = [
        {
            "world_agent": PRIMARY_WORLD_AGENT,
            "location": player_node or "",
            "souls": list(primary),
        }
    ]
    for node, iids in kept_groups:
        integrations.append(
            {"world_agent": f"loc:{node}", "location": node, "souls": list(iids)}
        )

    # File-as-router: the routing decision lands in playthrough.json here.
    set_active_souls(root, list(active_iids), integrations=integrations)

    # M22 双视角 feed: every active soul gets ITS OWN perspective packet.
    per_soul_packets: dict[str, ScenePacket] = {}
    primary_packet = _soul_packet(scene_packet, node=player_node, root=root)
    for iid in primary:
        per_soul_packets[iid] = primary_packet
    for node, iids in kept_groups:
        loc_packet = _soul_packet(scene_packet, node=node, root=root)
        for iid in iids:
            per_soul_packets[iid] = loc_packet

    return SceneUnderstanding(
        player_node=player_node,
        active_iids=active_iids,
        reasons=reasons,
        per_soul_packets=per_soul_packets,
        integrations=tuple(integrations),
        fallback_used=bool(kept_groups),
        away_roster=tuple(away),
    )


def broadcast(bus: Any, understanding: SceneUnderstanding, root: Path | None = None) -> None:
    """Publish each active soul's ScenePacket to ``soul/<iid>/request``.

    Pure code, no LLM — the execution half of file-as-router. The bus records
    the publishes, so the routing decision (and each soul's exact perception)
    is captured in the turn trace.

    T2c(M24 双写过渡):给了 ``root`` 时,同一感知包**同时投进该 soul 的
    文件收件箱**(kind=perception)——通信面统一到 mailbox(落盘=trace),
    消费侧优先 drain 收件箱、异常回退内存包,行为等价。
    """
    for iid in understanding.active_iids:
        packet = understanding.per_soul_packets.get(iid)
        if packet is None:
            continue
        payload: dict[str, Any] = {"instance_id": iid, **asdict(packet)}
        bus.publish(topics.soul_request(iid), payload)
        if root is not None:
            try:
                from neonrp.core.inbox import InboxMessage, send

                send(
                    root,
                    InboxMessage.new(
                        "perception", "scene-understanding", iid, {"packet": asdict(packet)}
                    ),
                )
            except Exception:  # noqa: BLE001 — 投递面故障不阻塞回合
                logging.getLogger("neonrp.scene_understanding").debug(
                    "perception inbox dual-write failed", exc_info=True
                )


def _soul_packet(base: ScenePacket, *, node: str | None, root: Path) -> ScenePacket:
    """Derive a soul-perspective packet from the player-centric base.

    - the scene is the SOUL's location (label rebuilt for away groups);
    - ``last_narration`` is that location's narration (player-scene narration
      never leaks into an away soul's feed — and vice versa later);
    - player-onboarding fields (player_summary, startup opening/choices) are
      stripped: a soul perceives the scene, not the player's character sheet.
    """
    from neonrp.core.place_nav import qualify_location, split_location, town_node_view

    time = base.time if isinstance(base.time, dict) else {}
    day = time.get("day") or time.get("cycle_day") or "?"
    clock = time.get("clock") or time.get("period") or "?"
    # `node` arrives already scoped (the router qualified it). Compare against
    # the player's scoped address so same-scene is an exact address match.
    _base_player = qualify_location(
        root,
        (base.location or {}).get("node") or (base.location or {}).get("node_id"),
        current_town=(base.location or {}).get("node_id"),
    ) or None
    same_scene = node is None or _base_player == node

    # Surgical nav feed: resolve this soul's node on the canonical town_map so
    # its perception lists the real adjacent nodes it may move to. A scoped
    # address pins the exact town (no guessing); split it into (town, node) and
    # let town_node_view confirm — wilderness nodes resolve to None (graceful).
    _loc_town, _loc_node = split_location(node if not same_scene else (base.location or {}).get("node"))
    _prefer_town = _loc_town or (base.location or {}).get("node_id")
    _view = town_node_view(root, _loc_node, prefer_town=_prefer_town)
    _place_name = _view["name"] if _view else ""
    _exits = list(_view["exits"]) if _view else []

    if same_scene:
        scene_label = base.scene_label
        location = dict(base.location)
    else:
        # Show the friendly place name (else the scoped id) — never raw "T004/".
        scene_label = f"{_place_name or node} · 第{day}日·{clock}"
        location = {"node": node, "node_id": _loc_town} if _loc_town else {"node": node}

    return replace(
        base,
        scene_label=scene_label,
        location=location,
        place_name=_place_name,
        exits=_exits,
        player_summary="",
        startup_opening="",
        startup_choices=[],
        # P2: only a CO-LOCATED soul (same scene as the player) perceives the
        # player's declared action this turn; an away soul never sees it.
        player_declared_action=base.player_declared_action if same_scene else "",
        # An away soul must NOT receive the player-scene narration (legacy
        # untagged records count as player-scene), hence accept_untagged only
        # for the player's own scene. The player's choice menu is stripped so
        # it never pollutes an autonomous soul's context.
        last_narration=strip_choice_block(
            read_last_narration(
                root, location_node=node, accept_untagged=same_scene
            )
        ),
    )


def _soul_node(root: Path, soul: Any) -> str | None:
    """Read a soul's current node from its ``run_state.json`` (a string node)."""
    state = _read_json(root / "souls" / f"{soul.sid}-{soul.instance_id}" / "run_state.json")
    if not isinstance(state, dict):
        return None
    loc = state.get("location")
    return str(loc) if isinstance(loc, str) and loc else None


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
