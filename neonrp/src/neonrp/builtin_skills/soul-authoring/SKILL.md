---
name: soul-authoring
description: Scaffold a self-contained NeonRP soul folder (a player avatar or NPC character bundle) from a one-line description using the neonrp agent toolchain — persona kernel, immutable background, RPG character mechanics, behaviour rules, seeded memory, and the 6 soul-* sub-agent manifest. Use when the user asks the agent to create a new soul / character directly inside a freshly-minted soul folder (NOT when authoring a world `game/` folder, and NOT when importing a tavern character card).
---

> **Spec first.** Before writing, call `read_spec(name="soul")`; it is the authoritative shape of what you write.

# NeonRP Soul Folder Authoring

Use this skill whenever the agent itself is expected to fill a freshly
created soul bundle that lives under `~/.worldlines/souls/<sid>-<ts>/`.
This is the soul-side counterpart of `world-game-authoring`:

- `world-game-authoring` → the world the runtime loads (`game/`)
- `soul-authoring`        → an inhabitant of that world (the `soul/` bundle)
- `player-character-authoring` → the protagonist *inside* an existing world

If the user asks "create a character" / "make me an NPC" / "design a
companion soul", use this skill unless they explicitly want a tavern
character card or a world.

The soul folder skeleton (`agents/ persona/ background/ character/
rules/ short-term-memo/ long-term-memo/ trajectory/` + `.commits/`) has
already been minted by `neonrp.core.souls.create_soul_dir` before this
skill runs. The skill's job is to fill those empty subfolders plus the
root `soul.md` charter with real content — never to invent new top-level
folders.

# Build Mode: authoring a soul from inside a world (M31)

**If you are in build mode inside a live world, this section overrides the
IO contract below.** There is no pre-minted folder and no working
directory — you create the files yourself, then hand the soul to the
world. Everything else in this skill (what a soul is made of, the voice,
the schema) still applies.

1. **Do not survey the world first.** You need the world's name and tone,
   nothing more — read at most one or two files. Reading the whole world
   before writing anything is the single most common failure here: the
   turn runs out while the character still does not exist.
2. **Pick a stable ASCII `sid`** from the name you were given (`罗文·铁砧`
   → `luowen`). Keep it stable for the rest of the turn.
3. **Write into `.neonrp/soul-drafts/<sid>/`**, project-relative, with
   `write_file`. Paths look like
   `.neonrp/soul-drafts/luowen/persona/core_traits.json`.
4. **Author a minimum viable soul first** — six files, in this order:
   - `soul.md` — the charter: voice, values, how they behave under pressure
   - `persona/core_traits.json`, `persona/motivations.json`
   - `background/origin.md`
   - `rules/interaction_rules.md`
   - `character/profile.json`
   The rest of the file map below is the *full* shape; fill more only if
   the author asks for depth. A soul that exists beats a soul that was
   still being written when the turn ended.
5. **Call `cast_soul(sid)` to finish.** Authoring files does not put the
   character in the world — this call does. It also backfills anything
   structurally required (`agents/manifest.json` is template policy and is
   never yours to write). Cast as `role="player"` only if the author
   explicitly wants a player avatar.
6. **Then stop and say what you made** in one or two sentences. Do not
   re-author on the next turn.

Never hand-edit `.neonrp/playthrough.json` — it feeds the commit hash
chain, and a hand-edit makes the next turn unlandable.

# Invocation / IO Contract

> The rest of this document describes the **library** flow (a folder the
> runtime minted for you under `~/.worldlines/souls/`). In build mode use
> the section above for *where* and *how to finish*, and this one for
> *what a soul contains*.

Mirrors `world-game-authoring` exactly, only soul-shaped:

- **Input**: a one-line soul description plus the `agent_template`
  chosen at create time (`heroine-classic` → the full 6-agent set;
  `minimal` → a single dialogue-only agent for cheap NPC drafts).
- **Working directory**: the freshly-created soul folder; all writes are
  relative to it (same as `world-game-authoring` runs inside `game/`).
- **Output**: the seed files described below, authored once, then the
  thread is handed back to the runtime. Do not loop / re-author on
  subsequent turns; keep ids and `sid` stable.

# Target Paths Under The Soul Folder

A fully scaffolded soul touches these directories (the §2 schema of
`docs/M16_SOULHUB_DESIGN.md` / `docs/WORLD_SOUL_FOLDERS.md`):

- `soul.md` — the prose-facing soul charter
  - voice, values, pressure pattern, social posture, blind spots

- `persona/` — immutable psychological kernel
  - `core_traits.json` — stable personality traits
  - `motivations.json` — what drives this soul
  - `values.json` — moral / aesthetic compass
  - `relationships.json` — initial relationship dispositions
- `background/` — immutable lore prose
  - `origin.md`, `history.md`, `secrets.md`
