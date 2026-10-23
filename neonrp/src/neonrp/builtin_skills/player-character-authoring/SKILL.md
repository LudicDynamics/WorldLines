---
name: player-character-authoring
description: Build or update the NeonRP `game/player/` folder — the protagonist entity, stats, inventory, equipment, wallet, and flags — using the neonrp agent toolchain. Use when the user asks the agent to create a player character for this campaign, onboard a new player role, or reset the player state. Distinct from character-card-authoring (tavern format) and tavern-game-import (conversion).
---

> **Spec first.** Before writing, call `read_spec(name="soul")`; it is the authoritative shape of what you write.

# NeonRP Player / Character Folder Authoring

Use this skill whenever the agent itself is expected to create or update
the player-controlled character inside a NeonRP project. This is the
engine-native counterpart of `character-card-authoring`:

- `character-card-authoring` → SillyTavern-format shareable card
- `player-character-authoring` → `game/player/*.json` for the live runtime
- `tavern-game-import`        → convert a tavern card INTO a player entity

# Target Paths Under `game/player/`

A complete player package usually consists of:

- `game/player/player.json` — canonical protagonist entity
- `game/player/stats.json` — mechanical stats (hp, attributes, skills)
- `game/player/inventory.json` — items the player carries
- `game/player/equipment.json` — currently worn / wielded gear
- `game/player/wallet.json` — currency balance
- `game/player/flags.json` — narrative flags and progression markers
- `game/player/relationships.json` — reputations and bonds (optional)

Prefer the existing file set already present in the project; do not
invent new files when existing ones cover the data.

# Entity Conventions

`game/player/player.json` must include:

- `id` — usually `"player"` (ASCII, stable)
- `kind` — `"player"` or `"character"` depending on project schema
- `name` — display name, may be Chinese/Japanese/Korean
- `summary` — 1-2 sentence persona hook
- `backstory` — 3-8 sentences; who they were before the game starts
- `goals` — list of 1-3 short strings; what they want now
- `traits` — short trait list (e.g., `["stoic", "careful", "left-handed"]`)
- `appearance` — compact physical description
- `tags` — discovery tags
- `starting_location` — id of the location where the player spawns
- `hooks` — list of plot hooks the character is personally tied to

Optional sub-fields (when schema supports):

- `origin`, `faction`, `profession`, `species`, `age`, `gender`,
  `pronouns`, `language`, `notes`

# Stats / Mechanical Fields

`game/player/stats.json` should only contain fields the active rules
profile actually consumes. Typical minimum:

- `hp` / `max_hp`
- `mp` / `max_mp` (if magic system is active)
- `attributes` — object keyed by attribute id (strength, agility, ...)
- `skills` — object keyed by skill id → integer or level
- `status_effects` — list (usually empty at start)

Read `rules/*.json` or `.neonrp/schema/*.json` before inventing new stat
keys.

# Inventory / Equipment / Wallet

- `inventory.json`: `{ "items": [ { "id": "...", "qty": N } ] }`
- `equipment.json`: `{ "weapon": "id", "armor": "id", "accessory": "id" }`
  — use `null` for empty slots
- `wallet.json`: `{ "currency": { "gold": N } }` (or whatever currency
  ids the world uses)

Every referenced item id MUST correspond to a real `game/item/<id>.json`
entity. If it does not exist, create it first using `world-game-authoring`.

# Required Workflow

1. Read `game/meta/game-start.json` for the opening scene.
2. Read any existing `game/player/*.json` — never overwrite blindly.
3. Read `rules/*.json` / schema to know which stat fields are valid.
4. If backstory or persona is ambiguous, ask the user — do NOT invent
   traits that constrain future play without confirmation.
5. Derive `starting_location` from `game-start.json` if present.
6. Write the player files with `submit_proposal` (sandbox) or direct
   write/edit (build).
7. Keep ids stable; `player.json` id is conventionally `"player"`.
8. Do NOT touch `active-agent.json` — that belongs to runtime scaffold.

# Integration With `world-game-authoring`

- The player's `starting_location` must point at a real location or
  town that exists under `game/`. If it doesn't yet, author the
  location first (or coordinate both in one proposal).
- If the player belongs to a faction, that faction must exist under
  `game/world/factions.json`.
- Items in inventory / equipment must exist as `game/item/<id>.json`.

# Language Handling

- `name`, `summary`, `backstory`, `appearance`, `goals`, `traits` may be
  in zh / ja / ko / en — use the project's primary narrative language.
- `id` stays ASCII. Use `"player"` unless the project schema explicitly
  requires a different convention.
- Tags and flag keys stay in ASCII snake_case.

# Minimum Viable Player On First Creation

When the user says "make me a player for this world":

1. `player.json` with `id`, `kind`, `name`, `summary`, `backstory`,
   1-3 `goals`, 3-6 `traits`, `appearance`, `starting_location`.
2. `stats.json` with starting hp + attributes matching rules.
3. `inventory.json` with 2-4 starter items (create missing item
   entities if needed).
4. `equipment.json` with at most one weapon + one armor slot filled.
5. `wallet.json` with a small opening purse appropriate to the tone.
6. `flags.json` with an empty dict or a single `game_started: false`.

Only expand beyond this minimum when the user asks for more depth.

# Quality Checklist Before Finishing

- `id` in each file matches filename.
- `kind` matches the expected schema.
- Starting location exists.
- Every inventory / equipment item id exists under `game/item/`.
- `backstory` does not contradict `game/meta/game-start.json`.
- No gameplay rules invented that the active rules profile cannot
  resolve.
- No duplicate / conflicting traits between `player.json` and
  `stats.json`.

# Do Not

- Do not invent stat fields without checking the rules profile.
- Do not bake the user's specific session choices (e.g., "just defeated
  Dragon X") into the starting player entity — those are event-log
  events, not player facts.
- Do not put lore prose in `player.json.summary`; keep that file lean
  and store prose in `game/lore/*.md` or `player.backstory`.
- Do not set `max_hp` equal to zero or negative numbers; the rules
  engine will reject or mishandle such values.
- Do not overwrite a user's in-progress player state without confirmation.
- Do not change `id` across edits; downstream references will break.
