# Soul spec (character folder)

> Describes the NeonRP engine as currently implemented. Minimum runnable unit = **pack** (engine rules) + **world** (data) + **souls** (data); a **template** optionally binds them together. This document covers souls only. See [world.en.md](world.en.md) for worlds and [template.en.md](template.en.md) for templates.
>
> Status tags: **implemented** = in the code and in effect today; **in design** = the field or location is reserved or declared, but the engine does not fully use it yet.

---

## 1. What it is

A **soul** is a self-contained folder for one character: identity, persona, behaviour rules, memory, runtime state, art, and a manifest of what this character may write when it runs as an agent.

- A soul is world-agnostic and reusable: the same soul can be cast into different worlds.
- Inside a world, each soul instance is **one independent agent** (1 soul = 1 agent). It reads and writes only its own folder, and has read-only access to the world.
- The world (narrator / world-agent) **may not** write a soul's state or diary. Only the soul's own reply or the engine's soul settlement writes those (see §5).

Souls live in two places:

| Location | Path | Purpose | Status |
|---|---|---|---|
| In a world (instance) | `<world>/souls/<sid>-<instance_id>/` | The copy living in one world; runtime state is written here | implemented |
| Soul library | `~/.worldlines/souls/<sid>/` or `~/.worldlines/souls/<sid>-<timestamp>/` | The world-agnostic original, castable into any world | implemented |

---

## 2. Directory layout

Elena from the built-in `stoneford-elena` world (`souls/elena-si-elena0001/`):

```
elena-si-elena0001/
├── soul.json                 # identity envelope (required)
├── soul.md                   # charter: voice, drives, pressure pattern, blind spots
├── run_state.json            # runtime state: location, hp, mood, trust, intention
├── agents/
│   ├── manifest.json         # agent manifest: write permissions (write_globs)
│   ├── contracts.md          # human-readable contract note
│   └── soul-agent/system.md  # (optional) overrides the engine's default soul system prompt
├── persona/                  # persona kernel (immutable after authoring)
│   ├── core_traits.json
│   ├── motivations.json
│   ├── values.json
│   └── relationships.json
├── background/               # origin / history / secrets (immutable after authoring)
│   ├── origin.md
│   ├── history.md
│   └── secrets.md
├── rules/                    # behaviour rules (immutable after authoring)
│   ├── action_rules.md
│   ├── decision_rules.md
│   └── interaction_rules.md
├── character/                # RPG body: profile, stats, equipment, inventory, wallet, status
│   ├── profile.json
│   ├── stats.json
│   ├── status.json
│   ├── equipment.json
│   ├── inventory.json
│   └── wallet.json
├── short-term-memo/          # short-term memory (written at runtime)
│   ├── current_context.json
│   ├── conversation_cache.json
│   ├── recent_events.json
│   └── perceived.json        # created by the engine at runtime: each beat as she saw it
├── long-term-memo/           # long-term memory (author seeds; appended at runtime)
│   ├── important_events.md
│   ├── learned_facts.json
│   └── emotional_memories.json
├── trajectory/
│   └── action_log.md         # action trail (append-only)
└── assets/
    ├── portrait.png          # portrait
    └── sprite.webp           # (optional) sprite
```

When the engine mints a new soul it creates these subfolders: `agents persona background character rules short-term-memo long-term-memo trajectory .commits` (`src/neonrp/core/souls.py:SOUL_SUBFOLDERS`), plus `assets/`. Every subfolder is **optional**. A missing one degrades the soul instead of crashing it (see §7).

---

## 3. Files one by one

"Writer" column: **author** = written at authoring time; **soul** = written at runtime by the soul's own agent, inside its write scope; **engine** = written deterministically by engine code.

### 3.1 Root files

| Path | Required | Writer | Key fields | Read by | Status |
|---|---|---|---|---|---|
| `soul.json` | **required** (`sid`, `name`) | author | see table below | identity, display name, cast, soul backend selection | implemented |
| `soul.md` | recommended | author | Markdown; the `## Core Presence` and `## Voice And Social Posture` sections are extracted as summary / voice | injected into the soul system prompt (first ~900 chars go into the scene registry) | implemented |
| `run_state.json` | recommended | author sets initial values; engine writes at runtime | see §3.2 | location, mood, hp, trust, intention | implemented |

**`soul.json` fields**

