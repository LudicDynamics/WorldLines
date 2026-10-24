# World spec (the world folder)

> Status labels: **implemented** = engine code reads or validates it; **convention** = engine code does not parse it, agents read it because their prompts tell them to; **not read** = documented or present in data, but no code reads it.
> This page matches the current engine source (`src/neonrp/`). Field tables list only the keys the code actually reads. Other keys are allowed (open schema) and the engine keeps them as they are.

---

## 1. What it is

A **world** is the data layer of one setting: the map hierarchy (world → town / dungeon → place), towns, places, NPCs, items, lore text, the opening, and the world's own agent definitions. It is a plain folder, with most content under `game/`. Every turn the engine reads these files and normalizes them on the fly into one registry (`src/neonrp/core/registry.py:load_registry`) with five tables: variables / entries / classes / actions / triggers.

Layering (decided):

```
minimum runnable = pack (rules, inside the engine) + world (data, this page) + souls (characters, data)
template         = optional layer on top that binds the three
```

- The **pack** decides how the world is read. The default pack is `rpg` (`src/neonrp/packs/rpg/`). The folder layout on this page is the one the rpg pack's loader reads (`src/neonrp/packs/rpg/loaders.py:load`); `pct` (percentile investigation, BRP family) is built on rpg and reads the same layout. Other packs (`werewolf`, `monopoly`) rely only on generic class folders (see §3.9).
- **Souls** are characters with their own agents. They live under `souls/`; see [soul.md](./soul.en.md).
- The **template** does the binding (`playthrough.json`, which pack to use, prompts / plot packs); see [template.md](./template.en.md).

This page covers only the world folder itself.

---

## 2. Directory layout

Taken from the built-in world `src/neonrp/templates/stoneford-elena` (the one the `stoneford-town` template binds; `souls/` is left out, that layer belongs to the soul spec):

```
<world>/
├── manifest.json                 optional · world language / pack name / prompt entries / triggers
├── agents/                       the world's own agents (where the runtime really reads them)
│   ├── world-agent/
│   │   ├── agent.json            routing / narrating agent (one is required; added at startup if missing)
│   │   ├── system.md
│   │   └── voice.md              optional · narration voice for v3 turns
│   └── town-agent/ …             optional · sub-agents, one folder each
├── assets/                       optional · images
│   ├── cover.png
│   ├── art-style.md
│   ├── maps/<level>.webp|.json|.guide.png
│   └── places/<town>__<place>.webp
└── game/                         data directory
    ├── world/world_map.json      the world itself: name, routes, time; places are not listed here
    ├── locations/                the map = a folder tree, one folder per place
    │   ├── T001/location.json                a world-level place (town / dungeon / region)
    │   ├── T001/gate_north/location.json     a place in the town, address T001/gate_north
    │   ├── T001/<place>/<room>/location.json a place inside a place, drawn one layer down
    │   └── D001/D001_R001/location.json      a dungeon room
    ├── towns/<T###>/
    │   ├── town.json             town properties
    │   ├── town_map.json         optional · the town level's own keys (state.discovered_nodes, scale); no nodes in tree form
    │   ├── npcs.json             optional · lightweight NPCs
    │   ├── quests.json           optional · guild commissions
    │   └── facilities/*.json     optional · facility details
    ├── dungeons/<D###>/          optional · dungeons
    │   ├── dungeon.json
    │   ├── rooms/<room id>.json  a room's description and state
    │   ├── encounter_tables.json
    │   └── loot_tables.json
    ├── npc/*.json                optional · flat NPCs
    ├── item/**/*.json            optional · items (items/ also accepted)
    ├── lore/
    │   ├── story.md              main story / world introduction
    │   ├── rumors.md             rumors
    │   ├── notes.md              GM notes (souls cannot read)
    │   └── gm-truth.md           GM truth (souls cannot read)
    ├── rules/*.md                optional · rules text (checks, combat)
    ├── secrets/*.json            optional · secrets overlay
    ├── timeline/current.json     optional · current time / weather / active leads
    ├── player/                   the player's starting state
    │   ├── profile.json  stats.json  wallet.json
    │   ├── equipment.json  inventory.json  flags.json
    │   ├── controller.json  journal.md
    │   └── assets/portrait.png
    ├── agents/manifest.json      optional · template for the world's agent team
    └── meta/
        ├── run_state.json        player location / time / turn count
        ├── game-start.json       the opening
        ├── active-agent.json     current routing agent (maintained by the engine)
        ├── prompt.json           optional · prompt entries
        ├── engine.json           optional · turn engine config
        ├── variables.json  classes.json  entries.json
        ├── actions.json  triggers.json   optional · overlays for the five tables
        ├── roster.json           optional · cast list (only the world-agent sees it)
        ├── schedule.json         convention · timed events
        └── flag_aliases.json     convention · flag aliases
```

`.neonrp/` is managed by the engine (sessions, events, saves, `manifest.json`, `runtime_contract.json`, `playthrough.json`) and is **not** authored content. Built-in worlds and worlds shipped inside templates keep `runtime_contract.json` and `playthrough.json` at the root as source shapes, copied into `.neonrp/` when a run is set up (`src/neonrp/core/template_assets.py:copy_souls_and_playthrough_from_template`, and the new-run migration in `src/neonrp/worlds.py`).

The data directory is named `game` by default. `.neonrp/runtime_contract.json` can rename it with `data_dir`, but some code still hard-codes `game/` (e.g. the town-folder lookup in `src/neonrp/core/place_nav.py`). **Keep it `game`.**

