# World spec (the world folder)

> Status labels: **implemented** = engine code reads or validates it; **convention** = engine code does not parse it, agents read it because their prompts tell them to; **in design** = documented or present in data, but no code reads it.
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

Based on the built-in world `src/neonrp/templates/stoneford-elena` (`souls/` is left out because it belongs to the soul spec):

```
<world>/
├── manifest.json                 optional · world language / pack name / prompt entries / triggers
├── agents/                       the world's own agents (where the runtime actually loads them)
│   ├── world-agent/
│   │   ├── agent.json            router / narrator agent (one is required; added automatically at launch if missing)
│   │   ├── system.md
│   │   └── voice.md              optional · narration voice for v3 turns
│   └── town-agent/ …             optional · sub-agents, one folder each
├── assets/                       optional · images
│   ├── cover.png
│   ├── art-style.md
│   ├── maps/<level>.webp|.json|.guide.png
│   └── places/<town>__<place>.webp
└── game/                         data directory
    ├── world/world_map.json      world level: town / dungeon / region nodes + roads
    ├── towns/<T###>/
    │   ├── town.json             town properties
    │   ├── town_map.json         graph of places inside the town (with a gate)
    │   ├── npcs.json             optional · lightweight NPCs
    │   ├── quests.json           optional · guild board
    │   └── facilities/*.json     optional · facility details
    ├── dungeons/<D###>/          optional · dungeons
    │   ├── dungeon.json
    │   ├── layout.json
    │   ├── rooms/<room-id>.json
    │   ├── encounter_tables.json
    │   └── loot_tables.json
    ├── locations/*.json          optional · flat places (merged into town places)
    ├── npc/*.json                optional · flat NPCs
    ├── item/**/*.json            optional · items (items/ also works)
    ├── lore/
    │   ├── story.md              main story / world introduction
    │   ├── rumors.md             rumors
    │   ├── notes.md              GM notes (characters cannot read)
    │   └── gm-truth.md           GM truth (characters cannot read)
    ├── rules/*.md                optional · rules text (checks, combat)
    ├── secrets/*.json            optional · secrets overlay
    ├── timeline/current.json     optional · current time / weather / active threads
    ├── player/                   player's starting state
    │   ├── profile.json  stats.json  wallet.json
    │   ├── equipment.json  inventory.json  flags.json
    │   ├── controller.json  journal.md
    │   └── assets/portrait.png
    ├── agents/manifest.json      optional · roster template for the world's agents
    └── meta/
        ├── run_state.json        player location / time / turn count
        ├── game-start.json       the opening
        ├── active-agent.json     current routing agent (engine-maintained)
        ├── prompt.json           optional · prompt entries
        ├── engine.json           optional · turn-engine config
        ├── variables.json  classes.json  entries.json
        ├── actions.json  triggers.json   optional · overlays for the five tables
        ├── roster.json           optional · cast sheet (world-agent only)
        ├── schedule.json         convention · scheduled events
        └── flag_aliases.json     convention · flag aliases
```

`.neonrp/` is managed by the engine (sessions, events, saves, `manifest.json`, `runtime_contract.json`, `playthrough.json`). It is **not** authored content. Built-in templates keep `runtime_contract.json` and `playthrough.json` at the folder root as their source shape; setup copies them into `.neonrp/` (`src/neonrp/core/template_assets.py:copy_souls_and_playthrough_from_template`, and the new-run migration in `src/neonrp/worlds.py`).

The data directory is `game` by default. The `data_dir` key in `.neonrp/runtime_contract.json` can rename it, but map navigation, the validator and the creation flow hard-code `game/` in a few places (`src/neonrp/core/place_nav.py:load_world_map`, `src/neonrp/core/validation.py:_known_locations`). **Keep it as `game`.**

---

## 3. Files one by one

### 3.1 Addressing rules (read first)