| Field | Type | Required | Meaning | Status |
|---|---|---|---|---|
| `sid` | string | yes | character id, stable across worlds (e.g. `elena`) | implemented |
| `name` | string | yes | primary name (e.g. `Elena Vale`) | implemented |
| `name_local` | string | no | local-language name (e.g. `艾琳娜`); preferred in scenes | implemented |
| `schema_version` | int | no | currently `1` | implemented |
| `version` | string | no | author version, default `"1.0"`; written into the playthrough's `version_hash` on cast | implemented |
| `created_at` | string | no | ISO timestamp | implemented |
| `source` | object | no | `{kind: soulhub\|builtin\|local-create, hash, version}` provenance | implemented |
| `agent_template` | string | no | authoring-flavour marker (e.g. `heroine-classic`); does not change the runtime roster | implemented |
| `tags` | string[] | no | tags; `pc` / `player` etc. are dropped when projected as an NPC | implemented |
| `source_lang`, `name_i18n`, `summary_i18n`, `voice_i18n` | string / `{en,zh,ja,ko}` | no | multilingual display | implemented |
| `standalone` | bool | no | the author lets this character leave its world: chatted with on its own without being gained first, published on its own; talking with it is noted in the player data's `talked`, **not** a gain (gaining is `takeable` + `take_when` only). Shown as the template list's `standalone` and each `/api/v1/local/souls` row's `standalone`; true / false only (lint `soul.standalone`). A protagonist says the same in `game/player/profile.json` (listed as `player`) | implemented (10-15) |
| `takeable` · `take_when` | bool · string | no | whether a player may take the character home (default true) and on what (default `companion_at_ending` = it walks with the player when an ending lands; or `ending:<ending id>`). When it holds the character is gained with its full memory (player data `memory: full`). Template meta `take: {sid: condition \| null}`, each `/api/v1/local/souls` row's `takeable` / `take_when`; lint `soul.takeable` / `soul.take_when` (the ending must be this world's) | implemented (10-15) |
| `intro_i18n` | `{en,zh,ja,ko}` | no | card blurb (read by the display layer) | implemented (display only) |
| `backend` | string | no | `internal-llm` (default) / `stub` / `http`; unknown values fall back to the default | implemented |
| `backend_url`, `backend_timeout_s` | string / number | when `backend=http` | external soul service URL and timeout | implemented |
| other backends (external front-ends, a human) | — | — | reserved behind the same message contract | in design |

Elena's `soul.json` (excerpt):

```json
{
  "schema_version": 1,
  "sid": "elena",
  "name": "Elena Vale",
  "name_local": "艾琳娜",
  "version": "1.0",
  "source": { "kind": "builtin", "hash": "stonefordelena001", "version": "1.0" },
  "agent_template": "heroine-classic",
  "tags": ["pc", "heroine", "adventurer", "stoneford"]
}
```

### 3.2 `run_state.json`

| Field | Type | Writer | Meaning | Status |
|---|---|---|---|---|
| `sid` | string | author / engine | same as `soul.json` | implemented |
| `instance_id` | string | author / engine | same as the folder-name suffix | implemented |
| `location` | string | author sets it; at runtime only the engine's `move` lands it | place id; a bare node (e.g. `gate_north`) is qualified with the current town into `T001/gate_north`. Missing = not at any place | implemented |
| `status.hp` / `status.max_hp` | int | author; soul | hit points | implemented |
| `status.mood` | string | author sets it; at runtime the engine (soul settle) | mood. Settle picks from `calm warm curious hopeful alert anxious guarded angry hurt sad tired` (or keeps the current value) | implemented |
| `status.trust.player` | int, -10…10 | **engine only (soul settle)** | trust toward the player; changes by -2…+2 per turn | implemented |
| `status.intention` | string | **engine only (soul settle)** | the goal she most wants to push next, chosen from `persona/motivations.json` | implemented |
| `turn_count` | int | engine | turn counter | implemented |
| other keys (e.g. `loop_state`) | any | author | open fields, the world's own data | implemented (passed through) |

Elena's initial values:

```json
{
  "sid": "elena",
  "instance_id": "si-elena0001",
  "location": "gate_north",
  "status": { "hp": 24, "max_hp": 24, "memory": "amnesia", "mood": "alert" },
  "turn_count": 0
}
```

### 3.3 `agents/`

| Path | Required | Writer | Meaning | Status |
|---|---|---|---|---|
| `agents/manifest.json` | recommended (auto-filled at runtime if missing) | author / engine | `{schema_version, agent_template, agents:[{id, role, write_globs}]}`. `write_globs` are relative to the soul folder and decide where the soul agent may write | implemented |
| `agents/contracts.md` | no | author / engine | contract note for humans; not parsed by the engine | implemented |
| `agents/soul-agent/system.md` | no | author | replaces the engine's default soul system prompt entirely. Placeholders: `{name} {sid} {soul_rel} {role_contract} {charter} {persona}` | implemented |

Standard manifest (every soul is a single agent):

