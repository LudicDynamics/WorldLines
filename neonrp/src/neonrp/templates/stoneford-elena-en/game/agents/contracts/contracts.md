# Subagent Contracts (Read/Write Boundaries)

Stoneford Elena extends the real Stone Ford contract with explicit souls.
`game/player/*` remains a compatibility projection for the heroine, not the only
character truth source.

Each subagent MUST:
- Only read the allowed file globs
- Only write the allowed file globs
- Output changes as a "patch plan" describing which files to create/update and why

## Orchestrator (main)
READ: game/** (all), but write only through patch plans or direct world-agent updates
WRITE: game/run_state.json, lore/notes.md (optional), lore/story.md (optional)

Soul runtime note:
- Active souls are declared in `playthrough.json`
- The world-agent receives soul outputs, but does not directly read `souls/**`
- `game/player/*` is the local projection of Elena's state for legacy Stone Ford flows

## World Builder
READ: world/world_map.json, lore/story.md, lore/notes.md
WRITE: world/world_map.json, world/regions.json (optional), world/factions.json (optional)

## Story / Narrative
READ: lore/story.md, lore/notes.md, world/world_map.json, player/flags.json
WRITE: lore/story.md, lore/rumors.md (optional)

## Town Agent (per town)
READ: towns/<town>/**, player/**, lore/notes.md
WRITE: towns/<town>/town.json, towns/<town>/town_map.json, towns/<town>/npcs.json, towns/<town>/quests.json

## Facility Agents (Guild/Shop/Inn)
READ: towns/<town>/facilities/*.json, towns/<town>/quests.json, player/**
WRITE: towns/<town>/facilities/*.json, towns/<town>/quests.json, player/inventory.json, player/wallet.json, player/flags.json, player/stats.json (inn rest)

## Dungeon Agent (per dungeon)
READ: dungeons/<dungeon>/**, player/**, rules/combat_rules.md
WRITE: dungeons/<dungeon>/** (state), world/world_map.json (discover/clear flags), player/flags.json

## Combat Referee
READ: rules/combat_rules.md, player/stats.json, player/equipment.json, player/inventory.json
WRITE: player/stats.json, player/inventory.json, player/wallet.json (loot), lore/notes.md
