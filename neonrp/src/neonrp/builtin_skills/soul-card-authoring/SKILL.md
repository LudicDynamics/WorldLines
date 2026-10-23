---
name: soul-card-authoring
description: Transform a SillyTavern character card (角色卡) into a COMPLETE, rich NeonRP soul bundle. Given a card's fields (name, description, personality, scenario, first_mes, tags), author the full soul folder — persona kernel, background lore, RPG mechanics, behaviour rules, seeded memory — staying faithful to the card's character while filling in everything the card leaves unspecified by reasonable inference. Use when importing a tavern character card INTO the soul library (NOT when writing a tavern card out — that is character-card-authoring — and NOT for a world game/ folder — that is world-game-authoring).
---

> **Spec first.** Before writing, call `read_spec(name="soul")`; it is the authoritative shape of what you write.

# NeonRP Soul-Card Authoring

Use this skill to turn a **SillyTavern character card** into a first-class
NeonRP **soul** that lives under `~/.worldlines/souls/<sid>-<ts>/` and is
playable + reusable from the library.

This is the card-fed counterpart of `soul-authoring`:

- `soul-authoring`      → author a soul from a one-line description
- `soul-card-authoring` → author a soul from a tavern **card's** fields

A tavern card carries only a handful of free-text fields. A NeonRP soul is a
structured, multi-file bundle. Your job is to **faithfully expand** the card
into that bundle — keep the character exactly who the card says they are, and
**fill in** the structure the card doesn't spell out (trait/intensity arrays,
motivations, relationships, stats, rules, seed memory) by reasonable inference
from the card's own prose. Do NOT invent a different character, a different
name, or lore that contradicts the card.

# Input

You are given the parsed card as a concept, containing (any of):

- `name` — the character's display name (may be non-ASCII; keep it verbatim)
- `description` — persona + appearance + traits (the richest field; mine it)
- `personality` — a short personality summary
- `scenario` — the opening situation / setting the character is placed in
- `first_mes` — the character's first line / greeting (their VOICE — study it)
- `tags` — freeform tags

The `sid` (a stable ASCII slug) has already been minted by the library; use it
verbatim in every file. The folder skeleton (`agents/ persona/ background/
character/ rules/ short-term-memo/ long-term-memo/ trajectory/` + `.commits/`)
already exists — never invent new top-level folders.

# Output — IO Contract

Return **one JSON object** whose keys are `"<subfolder>/<filename>"` (and the
bare `"soul.md"`) and whose values are the file *contents* — an object for
`.json` files, a string for `.md` files. Anything you omit is backfilled with a
structural seed, but you should author every content-bearing file below so the
soul is rich, not a husk. Do **not** include `soul.json`, `run_state.json`, or
`agents/` (the library/runtime/template own those).

Author these keys:

- `soul.md` — the prose soul charter: voice, values, pressure pattern, social
  posture, blind spots. Ground the voice in the card's `personality` +
  `first_mes`. This is the most important file; make it read like the card's
  character, not a generic template.
- `persona/core_traits.json` — `{ "sid", "personality_type": <sentence>,
  "core_traits": [{"trait","intensity":0-100,"description"}...],
  "temperament": {big-five 0-100}, "emotional_tendencies": {...},
  "quirks": [...], "fears": [...], "pet_peeves": [...] }`. Derive 4-6 traits
  with intensities from the card's description/personality — inferred, but
  clearly grounded in the card.
- `persona/values.json` — `{ "sid", "values": [<short value statements>] }`.
- `persona/motivations.json` — `{ "sid", "motivations": [<what drives them>] }`.
- `persona/relationships.json` — `{ "sid", "relationships": { ... } }`; seed
  from any relationships the card names, else an empty-but-valid map.
- `character/profile.json` — `{ "sid", "display_name", "name_local",
  "age"?, "role":"npc", "tags":[...], "appearance": {...}, "summary" }`.
  `display_name`/`name_local` must match the card's name.
- `character/stats.json` — `{ "sid", "hp", "max_hp", "skills":[...] }` sized to
  the card's implied competence (a healer ≠ a warrior).
- `character/status.json` — `{ "sid", "mood", "flags": {...} }` (sane initial).
- `character/equipment.json` / `character/inventory.json` — plausible starting
  gear/items implied by the card (empty-but-valid if none implied).
- `character/wallet.json` — `{ "sid", "currency": <int> }`.
- `background/origin.md` — where they come from; fold in the card's `scenario`
  and the backstory implied by `description`.
- `background/history.md` — key past events, consistent with origin + persona.
- `background/secrets.md` — 1-3 private truths (inferred, tasteful, in-character).
- `rules/decision_rules.md`, `rules/interaction_rules.md`,
  `rules/action_rules.md` — behaviour guardrails so the runtime sub-agents stay
  in character (how they decide, talk, act).
- `short-term-memo/recent_events.json` — `{ "sid", "events": [] }` (start empty).
- `long-term-memo/learned_facts.json` — `{ "sid", "facts": [] }` (start empty).

# Faithfulness Rules

- Keep the card's `name`, personality, and any concrete lore EXACTLY. Expand,
  never overwrite the character.
- Where the card is silent (structured traits, stats, motivations, secrets),
  infer values that a reader of the card would find obviously consistent — not
  a random new invention.
- Match the soul's `personality_type`, `core_traits`, `values`, and `soul.md`
  voice to each other and to the card. No internal contradictions (e.g. a
  gentle healer must not also read as a bloodthirsty raider).

# Language

- Keep `name`, prose lore, persona descriptions, and `soul.md` in the card's
  own language (zh / ja / ko / en) — mirror the card's voice.
- Keep `sid` and all ids ASCII-only.

# JSON Conventions

- 2-space indent, UTF-8, trailing newline conceptually; structured facts in
  JSON, prose in `.md` — do not duplicate.
- `character/profile.json` must carry `sid` + name consistent with the library.
- Do not exceed ~80KB per JSON file; put long prose in the `.md` files.

# Do Not

- Do not invent new top-level folders or rename the skeleton.
- Do not write `soul.json`, `run_state.json`, or `agents/*` — those are owned
  elsewhere.
- Do not change the character into someone else, or add world/location lore
  (that belongs in `game/`).
- Do not leave `soul.md` / `persona/` / `background/` / `rules/` empty —
  nothing writes them after creation.
