---
name: world-building
description: World entity structure, map coherence, and NPC design guidance.
---

> **Spec first.** Before writing, call `read_spec(name="world")` and `read_spec(name="ops", pack=…)` for the ops the world's play pack allows; it is the authoritative shape of what you write.

# Entity Conventions

- Store entities under the world's `game/` folder: places as folders `game/locations/<T>/<spot>/location.json`, towns in `game/towns/<T>/`, items in `game/item/**/<id>.json` (full layout: `read_spec(name="world")`).
- Keep `id`, `kind`, and `name` consistent.
- Use stable IDs; avoid rewriting IDs unless required.

# Map Coherence

- Ensure location connections are bidirectional where expected.
- Keep travel descriptions aligned with location metadata.
- Introduce new locations with at least one meaningful hook.

# NPC Design

- Give each NPC a concrete role and motivation.
- Track relation to player/world factions.
- Keep dialogue style consistent with setting tone.

# Continuity

- Prefer incremental edits over large rewrites.
- Preserve established facts unless explicitly retconned.
