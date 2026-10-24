---
name: casting
description: Cast a reusable soul into a specific world — adapt it into a world-baked NPC (game/npc/<id>.json) with a coherent placement (role, reason, relationships, known lore).
tags: [casting, placement, npc, worldbuilding]
---

> **Spec first.** Before writing, call `read_spec(name="soul")`; it is the authoritative shape of what you write.

# Casting a Soul Into a World

Casting (placement) takes a **reusable, world-agnostic soul** and adapts it
into **this** world as a baked NPC at `game/npc/<id>.json`. The soul says
*who the character is*; casting decides *who they are HERE* — their role in
this world, why they are present, how they relate to the player and the
existing cast, and what of this world they do and do not know.

This is creative adaptation, not a copy. A deterministic fast-path can copy
the soul's content verbatim; your job is the part a copy cannot do.

## Inputs to read first

1. **The soul** — its `soul.md` charter, `persona/` (core_traits,
   motivations, values, relationships), `background/` (origin, history,
   **secrets** — GM-only), and `character/`. If the NPC json already exists
   from a fast-path cast, the full soul is under its `"soul"` key.
2. **The world** — `game/lore/` (story, notes, rumors), `game/world/`
   (map, factions, items), and the existing `game/npc/*.json` cast. Match
   tone, geography, and continuity.

## What to author

Write/update `game/npc/<id>.json`. Preserve the engine-facing fields
(`id`, `kind: "npc"`, `name`, `location`, `state`, `memory`, `inventory`)
and the lossless `"soul"` block. **Fill the `"placement"` overlay** — this
is the whole point of casting:

```json
"placement": {
  "role_in_world": "Who they are in THIS world (job, station, standing).",
  "why_here": "A concrete in-world reason they are present now.",
  "relationship_to_player": "Their stance toward the player on first contact.",
  "current_goal": "What they want right now, in this world's terms.",
  "known_lore": ["World facts this character would plausibly know"],
  "unknown_lore": ["World facts they must NOT know (drives discovery/tension)"],
  "adapted": true
}
```

Also reconcile the carried-over fields to this world:
- **location** — a real place id: a folder under `game/locations/` (a town such as `T001`, or a spot inside it such as `gate_north`).
- **relationships** in `soul.persona.relationships` — keep only what makes
  sense here; re-point or drop references to people not in this world.
- **secrets** — keep the soul's GM-only secrets, and add any world-specific
  secret that this placement creates (the world-agent is the GM and may use
  them; the character never volunteers them).
- **voice / traits** — keep faithful to the soul; do not flatten its voice.

## Principles

- **Faithful, not generic.** The cast NPC must still feel like the soul —
  same voice, same drives — only now anchored in this world.
- **One or two key bindings.** Give a concrete reason-to-be-here and one
  relationship hook (to the player or an existing NPC). Avoid vague "a
  traveler who arrived recently."
- **Respect capacity & continuity.** Fit the existing cast and the world's
  tone; do not contradict established lore. Prefer incremental edits.
- **Set `adapted: true`** only after the placement overlay is genuinely
  authored from this world's context.

## Player avatar (分身) casting

When casting a soul `--as player`, adapt it into `game/player/profile.json`
instead: the player's role, starting goal, and standing in this world. Same
principle — the unified avatar is projected into THIS world's terms — but
the human drives it, so keep `placement` light (role + starting goal +
starting relationships) and never script the player's choices.