```json
{
  "schema_version": 1,
  "agent_template": "heroine-classic",
  "agents": [
    {
      "id": "soul-agent",
      "role": "soul",
      "write_globs": ["run_state.json", "trajectory/**", "short-term-memo/**", "long-term-memo/**", "character/**"]
    }
  ]
}
```

Runtime permissions of the soul agent (`src/neonrp/core/soul_agent.py:resolve_soul_agent_data`):

| Permission | Scope |
|---|---|
| read | its own `souls/<sid>-<iid>/**`; the world's `game/meta/run_state.json`, `game/timeline/**`, `game/locations/**` |
| write | the union of every manifest entry's `write_globs`, rebased onto its own folder |
| deny | its own `persona/**`, `background/**`, `rules/**` (immutable after authoring); `game/lore/gm-truth.md`, `game/lore/notes.md`, `game/secrets/**`, `.neonrp/**`, `agents/**`; other souls' folders (outside the allow list); the player's `game/player/*` |

### 3.4 `persona/` (immutable)

| File | Key fields | Read by | Status |
|---|---|---|---|
| `core_traits.json` | `personality_type`: string; `core_traits`: `[{trait, intensity, description}]` | system prompt (injected in full); the scene registry keeps the first 6 `trait`s | implemented |
| `motivations.json` | `motivations`: string[] (`goals` also accepted) | goal list (first 6); soul settle picks `intention` from it | implemented |
| `values.json` | `values`: string[] | system prompt (injected in full) | implemented |
| `relationships.json` | `relationships`: `{<sid>: {disposition, known, truth, …}}` | the scene registry carries only entries where `known != false` | implemented |

Every `*.json` under `persona/` is injected verbatim into the soul's system prompt. Example (Elena's `motivations.json`):

```json
{ "sid": "elena", "motivations": ["在石津镇拿到第一份真正像样的契约", "靠自己的本事挣出名声", "弄清灰雾北境究竟藏着什么"] }
```

### 3.5 `background/` and `rules/` (immutable)

| File | Content | Read by | Status |
|---|---|---|---|
| `background/origin.md`, `history.md` | origin, history | readable by the soul itself; folded into the NPC record in orchestrator mode | implemented |
| `background/secrets.md` | what only the GM and the character know | same; never shown to the player | implemented |
| `rules/decision_rules.md` | decision rules | the scene registry takes the first ~500 chars | implemented |
| `rules/action_rules.md`, `interaction_rules.md` | action / interaction rules | readable by the soul itself; folded into the NPC record in orchestrator mode | implemented |

### 3.6 `character/`

The RPG body. Writable by the soul agent (inside `write_globs`).

| File | Key fields (Elena) | Status |
|---|---|---|
| `profile.json` | `sid, display_name, name_local, age, role, tags, appearance{…}, summary` | implemented |
| `stats.json` | `hp, max_hp, skills[]` | implemented |
| `status.json` | `mood, memory, flags{…}` | implemented |
| `equipment.json` | `equipped{weapon, armor, cloak}` | implemented |
| `inventory.json` | `items[]` | implemented |
| `wallet.json` | `currency` | implemented |

Note: `profile.json`'s `role` is only a fallback when there is no playthrough. The character's actual role in a world is the playthrough row's `role` (Elena's profile says `player`, but in stoneford-elena she is cast as `npc`). A folder without `soul.json` (e.g. some Hub downloads) falls back to `profile.json`'s `sid / display_name / name_local` for identity.

### 3.7 Memory and trajectory

| File | Shape | Writer | Status |
|---|---|---|---|
| `short-term-memo/recent_events.json` | `{events:[{turn, event, my_reaction, affect, important?, trust_delta?, by}]}`, last 40 kept | engine (soul settle, `by: "engine.settle"`); under the older turn engine the soul agent appends it itself | implemented |
| `short-term-memo/perceived.json` | `{beats:[{turn, place, text}]}`, last 30 kept | engine: the turn's narration rewritten as what she saw and heard | implemented |
| `short-term-memo/current_context.json` | `{scene, turn, notes[]}` | author seeds; soul | implemented |
| `short-term-memo/conversation_cache.json` | `{exchanges[]}` | soul | implemented |
| `long-term-memo/important_events.md` | Markdown | author seeds; soul | implemented |
| `long-term-memo/learned_facts.json` | `{facts[]}` | author seeds; soul | implemented |
| `long-term-memo/emotional_memories.json` | `{memories[]}` | author seeds; soul | implemented |
| `trajectory/action_log.md` | append-only, one line per turn `- [turn] what I did/thought` | soul | implemented |
| `.commits/` | the soul's own version store | engine | in design (folder is created) |

