---
name: world-game-authoring
description: Build or extend a playable NeonRP `game/` world folder using the neonrp agent toolchain — towns, locations, NPCs, items, quests, factions, lore prose, and meta entities. Use when the user asks the agent to create a new world, expand an existing setting, or flesh out a region directly inside the project (NOT when importing a tavern card, and NOT when authoring a tavern-style world book).
---

> **Spec first.** Before writing, call `read_spec(name="world")` and `read_spec(name="ops", pack=…)` for the ops the world's play pack allows; it is the authoritative shape of what you write.

# NeonRP World / Game Folder Authoring

Use this skill whenever the agent itself is expected to create or expand
the world that lives under `game/` (and its supporting `world/*`, `lore/*`,
`rules/*` companions). This is the engine-native counterpart of
`world-card-authoring`:

- `world-card-authoring` → SillyTavern-format JSON cards for sharing
- `world-game-authoring` → actual NeonRP entities the runtime loads
- `tavern-game-import`   → convert a tavern card INTO a `game/` slice

If the user asks "build me a world", use this skill unless they explicitly
want a tavern card.

# Target Paths Under `game/`

Prefer existing kinds already used by the project. A fully fleshed world
usually touches these directories:

- `game/meta/` — runtime scaffolding
  - `game-start.json` — entry point and opening brief
  - `active-agent.json` — router state (usually left to `ensure_playable_scaffold`)
  - `run_state.json` — transient state (do not invent unless needed)
- `game/world/` — cosmology, timelines, factions metadata
  - `species.md`, `factions.json`, `calendar.json`, `cosmology.md`
- `game/lore/` — narrative prose
  - `story.md` (main plot), `notes.md` (creator notes), `legends.md`
- `game/towns/<town_id>/` — hub package
  - `town_map.json` — location topology
  - `npcs.json` — town roster
  - `quests.json` — local quest list
- `game/location/<id>.json` — single location entity
- `game/dungeon/<id>.json` — explorable hostile area
- `game/npc/<id>.json` — named NPC entity
- `game/character/<id>.json` — protagonist-candidate or major recurring
- `game/item/<id>.json` — gear, consumables, artifacts
- `game/quest/<id>.json` — top-level arcs

Do NOT invent parallel directories when an existing one fits.

# Required Workflow

1. Read the runtime contract first (`.neonrp/runtime_contract.json`).
2. Read current `game/meta/game-start.json` if present.
3. Read `rules/game_entity.schema.json` (or `.neonrp/schema/*`) to know
   the mandatory fields.
4. Call `list_entities` to see what already exists — never duplicate ids.
5. Draft a short plan in plain language before touching files (only when
   scope is large).
6. Author entities with `submit_proposal` in sandbox mode, or direct
   write/edit tools in build mode.
7. Keep ids stable; never rename on subsequent edits.
8. Finish with `ensure_playable_scaffold(...)` so `active-agent.json`
   stays canonical.

# Entity Field Conventions

Every JSON entity under `game/` must include:

- `id` — ASCII slug, must match filename stem
- `kind` — matches parent folder name
- `name` — display name, may be Chinese/Japanese/Korean
- `summary` — 1-2 sentence description for search and context

Recommended optional fields:

- `tags` — short discovery tags
- `location` — id of containing location / town (for npcs, items-on-ground)
- `faction` — faction id (for npcs, locations with ownership)
- `connections` — list of location ids (for location / town)
- `hooks` — list of quest ids / plot hooks
- `lore_refs` — list of `game/lore/*.md` file paths

# Characters as Multi-Agent Souls

NeonRP worlds are multi-agent: each character is authored as a SOUL folder,
not as a flat `game/npc/<id>.json`. Author `>=3` characters this way so the
world is playable as a multi-agent cast.

- A soul lives at `souls/<sid>-si<sid>0001/`, where `<sid>` is a short
  lowercase ASCII slug of the character's name (e.g. `elena` →
  `souls/elena-sielena0001/`). The instance suffix is literally
  `si<sid>0001`.
- `souls/<sid>-si<sid>0001/soul.json` — object:
  `{"schema_version":1,"sid":"<sid>","name":"<English name>",`
  `"name_local":"<native name>","version":"1.0","tags":["npc"]}`
  (optional `intro_i18n`).
- `souls/<sid>-si<sid>0001/soul.md` — the heart of the soul: prose persona
  covering who they are, voice, personality, what they want, their
  relationship to the player, and secrets. Make it specific and grounded in
  THIS world's concept, never generic fantasy.
