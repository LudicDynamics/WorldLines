---
name: entity-authoring
description: Schema-aware workflow for creating or updating WorldLines game entities (JSON files under game/). Use when adding/editing NPCs, locations, items, quests, or fixing validation errors in entity files.
---

# Entity Authoring Workflow

Use this workflow whenever game entities are created or updated.

## 1) Read Rules First

- Read the entity schema: the world's own override `rules/game_entity.schema.json` if it exists, otherwise the engine's
  default `neonrp/src/neonrp/schema/game_entity.schema.json`
- Read the world spec for each folder under `game/`: `documents/spec/world.zh.md` (English: `world.en.md`)
- Read existing entities of the same kind for patterns
- Check cross-entity references before writing

## 2) Author Entities Safely

- Store entities at `game/<kind>/<id>.json` (or `game/<category>/<id>/<file>.json` for nested)
- Keep these aligned:
  - Path kind segment matches `kind` field
  - Filename matches `id` field
  - All three (path-kind, filename-id, field-id) are consistent
- Always include required fields: `id`, `kind`, `name`
- Keep IDs stable; avoid renaming unless required
- For references (`location`, `connections`, `npcs`, `items_available`), use existing IDs and avoid dangling links

## 3) Kind-specific Rules

| Kind | Extra Fields | Notes |
|---|---|---|
| `character` / `player` / `npc` | `hp`, `max_hp`, `location`, `inventory` | `location` must point to a real location ID |
| `location` / `town` / `dungeon` | `connections`, `npcs` | `connections` = array of location IDs; `npcs` = array of NPC IDs |
| `item` | `value`, `weight`, `quantity`, `effects` | — |

## 4) Consistency Checklist

- `id` matches filename
- `kind` matches parent folder
- Required fields present
- Cross-entity references point to real entities
- No dangling `location` / `connections` / `npcs` references