**Write an author's starting memories as lists** (10-20): seed files such as `long-term-memo/*.md` as top-level list items, one thing per item, grouped by topic under `## ` headings; in seeded JSON memories give list elements an `id`. After a player takes the character home, a later change of yours reaches them as a diff they choose from item by item (each top-level list item and each `## ` section's other text is one entry; JSON by field, lists with ids by id) — a long paragraph can only be taken or left whole.

### 3.8 `assets/`

| File | Meaning | Status |
|---|---|---|
| `portrait.*` | portrait (`.png/.jpg/.webp`); used as the avatar in the UI. Copied with the folder on cast | implemented |
| `sprite.*` | sprite | implemented |
| "a portrait is required before publishing" check | the template layer declares "souls need a portrait", but lint does not enforce it for souls yet | in design |

---

## 4. sid vs instance, putting a soul into a world

| Concept | Example | Meaning |
|---|---|---|
| `sid` | `elena` | character id. The same in every world |
| `instance_id` | `si-elena0001` | this character's copy in **one** world. Generated on cast as `si-<12 hex chars>` |
| folder name | `elena-si-elena0001` | always `<sid>-<instance_id>`; the engine locates the soul by it |
| agent id | `soul:elena:si-elena0001` | the soul's id as a runtime agent |

One `sid` can have several instances in different worlds (or the same world). Each instance has its own memory and state.

### 4.1 Souls rows in the playthrough

A world registers its souls in `.neonrp/playthrough.json` (in a template, `playthrough.json` at the world root). All five fields of a row are **required** (`src/neonrp/core/playthrough.py:_parse_souls`):

```json
"souls": [
  { "sid": "elena", "instance_id": "si-elena0001", "version_hash": "stonefordelena001",
    "head_commit": "seed-soul-elena-0001", "role": "npc" }
],
"active_souls": ["si-elena0001", "si-rowan0001"]
```

| Field | Meaning |
|---|---|
| `sid`, `instance_id` | point at `souls/<sid>-<instance_id>/` |
| `version_hash` | the soul's version when it was placed (cast uses `soul.json.version`) |
| `head_commit` | seed commit marker; empty string on cast |
| `role` | `npc` or `player` |
| `active_souls` | instances currently on stage and scheduled. Rewritten each turn by the engine's scene-understanding step; off-stage souls make no LLM call |

### 4.2 `neonrp cast`

```
neonrp cast <sid|soul-folder-path> [--into <world folder>] [--as npc|player] [--location …] [--id …] [--force] [--adapt]
```

- `<sid>`: looks in the soul library `~/.worldlines/souls/` for a folder named `sid` or starting with `sid-` (newest wins). `<path>`: must be a folder containing `soul.json`.
- Where it lands depends on the world's `execution_mode` (read from `.neonrp/runtime_contract.json`):

| World mode | `--as npc` | `--as player` |
|---|---|---|
| `multi-agent` | the whole folder is copied to `souls/<sid>-si-<hex>/`, a souls row is appended, and the instance is added to `active_souls` | a `pid: "player"` entry is written to the playthrough's `players[]` (the player is not a soul) |
| `orchestrator` | flattened into one world NPC at `game/npc/<id>.json` (no soul folder, no separate agent) | written into `game/player/profile.json` |

- A multi-agent world must already have a playthrough.json, otherwise cast is refused. If the world declares an NPC cap, cast past it is refused (`--force` overrides).
- CLI `neonrp cast` copies the folder as-is and does not set a location. The authoring agent's cast tool (`src/neonrp/core/skills.py`) additionally writes `run_state.json.location` (the given place, or wherever the player stands; `src/neonrp/core/placement.py:seed_soul_location`) and archives a copy of the character into the soul library (without `run_state.json`, because runtime state belongs to the world instance).

### 4.3 What a template may change

A template can supply a "prompt-layer overlay" for a soul (`prompts/souls/<sid>/…`), but may only overlay `soul.md`, `persona/`, `rules/`, `agents/` (`src/neonrp/template/__init__.py:SOUL_PROMPT_PATHS`). `character/`, memory, `soul.json` and `run_state.json` are soul data; a template cannot overlay them, and lint blocks the attempt with `prompt.soul.data`. See [template.en.md](template.en.md).

### 4.4 Character library and links (10-08)

The library `~/.worldlines/souls/<name>/` is a soul's home; it belongs to no world. A soul can be linked into many templates, a template can link many souls.