---

## 3. Files one by one

### 3.1 Addressing rules (read first)

| Rule | Detail | Code |
|---|---|---|
| Town / dungeon / region id | Must match `^[A-Z]{1,3}\d{2,4}$`, e.g. `T001`, `D001`, `R003`. Ids that don't match are treated as in-town place ids | `src/neonrp/core/place_nav.py:_TOWN_ID_RE` |
| Place id | The folder name (an `id` in `location.json` that differs from it becomes an alias) | `src/neonrp/core/place_tree.py:_node_of` |
| In-town place address | `T001/gate_north` (town id + `/` + place id). A bare `gate_north` is looked up in the player's current town first, then in the first town that has it | `place_nav.py:qualify_location`, `split_location` |
| One layer deeper | `game/locations/T001/guild/hall/` still has the address `T001/hall`; the map draws it one layer below `guild`, and you go in and out through `guild` | `place_tree.py` (module header) |
| Dungeon room address | `D001/D001_R002` | `loaders.py:_load_dungeons` |
| Gate | A place with `type: "gate"` (or an id starting with `gate`). Travel between towns goes through a gate | `place_nav.py:_gate_of` |

### 3.2 The map: `game/world/world_map.json` + `game/locations/` · implemented

The map is a folder tree: **a place = a folder holding a `location.json`; the folder it sits in is the place it belongs to.** `world_map.json` describes the world itself and lists no places. When `world_map.json` has **no** `nodes` list the engine reads the folder tree (`src/neonrp/core/place_tree.py:is_tree`); the worlds of both built-in templates are written this way. Older worlds that still have a `nodes` list read as before, see 3.5.

