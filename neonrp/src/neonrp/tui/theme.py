"""Shared theme tokens for the NeonRP TUI.

The play surface uses the WorldLines green family — same green the
launcher splash and the matrix-silhouette renderer use — so the whole
terminal experience reads as one coherent art style. Agents are kept
distinguishable by varying the green hue/luminance rather than jumping
to unrelated colors; the one deliberate exception is the structural
amber for rules/dice/referee agents, which are mechanics (not
narrative) and should read as a separate lane.

    WORLD    #18FF82   bright green   — narrator / world agents
    SOUL     #5BE0B0   mint           — character / NPC agents
    ACCENT   #3FB36A   deep green     — orchestrator / system
    COMMAND  #27C93F   command green  — command surface / kicker
    REFEREE  #E8A33D   amber          — rules / dice / referee lane

``agent_accent`` resolves a stable hex color for an agent. Authors can
override per agent by setting ``presentation_color`` in agent.json;
otherwise the kind/id heuristic below applies, and as a last resort the
id hashes into the palette so two unknown agents never collide silently.
"""

from __future__ import annotations

import json
from pathlib import Path

# WorldLines green accent tokens.
ACCENT = "#3FB36A"        # orchestrator / system
SOUL = "#5BE0B0"          # character / NPC
WORLD = "#18FF82"         # narrator / world
COMMAND = "#27C93F"       # command surface
REFEREE = "#E8A33D"       # rules / dice / referee (structural lane)

# Neutral text ramp.
TEXT_PRIMARY = "#E4E4E7"
TEXT_DIM = "#7f9a86"
DIVIDER = "#1f3a29"

# Deterministic fallback palette — used only when an agent matches no
# heuristic. All green-family, ordered for good adjacent contrast.
_FALLBACK_PALETTE = (
    "#4ADE80",  # spring green
    "#9BE89B",  # sage
    "#5BD9C0",  # seafoam
    "#7BE05B",  # lime
    "#34D399",  # emerald
    "#A8E063",  # chartreuse
)

# Keyword → accent. Checked against the lowercased agent id; first hit
# wins, so order matters (more specific terms first).
_KIND_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("combat", "referee", "dice", "rule", "san", "sanity", "check"), REFEREE),
    (("orchestrator", "router", "system", "meta"), ACCENT),
    (("narrator", "world", "scene", "event", "gm"), WORLD),
    (("character", "npc", "soul", "actor", "companion"), SOUL),
)


def _hash_pick(key: str) -> str:
    """Stable index into the fallback palette for an arbitrary key."""
    h = 0
    for ch in key:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return _FALLBACK_PALETTE[h % len(_FALLBACK_PALETTE)]


def agent_accent(root: Path | None, agent_id: str | None) -> str:
    """Resolve a stable hex accent color for ``agent_id``.

    Resolution order:
      1. ``presentation_color`` field in ``agents/<id>/agent.json``
      2. keyword heuristic on the (lowercased) agent id
      3. deterministic hash into the fallback palette
    """
    raw = str(agent_id or "").strip()
    if not raw:
        return WORLD  # bare "Narrator" with no id → world lane

    if root is not None:
        agent_json = Path(root) / "agents" / raw / "agent.json"
        if agent_json.is_file():
            try:
                payload = json.loads(agent_json.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    explicit = str(payload.get("presentation_color") or "").strip()
                    if explicit.startswith("#") and len(explicit) in (4, 7):
                        return explicit
            except Exception:
                pass

    lowered = raw.lower()
    for keywords, color in _KIND_RULES:
        if any(kw in lowered for kw in keywords):
            return color

    return _hash_pick(lowered)