| What | How | Status |
|---|---|---|
| Put a soul in a world | the template's cast row `{"lib": "<name>", "role": "npc"\|"companion"\|"player"}` (template spec 3.6); the `set_cast` authoring op | implemented |
| When it becomes real | only when a run is built: copied into the run's `souls/<sid>-<instance_id>/`; until then the template holds a link | implemented |
| What differs in this world | the template's `prompts/souls/<sid>/` (4.3) and `world-overlay/`; the library soul is never changed | implemented |
| Which worlds link it | `template.bindings_of(<name>)` · `GET /api/v1/local/souls/<name>/bindings` | implemented |
| Take it out / bring it back | `neonrp template export --soul <name>`; a template package carries the souls it links (template spec 9.2) | implemented |
| A sheet per contract | `character/sheets/<contract id>.json`: one sheet per kind of game, none overwrites another; a missing one is made by the converter at the start of a run | in design |
| What a run writes back | only what the contract's `souls.out` lists (memories, trust, affection); roles / secrets the world hands out live in that run only | in design |
| The player from the library too | pick or create one; a `role: player` link becomes the run's player | in design |

### 4.5 Out of the world: direct chat (10-15)

The player can chat with a character one-on-one outside its world (the phone chat screen). Code: `src/neonrp/core/soul_chat.py`; routes: `src/neonrp/webui/launcher_routes.py:_chat_route`. Local and browser builds use the same HTTP.

Who can be talked to: a `standalone: true` character (its author lets it leave the world), or one the player has gained (player data `characters`, see `takeable` / `take_when` in 3.1). Every other character is `locked`.

| Endpoint | Returns | Status |
|---|---|---|
| `GET /api/v1/chat/souls?lang=` | `{souls: [{tpl, sid, name, avatar_url, avatar_thumb_url, world, standalone, obtained, talked, memory: full\|trial, last: {from, kind, text?, sticker?, at} \| null}]}`; lists standalone, gained and talked-with characters; `world` = the world it comes from (the template title, in lang); one character (same sid and name) carried by several templates is listed once: the copies the player has touched (gained — the world it was gained in —, talked with, has a thread); none touched → the officially listed world's copy (template `zone: reviewed`); other variants are not listed; `avatar_url` = the template portrait slot `soul.portrait:<sid>`, `avatar_thumb_url` = the same picture at 256 px (any template picture takes `&w=<px>`) | implemented |
| `GET /api/v1/chat/thread?tpl=&sid=&lang=` | `{soul: {tpl, sid, name, avatar_url, avatar_thumb_url, tagline, world, lang}, access: standalone\|obtained\|locked, memory, messages: [{id, from: me\|soul, kind: text\|sticker, text?, sticker?, at}], stickers: {soul: [{id, label, url}]}}` | implemented |
| `POST /api/v1/chat/send` `{tpl, sid, lang?, kind: text\|sticker, text?, sticker?}` | 200 `{messages: [the character's 1–5 replies], usage, ms}` (synchronous, no events); the player's message is saved too | implemented |
| `GET /api/v1/chat/sticker?tpl=&sid=&id=` | a character's own sticker image | implemented |