| Rule | Detail | Implementation |
|---|---|---|
| Town / dungeon / region ids | Must match `^[A-Z]{1,3}\d{2,4}$`, e.g. `T001`, `D001`, `R003`. An id that does not match is treated as a place id inside a town | `src/neonrp/core/place_nav.py:_TOWN_ID_RE` |
| Place address inside a town | `T001/gate_north` (town id + `/` + node id). A bare `gate_north` is looked up in the player's current town first, then in the first town that has it | `place_nav.py:qualify_location`, `split_location` |
| Dungeon room address | `D001/D001_R002` | `loaders.py:_load_dungeons` |
| Gate | A node with `type: "gate"` (or an id starting with `gate`). Moving between towns goes through gates | `place_nav.py:_gate_of` |

### 3.2 `game/world/world_map.json` — world level · implemented

Readers: `src/neonrp/packs/rpg/loaders.py:_load_world` (registry), `src/neonrp/core/worldmap.py:build_map_tree` (map tree), `src/neonrp/core/place_nav.py:load_world_map` / `_world_route` (checks for moves between towns).

| Field | Type | Required | Notes |
|---|---|---|---|
| `world_id` | str | recommended | id of the world entry; defaults to `"world"` |
| `name` | str | recommended | world name |
| `nodes[]` | list | yes (rpg) | world-level nodes |
| `nodes[].id` | str | yes | `T001` / `D001` / `R003` (see §3.1) |
| `nodes[].type` | str | yes | `town` / `city` / `village` / `dungeon` / `region` etc. In the registry only `town` becomes the town class; everything else becomes the region class (switched to the dungeon class when `game/dungeons/<id>/` exists). The route check between towns treats `town` / `city` / `village` as towns |
| `nodes[].name` | str | yes | display name |
| `nodes[].pos` | `[x, y]` | needed for map images | world-level coordinates. A level can only be drawn when all its children have coordinates |
| `nodes[].links` | list[str] | no | neighbouring node ids or road ids. Road ids that are never declared as nodes still count as connection points, so two towns that both link `R001` are connected |
| `nodes[].summary` / `state` / `lore` / `travel_info` / `region` | any | no | copied into entry props and the map tree |
| `routes[]` | list | no | roads: `{id, from, to, kind, distance, tags, state: {blocked}}`, drawn as edges in the map tree |
| `foreign_lands[]` | list | no | places beyond the map edge; go into the map tree's `frontier` |
| `parent_territory` | str | no | caption of the map tree's root |

```json
{
  "world_id": "W001",
  "name": "灰雾北境",
  "nodes": [
    { "id": "T001", "type": "town", "name": "石津镇", "pos": [12, 7],
      "summary": "河港贸易小镇,雾常年不散。", "links": ["R001", "R002"],
      "state": { "discovered": true, "danger_nearby": 2 } }
  ],
  "routes": [
    { "id": "R002", "from": "T001", "to": "D001", "kind": "trail", "distance": 6,
      "tags": ["foggy", "beasts"], "state": { "blocked": false } }
  ]
}
```

### 3.3 `game/towns/<T###>/` — towns · implemented

The folder name is the town id. The town should also appear as a node in `world_map.json`; otherwise the map tree reports `orphan`.

**`town.json`** — readers: `loaders.py:_load_towns` (every key except `id` goes into the town entry), `worldmap.py:build_map_tree` (`overview`, `tags`, `economy`, `laws`, `state`), `loaders.py:_load_variables` (`state.alert` → variable `town.alert`, 0–5).

| Field | Type | Notes |
|---|---|---|
| `name` | str | town name (defaults to the folder name) |
| `overview` | str | short introduction, goes into the narration context (the town class render template is `## 镇 {id} {name}\n{overview}`) |
| `state.alert` | int | the `town.alert` variable is registered only when this key exists |
| others (`tags`, `economy`, `laws`, `entry_points`…) | any | kept as they are |

**`town_map.json`** — readers: `loaders.py:_load_towns`, `worldmap.py:build_map_tree`, `place_nav.py` (move checks), `validation.py:_travel_graph_issues`.

