"""M18 Phase 2 — the topic vocabulary.

The transport-agnostic topic namespace agents and observers publish/
subscribe on (M18 §2.1). Topic *strings* are built only here so the
namespace has one source of truth; everything else imports these builders.

Namespace
---------
    world/scene             world-agent -> souls: the scene to perceive
    world/narration         world-agent -> player-agents: raw narrative
    world/state             world state-change events (observers)
    soul/<iid>/request      world -> one soul: its per-turn ScenePacket
    soul/<iid>/response     one soul -> world: its SoulTurnReport
    player/<pid>/cmd        frontend -> engine: a human's raw input
    player/<pid>/output     player-agent -> frontend: render directives
    engine/event            the lifecycle / orchestration trace stream
    engine/beat             node.enter/leave · plan.beat · resolve.beat · dice · tool · state.changed · run.settled

A soul is addressed by its ``instance_id`` alone — the iid is globally
unique, so the soul ``sid`` would only be redundant in the topic (it still
travels in the message *payload* for display). The ``+`` / ``#`` wildcards
(see message_bus.topic_matches) let the world-agent subscribe to
``soul/+/response`` and an observer to ``engine/#``.
"""

from __future__ import annotations

# ---- static topics -------------------------------------------------------
WORLD_SCENE = "world/scene"
WORLD_NARRATION = "world/narration"
WORLD_STATE = "world/state"
WORLD_INTEGRATE = "world/integrate"  # trigger: world-agent(s) integrate soul reports
ENGINE_EVENT = "engine/event"
ENGINE_STREAM = "engine/stream"  # token-volume deltas: dispatched, never recorded
ENGINE_BEAT = "engine/beat"  # contract 1.0 beat events (core/beat_events) per beat as it lands — derived from the trace, never recorded

# ---- wildcard patterns (for subscribers) ---------------------------------
ALL_SOUL_RESPONSES = "soul/+/response"
ALL_SOUL_REQUESTS = "soul/+/request"
ALL_PLAYER_CMDS = "player/+/cmd"
ALL_WORLD_NARRATIONS = "world/narration"  # future: "world/+/narration" when multi-world
ALL_ENGINE = "engine/#"


# ---- per-entity topic builders ------------------------------------------
def soul_request(instance_id: str) -> str:
    """Topic the world-agent publishes a soul's per-turn ScenePacket on."""
    return f"soul/{instance_id}/request"


def soul_response(instance_id: str) -> str:
    """Topic a soul publishes its SoulTurnReport on."""
    return f"soul/{instance_id}/response"


def player_cmd(pid: str) -> str:
    """Topic a frontend publishes a human's raw input on."""
    return f"player/{pid}/cmd"


def player_output(pid: str) -> str:
    """Topic a player-agent publishes render directives on."""
    return f"player/{pid}/output"
