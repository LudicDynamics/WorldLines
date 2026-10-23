---
name: soul-authoring
description: Scaffold a WorldLines soul folder (角色灵魂包) — a self-contained character bundle (soul.json identity, soul.md charter, persona kernel, background, rules, RPG body, seeded memory, run_state.json, assets/ portrait and the soul-agent manifest) that can be cast into any world. Use when creating a new soul / character that will inhabit a world.
---

# Soul Folder Authoring

Use this skill when creating a WorldLines soul — a self-contained character
bundle that can be cast into a world (`neonrp cast <folder>`).

**Spec: `documents/spec/soul.zh.md`** (English: `soul.en.md`). Read it before writing; every field below is described
there with who writes it (author / soul / engine) and whether it is implemented. Never invent a field the spec does not list.

## Architecture

```
<sid>/
  soul.json               ← identity envelope (required: sid, name)
  soul.md                 ← prose charter (voice, values, pressure pattern)
  run_state.json          ← initial runtime state: location, status (hp, mood); the engine writes it during play
  agents/
    manifest.json         ← one soul-agent and its write_globs (optional: filled in at runtime if missing)
  persona/                ← psychological kernel (immutable after authoring)
    core_traits.json
    motivations.json
    values.json
    relationships.json
  background/             ← lore (immutable)
    origin.md
    history.md
    secrets.md
  rules/                  ← decision guardrails (immutable)
    action_rules.md
    decision_rules.md
    interaction_rules.md
  character/              ← RPG body (runtime-writable)
    profile.json
    stats.json
    status.json
    equipment.json
    inventory.json
    wallet.json
  short-term-memo/        ← working memory (runtime)
    current_context.json
    conversation_cache.json
    recent_events.json
  long-term-memo/         ← durable memory (seeded by the author, appended at runtime)
    important_events.md
    learned_facts.json
    emotional_memories.json
  trajectory/             ← append-only action log
    action_log.md
  assets/
    portrait.png          ← portrait (.png / .jpg / .webp); shown as the avatar
    sprite.webp           ← (optional) sprite
```

Every subfolder is optional — a missing one degrades, it does not crash (spec §7). The minimum that runs is `soul.json`
alone; the recommended minimum is `soul.json` + `soul.md` + `persona/motivations.json` + `run_state.json` (spec §6).

## `run_state.json`

The author gives the initial values; during play only the engine writes `location` (after a move is judged),
`status.mood`, `status.trust.player` and `status.intention` (spec §3.2, §5).

```json
{"sid": "mina", "location": "<place id>", "status": {"hp": 20, "max_hp": 20, "mood": "calm"}}
```

A soul with no `location` is in no place; under the `rpg` pack only souls in the player's place join the turn, so give
one if she should appear.

## `agents/manifest.json`

One agent for every soul (spec §3.3):

```json
{
  "schema_version": 1,
  "agents": [
    {"id": "soul-agent", "role": "soul",
     "write_globs": ["run_state.json", "trajectory/**", "short-term-memo/**", "long-term-memo/**", "character/**"]}
  ]
}
```

## Workflow

1. Read the soul description (one-line premise, archetype, traits).
2. Derive a stable ASCII `sid` slug from the character name; write `soul.json` (`sid`, `name`, `name_local`).
3. Author `soul.md` first — it constrains voice, values, and social posture.
4. Author `persona/` kernel consistent with the charter.
5. Author `background/` and `rules/` consistent with persona.
6. Author `character/` mechanics sized to the implied power level.
7. Write `run_state.json` with a starting location and status.
8. Seed memory folders with a plausible starting state.
9. Create `assets/` and ask the user for a portrait they have the rights to use.
10. Write `agents/manifest.json` last, then check: copy a world, `neonrp cast <folder>`, `neonrp validate`.

## Immutable vs Mutable

- **Immutable** (author once): `soul.md`, `persona/`, `background/`, `rules/`
- **Mutable** (runtime updates): `run_state.json`, `character/`, `short-term-memo/`, `long-term-memo/`, `trajectory/`

Make immutable folders complete at authoring time. Mutable folders only need a sane initial state. Never pre-fill trajectory with fabricated history.

## Language

- `name`, prose, persona in the soul's native language (zh / ja / ko / en)
- `sid` and all IDs ASCII-only (use pinyin / romaji / semantic slug)

## Do Not

- Do not invent new top-level folders beyond the canonical structure
- Do not put world/location lore here — that belongs in the world's `game/`
- Do not pre-fill `trajectory/` with fake action history
- Do not skip `soul.md`