| Field | Type | Required | Notes |
|---|---|---|---|
| `town_id` | str | recommended | defaults to the folder name |
| `nodes[].id` | str | yes | node id inside the town; its address is `T001/<id>` |
| `nodes[].name` | str | recommended | display name |
| `nodes[].type` | str | recommended | `gate` (every town on the world map needs at least one), `street`, `facility`, `dock`, etc. |
| `nodes[].links` | list[str] | recommended | neighbouring node ids in the same town. Every node should be reachable from some gate through links |
| `nodes[].pos` | `{x, y}` or `[x, y]` | needed for map images | town-level coordinates |
| `nodes[].parent` | str | no | puts this node inside another node (one level down); you enter and leave through the parent |
| `nodes[].facility_file` | str | no | path relative to the town folder, e.g. `facilities/inn.json`; its content goes into the place's `facility` prop |
| `nodes[].description` | str | no | place summary in the map tree |
| `state.discovered_nodes` | list[str] | no | when present, only the listed nodes count as discovered |

```json
{
  "town_id": "T001",
  "nodes": [
    { "id": "gate_north", "name": "北门", "type": "gate",
      "pos": { "x": 236, "y": 153 }, "links": ["main_street"] },
    { "id": "inn", "name": "河灯旅店", "type": "facility",
      "facility_file": "facilities/inn.json",
      "pos": { "x": 621, "y": 268 }, "links": ["main_street"] }
  ]
}
```

**`npcs.json`** — lightweight NPCs (played by the narrator; they have **no** agent of their own). Readers: `loaders.py:_load_npcs`, `worldmap.py:build_map_tree`.

| Field | Type | Notes |
|---|---|---|
| `npcs[].id` | str | required; becomes `T001/<id>` when it clashes with another entry |
| `npcs[].name` | str | a trailing role in parentheses is stripped to make the short name, e.g. `赫伦(公会管事)` → `赫伦` |
| `npcs[].role` / `traits` / `state` | any | go into the npc entry |
| `npcs[].location` | str | node id inside the town; defaults to the whole town |
| `npcs[].state.soul_ref` | str | when it points to a soul folder, the map shows the soul instead of this NPC |

```json
{ "town_id": "T001", "npcs": [
  { "id": "NPC003", "name": "米拉(旅店老板娘)", "role": "innkeeper",
    "traits": ["热情", "消息灵通"], "state": { "met": false }, "location": "inn" } ] }
```

**`quests.json`** — guild board; each row becomes one `job` entry with id `T001/<qid>`. Reader: `loaders.py:_load_quests`.

| Field | Type | Notes |
|---|---|---|
| `quests[].qid` (or `id`) | str | required |
| `title` / `tier` / `summary` | str / int / str | display and ordering |
| `state` | str | defaults to `available` |
| `reward` | `{gold, item: {id, name, qty}}` | used to build `reward_text` |
| `hooks` / `unlocks` / others | any | kept as they are (progress keys written during play are kept when read back) |

**`facilities/*.json`** — read only when a `town_map.json` node references it through `facility_file`. All keys except `facility_id` and `rumor_pool_ref` go into the place props.

### 3.4 `game/dungeons/<D###>/` — dungeons · implemented

Readers: `loaders.py:_load_dungeons`, `worldmap.py:build_map_tree`. The folder name should appear in `world_map.json` as a node with `type: "dungeon"`.

| File | Keys read |
|---|---|
| `dungeon.json` | `id`, `name`, `theme`, `danger`, `recommended_level`, `boss`, `state.{discovered, cleared}`, `entrance_from` |
| `layout.json` | `rooms[].{id, name, type, links, state}`, `state.current_room`. Rooms have no coordinates; the map lays them out by BFS |
| `rooms/<id>.json` | `name`, `description`, `features`, `state` |
| `encounter_tables.json` | `tables.<room-id>[] = {enemy, count, chance}` |
| `loot_tables.json` | `tables` (attached to the dungeon entry) |

When `discovered` / `danger` differ between `world_map.json` and `dungeon.json`, the map tree reports `conflict`.

### 3.5 `game/locations/` — flat places · implemented

Readers: `loaders.py:_load_locations`, `worldmap.py:build_map_tree`. Mainly used to add descriptions to town nodes. If a file matches a town node by id (normalized with `canonical_node`) or by name, only `summary`, `tags` and `notes` are copied over, and the file id is registered as an alias. If nothing matches, the file becomes a standalone place entry: `parent` defaults to the player's current town and `connections` are its exits. Scene folders `game/locations/<node>/location.json` are also supported.

```json
{ "id": "north-gate", "kind": "location", "name": "石津镇·北门",
  "summary": "歪斜的木栅门,湿冷的晨雾…", "connections": ["market-square", "old-road"] }
```