- `character/` — RPG mechanics (writable at runtime by `soul-action`)
  - `stats.json`, `inventory.json`, `equipment.json`, `wallet.json`
  - `status.json` (current HP/MP/energy/mood), `profile.json`
- `rules/` — decision / behaviour guardrails (read-only at runtime)
  - `decision_rules.md`, `interaction_rules.md`, `action_rules.md`
- `short-term-memo/` — session working memory, lightly seeded
  - `current_context.json`, `conversation_cache.json`, `recent_events.json`
- `long-term-memo/` — durable memory, lightly seeded
  - `important_events.md`, `learned_facts.json`, `emotional_memories.json`
- `trajectory/` — append-only autonomous-action log, created empty
  - `action_log.md` (header only — runtime appends)
- `agents/` — the soul's sub-agent roster
  - `manifest.json` — the 6 soul-* agents + per-agent `write_globs`
  - `contracts.md` — input/output schema notes per agent

Do NOT invent parallel directories. Do write `soul.md`. Do NOT write
`soul.json` / `run_state.json` — `soul.json` is the library's identity
envelope and `run_state.json` is runtime-only.

# Required Workflow

1. Read the soul description and `agent_template` you were handed.
2. Derive a stable ASCII `sid` slug if not already provided (the
   library may have minted it — never rename it).
3. Author `soul.md` first or alongside the persona kernel: it constrains the overall voice.
4. Author the `persona/` kernel so it matches the soul charter.
5. Author `background/` so it is consistent with the charter + persona.
6. Author `character/` mechanics sized to the implied power level.
7. Author `rules/` so the runtime sub-agents have guardrails.
8. Seed memory folders with a small, plausible starting state.
9. Write `agents/manifest.json` last (roster is template-driven).
10. Keep every id / `sid` stable on any later edit.

# `agents/manifest.json` Shape

`heroine-classic` ships all six specialists; `minimal` ships only
`soul-dialogue` (still listed with an empty `write_globs` for the
others is NOT done — minimal lists exactly one agent). Schema:

```json
{
  "schema_version": 1,
  "agent_template": "heroine-classic",
  "agents": [
    {
      "id": "soul-orchestrator",
      "role": "dispatcher",
      "system_prompt": ".claude/agents/soul-orchestrator.md",
      "write_globs": ["run_state.json", "trajectory/**"]
    },
    {"id": "soul-mind",      "role": "cognition",   "write_globs": []},
    {"id": "soul-memory",    "role": "retention",
     "write_globs": ["short-term-memo/**", "long-term-memo/**"]},
    {"id": "soul-action",    "role": "execution",
     "write_globs": ["character/**", "trajectory/**", "run_state.json"]},
    {"id": "soul-dialogue",  "role": "speech",
     "write_globs": ["short-term-memo/conversation_cache.json"]},
    {"id": "soul-narrative", "role": "story-iface",
     "write_globs": ["run_state.json"]}
  ]
}
```

# Write-Permission Contract (M16 §2.3)

The skill seeds content but must respect the runtime writer boundaries
so the apply-pipeline routing stays valid:

| Folder | Runtime writer |
|---|---|
| `soul.md` | none (immutable post-creation) |
| `persona/`, `background/`, `rules/` | none (immutable post-creation) |
| `character/` | `soul-action` |
| `short-term-memo/` | `soul-memory`, `soul-dialogue` |
| `long-term-memo/` | `soul-memory` |
| `trajectory/` | `soul-action`, `soul-orchestrator` (append-only) |
| `run_state.json` | `soul-orchestrator`, `soul-action` |

Therefore: `soul.md`, `persona/`, `background/`, `rules/` must be *complete* at
authoring time (nothing writes them later). `character/`,
`short-term-memo/`, `long-term-memo/` only need a sane *initial* state.
`trajectory/action_log.md` is a header stub — never pre-populate
autonomous actions that did not happen.

# JSON Field Conventions

Every JSON file uses 2-space indent, UTF-8, trailing newline. Keep
structured facts in JSON and prose in `.md` — do not duplicate.
`character/profile.json` must carry the soul's `sid`, `name`, and
`name_local` consistent with `soul.json`.

# Language Handling

- Keep `name`, prose lore, and persona descriptions in the soul's
  native language (zh / ja / ko / en).
- Keep `sid` and all ids ASCII-only — derive via pinyin / romaji /
  hangul→latin / semantic slug, never raw CJK.

# Do Not

- Do not invent new top-level folders or rename the minted skeleton.
- Do not skip `soul.md`; the runtime now treats it as a first-class charter.
- Do not write `soul.json` or `run_state.json` (library/runtime own
  these).
- Do not pre-fill `trajectory/` with fabricated action history.
- Do not put world / location lore here — that belongs in `game/`.
- Do not exceed ~80KB per JSON file; split detail into prose instead.
- Do not leave persona / background / rules incomplete — nothing
  writes them after creation.