Errors: `403` locked · `404` no such character · `409` still answering the previous message · `400` empty text / sticker · `502` model error `{error, billing?}` (`billing` has the same shape as a turn's billing_stop). A failed send leaves nothing in the thread.

| What | Rule | Status |
|---|---|---|
| What the character knows | its own folder's `soul.md`, `persona/`, `background/`, `character/profile.json`, `long-term-memo/`, `short-term-memo/` (capped at 9000 chars), plus the last 24 messages | implemented |
| Where memory comes from | gained: when gained, the run's character folder is snapshotted to `~/.worldlines/player-data/<player>/souls/<tpl>/<sid>/` (`assets/` not copied), `memory: full`; not gained: the template's folder, `memory: trial` | implemented |
| Thread | `~/.worldlines/player-data/<player>/chats/<tpl>__<sid>.jsonl`; belongs to the player, never to the template | implemented |
| talked | the first chat with a standalone character is noted in player data `talked` — **not a gain** | implemented |
| Stickers | built-in `wl:<id>`, 16 of them: hello happy laugh shy love thanks ok think surprised sad cry angry sleepy sorry cheer bye (drawn by the front end); a character's own `soul:<id>` = `stickers/<id>.png` in its folder, its meaning in `stickers/stickers.json` (`{<id>: {label: {zh, en, ja, ko}, when}}`: the picker shows the label in the chat's language, the model sees label + when to send it); read from the source (template / library — a gained character gets stickers added later too), the snapshot only when the source has none. The character sends one by writing `[sticker <id>]` on its own line; unknown ids are dropped; `[~image …]` / `[image …]` lines (image generation, an interface only) are dropped, never shown as text. Bench read / write: `GET /api/v1/souls/stickers?ref=` · `POST /api/v1/souls/stickers?ref=&id=` (PNG ≤ 2 MB) · `/stickers/meta {ref, id, label, when}` · `/stickers/remove {ref, id}` (Local; built-in templates read-only) | implemented |
| Model and billing | the bound run's provider if there is one, else the player's default; one call per message, metered like a turn; prompts in four languages `prompts/soul_chat.<lang>.json` | implemented |
| Tools (image generation, …) | set by the orchestration graph's chat node `tools`: `sticker` is live; `image.generate` (`[~image …]`, async), `image.crop`, `memo.write` are interfaces only (lint `orch.tool_off`) | partly implemented (10-16) |
| Three kinds of character (10-16) | `tpl` + `sid`, or one `ref`: `lib:<folder>` = a character in the library (the player's own, always open, `access: library`, its memory is that folder; thread `chats/lib__<folder>__<sid>.jsonl`) · `tpl:<template>/<sid>` = a world's character; `/chat/souls` lists the library's after the worlds' (`library: true`). A character tried first and gained later keeps one thread | implemented |

### 4.6 A character's own orchestration graph (10-16)

The graph the soul orchestration bench (Local only) edits. Same format as the world's `worldlines.orchestration/1`, plus `subject: "soul"`. Code: `src/neonrp/core/soul_orchestration.py`.

| What | Rule | Status |
|---|---|---|
| Node kinds | `chat` (a message in, 1–5 replies out; params `history` · `docs` · `doc_cap` · `max_bubbles` · `tools`) · `tick` (acting on its own; params `interval_min` 1–1440 · `daily_max` 1–288 · `proactive_daily` 0–20 · `prompt`, empty = the engine's) · `reflect` (folding memory; params `every` 0–100, 0 = off, the default · `keep` 1–40) · `in_world` (the beat a world's turn asks of it: not a node of this graph — the bench shows its real settings in the world, below). Each kind's real steps / params / ranges = `describe()` (`hooks` of `GET /api/v1/souls/orchestration`); the bench draws from it | implemented |
| Edges | `{id, from, to, on, when?}`; `on`: `{chat: "message"}` · `{tick: <name>}` (the foreground clock, every `interval_min`) · `{idle: <minutes>}` (only idle edges: the phone open and the player silent that long → one tick, once per quiet stretch; the player's next message starts a new one). `always` is read by nothing and no longer offered | implemented |
| Reflect | a reflect node with `every` ≥ 1: after every `every` ticks one cheap model call (≤ 400 tokens) reads `short-term-memo/recent_events.json` + the existing `long-term-memo/reflections.md`, answers `{"keep": [≤ 5 lines]}` → appended to `reflections.md`; short-term keeps its last `keep` events. A model failure changes nothing; the next tick tries again | implemented |
| In the world (in_world) | the character's real settings in its world: turn mode · variant (`turn.parallel.souls.per_soul[sid]`, else `default_variant`; legacy whenever the world is not v3) and which layer set it · the depth rules (silent skipped · gesture no model · speak / act under the variant · away always S-direct) · the prompt names its path reads (the private layer's marked by name, never their text). A library character: the world that links it (`?world=`, else the first). The variant is written by `POST /api/v1/souls/in_world {ref, variant, world?}` → author op `set_engine_setting` (the template's `template.json` `pack.engine`, merged into `game/meta/engine.json` at build; built-in templates are read-only). A turn's trace records the variant each character ran under in `timing.soul_variants` | implemented |
| Free time (tick) | `src/neonrp/core/soul_tick.py`. Only the player's own characters tick (the library's, or gained ones), only with a tick node in the graph, and **the player's switch is off by default** (it spends credits); no background: while the phone is in the foreground it asks `POST /api/v1/chat/tick {ref, catchup?}` once a minute and the engine keeps the pace (the tick node's `interval_min` · `daily_max`, by default once per 10 minutes · 24 a day); opening a thread catches up once. One tick = one model call (its documents + the routine for this time of day from its simple world + the last messages + its last doings) → one line in `trajectory/action_log.md` + one event in `short-term-memo/recent_events.json` (`by: soul.tick`); at most `proactive_daily` (default 2) messages a day into the thread on its own (`origin: tick`). `GET /api/v1/chat/tick?ref=` status · `POST /api/v1/chat/tick/settings {ref, on}` | implemented |
| Simple world view | `ambient/world.json` (`worldlines.soul-ambient/1`: setting · places ≤ 6 · routine morning / afternoon / evening / night · people ≤ 4 · clock real). A world's character without one gets one replicated from its world (the card's pitch · its town · the places around · the people its persona knows; never the GM's truth / notes / secrets); a library character needs one generated (one model call) or written. Template override `prompts/souls/<sid>/ambient/world.json` (author op `set_soul_ambient`). Endpoints `GET /api/v1/souls/ambient?ref=[&replicate=1]` · `POST /api/v1/souls/ambient {ref, world}` · `POST /api/v1/souls/ambient/generate {ref}` (Local) | implemented |
| Where it comes from (later wins) | the engine default (= the 10-15 phone) → the soul folder's `agents/orchestration.json` → the template override `prompts/souls/<sid>/orchestration.json` (this world only). A file is a whole graph or a patch `{nodes, remove, add}` | implemented |
| Gained characters | the graph is read from the source (template / library), memory from the player's snapshot: an edited graph reaches a character already taken home, its memory intact | implemented |
| Spec versions | a graph declares `targets: {soul_spec, world_spec}`; the engine reads `SOUL_SPEC = 1` / `WORLD_SPEC = 1`. Newer than the engine → block `orch.spec_mismatch`; the soul folder (`soul.json` `spec_version`, else `schema_version`) older than the graph wants → warn | implemented |
| Lint | `orch.subject` · `orch.spec_mismatch` · `orch.start` · `orch.node_kind` · `orch.edge` · `orch.param_range` (a param / idle minutes out of range) (block); `orch.tool_unknown` · `orch.tool_off` (a tool not live, or not one this kind calls: `memo.write` runs in tick / reflect only, a chat writes no memory) · `orch.on_unknown` · `orch.on_target` (tick / idle only start a tick node) · `orch.node_off` (reflect with every 0) · `orch.no_chat` (warn) | implemented |
| Write-back | a library character → its folder's `agents/orchestration.json`; a world's character → template author op `set_soul_orchestration {sid, graph}` (built-in templates are read-only: copy first); stored as a patch on what it gets without that file, `{}` = the same | implemented |