When the name has the form `town name·place name`, the map tree uses it to match a town node; if nothing matches, the map tree reports `unresolved`.

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

**`engine.json`** — this world's turn-engine config. Layer order: built-in defaults < pack.loop < the contract's engine block < `game/meta/engine.json` < `.neonrp/playthrough.json["engine"]` < environment variables (`src/neonrp/core/engine_config.py`). Example: `{"turn": {"mode": "v3"}}`.

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

### 3.16 In design

| Path | Status |
|---|---|
| `game/world/regions.json` | appears in older docs and agent permissions; engine code does not read it |
| `game/world/factions.json`, `game/world/economy.json` | read only when the pack composes the `factions` / `economy` mixin (`src/neonrp/packs/mixins/`); the default rpg pack does not read them |

---

## 4. Smallest valid world

**Bottom line:** `neonrp validate` passes even on an empty folder (it is judged `build`, so there is nothing to check). The smallest world the rpg pack can actually play is the five files below. You can leave out the router agent; it is added at launch.

```
mini/
├── manifest.json                    {"lang": "zh"}   (optional, but without lore a small world is detected as en)
└── game/
    ├── world/world_map.json
    ├── towns/T001/town.json
    ├── towns/T001/town_map.json
    └── meta/
        ├── run_state.json
        └── game-start.json
```

