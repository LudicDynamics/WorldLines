---
title: "Characters & Multi-Agent"
description: "A world runs one of two ways: an orchestrator World-Agent with sub-agents (town / dungeon / npc), or the multi-agent village where each character is its own Character-Agent — a first-class identity with its own soul, memory, voice, and sub-agents. Both ship today."
---

<!-- section: today -->
## Today — World-Agent + sub-agents

In v0.1, every entity in the world is reached through a single top-level **World-Agent** (the orchestrator / narrator). The World-Agent delegates via `task()` to its **sub-agents**:

| Sub-agent under World-Agent | Responsibility                                               |
|-----------------------------|--------------------------------------------------------------|
| **Town sub-agent**          | Places, merchants-at-large, events inside a town             |
| **Dungeon sub-agent**       | Geography, traps, encounter pacing inside a dungeon          |
| **NPC sub-agent**           | Individual NPC dialogue and reactions (shared pool today)    |

This works — but every NPC shares one narrative lens (the World-Agent's system prompt), and their "personhood" is reconstructed each turn from static character JSON.

<!-- section: character-agent -->
## Character-Agent — a parallel branch ✅

> **Shipped in v0.2.3 (local)** — this is the multi-agent village. See [Multi-Agent Mode](/docs/core-concepts/engine-modes#multi-agent).

World-Agent and each character (a **soul-agent**) are independent agents that talk over a shared **message bus** — the narrator never puppets the characters:

```
   world-agent  ◄─────►┌────────────────┐◄─────►  soul-agents
   (host /             │  message bus   │         ┌─ Elena  (soul.md · memory · voice · subs)
    narrator)          └────────────────┘         ├─ Rowan  (its own mind)
                                                   └─ …

   The world-agent posts the scene to the bus; the souls present this turn
   each read it, decide their own speech / action / inner voice, and post
   back; the world-agent weaves the replies into a single narration.
```

Each soul owns:

- **`soul.md`** — an identity document. Core values, history, relationships, scars. Written once, updated on big story moments.
- **Long-term memory** — lived experience across sessions. Condensed, searchable, survives snapshot/load.
- **Short-term memory** — the current scene context. Decays / compacts as the scene shifts.
- **Personality** — structured traits (big-five, custom axes, whatever the author wants).
- **Narrative style** — her voice as a prompt fragment. Consistent across turns; even when the World-Agent narrates around her, her direct speech stays in-character.
- **Custom sub-agents** — authors can give a character her own delegates (Elena might have an `innkeeper` skill sub-agent for menu pricing, a `confidante` one for heart-to-heart moments). Composable per-character, not forced through the shared NPC pool.

<!-- section: why-parallel -->
## Why parallel, not nested

Putting Character-Agent **next to** World-Agent (rather than under it) matters because:

- A character's identity shouldn't be a branch of world logic. Elena should stay Elena when the scene moves to a new town.
- Memory scopes differ: World-Agent remembers world events; Character-Agent remembers *her* events.
- Voice survives a scene change — the same character Agent speaks whether she's in a tavern (town sub-agent) or fleeing through a dungeon (dungeon sub-agent).
- Custom sub-agents per character scale better than piling them into the shared NPC pool.

This is exactly what **Multi-Agent mode — the village** (✅ shipped v0.2.3, see [Router Modes](/docs/core-concepts/engine-modes#multi-agent)) carries: each character is its own agent that holds the pen across turns and keeps its own memory, instead of being re-voiced from scratch by the narrator each time.

<!-- section: bridge -->
## Orchestrator or village — both ship today

**Orchestrator worlds** (like `stoneford`) keep NPCs as data in `game/npc/` and voice them through the World-Agent's shared sub-agent pool. Simple, cheap, great for rule-heavy play.

**Village worlds** (like `kagura-island` and `stoneford-elena`) give each character its own Character-Agent: promote an NPC to a soul folder under `souls/` + a `playthrough.json`, and it thinks for itself across turns. See [Multi-Agent Mode](/docs/core-concepts/engine-modes#multi-agent).

See [Agents & Orchestration](/docs/core-concepts/agents-orchestration) for the underlying agent anatomy and [Building Character Agents](/docs/guides/building-character-agents) for the authoring flow.
