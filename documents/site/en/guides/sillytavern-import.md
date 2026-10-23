---
title: "SillyTavern Import"
description: "Import SillyTavern world cards and character cards into WorldLines."
---

<!-- section: character-cards -->
## Character cards

SillyTavern character cards ship as either JSON files or PNG images with embedded tEXt metadata. Both are supported.

```bash
neonrp import sillytavern-card card.png --id mira-ashford
neonrp import sillytavern-card card.json --id mira-ashford
```

The command parses the card, maps it into WorldLines' `npc/` schema, and writes the entity under `game/npc/<id>.json`.

📸 **Screenshots coming** — the import dialog with a PNG preview.

<!-- section: world-cards -->
## World cards

SillyTavern world cards (lorebooks) are richer — they define regions, factions, and world lore. Import:

```bash
neonrp import sillytavern-world world-card.json
```

Entities split into `game/lore/`, `game/towns/`, and `game/world/` as appropriate.

📸 **Screenshots coming** — the before/after diff view of the imported lorebook.

<!-- section: caveats -->
## Caveats

- SillyTavern fields that don't map 1:1 land in a `_meta.silly_tavern` blob on the resulting entity. Nothing is lost; it's just not yet first-class in the schema.
- Import is **one-way** in v0.1. A round-trip export back to SillyTavern format is planned for v0.2.
- If the card references images hosted elsewhere, the import logs a warning but does not download them.