```json
// game/world/world_map.json
{ "world_id": "W001", "name": "灰岸",
  "nodes": [ { "id": "T001", "type": "town", "name": "渡口镇", "pos": [0, 0], "links": [] } ] }
```
```json
// game/towns/T001/town.json
{ "name": "渡口镇", "overview": "河边的小镇,雾很重。" }
```
```json
// game/towns/T001/town_map.json
{ "town_id": "T001", "nodes": [
  { "id": "gate",   "name": "镇门", "type": "gate",     "pos": { "x": 0,   "y": 0 },  "links": ["square"] },
  { "id": "square", "name": "广场", "type": "street",   "pos": { "x": 100, "y": 60 }, "links": ["gate", "inn"] },
  { "id": "inn",    "name": "旅店", "type": "facility", "pos": { "x": 200, "y": 40 }, "links": ["square"] } ] }
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
| `neonrp validate` (no `agents/`) | `✓ playable — build · 3 location(s)`; only JSON and entities are checked, not the opening |
| after adding the router agent (`ensure_playable_world` writes `agents/world-agent/` and `.neonrp/runtime_contract.json`) | `✓ playable — orchestrator · 3 location(s) · router 'world-agent'`, 0 blockers |
| `neonrp schema list entries` | 6 entries: `W001` world, `T001` town, `T001/gate` / `T001/square` / `T001/inn` place, `player` (at `T001/gate`) |
| `neonrp map status` | two levels, `world` and `T001`, both with image missing (expected) |
| `authored_opening` | with `manifest.json {"lang":"zh"}`: the Chinese opening + `① 进镇 / ② 先看看四周`; without it: English |
| `neonrp play "开始游戏"` (with one soul added, and the stub model that never calls a real model) | printed the opening narration and choices exactly as written, without calling the model; with no soul, the same cue went to the model |

Warnings: this minimal world gets about 11 `structure` warnings; see the first row of §6. They are expected.

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
| `game/meta/run_state.json: 'id' is a required property` (same for `world_map.json`, `town_map.json`, `town.json`, `player/*.json`, `facilities/*.json`) | layer 7 checks **every** JSON under `game/` against the entity schema, and these files are not entities. Built-in worlds get them too (stoneford-elena has 116) | safe to ignore; does not affect playability |
| `… is not of type 'string'` (`location` in `run_state.json`) | the entity schema's `location` is a string; `run_state` uses an object | safe to ignore |
| `Invalid JSON: Expecting ',' delimiter (line 2, column 1)` | JSON syntax error; the runtime silently skips the file and its content is lost | **blocker**; fix the syntax |
| `Duplicate id 'lamp' also appears in game/item/lamp.json` | two entity files share an id | **blocker**; make ids unique |
| `kind 'location' does not match path segment 'locations'` | `kind` must equal the first folder under `game/`. The built-in world's `game/locations/*.json` gets this warning too | change `kind` or the folder (the loader accepts both) |
| `id 'wrongname' does not match filename 'a'` | entity id must equal the file name | rename the id or the file |
| `Town 'T001' has nodes unreachable from any gate: cellar` | the node is not linked to a gate: characters can be placed there but cannot walk there | add `links` |
| `Town 'T002' is on the world map but has no gate node — travel in/out can't be staged` | a town on the world map has no gate | add a node with `"type": "gate"` |
| `Soul '<sid>' is at '<loc>', which no game/towns/*/town_map.json defines` | a soul's `run_state.location` points to a node that does not exist | change it to `T001/<node>` |
| `unknown audience token(s) ['friend']` | secret audience must be `gm` / `player` / `npc:` / `soul:` / `agent:` | fix the audience |
| `Secret 's1' is about 'item/ghost', which has no entity file` | the `game/<kind>/<id>.json` named by `about` does not exist | point it at an existing entry |
| `No game-start file — the world opens without an authored opening scene` | no `game/meta/game-start.json` | write one following §3.12 |
| `Router agent '<id>' has no agents/<id>/agent.json` | no router agent | added at launch; or write your own |
| `active-agent.json: active_agent '<id>' has no corresponding agent directory at …` | routing state names an agent that does not exist | launching once resets it |
| map: `! orphan: towns/T009 不在 world_map.nodes 里` ("not in world_map.nodes") | a town folder exists but the world map has no such node (the town is left out of the map tree) | add the node to `world_map.json` |
| map: `<address> 指向的 facilities/x.json 不存在` ("the referenced file does not exist") | wrong `facility_file` | fix the path |
| map: `locations/x.json「…」在层级地图里找不到对应节点` ("no matching node in the map hierarchy") | a flat place matched no town node | make the id or `town·place` name match |
| (no message) a small world's opening comes out in English | no lore and no `lang` | add `{"lang": "zh"}` to the root `manifest.json` |
| (no message) addresses resolve wrongly after naming a town `town1` | town ids must match `^[A-Z]{1,3}\d{2,4}$` | use ids like `T001` |

---

## 7. Reference implementation

| Topic | Location |
|---|---|
| Registry (five tables, normalized on read) | `src/neonrp/core/registry.py:load_registry`, `_apply_overlays`, `_load_class_folders`, `register`, `check_envelope` |
| rpg pack world loader | `src/neonrp/packs/rpg/loaders.py:load`, `_load_world`, `_load_towns`, `_load_locations`, `_load_dungeons`, `_load_quests`, `_load_player`, `_load_npcs`, `_load_items`, `_load_variables` |
| rpg built-in classes | `src/neonrp/packs/rpg/pack.py:CLASSES` (world / town / place / region / player / soul / npc / item / job / dungeon / road / room / carry / status) |
| Which pack is used | `src/neonrp/packs/__init__.py:resolve` |
| Map tree, images, hotspots | `src/neonrp/core/worldmap.py:build_map_tree`, `map_levels`, `hotspots`, `map_status`, `generate_map` |
| Addresses and movement | `src/neonrp/core/place_nav.py:qualify_location`, `split_location`, `_gate_of`, `load_world_map`, `_world_route` |
| Validation | `src/neonrp/commands/validate.py`, `src/neonrp/core/validation.py:check_world`, `validate_game_data`; entity schema `src/neonrp/schema/game_entity.schema.json` (can be overridden with `rules/game_entity.schema.json`) |
| Opening | `src/neonrp/core/opening.py:authored_opening`, `is_start_cue`, `start_cue`; `src/neonrp/core/output_lang.py:pick_opening` |
| Router agent repair | `src/neonrp/core/runtime_contract.py:ensure_playable_world`, `load_runtime_contract`, `get_startup_entry_agent` |
| Secrets | `src/neonrp/core/secrets.py:load_secrets` |
| Prompt entries / world language | `src/neonrp/core/adv.py:prompt_spec`, `entries_for`, `world_lang_raw` |
| Turn-engine config | `src/neonrp/core/engine_config.py` |
| Reference worlds | `src/neonrp/templates/stoneford-elena` (complete), `src/neonrp/templates/white-blank` (blank skeleton) |