Endpoints (Local; the browser engine answers 404): `GET /api/v1/souls/catalog?lang=` (all three kinds in one table: `ref` · `kinds` (`library` / `independent` / `standalone` / `takeable`) · `worlds` · `chat` · `edit {to: library|template, id, writable}`) · `GET /api/v1/souls/orchestration?ref=` (`graph` · `base` · `default` · `layers` · `lint` · `hooks` · `edit`) · `POST /api/v1/souls/orchestration {ref, graph}` (403 read-only · 400 a block) · `POST /api/v1/souls/orchestration/lint {graph}`.

---

## 5. What the engine writes at runtime

### 5.1 Three-party isolation: the world cannot write a soul

| World-side attempt | Result | Code |
|---|---|---|
| `patch <character> prop=…` | refused: "her state is decided only by her own reply; the world side does not write it" | `src/neonrp/core/sdk.py` (patch check, `env.cls == "soul"`) |
| `mood <character> …` | refused: a soul-side op, never world-side | `src/neonrp/core/sdk.py` (`spec.scope == "souls"`) |
| file ops `write/edit/rm` into `souls/` | refused: the file-op sandbox is the world data folder (`game/`) only | `src/neonrp/core/worldfiles.py:normalize` |
| `move <character> <place>` | allowed, but goes through the move referee; on success the engine writes `run_state.json.location` | `src/neonrp/packs/rpg/atlas/move.py:move` → `src/neonrp/core/ontology.py:move_entity` |

A move proposed by the soul itself is also just a proposal and goes through the same referee before it lands.

### 5.2 What the engine writes

| Write | File | When | Status |
|---|---|---|---|
| soul settle: `mood`, `trust.player` (±2 per turn, clamped to -10…10), `intention` | `status` in `run_state.json` | after the turn, judged from the **final landed narration** (not the soul's own proposal); every question has a deterministic fallback: mood unchanged, trust 0, intention unchanged | implemented (the rpg pack's `settle` seam) |
| one event record `{turn, event, my_reaction, affect, …, by:"engine.settle"}` | `short-term-memo/recent_events.json` | same, one per soul that took part in the turn | implemented |
| the narration from her point of view | `short-term-memo/perceived.json` | after the turn, one per present soul | implemented |
| location | `run_state.json.location` | after a `move` passes the referee | implemented |
| who is on stage | `active_souls` in `.neonrp/playthrough.json` | scene understanding, each turn | implemented |
| missing agent manifest | `agents/manifest.json`, `agents/contracts.md` | self-healed the first time the soul agent is resolved | implemented |

Under the rpg pack, a soul's beat is "judge + speak": the judgment is closed-choice (attitude, register, urgency, whether to move), then one LLM call writes 1–3 sentences. Soul settle never lets an LLM write memory directly. Under the default older turn engine (the world-agent tool loop), the soul agent uses tools to write `recent_events.json`, `action_log.md` and `character/status.json` within its own `write_globs`; writes outside that scope are refused.

---

## 6. Smallest valid soul

The smallest soul that **can be cast and run**:

```
mina/
└── soul.json        {"sid": "mina", "name": "Mina"}
```

