---
name: character-card-authoring
description: Author or edit a SillyTavern-compatible 角色卡 / character card (V2/V3 spec) directly inside a NeonRP project. Use when the user asks to write a tavern character card, convert a NeonRP character entity into a shareable tavern card, or fix schema issues in an existing card. Distinct from tavern-game-import, which converts a card INTO a NeonRP slice — this skill is about producing the tavern card itself.
---

# Character Card Authoring

Use this skill whenever the user wants to create or edit a tavern-style
character card (角色卡) for export to, or sharing with, SillyTavern or any
tavern-compatible frontend.

# Scope

- Character Card V2 JSON (`spec: "chara_card_v2"`, `spec_version: "2.0"`)
- Character Card V3 JSON (`spec: "chara_card_v3"`, `spec_version: "3.0"`)
- Embedded world-info via `data.character_book`
- Optional PNG-embedded cards (do NOT manipulate the binary PNG here; output
  the JSON that can later be embedded with a dedicated tool)

Do NOT use this skill:

- To import a tavern card INTO NeonRP — use `tavern-game-import`.
- To author a standalone world book — use `world-card-authoring`.
- To write NeonRP-native `game/character/<id>.json` entities — use
  `entity-authoring`.

# Canonical File Layout In A NeonRP Project

- `cards/character/<id>.json` — full tavern character card payload (preferred)
- `game/character/<id>.json` — NeonRP-native character entity (different shape)
- If both exist for the same persona, keep them cross-referenced in
  `cards/character/<id>.json.meta.neonrp_entity = "game/character/<id>.json"`.

# V2 Card Shape (authoritative)

```json
{
  "spec": "chara_card_v2",
  "spec_version": "2.0",
  "data": {
    "name": "<display name — may be Chinese>",
    "description": "<persona + appearance + traits>",
    "personality": "<short summary>",
    "scenario": "<opening situation>",
    "first_mes": "<first message shown to player>",
    "mes_example": "<<START>>\\n{{user}}: ...\\n{{char}}: ...",
    "creator_notes": "<author-facing notes, not sent to LLM>",
    "system_prompt": "<optional override>",
    "post_history_instructions": "",
    "alternate_greetings": ["<alt greeting 1>"],
    "tags": ["<tag>", "<tag>"],
    "creator": "<author handle>",
    "character_version": "1.0",
    "extensions": {},
    "character_book": { /* see world-card-authoring */ }
  }
}
```

Top-level legacy fields (`name`, `description`, `personality`, `scenario`,
`first_mes`, `mes_example`) may be mirrored for backwards compatibility with
older frontends, but the canonical source of truth is under `data.*`.

# V3 Card Shape (additions over V2)

- `spec: "chara_card_v3"`, `spec_version: "3.0"`
- `data.assets[]` — multimedia attachments
- `data.nickname` — alternate speaker label
- `data.creator_notes_multilingual` — localized creator notes
- `data.source` — origin URL / credit
- `data.group_only_greetings` — greetings only used in group chat
- `data.creation_date`, `data.modification_date` — unix timestamps

Treat V3 as a superset; always write `spec_version: "3.0"` when any V3-only
field is present.

# Placeholder Substitution Rules

SillyTavern evaluates these placeholders at chat time:

- `{{char}}` — character's display name (`data.name`)
- `{{user}}` — player-set persona name
- `{{random:a,b,c}}` — random pick
- `{{pick:a,b,c}}` — sticky random (one per message)
- `{{roll:NdM}}` — dice roll
- `{{date}}`, `{{time}}`

Write these exactly — do NOT expand them at authoring time.

# Authoring Workflow

1. Read the existing card (if any) before editing.
2. Clarify scope: persona-only, persona + world (embedded `character_book`), or
   full conversion from a NeonRP entity.
3. Decide target spec: V2 for maximum compatibility, V3 when the user asks
   for multilingual notes / assets / group-greetings.
4. Write clear, non-redundant fields:
   - `description` = who they are + appearance + core traits
   - `personality` = compact trait list for model to lean on
   - `scenario` = the *situation* the chat begins in
   - `first_mes` = the opening message in the character's voice
5. Provide `mes_example` with at least one `<START>` block showing dialogue
   style; use `{{char}}` / `{{user}}` placeholders.
6. Fill `tags` with 3-10 short descriptors that help discovery.
7. If the card ships with lore, author `data.character_book` entries using
   the `world-card-authoring` rules.
8. Validate: all required fields present, placeholders balanced, `spec` and
   `spec_version` consistent.

# Quality Rules

- Keep Chinese / non-ASCII text in `name`, `description`, `first_mes`,
  `mes_example`, `creator_notes`. Never transliterate.
- Use present-tense, third-person `description`.
- `first_mes` should be written in the character's voice, not as narrator.
- `mes_example` must use `{{char}}` / `{{user}}` literally — never bake in
  a specific user's name.
- Do NOT include meta-instructions ("You are an AI playing...") in `description`;
  use `system_prompt` if the card absolutely requires it.
- Keep `description` under ~1500 characters for most frontends; split
  long lore into `character_book` entries.
- Preserve `creator`, `character_version`, `creator_notes` across edits.

# Converting A NeonRP Character Into A Tavern Card

When the user says "export `game/character/<id>.json` as a tavern card":

1. Read the NeonRP entity.
2. Read any related `game/lore/*.md` referenced by that character.
3. Map fields:
   - `name` ← `name`
   - `description` ← build from `summary` + relevant lore + traits
   - `personality` ← summarize traits / tags
   - `scenario` ← derive from current location / opening context
   - `first_mes` ← craft new; do NOT reuse raw summary
   - `mes_example` ← invent a representative exchange
   - `tags` ← intersect `tags` + `kind`
4. Optionally attach relevant world lore as `character_book`.
5. Write to `cards/character/<id>.json`.
6. Record the source link in `data.extensions.neonrp.source_entity`.

# Do Not

- Do not invent tavern spec fields that do not exist.
- Do not stuff gameplay state (HP, gold, inventory) into the card — that is
  per-run runtime state, not a shareable card.
- Do not overwrite a creator's `creator_notes` / `creator` when editing.
- Do not embed actual PNG binaries from this skill; emit JSON only.
- Do not leak internal NeonRP file paths into player-visible fields.
