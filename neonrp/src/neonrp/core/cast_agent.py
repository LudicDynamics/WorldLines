"""Agentic casting — run the `casting` skill to adapt a placed NPC.

The deterministic fast-path (``placement.project_soul_as_npc``) copies a
soul into ``game/npc/<id>.json`` losslessly but leaves the ``placement``
overlay blank (``adapted: false``). This module runs ONE build-mode agent
turn that reads the world's lore + existing cast and authors that overlay —
the character's role in THIS world, why they're here, their relationship to
the player, current goal, and which lore they do/don't know — then fixes the
NPC's ``location`` to a real node and sets ``placement.adapted = true``.

Build mode is used because it can write anywhere (see conversation.py:
"Build mode can write anywhere"), so the authoring agent can rewrite
``game/npc/<id>.json`` regardless of play-mode write permissions.

Best-effort and opt-in: a failure leaves the faithful fast-path NPC intact.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


_PROMPT = """\
Use the `casting` skill. A soul was just placed into this world as a baked
NPC at `game/npc/{npc_id}.json` by a deterministic copy — its `placement`
overlay is still blank (`adapted: false`) and its `location` may be a
placeholder.

Your task — ADAPT this character into THIS world (do not invent a new one):

1. Read `game/lore/` (story, notes, rumors), `game/world/` (map, factions),
   and the existing `game/npc/*.json` cast for tone + continuity.
2. Read `game/npc/{npc_id}.json` — especially its embedded `soul` block
   (charter, persona, background incl. GM-only secrets). Keep the character
   faithful to that soul; do not flatten its voice.
3. Rewrite `game/npc/{npc_id}.json`, keeping every existing field
   (`id`, `kind`, `name`, `soul`, `source_soul`, engine fields) AND filling
   the `placement` object:
     - role_in_world: who they are in THIS world
     - why_here: a concrete in-world reason they are present now
     - relationship_to_player: their stance on first contact
     - current_goal: what they want now, in this world's terms
     - known_lore: world facts they would plausibly know
     - unknown_lore: world facts they must NOT know (drives tension)
     - adapted: true
4. Set `location` to a REAL node from the world map (not a placeholder).

Write the file with the `write_file` tool. Keep it valid JSON.
"""


def adapt_npc_with_agent(root: Path, npc_id: str, *, provider: str | None = None) -> bool:
    """Run the casting skill (build mode) to author the NPC's placement.

    Returns ``True`` if ``game/npc/<npc_id>.json`` ends up with
    ``placement.adapted == true``; ``False`` on any failure (the fast-path
    NPC is left untouched and remains playable).
    """
    npc_path = root / "game" / "npc" / f"{npc_id}.json"
    if not npc_path.exists():
        logger.debug("adapt_npc_with_agent: %s missing", npc_path)
        return False

    try:
        from neonrp.core.conversation import ConversationSession
        from neonrp.core.runtime_contract import resolve_router_agent_id

        agent_id = resolve_router_agent_id(root)
        conv = ConversationSession(
            root=root, agent_id=agent_id, mode="build", provider=provider
        )
        conv.send(_PROMPT.format(npc_id=npc_id))
    except Exception:
        logger.debug("adapt_npc_with_agent: build turn failed", exc_info=True)
        return False

    try:
        data = json.loads(npc_path.read_text(encoding="utf-8"))
        return bool(data.get("placement", {}).get("adapted"))
    except (OSError, ValueError):
        return False


_PREVIEW_PROMPT = """\
You adapt a reusable character (soul) into a specific world — a placement
preview. Output STRICT JSON only, no prose.

WORLD LORE:
{lore}

CHARACTER (soul):
{soul}

Output what this character BECOMES in THIS world as JSON:
{{"role_in_world": "...", "why_here": "...",
  "relationship_to_player": "...", "current_goal": "..."}}
Keep the character faithful to its soul; ground each field in the world's lore.
Each value 1-2 sentences, in the character's source language.
"""


def preview_placement(soul_dir: Path, world_id: str) -> dict | None:
    """One-shot LLM preview: what a soul BECOMES when adapted into a world.

    Reads the world TEMPLATE's lore directly (no scaffold, no game folder)
    and the soul's own profile, then makes a single LLM call returning the
    placement overlay (role_in_world / why_here / relationship_to_player /
    current_goal). Returns the dict, or None on any failure. Blocking — call
    from a worker thread in the TUI.
    """
    try:
        import importlib.resources as _res
        import re

        from neonrp.worlds import get_world
        from neonrp.core.config import load_config, resolve_provider
        from neonrp.core.llm import Message, get_adapter_from_config
        from neonrp.core.placement import _soul_profile

        world = get_world(world_id)
        template = (world or {}).get("template") or world_id
        tpl_root = Path(str(_res.files("neonrp") / "templates" / template))

        lore_parts: list[str] = []
        for sub in ("game/lore", "game/world"):
            d = tpl_root / sub
            if d.is_dir():
                for f in sorted(d.glob("*")):
                    if f.is_file() and f.suffix in (".md", ".json"):
                        try:
                            lore_parts.append(f.read_text(encoding="utf-8")[:1500])
                        except OSError:
                            pass
        lore = ("\n\n".join(lore_parts))[:6000] or "(no lore authored)"

        prof = _soul_profile(soul_dir)
        soul_txt = (
            f"name: {prof['name']}\nsummary: {prof['summary']}\n"
            f"voice: {prof['voice']}\ntraits: {prof['traits']}"
        )

        config = load_config(tpl_root)  # default policy: user config in play, never under pytest (10-02: stub e2e was calling the real provider)
        provider_config = resolve_provider(config, None, None)
        adapter = get_adapter_from_config(provider_config)
        res = adapter.chat(
            [Message(role="user", content=_PREVIEW_PROMPT.format(lore=lore, soul=soul_txt))]
        )
        msg = getattr(res, "message", None)
        text = getattr(msg, "content", None) or (msg if isinstance(msg, str) else "") or ""
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else None
    except Exception:
        logger.debug("preview_placement failed", exc_info=True)
        return None