**Recommended minimum** (a voice, goals, and a place):

```
mina/
├── soul.json                    {"sid": "mina", "name": "Mina", "name_local": "米娜"}
├── soul.md                      # one ## Core Presence section
├── persona/motivations.json     {"motivations": ["keep the ferry running", "learn who burned the old bridge"]}
└── run_state.json               {"sid": "mina", "location": "<place id>", "status": {"mood": "calm"}}
```

`agents/manifest.json` can be left out; the runtime fills in the standard manifest.

Verified (in a temp directory, on a copy of the built-in `stoneford-elena` world):

1. The recommended minimum without `run_state.json`: `neonrp cast <path>` succeeds. The soul lands at `souls/mina-si-<hex>/`, a playthrough row is appended, and the instance is added to `active_souls`.
2. `neonrp validate` → playable, one warning (missing `agents/manifest.json`).
3. The engine's scene registry loads the soul (display name from `name_local`, goals from `motivations`). The first time the soul agent is resolved, `agents/manifest.json` is written automatically.
4. A soul with only `soul.json`: playable, three warnings (missing `soul.md` / `persona` / `agents/manifest.json`).
5. A playthrough row whose folder does not exist: **NOT playable** (blocker `soul-missing`).

Note: a soul without `run_state.json.location` is not at any place. Under the rpg pack only souls standing where the player stands take part in a turn, so give her a location if she should appear.

---

## 7. Validation

`neonrp validate` (run inside the world folder; `--json` for structured output) checks souls as follows (`src/neonrp/core/validation.py:check_world`):

| Check | Level | code |
|---|---|---|
| a soul registered in the playthrough has no `souls/<sid>-<instance_id>/` folder | blocker | `soul-missing` |
| missing `soul.json` (identity falls back to the sid) | warning | `soul-incomplete` |
| missing `soul.md` (no charter voice) | warning | `soul-incomplete` |
| missing `persona/` (no persona kernel) | warning | `soul-incomplete` |
| missing `agents/manifest.json` | warning | `soul-incomplete` |
| `run_state.json.location` not defined by any `game/towns/*/town_map.json` | warning | `location-dangling` |
| every `*.json` under `souls/` must parse | blocker | `json-parse` |
| a playthrough souls row missing a required field | blocker (the playthrough cannot be parsed) | playthrough layer |

Template lint (`neonrp template`) also checks that every soul the template references exists (`ref.soul`) and that the prompt layer only overlays allowed paths (`prompt.soul.data`).

---

## 8. Reference implementation

| Topic | Location |
|---|---|
| identity envelope, soul library, skeleton | `src/neonrp/core/souls.py:SoulMeta`, `read_soul_json`, `create_soul_dir`, `SOUL_SUBFOLDERS`, `archive_soul` |
| cast resolution and landing | `src/neonrp/core/placement.py:resolve_soul_dir`, `project_soul_multiagent`, `project_avatar_multiagent`, `project_soul_as_npc`, `load_soul_full` |
| CLI | `src/neonrp/commands/cast.py:cast`, `src/neonrp/commands/validate.py:validate` |
| playthrough souls rows | `src/neonrp/core/playthrough.py:SoulRef`, `_parse_souls`, `set_active_souls` |
| soul → agent (prompt, read/write scope) | `src/neonrp/core/soul_agent.py:resolve_soul_agent_data`, `_system_template` |
| agent manifest and self-heal | `src/neonrp/core/soul_authoring.py:build_manifest`, `ensure_soul_agent` |
| soul backends | `src/neonrp/core/soul_backend.py:resolve_soul_backend` |
| scene registry (which fields the engine reads) | `src/neonrp/packs/rpg/loaders.py:_load_souls` |
| per-beat judge + speak | `src/neonrp/packs/rpg/soul_step.py:soul_step`, `judge_soul` |
| post-turn settle (mood / trust / intention) | `src/neonrp/packs/rpg/soul_settle.py:settle_souls`, `_apply_patch` |
| narration from her point of view | `src/neonrp/core/soul_view.py:write_views` |
| the world cannot write a soul | `src/neonrp/core/sdk.py` (patch check), `src/neonrp/core/worldfiles.py:normalize` |
| move landing | `src/neonrp/packs/rpg/atlas/move.py:move`, `src/neonrp/core/ontology.py:move_entity` |
| what a template may overlay | `src/neonrp/template/__init__.py:SOUL_PROMPT_PATHS` |
| validation | `src/neonrp/core/validation.py:check_world`, `_SOUL_BUNDLE_WARN_PIECES` |
| reference souls | `src/neonrp/templates/stoneford-elena/souls/elena-si-elena0001/`, `rowan-si-rowan0001/` |
