---
title: "World Protocol"
description: "The shape of a distributable WorldLines world. What goes into the zip uploaded to WorldHub, and how a downloader rehydrates it into a runnable game directory."
---

<!-- section: what-is-a-world -->
## What a world is

A *world* is the setting: regions, towns, NPCs, factions, quests, spatial maps, lore, rules. It does **not** include the player or the agents that play it — those are separate protocols ([Soul](/docs/protocol/soul) and [Agent](/docs/protocol/agent)). A world plus a soul plus an agent set is a *runnable session*.

Every world has a stable identifier — `wid` — that's the slug under WorldHub and the key users pin saves and hashes against.

<!-- section: bundle-layout -->
## Bundle layout — game/

A world bundle is a `game/` directory. Creator-authored, versioned by the world author, distributed via WorldHub. This is the canonical on-disk shape (see [Folders & Versioning](/docs/protocol/folders) for the full contract):

```
game/
├── agents/                 ← the world's agent roster (creator-versioned)
│   ├── manifest.json       ← which sub-agents this world ships
│   └── contracts/          ← per-agent IO contracts
├── meta/
│   ├── run_state.json      ← live position / time / turn_count
│   ├── active-agent.json   ← which sub-agent holds the write lock
│   ├── game-start.json     ← opening scene / handoff
│   ├── flag_aliases.json   ← readable names for story flags
│   └── schedule.json       ← timed / scheduled world events
├── lore/
│   ├── story.md            ← main storyline (append-only narrative)
│   └── notes.md            ← rumours / world observations
├── world/
│   ├── world_map.json      ← node graph (REQUIRED)
│   ├── regions.json
│   └── factions.json
├── towns/<Txxx>/           ← town location nodes
├── dungeons/<Dxxx>/        ← dungeon location nodes
├── rules/                  ← rule schema (dice, checks, combat)
└── player/                 ← legacy player state — superseded by a soul
```

The zip uploaded to `s3://worldlines-hub/worlds/<hash>.zip` **is** this `game/` folder, gzipped. `game/agents/manifest.json` is the creator-versioned template for the world's sub-agent team; at playthrough creation it is seeded into `playthrough.json` (the running engine reads that, never the bundle manifest directly). `game/player/` is the pre-M16 single-player model, kept only as a staged compatibility surface — the long-term ontology is that the player avatar is a soul instance.

<!-- section: schemas -->
## What lives where

| Area | Path | Form |
|---|---|---|
| Agent roster | `game/agents/manifest.json` | JSON — creator-versioned template |
| Live run state | `game/meta/run_state.json` | JSON — per playthrough |
| Opening scene | `game/meta/game-start.json` | JSON |
| Storyline | `game/lore/story.md` | **Markdown** — append-only narrative |
| Rumours | `game/lore/notes.md` | **Markdown** |
| Navigation | `game/world/world_map.json` | JSON — node graph |
| Regions / factions | `game/world/{regions,factions}.json` | JSON |
| Locations | `game/towns/<Txxx>/` · `game/dungeons/<Dxxx>/` | JSON per node |
| Rules | `game/rules/` | JSON — dice / checks / combat |

The world↔soul binding and the live agent team are authoritative only in the session-layer `playthrough.json` (see [Folders & Versioning](/docs/protocol/folders)).

<!-- section: authoring-rules -->
## Authoring rules of thumb

- **`wid` is forever.** Renames break links.
- **Narrative lore is Markdown.** `lore/story.md` and `lore/notes.md` are append-only Markdown — the storyline grows during play. Structured world data (`world_map.json`, `regions.json`, `factions.json`, location nodes) stays JSON so agents can quote, mutate, and search it.
- **Locations are node folders.** `towns/<Txxx>/` and `dungeons/<Dxxx>/` — one folder per node, not one flat file per entity.
- **Don't ship a playthrough with a template.** Template worlds carry no live `meta/run_state.json` history — only saved-game exports do.
- **The agent roster is creator-versioned.** It ships in the bundle as a template and is seeded into `playthrough.json` at fork; runtime never reads the bundle manifest directly.

<!-- section: distribution -->
## Distribution

```
neonrp world upload examples/orch/dark-train --slug dark-train --version 2.0
# → s3://worldlines-hub/worlds/<hash>.zip + worlds/index.json entry
neonrp world download dark-train
# → ~/.worldlines/games/dark-train-<world_instance_id>/  → playable
```

Browse what's already published at [hub.worldlines.gg/worlds](https://hub.worldlines.gg/worlds). Full address-model details at the [WorldHub spec on GitHub](https://github.com/LudicDynamics).

<!-- section: see-also -->
## See also

- [Soul Protocol](/docs/protocol/soul) — what plays the world
- [Agent Protocol](/docs/protocol/agent) — how the world's agent set drives play
- Canonical spec on GitHub: [WORLD-PROTOCOL.md](https://github.com/LudicDynamics)