- Optional but encouraged: `background/history.md`, `background/secrets.md`,
  and `persona/core_traits.json` (`{"traits":{"brave":0.8,...}}`).
- Do NOT author `run_state.json` — the deterministic finalizer adds a valid
  one for each soul.

# Minimum Playable Slice (First Pass)

When the user says "create a world around this idea":

1. One `game/meta/game-start.json` with an opening paragraph + starting
   location id + player role note.
2. One starting hub: `game/towns/<id>/town_map.json` + `npcs.json`
   (2-5 NPCs) + `quests.json` (1 starter quest).
3. One adjacent location or dungeon for exploration pressure.
4. One main-plot hook written as `game/lore/story.md`.
5. One brief creator notes file at `game/lore/notes.md`.
6. Optional: `game/world/factions.json` if the setting has factions.

Do not attempt to flesh out every corner in the first pass — the slice
must be playable, not complete.

# Cross-Referencing Rules

- Every id referenced in connections / hooks / faction / location MUST
  point to an entity the index can find.
- When you add a new NPC who lives somewhere, update that town's
  `npcs.json` array too.
- When you add a new location to a town's `town_map.json.locations`,
  write the corresponding `game/location/<id>.json` (unless the town's
  map already defines inline location objects).
- Quests listed in `game/towns/*/quests.json` should reference real
  NPCs, items, and locations.

# Secrets Partition (game/secrets/)

Secrets must NOT live inside entity files — anything written in an entity's
`summary`/`content` is visible to every agent that reads it, which spoils the
mystery before play reveals it. Author the PUBLIC face in the entity, and put
the hidden truth in a `game/secrets/<kind>--<id>.json` overlay:

```jsonc
// game/secrets/location--cellar.json
{
  "id": "secret-location--cellar",
  "kind": "secret",
  "about": "location/cellar",                  // host entity, relpath under game/
  "audience": ["gm"],                          // gm | npc:<id> | soul:<sid> | agent:<id>
  "content": {
    "summary_hidden": "暗门后是走私者的地下码头。",  // *_hidden merges into the base field on reveal
    "connections_hidden": ["smuggler-dock"]
  },
  "revealed_when": [
    { "trust_gte": { "npc": "innkeeper", "value": 60 } },   // machine-checked each turn
    { "judgment": "玩家认真搜查地窖" }                        // fuzzy — the keeper adjudicates
  ]
}
```

Rules:
- Entity files carry a public description that does not spoil and does not lie.
- Hidden connections go in `connections_hidden` — an unrevealed passage does
  not exist on the map, so it cannot be walked through.
- An NPC's own secret gets `audience: ["gm", "npc:<id>"]` (the character must
  know it to play it); secrets about agentless characters are `["gm"]`.
- Director notes (what a character does NOT know) are secrets too — a
  `does_not_know` list is a catalogue of the world's mysteries.
- The engine reveals a secret by merging `*_hidden` into the host entity and
  recording it in `game/meta/secret_ledger.json`. Never duplicate hidden text
  anywhere else.

# Lore Prose Rules

`game/lore/*.md` files should be readable by humans and by the agent:

- Use section headers (`## Factions`, `## Timeline`, `## Legends`).
- Keep paragraphs under ~150 words.
- Avoid duplicating structured facts that live in JSON entities — prefer
  summarizing and pointing at them.
- Use the world's in-setting language for flavor text, but keep meta
  notes (tone guidance, unresolved hooks) in plain author voice.

# Language Handling

- Keep `name`, `summary`, and prose lore in the setting's native
  language (zh / ja / ko / en).
- Keep ids ASCII-only — derive via pinyin / romaji / hangul→latin /
  semantic slug, never via raw CJK.
- Do not transliterate inside `name` / `summary` / lore.

# Do Not

- Do not invent new top-level folders unless the runtime contract
  explicitly allows them.
- Do not put gameplay state (HP, gold, inventory) into world entities —
  that belongs in `player/` or `run_state.json`.
- Do not leave dangling references when an id is renamed — update every
  occurrence.
- Do not overwrite `active-agent.json` manually; use
  `ensure_playable_scaffold(...)`.
- Do not author characters as flat `game/npc/<id>.json` when creating a
  world — author them as souls under `souls/<sid>-si<sid>0001/` instead.
- Do not exceed ~80KB per JSON entity — split into related entities
  (e.g., one per district) if you approach that budget.