Read by: `src/neonrp/core/place_tree.py` (`level_doc` / `folder_nodes`, turning the tree back into each level's map), `src/neonrp/packs/rpg/loaders.py:_load_world` / `_load_towns` (registry), `src/neonrp/core/worldmap.py:build_map_tree` (map tree), `src/neonrp/core/place_nav.py` (movement checks).

**`world_map.json`** (tree form):

| Field | Type | Required | Notes |
|---|---|---|---|
| `world_id` | str | recommended | id of the world entry; defaults to `"world"` |
| `name` | str | recommended | world name |
| `routes[]` | list | no | world-level roads: `{id, from, to, kind, distance, tags, state: {blocked}}`, drawn as edges |
| `foreign_lands[]` | list | no | places beyond the map's edge, become the map tree's `frontier` |
| `parent_territory` | str | no | caption for the map tree's root |
| `time` / `travel` / `layout` / `seed` | any | no | kept as is |

**`game/locations/<…>/location.json`**: only the place's own facts.

| Field | Type | Notes |
|---|---|---|
| `name` (or `name_i18n`) | str | display name |
| `type` | str | world level: `town` / `city` / `village` / `dungeon` / `region` etc. (only `town` registers as the town class, the rest as region; dungeon when `game/dungeons/<id>/` exists). In a town: `gate` (each town needs one), `street`, `facility`, `dock`, `road` etc. |
| `pos` | `[x, y]` or `{x, y}` | coordinates in the **parent** level; needed to draw the map. A level is drawn only when all its places have coordinates |
| `connections` | list[str] | ids of neighbouring places on the same level (world level may also name route ids). Every in-town place should be reachable from a gate |
| `summary` / `description` | str | summary, goes into the narration context and the map tree |
| `aliases` | list[str] | other names (names, old ids) |
| `tags` / `state` / `notes` / `region` / `travel_info` | any | kept as entry properties |
| `entry` | str | on a level's own `location.json` (e.g. `T001/location.json`): the place you land on when you come in from the level above |
| `ports.up` | list[str] | which parent-level routes (`routes[].id`) land here when you take them into this level |
| `isolated` | bool | a world-level place deliberately left without roads (a plot opens the way later); lint stops reporting `map.isolated` |
| `scale` | str | display and image prompts only: `world` · `region` · `town` · `district` · `building` · `indoor` · `dungeon` · `island` · `wilds` |
| `facility_file` | str | path relative to the town folder (`game/towns/<T>/`), e.g. `facilities/guild.json`; merged into the place's `facility` property |
| `enter_if` / `enter_refused` | list / `{zh,en,ja,ko}` | entry conditions (the trigger IF forms, all must hold) and the reason given to the host when the player is stopped; only player moves are checked |
| `audio` | object | ambient sound / music for this place (and places inside it), see template spec 6.7 |

Other files in the folder (`notes.md`, `scene_state.json`, `assets/`) travel with the place. `parent` / `within` need not be written and are not read: the folder alone says where a place sits.

```json
// game/locations/T001/location.json
{ "type": "town", "name": "Stoneford", "pos": [12, 7], "summary": "A river-port trading town, fog all year.",
  "state": { "discovered": true, "danger_nearby": 2 }, "connections": ["T002", "D001", "T004"], "entry": "gate_north" }
```
```json
// game/locations/T001/gate_north/location.json
{ "name": "North Gate", "type": "gate", "pos": { "x": 236, "y": 153 },
  "connections": ["main_street", "market-square"], "aliases": ["north-gate"],
  "summary": "A crooked wooden gate, cold morning fog…", "ports": { "up": ["R001", "R002", "R004"] } }
```

A template adds or changes a place of a built-in world with `world-overlay/game/locations/<T>/<place>/location.json` (whole-file replacement); `stoneford-town`, for instance, adds `road_camp` outside the north gate.

### 3.3 `game/towns/<T###>/` — towns · implemented

The folder name is the town id; there should be a world-level place of the same id in `game/locations/`.

**`town.json`** — read by `loaders.py:_load_towns` (every key except `id` goes into the town entry), `worldmap.py:build_map_tree` (`overview`, `tags`, `economy`, `laws`, `state`), `loaders.py:_load_variables` (`state.alert` → variable `town.alert`, 0–5).

| Field | Type | Notes |
|---|---|---|
| `name` | str | town name (defaults to the folder name) |
| `overview` | str | a paragraph that goes into the narration context (the `town` class renders as `## 镇 {id} {name}\n{overview}`) |
| `state.alert` | int | the `town.alert` variable is registered only if this key exists |
| others (`tags`, `economy`, `laws`, `entry_points`…) | any | kept as is |

**`town_map.json`** (optional) — in tree form it holds only the town level's own keys: `town_id`, `scale`, `state.discovered_nodes` (when present, only the listed places count as discovered), `entry`. The places themselves live under `game/locations/<T>/`.

**`npcs.json`** — lightweight NPCs (voiced by the narrator, **no** agent of their own). Read by `loaders.py:_load_npcs`, `worldmap.py:build_map_tree`.

| Field | Type | Notes |
|---|---|---|
| `npcs[].id` | str | required; becomes `T001/<id>` if it collides with another entry |
| `npcs[].name` | str | a role in trailing parentheses is stripped to form the short name, e.g. `赫伦(公会管事)` → `赫伦` |
| `npcs[].role` / `traits` / `state` | any | go into the npc entry |
| `npcs[].location` | str | in-town place id; defaults to the whole town |
| `npcs[].state.soul_ref` | str | if it points to a soul folder, the map shows the soul instead of this NPC |

```json
{ "town_id": "T001", "npcs": [
  { "id": "NPC003", "name": "米拉(旅店老板娘)", "role": "innkeeper",
    "traits": ["热情", "消息灵通"], "state": { "met": false }, "location": "inn" } ] }
```

**`quests.json`** — guild commissions; each row becomes a `job` entry with id `T001/<qid>`. Read by `loaders.py:_load_quests`.

| Field | Type | Notes |
|---|---|---|
| `quests[].qid` (or `id`) | str | required |
| `title` / `tier` / `summary` | str / int / str | display and sorting |
| `state` | str | defaults to `available` |
| `reward` | `{gold, item: {id, name, qty}}` | produces `reward_text` |
| `hooks` / `unlocks` / others | any | kept as is (progress keys written during play are kept when read back) |

**`facilities/*.json`** — read only when a place's `facility_file` references it; every key except `facility_id` and `rumor_pool_ref` goes into the place's properties.

### 3.4 `game/dungeons/<D###>/` — dungeons · implemented

Read by `loaders.py:_load_dungeons`, `place_tree.py:dungeon_rooms`, `worldmap.py:build_map_tree`. There should be a world-level place with `type: "dungeon"` of the same id in `game/locations/`.

| File | Keys read |
|---|---|
| `dungeon.json` | `id`, `name`, `theme`, `danger`, `recommended_level`, `boss`, `state.{discovered, cleared}`, `entrance_from` |
| `game/locations/<D###>/<room id>/location.json` | the room on the map: `name`, `type`, `connections`, `state`, `ports.up`. Without coordinates the map lays rooms out by BFS |
| `rooms/<id>.json` | `name`, `description`, `features`, `state` |
| `encounter_tables.json` | `tables.<room id>[] = {enemy, count, chance}` |
| `loot_tables.json` | `tables` (attached to the dungeon entry) |
| `layout.json` | optional: `state.current_room`, `entry`; the old form's `rooms[]`, see 3.5 |

If the world-level place and `dungeon.json` disagree on `discovered` / `danger`, the map tree reports `conflict`.

### 3.5 The old form: `nodes` lists and flat places (still accepted)

Worlds from before 1.0 write places in three spots: `world_map.json` `nodes[]` (world level), `towns/<T>/town_map.json` `nodes[]` (in town; fields `id / name / type / links / pos / parent / facility_file / description`), and flat `game/locations/*.json` (matched to an in-town place by id or `town name·place name`, adding `summary` / `tags` / `notes`); dungeon rooms in `layout.json` `rooms[]`. These worlds still play; lint reports `map.legacy_level` (warn).

To turn one into the folder tree (a script in the source repo):

```
uv run python scripts/migrate_map_to_folders.py <world dir>            # dry run: print the plan
uv run python scripts/migrate_map_to_folders.py <world dir> --write    # do it
```

It makes one folder per place, merges a flat record into the matching in-town place (the other id goes into `aliases`), then drops `nodes` from `world_map.json` and every `town_map.json` (other keys stay).

### 3.6 NPCs and items · implemented

| Path | Reader | Rule |
|---|---|---|
| `game/npc/*.json` | `loaders.py:_load_npcs` | needs `id`; `location` defaults to the current town; other keys become props |
| `game/item/**/*.json`, `game/items/**/*.json` | `loaders.py:_load_items` | needs `id`; `owner` or `location` becomes the parent |

```json
{ "id": "elena-locket", "kind": "item", "name": "艾琳娜的银坠",
  "summary": "一枚磨得发亮的银质小坠…", "owner": "elena" }
```

Note: **a lightweight NPC is not a soul.** The people in `npcs.json` / `game/npc/` are voiced by the narrator. A character that thinks for itself and keeps memories should be a soul (see [soul.md](./soul.en.md)). If you play a world that has no `.neonrp/manifest.json` yet, the launch flow converts `game/npc/*.json` into soul folders automatically, but only when there is no `souls/` folder yet (`src/neonrp/core/created_world.py:finalize_created_world`).

### 3.7 Lore and rules text · implemented

| Path | Reader | Use |
|---|---|---|
| `game/lore/story.md` | `loaders.py:load` → `reg.texts["lore"]` (first 4000 chars) | world introduction, goes into the narration context; also used to detect the world language |
| `game/lore/rumors.md` | same → `texts["rumors"]` (first 800 chars) | rumors |
| `game/rules/*.md` | same → `texts["rules"]` (first 3000 chars of each file) | read by the referee / combat layers |
| `game/lore/notes.md`, `game/lore/gm-truth.md` | `src/neonrp/core/soul_agent.py` (soul `deny_globs`) | GM-only; souls cannot read them; agents read them when their prompts say so |

### 3.8 `game/meta/` · implemented (unless marked)

**`run_state.json`** — player location and time. Readers: `loaders.py:load`, `_load_variables`, `worldmap.py:build_map_tree`.

| Field | Type | Notes |
|---|---|---|
| `location.node_id` | str | the player's town, e.g. `T001` |
| `location.subnode_id` (or `node`) | str | node inside the town; `T001/gate_north` also works |
| `location.display` | str | for display |
| `time.day` / `time.clock` | int / str | variables `time.day` (≥1, at most +1 per turn) and `time.clock` |
| `turn_count` | int | read-only variable `turn` |
| `travel` | object | written by the engine while on the road; produces a `road` entry |
| `party.player.location` | str | if it disagrees with `location`, the map tree reports `conflict` |

```json
{ "location": { "scope": "town", "node_id": "T001", "subnode_id": "gate_north",
                "node": "gate_north", "display": "石津镇·北门" },
  "time": { "day": 1, "clock": "08:30" }, "turn_count": 0 }
```

**`game-start.json`** — the opening; see §3.12.

**`active-agent.json`** — `{"active_agent": "world-agent", …}`, routing state maintained by the engine. If it names an agent that does not exist, validate warns (`src/neonrp/core/active_agent.py:validate_active_agent`).

**`prompt.json`** — world-level prompt entries. Layer order: the pack's `prompt` < root `manifest.json` `prompt` < `game/meta/prompt.json` (`src/neonrp/core/adv.py:prompt_spec`).

| Field | Notes |
|---|---|
| `entries[] = {id, text, when}` | `when`: `"always"` (goes into the system prompt), `"post"` (end of the system prompt), `{"keyword": [...]}` or a condition in the trigger IF grammar (injected when it matches) |
| `voice` / `rules` / `blocks` / `ops_docs` / `examples` | optional overrides |

```json
{ "entries": [
  { "id": "town_attitude", "text": "石津镇对新来的冒险者并不热情,但会记住肯付账和肯守约的人。", "when": "always" },
  { "id": "rowan_legend", "text": "碧石镇有个年轻冒险者罗文…", "when": { "keyword": ["罗文", "碧石"] } } ] }
```

**`engine.json`** — this world's turn-engine config. Layer order (later wins): builtin < pack (pack.loop) < contract (the contract's engine block) < orchestration (the orchestration template named in the template's `uses`) < world (`game/meta/engine.json`) < graph (the orchestration graph's step settings) < playthrough (`.neonrp/playthrough.json["engine"]`) < env (environment variables) (`src/neonrp/core/engine_config.py`; see template spec 8.2). Example: `{"turn": {"mode": "v3"}}`.

