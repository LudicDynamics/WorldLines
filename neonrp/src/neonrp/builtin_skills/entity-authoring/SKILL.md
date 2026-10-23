---
name: entity-authoring
description: Schema- and rules-aware workflow for creating or updating NeonRP entities. Use when adding/editing files under world/<kind>/<id>.json, fixing validation errors, or introducing new kinds/fields.
---

> **Spec first.** Before writing, call `read_spec(name="world")` and `read_spec(name="ops", pack=…)` for the ops the world's play pack allows; it is the authoritative shape of what you write.

# Entity Authoring Workflow

Use this workflow whenever world entities are created or updated.

1. Read rules first.
2. Edit entities.
3. Re-check consistency before finishing.

# 1) Read Rules First

- Read `rules/game_entity.schema.json` if it exists.
- If `rules/game_entity.schema.json` is missing, read `.neonrp/schema/game_entity.schema.json` if present.
- Read `.neonrp/config.json` and check `rules.profile_path`.
- If `rules.profile_path` is set, read that profile file too (for domain validation and `resolve_action` behavior).

# 2) Author Entities Safely

- Store entities at `world/<kind>/<id>.json`.
- Keep these aligned:
  - Path kind segment (`<kind>`)
  - Filename (`<id>.json`)
  - Entity fields: `id`, `kind`
- Always include required fields:
  - `id`
  - `kind`
  - `name`
- Keep IDs stable; avoid renaming unless required by the task.
- For references (for example `location`, `connections`, `npcs`, `items_available`), prefer existing IDs and avoid dangling links.

# 3) Consistency Checklist Before Finish

- `id` matches filename.
- `kind` matches parent folder.
- Required fields are present.
- Field types/ranges match schema definitions.
- Cross-entity references point to real entities.
- New kinds/fields are reflected in schema/rules files when needed.

# Mode Notes

- `build` / `play`: use direct file tools (`read_file`, `write_file`, `edit_file`, `glob`, `grep`) as available.
- `sandbox`: bundle world changes into one `submit_proposal(...)`.
- If `resolve_action` is enabled, use it for deterministic mechanics; it is read-only and does not write files.
