---
name: world-card-authoring
description: Author or edit a SillyTavern-compatible 世界卡 / world book (V2/V3 spec) directly inside a NeonRP project. Use when the user asks to build, expand, or fix lorebook entries, world cards, character_book payloads, or tavern-style world packages. Distinct from tavern-game-import, which converts an existing card into a playable slice — this skill is about authoring the tavern format itself.
---

# World Card Authoring

Use this skill whenever the user wants to create or edit a tavern-style world
card (世界卡 / lorebook / character_book) that will be exported to, or shared
with, SillyTavern or a tavern-compatible frontend.

# Scope

- SillyTavern World Info / lorebook entries
- Embedded `character_book` entries inside a character card
- Standalone world card JSON (`entries` array at top level)
- Tavern V2 / V3 spec fields

Do NOT use this skill:

- To convert a tavern card INTO a NeonRP playable project — use
  `tavern-game-import` instead.
- To author NeonRP-native `world/<kind>/<id>.json` entities — use
  `entity-authoring` + `world-building` for that.

# Canonical File Layout In A NeonRP Project

- `world/lorebook/<name>.json` — full tavern world book
- `game/lore/<topic>.md` — narrative prose lore for internal use
- `character/<id>.json` — character entity with optional embedded `character_book`

Keep tavern-style lorebook files JSON only; do not invent extra fields that
SillyTavern will drop on import.

# Tavern V2 Entry Schema (authoritative keys)

Each `entries` item should include these keys where relevant:

- `uid` (integer, unique within the book)
- `key` (array of trigger keywords — case insensitive)
- `keysecondary` (array, optional, used with `selective` match)
- `comment` (short author label, NOT sent to LLM)
- `content` (the actual lore text sent to LLM when triggered)
- `constant` (bool; true = always injected, ignores keys)
- `selective` (bool; both `key` AND `keysecondary` must hit)
- `order` (integer; insertion order when multiple trigger)
- `position` (0 = before char defs, 1 = after, 2 = before example, 3 = after example, 4 = @D depth)
- `depth` (integer; required when `position = 4`; smaller = closer to latest message)
- `disable` (bool; keep false for active entries)
- `excludeRecursion` (bool)
- `probability` (0-100)
- `useProbability` (bool)
- `name` (optional display label, V3)
- `displayIndex` (integer; UI sort hint)
- `addMemo` (bool)
- `group` (string; logical grouping; V3 supports priority within group)
- `groupOverride` (bool)
- `groupWeight` (int)
- `scanDepth` (integer or null; override for chat scan depth)
- `caseSensitive` (bool or null)
- `matchWholeWords` (bool or null)
- `useGroupScoring` (bool or null)
- `automationId` (string, optional; for STscript hooks)

Prefer `null` for untouched overrides (tavern convention) rather than omitting.

# Top-level World Book Shape

```json
{
  "name": "Stoneford Lore",
  "description": "Regional lore for the Stone Ford setting",
  "scan_depth": 4,
  "token_budget": 2048,
  "recursive_scanning": false,
  "extensions": {},
  "entries": [ /* entries objects */ ]
}
```

For `character_book` embedded inside a character card, use the same shape under
`data.character_book` (V2) or `character_book` (V3 raw).

# Authoring Workflow

1. Read any existing tavern card / world book first. Never append blindly.
2. Decide the scope: a single new topic vs. a full new book.
3. For each entry, plan:
   - Triggering keywords (diverse, avoid false positives)
   - Constant vs. selective vs. keyword-only
   - Position + depth (most lore belongs at `position: 0` or `position: 1`)
   - Order within the same position bucket
4. Keep each `content` field focused — ideally one concept per entry.
5. Fill `comment` with a short human label (not sent to LLM).
6. Use stable `uid` values — do not renumber on each edit.
7. Respect `token_budget` at the book level; estimate content length.

# Quality Rules

- Trigger keywords should be specific (`"石津镇"` not `"镇"`).
- Each `content` block should be self-contained: a reader hitting only that
  fragment should still learn something coherent.
- Avoid leaking meta framing ("You are an AI that...") into lore content.
- Use neutral third-person voice unless the card explicitly requires otherwise.
- For faction / cosmology / timeline entries, prefer `constant: true` only
  when the entry is load-bearing for every reply.
- Keep Chinese / non-ASCII text in `content`, `comment`, `name`; never transliterate.
- Use `position: 4` + a small `depth` for lore the model should see near the
  very latest player message (combat mechanics, active modifier).

# Minimum Viable New Book

When the user asks to create a fresh world book from a short premise:

- 3-6 entries minimum
- At least one `constant` entry covering the setting frame
- At least one faction/organization entry
- At least one location entry
- At least one cultural/mechanical rule entry
- One "hooks" entry describing active tensions or mysteries

# Do Not

- Do not fabricate tavern spec fields that do not exist.
- Do not overwrite an existing book wholesale unless the user asks for a rewrite.
- Do not put gameplay state (HP, gold, inventory) in a lorebook — that belongs
  in NeonRP `game/` entities.
- Do not embed the same lore in more than one entry — split by trigger instead.
- Do not touch `game/` entities from this skill; for cross-domain changes,
  pair with `entity-authoring` or `tavern-game-import`.