**Overlays for the five tables** — `variables.json`, `classes.json`, `entries.json`, `actions.json`, `triggers.json`, each shaped `{id: spec}`. Readers: `src/neonrp/core/registry.py:_apply_overlays` / `_load_triggers`. Write them with `neonrp schema register`, which validates before writing (`registry.py:register`). Setting an op to `null` in `actions.json` disables that op.

**The player's `/` actions** — the `actions` list of the same `actions.json`: `[{name, help, args_hint, prompt, label?, common?}]` (`name` in letters / digits / hyphens; `{args}` in `prompt` becomes what follows the command). The TUI makes them `/` commands; a web front end reads them from `GET /api/v1/play/engine/actions` for completion and its quick bar; a player sending 「/go 3车」 as text gets the prompt line too (`src/neonrp/core/play_menu.py`, `player_action.py:prepare`). `common: true` marks the common ones (on the quick bar); none marked → the first 4 in written order. `label` is the name shown (a string, or `{zh, en, ja, ko}`; without one, common verbs — go / talk / look / search … — get the engine's word in the run's language, others show `name`). The localization layer `i18n/<lang>/` overrides `help` / `prompt` / `label` as usual.

**Display words for enum keys (`game/meta/labels.json`, 10-15)** — `{"mood": {"yearning": {"zh": "思念", …}}, "disposition": {…}, "role": {"gate-guard": {…}}}`: the words the player sees for a character's mood, a relationship, an NPC's role (the localization layer overrides as usual; a value may be a plain string in the run's language). Not written: an English run splits the key into words, other languages show nothing. Reader: `src/neonrp/core/labels.py`.

**Names and descriptions of skills / attributes** — the keys of the player sheet's (`player/stats.json`) `attributes` / `skills` are not localized; the shown name and a one-line description come from the pack's rule table (rpg family: rows of `rules.json` `attrs` / `skills`, `{zh, en, ja, ko, desc: {zh, en, …}}`), which a world extends or overrides in `game/rules/rules.json` (deep-merged by key). A skill the world adds (e.g. 「定力」) gets its description by a `desc` there. Front ends read `GET /api/v1/play/engine/sheet` (`src/neonrp/core/sheet.py`).

**`roster.json`** — cast sheet. Engine code does not parse it. It is explicitly kept out of what souls can read, so only the world-agent sees it (`soul_agent.py`).

**`schedule.json`, `flag_aliases.json`** — **convention**: engine code does not parse them; sub-agents read them when their prompts say so.

### 3.9 Generic class folders (any pack) · implemented

Register a class with a `folder` in `game/meta/classes.json` and the engine loads every JSON file in that folder as one entry of that class, with no code (`registry.py:_load_class_folders`). Entry file shape: `{id, parent, links, props, aliases, rels}`. A `folder` like `game/player/inventory.json#items` means a list inside one file, one entry per item (`_load_list_store`).

```json
{ "quest": { "folder": "game/quests", "required": ["name"], "scope": "town",
             "render": "- {id} {name} 阶段{stage}",
             "props": { "stage": { "type": "int", "min": 0, "max": 5 } }, "mutable": ["stage"] } }
```

### 3.10 `game/secrets/` — secrets overlay · implemented

One file per host entry. Reader: `src/neonrp/core/secrets.py:load_secrets`.

| Field | Type | Notes |
|---|---|---|
| `about` | str | path of the host entry under `game/`, without the extension, e.g. `location/cafe-basement`; that file must exist |
| `audience` | list[str] | `gm` / `player` / `npc:<id>` / `soul:<sid>` / `agent:<id>` |
| `content` | object | merged back into the host entry on reveal (`summary_hidden` → `summary`, etc.) |
| `revealed_when` | list | machine-checkable conditions; ones with `judgment` are fuzzy conditions decided by the model |

A malformed secret is treated as GM-only and never revealed. It does not break play.

### 3.11 `game/player/` — player's starting state · implemented

The player is not a soul; the player owns this folder. Readers: `loaders.py:_load_player`, `_load_variables`, `src/neonrp/core/player_controller.py`.

| File | Keys read → variables |
|---|---|
| `profile.json` | `name` (or `display_name`), `class`, `background`, `summary`, `origin` |
| `stats.json` | `level`, `hp: {current, max}` → `player.hp`, `mp`, `attributes`, `skills[]` |
| `wallet.json` | `gold` / `silver` / `copper` → `player.gold`, etc. |
| `equipment.json` | `weapon`, `armor`, `accessories` |
| `inventory.json` | `items[] = {id, name, qty}` (the rpg `carry` class) |
| `flags.json` | `story_flags` → `flag.*`; `reputation` → `reputation.*` |
| `controller.json` | player control policy (`player_controller.py`) |
| `journal.md` | the player agent's journal |
| `assets/portrait.*` | portrait |

All optional. Without them the player is named `player` and the matching variables are not registered.

### 3.12 The opening, `game/meta/game-start.json` · implemented

Readers: `src/neonrp/core/opening.py:authored_opening`, `is_start_cue`; `src/neonrp/core/output_lang.py:pick_opening`; `src/neonrp/core/player_controller.py` (scene packet at game start); `src/neonrp/core/runtime_contract.py:get_startup_entry_agent`.

| Field | Type | Notes |
|---|---|---|
| `id` / `kind` / `name` | str | use `game-start` / `meta` / any name so the entity lint does not warn |
| `tags` | list[str] | player input that is **exactly** one of these tags (length ≥ 2) also counts as the start cue |
| `startup.opening_scene` | str or `{zh,en,ja,ko}` | opening narration |
| `startup.opening_choices` | list[str] / `{lang: [...]}` / `[{lang: text}]` | first choices; at most 4 are shown, numbered ①②③④ |
| `startup.read_first` | list[str] | **convention**: a hint to the world-agent listing files to read first |
| `agent_routing.entry_agent` | str | entry (router) agent; corrected at launch to the router agent that actually exists |
| `agent_routing.router_type` | str | only `sticky` is implemented |
| `world_info` | object | **convention**: world summary for agents |

How the opening happens:

1. When a new run starts, the launcher sends the start cue automatically (the TUI sends `开始游戏` / `Start the game` / `ゲーム開始` / `게임 시작` in the run's language, `src/neonrp/commands/tui.py`).
2. `is_start_cue` recognizes it (a built-in set of phrasings in several languages, or a match in `tags`).
3. If this run has had no turn yet and the world has an `opening_scene`, the engine's opening node (`src/neonrp/core/opening.py`) outputs `opening_scene` plus the choices as the host's first beat **without calling the model**; a later start cue is an ordinary line. This path runs in multi-character (soul team) turns.
4. Otherwise (no souls in the world, or no `opening_scene`), the opening goes to the entry agent as part of the scene packet, and the model narrates the opening based on it (this calls the model).

Language: chosen by `prompt_lang`; if that language is missing, the fallback order is run language → en → zh → any. The world language comes from, in order: `lang` in the root `manifest.json` → `lang` in `playthrough.json` → folder-name suffix (`-en` / `-ja` / `-ko` / `-zh`) → the text of `game/lore/*.md` (fewer than 20 Han characters means en) (`src/neonrp/core/adv.py:world_lang_raw`).

```json
{
  "id": "game-start", "kind": "meta", "name": "Stoneford Elena — 游戏开始引导",
  "tags": ["entrypoint", "start", "开始游戏", "开始冒险"],
  "startup": {
    "opening_scene": { "zh": "黎明前的雾像湿布一样压在驿路上……", "en": "The pre-dawn fog presses down on the post road…" },
    "opening_choices": { "zh": ["自由行动", "和守门人说话", "直接走向镇中央", "先观察雾中的街道和旅店灯光"],
                         "en": ["Act freely", "Speak with the gatekeeper", "Head straight for the town center", "First take in the fog-bound streets"] }
  },
  "agent_routing": { "entry_agent": "world-agent", "router_type": "sticky" }
}
```

### 3.13 The world's own agents · implemented

| Path | Reader | Notes |
|---|---|---|
| `agents/<id>/agent.json` | `src/neonrp/core/dispatcher.py:AgentSpec.from_json`, `src/neonrp/core/conversation.py` | the agent definition the runtime actually loads |
| `agents/<id>/system.md` | same (the file named by `system_prompt`) | system prompt |
| `agents/world-agent/voice.md` | `src/neonrp/packs/rpg/contract.py:_voice` (first 1500 chars) | narration voice for v3 turns; `narrative.md` is not used in v3 |
| `game/agents/manifest.json` | referenced as `world_agent_team.seeded_from` in `playthrough.json` when a new run is created | roster template for the world's agents; during play the playthrough is authoritative |
| `game/agents/contracts/*.md` | **convention** | IO contract notes for agents to read |
| `.claude/agents/*.md` | not read by the engine runtime | for external coding assistants |

`agent.json` fields:

| Field | Type | Default | Notes |
|---|---|---|---|
| `id` | str | — | must equal the folder name |
| `name` / `description` / `version` | str | — | |
| `system_prompt` | str | `system.md` | relative to the agent folder |
| `triggers` | list[regex] | `[]` | matched against player input when dispatching |
| `tags` / `priority` | list / int | `[]` / 0 | dispatch ordering |
| `context_limit` | int | 20 | |
| `permissions.{read_globs, write_globs, deny_globs, direct_write_globs}` | list[glob] | — | file permissions; deny wins |
| `defaults` / `llm` | object | — | temperature etc.; `llm` can give this agent its own model |
| `presentation_roles` / `presentation_hidden` | object / bool | — | labels shown in the UI |

Router agent: the first of `narrator` → `orchestrator` → `world-agent` that exists. If none exists, `ensure_playable_world` repairs it before each launch: a single agent is renamed to `world-agent`; with no agents at all it writes a minimal `agents/world-agent/`. It then writes `.neonrp/runtime_contract.json` and fixes `entry_agent` in `game-start.json` (`src/neonrp/core/runtime_contract.py:ensure_playable_world`).

```json
{ "id": "world-agent", "name": "World Agent", "system_prompt": "system.md",
  "context_limit": 30, "triggers": [".*"], "priority": 100,
  "permissions": { "read_globs": ["game/**", ".neonrp/**"],
                   "write_globs": ["game/meta/run_state.json", "game/lore/**", "game/player/*.json"],
                   "deny_globs": [] } }
```

### 3.14 Root `manifest.json` · implemented

Not the same file as `.neonrp/manifest.json` (the engine's project manifest).

| Field | Reader | Notes |
|---|---|---|
| `lang` (or `language` / `source_lang`) | `adv.py:world_lang_raw` | world language `zh` / `en` / `ja` / `ko` |
| `template` | `src/neonrp/packs/__init__.py:resolve` | which pack to use; takes precedence over `playthrough.json`; defaults to `rpg` (template layer, see [template.md](./template.en.md)) |
| `prompt` | `adv.py:prompt_spec` | same shape as `game/meta/prompt.json`, lower precedence |
| `triggers` | `registry.py:_load_triggers` | same shape as `game/meta/triggers.json`, lower precedence |

### 3.15 `assets/` — images · implemented

| Path | Reader | Notes |
|---|---|---|
| `assets/maps/<level>.webp` | `worldmap.py:map_image_path` | level image; a level is an address like `world`, `T001`, `D001`, with `/` replaced by `__` |
| `assets/maps/<level>.json` | `worldmap.py:level_fit`, `map_status` | the coordinate transform frozen when the image was made, `fit {px, py, x0, y0, sx, sy}`, plus `layout_hash`; when the layout changes the image is marked `stale` |
| `assets/maps/<level>.guide.png` | `worldmap.py:draw_guide` | layout guide given to the image model |
| `assets/places/<town>__<node>.{webp,png,jpg,jpeg}` | `worldmap.py:scene_image_path` | place scene image, e.g. `T001__inn.webp` |
| `assets/art-style.md` | `worldmap.py:art_style` | image style prompt |
| `assets/cover.png` | launcher / web runtime | world cover |

All images are optional; the world plays without any. Generate them with `neonrp map generate` / `neonrp map scene` (needs an image backend configured).

### 3.16 Not read by the engine / read only with a mixin

| Path | Status |
|---|---|
| `game/world/regions.json` | appears in older docs and agent permissions; engine code does not read it |
| `game/world/factions.json`, `game/world/economy.json` | read only when the pack composes the `factions` / `economy` mixin (`src/neonrp/packs/mixins/`); the default rpg pack does not read them |

---

## 4. Smallest valid world

**Bottom line:** `neonrp validate` passes even on an empty folder (it is judged `build`, so there is nothing to check). The smallest world the rpg pack can actually play is the files below. You can leave out the router agent; it is added at launch.

```
mini/
├── manifest.json                    {"lang": "zh"}   (optional, but without lore a small world is detected as en)
└── game/
    ├── world/world_map.json
    ├── locations/T001/location.json
    ├── locations/T001/gate/location.json
    ├── locations/T001/square/location.json
    ├── locations/T001/inn/location.json
    ├── towns/T001/town.json             (optional: the town's overview and alert)
    └── meta/
        ├── run_state.json
        └── game-start.json
```

```json
// game/world/world_map.json
{ "world_id": "W001", "name": "灰岸" }
```
```json
// game/locations/T001/location.json   one town and no road out: mark it isolated
{ "name": "渡口镇", "type": "town", "pos": [0, 0], "entry": "gate", "isolated": true }
```
```json
// game/locations/T001/gate/location.json
{ "name": "镇门", "type": "gate", "pos": { "x": 0, "y": 0 }, "connections": ["square"] }
// game/locations/T001/square/location.json
{ "name": "广场", "type": "street", "pos": { "x": 100, "y": 60 }, "connections": ["gate", "inn"] }
// game/locations/T001/inn/location.json
{ "name": "旅店", "type": "facility", "pos": { "x": 200, "y": 40 }, "connections": ["square"] }
```
```json
// game/towns/T001/town.json
{ "name": "渡口镇", "overview": "河边的小镇,雾很重。" }
```
```json
// game/meta/run_state.json
{ "location": { "node_id": "T001", "subnode_id": "gate" }, "time": { "day": 1, "clock": "08:00" }, "turn_count": 0 }
```
```json
// game/meta/game-start.json
{ "id": "game-start", "kind": "meta", "name": "开场",
  "startup": {
    "opening_scene":   { "zh": "雾从河面漫上来,你站在渡口镇的镇门下。", "en": "Fog rolls off the river; you stand under the gate of the ferry town." },
    "opening_choices": { "zh": ["进镇", "先看看四周"], "en": ["Walk in", "Look around first"] } },
  "agent_routing": { "entry_agent": "world-agent", "router_type": "sticky" } }
```

What we observed (this world, built in a temporary folder):

| Check | Result |
|---|---|
| `neonrp validate` (no `agents/`) | `✓ playable — build · 0 soul(s) · 3 location(s) · 1 entities`; only JSON and entities are checked, not the opening |
| after adding the router agent (`ensure_playable_world` writes `agents/world-agent/` and `.neonrp/runtime_contract.json`) | `✓ playable — orchestrator · 0 soul(s) · 3 location(s) · 1 entities · router 'world-agent'`, 0 blockers |
| `neonrp schema list entries` | 6 entries: `W001` world, `T001` town, `T001/gate` / `T001/square` / `T001/inn` place, `player` (at `T001/gate`) |
| `neonrp map status` | two levels, `world` and `T001`, both with image missing (expected) |
| `authored_opening` | with `manifest.json {"lang":"zh"}`: the Chinese opening + `① 进镇 / ② 先看看四周`; without it: English |

Warnings: this minimal world gets a dozen or so `structure` warnings (`location.json`, `run_state.json` and others are not entity files but are checked against the entity schema); see the first row of §6. They are expected.

For characters, put souls in the world (see [soul.md](./soul.en.md)) or add one with `neonrp cast <soul>`.

---

## 5. Checking a world

```
neonrp validate          # human-readable
neonrp validate --json   # {ok, playable, flavor, blockers[], warnings[], stats}
```

Exit codes: `0` playable (warnings allowed) · `1` blockers · `2` system error. Implemented in `src/neonrp/commands/validate.py` → `src/neonrp/core/validation.py:check_world`, which checks in layers:

| Layer | What it checks | Severity |
|---|---|---|
| 1 json | everything in `game/**`, `souls/**`, `agents/**`, `.neonrp/*.json` parses | blocker |
| 2 playthrough | `.neonrp/playthrough.json` matches its schema (template / soul layer) | blocker |
| 3 scaffold | the router agent exists; `active-agent.json` names a real agent | warning (fixed at launch) |
| 4 souls | soul folders named by the cast exist and are complete | missing folder = blocker, missing files = warning |
| 5 references | soul locations resolve against the town maps; every node is reachable from a gate; towns on the world map have a gate | warning |
| 5c secrets | secret files are well-formed and their host entries exist | warning |
| 6 opening | `game-start.json` exists (skipped in `build` state) | warning |
| 7 structure / constraint | JSON under `game/` checked against the entity schema (needs `id` / `kind` / `name`; `kind` must equal the first folder under `game/`; `id` must equal the file name) | warning; **duplicate id = blocker** |

Other tools:

| Command | Use |
|---|---|
| `neonrp map status [--world DIR]` | lists map levels, place counts, whether images are missing / stale, and map-tree issues (`orphan` / `missing` / `conflict` / `unresolved` / `coarse`) |
| `neonrp schema list [variables\|classes\|actions\|triggers\|entries] [--class C] [--json]` | shows the registry as the engine actually reads it |
| `neonrp schema register` / `unregister` | writes overlays into `game/meta/<table>.json` (validated first) |

---

## 6. Common errors

All messages below are actual validator or map-tree output (reproduced with a temporary world).

| Message | Cause | Fix |
|---|---|---|
| `game/meta/run_state.json: 'id' is a required property` (same for `location.json`, `world_map.json`, `town_map.json`, `town.json`, `player/*.json`, `facilities/*.json`) | layer 7 checks **every** JSON under `game/` against the entity schema, and these files are not entities. Built-in worlds get them too (stoneford-elena has 116) | safe to ignore; does not affect playability |
| `… is not of type 'string'` (`location` in `run_state.json`) | the entity schema's `location` is a string; `run_state` uses an object | safe to ignore |
| `Invalid JSON: Expecting ',' delimiter (line 2, column 1)` | JSON syntax error; the runtime silently skips the file and its content is lost | **blocker**; fix the syntax |
| `Duplicate id 'lamp' also appears in game/item/lamp.json` | two entity files share an id | **blocker**; make ids unique |
| `kind 'location' does not match path segment 'locations'` | `kind` must equal the first folder under `game/`. A `location.json` that writes `"kind": "location"` gets this (the built-in world too) | safe to ignore; or leave `kind` out |
| `id 'wrongname' does not match filename 'a'` | entity id must equal the file name | rename the id or the file |
| `Town 'T001' has nodes unreachable from any gate: cellar` | the place is not connected to a gate: characters can be placed there but cannot walk there | add `connections` |
| `Town 'T002' is on the world map but has no gate node — travel in/out can't be staged` | a town on the world map has no gate | add a node with `"type": "gate"` |
| `Soul '<sid>' is at '<loc>', which no game/towns/*/town_map.json defines` | a soul's `run_state.location` points to a place that does not exist (the tree form reports the same line) | change it to `T001/<place>` |
| `unknown audience token(s) ['friend']` | secret audience must be `gm` / `player` / `npc:` / `soul:` / `agent:` | fix the audience |
| `Secret 's1' is about 'item/ghost', which has no entity file` | the `game/<kind>/<id>.json` named by `about` does not exist | point it at an existing entry |
| `No game-start file — the world opens without an authored opening scene` | no `game/meta/game-start.json` | write one following §3.12 |
| `Router agent '<id>' has no agents/<id>/agent.json` | no router agent | added at launch; or write your own |
| `active-agent.json: active_agent '<id>' has no corresponding agent directory at …` | routing state names an agent that does not exist | launching once resets it |
| map: `! orphan: towns/T009 不在 world_map.nodes 里` ("not in world_map.nodes") | a town folder exists but the world level has no such place (the town is left out of the map tree) | add `game/locations/T009/location.json` |
| `game/locations: 渡口镇 has no route or link — nobody can walk there …` | a world-level place has no route and no connection | add `routes` / `connections`, or write `"isolated": true` if that is intended |
| lint `map.legacy_level` | the world still uses the old `nodes` form | it plays as is; to convert it to the folder tree see 3.5 |
| map: `<address> 指向的 facilities/x.json 不存在` ("the referenced file does not exist") | wrong `facility_file` | fix the path |
| map: `locations/x.json「…」在层级地图里找不到对应节点` ("no matching node in the map hierarchy") | a flat place matched no town node | make the id or `town·place` name match |
| (no message) a small world's opening comes out in English | no lore and no `lang` | add `{"lang": "zh"}` to the root `manifest.json` |
| (no message) addresses resolve wrongly after naming a town `town1` | town ids must match `^[A-Z]{1,3}\d{2,4}$` | use ids like `T001` |

---

## 7. Reference implementation

| Topic | Location |
|---|---|
| Registry (five tables, normalized on read) | `src/neonrp/core/registry.py:load_registry`, `_apply_overlays`, `_load_class_folders`, `register`, `check_envelope` |
| rpg pack world loader | `src/neonrp/packs/rpg/loaders.py:load`, `_load_world`, `_load_towns`, `_load_locations` (old-form flat places), `_load_dungeons`, `_load_quests`, `_load_player`, `_load_npcs`, `_load_items`, `_load_variables` |
| rpg built-in classes | `src/neonrp/packs/rpg/pack.py:CLASSES` (world / town / place / region / player / soul / npc / item / job / dungeon / road / room / carry / status) |
| Which pack is used | `src/neonrp/packs/__init__.py:resolve` |
| Place folder tree | `src/neonrp/core/place_tree.py`; map lint `src/neonrp/core/map_lint.py`; old-form migration `scripts/migrate_map_to_folders.py` |
| Map tree, images, hotspots | `src/neonrp/core/worldmap.py:build_map_tree`, `map_levels`, `hotspots`, `map_status`, `generate_map` |
| Addresses and movement | `src/neonrp/core/place_nav.py:qualify_location`, `split_location`, `_gate_of`, `load_world_map`, `_world_route` |
| Validation | `src/neonrp/commands/validate.py`, `src/neonrp/core/validation.py:check_world`, `validate_game_data`; entity schema `src/neonrp/schema/game_entity.schema.json` (can be overridden with `rules/game_entity.schema.json`) |
| Opening | `src/neonrp/core/opening.py:authored_opening`, `is_start_cue`, `start_cue`; `src/neonrp/core/output_lang.py:pick_opening` |
| Router agent repair | `src/neonrp/core/runtime_contract.py:ensure_playable_world`, `load_runtime_contract`, `get_startup_entry_agent` |
| Secrets | `src/neonrp/core/secrets.py:load_secrets` |
| Prompt entries / world language | `src/neonrp/core/adv.py:prompt_spec`, `entries_for`, `world_lang_raw` |
| Turn-engine config | `src/neonrp/core/engine_config.py` |
| Reference worlds | `src/neonrp/templates/stoneford-elena` (complete), `src/neonrp/templates/white-blank` (blank skeleton) |
