# Template spec (`worldlines.template/1`)

> Status: **implemented** = in the code, and this spec follows the code; **in design** = the field can be written and is read or checked, but has no full runtime effect yet.
> Related specs: [World spec](./world.en.md) · [Soul spec](./soul.en.md)

---

## 1. What it is

A playable game needs three things at minimum:

| Layer | What | Spec |
|---|---|---|
| **pack** | engine layer: agent loop, base rules, base prompts, ops | built-in `rpg` / `pct` / `werewolf` / `monopoly`, or a `pack.json` folder |
| **world** | data: places, NPCs, items, entries, registry (open schema) | [world.en.md](./world.en.md) |
| **souls** | who plays: the world's own souls, or souls brought in from elsewhere | [soul.en.md](./soul.en.md) |

**A template is an optional layer on top.** It does not change the engine core. It does two things:

1. **binds**: which world, which souls, which pack (+ mixins), which engine switches;
2. **adds**: a prompt layer, plot packs, a mode (ending × freedom), a card, asset slots, lint rules.

A template is also **the unit you publish**. Listing, sharing and "new game" all work on one `<id>.template/` folder. `build` turns it into an ordinary run folder, the kind of world the current engine already plays.

| Capability | Status |
|---|---|
| load / build / lint / discover / new run | implemented |
| world binding (builtin / path) + overlay + shuffle | implemented |
| fixed soul list + soul pools | implemented |
| prompt layer (world side + character overlays) | implemented |
| plots (stages / triggers / endings / reveal) | implemented |
| ui: slots / views / panels / named prompts / budget | implemented |
| Localization layers `i18n/<lang>/` (laid by the run's language + a glossary residue check, see 4.1) | implemented |
| filling asset slots by upload / generation | implemented (generation needs a configured image backend) |
| runtime effect of `mode.freedom` | in design (metadata + validation only) |
| `soul` / `item` / `ending` rules under `lint.assets` | in design (only `card.cover` is enforced; asset requirements are enforced through `ui.slots[].required`) |

---

## 2. Folder layout

```
<id>.template/
  template.json                 required. schema = "worldlines.template/1"
  world/                        optional. a world shipped inside the template (world.path points here)
  world-overlay/                optional. data patches laid over the world (default name; used if present)
  souls/<sid>/                  optional. a soul brought in (souls[].path points here)
  prompts/world.json | *.md     optional. world-side prompt layer
  prompts/souls/<sid>/…         optional. character prompt layer: may overlay only soul.md / persona/ / rules/ / agents/
  plots/<id>/plot.json          optional. plot packs (+ their own assets/)
  assets/                       optional. card cover etc.
  i18n/<lang>/…                 optional. localization layers: files at the template's paths (see 4.1); i18n/glossary.json the proper nouns
```

The actual trees of the four reference templates:

**stoneford-elena** (binds a built-in world, adds a plot, multiple endings)
```
template.json
assets/cover.png
plots/P10/plot.json
prompts/voice.md
prompts/world.json
```

**stoneford-market** (same world + the economy / factions mixins, open ending)
```
template.json
assets/cover.png
prompts/world.md
world-overlay/game/world/economy.json
world-overlay/game/world/factions.json
```

**stoneford-three-towns** (market plus a full ui: slots / views / named prompts / budget)
```
template.json
assets/cover.jpg
prompts/world.md
world-overlay/game/meta/variables.json
world-overlay/game/world/economy.json
world-overlay/game/world/factions.json
```

**werewolf-night-village** (ships its own world, `werewolf` pack, roles dealt anew each run)
```
template.json
prompts/judge.md
world/manifest.json
world/game/meta/table.json
world/game/seats/S01.json … S06.json
```

---

## 3. `template.json` fields

Entry point: `neonrp.template:load`. Every field is tolerant: a missing object reads as `{}`, a missing list as `[]`.

### 3.1 Top level

| Key | Type | Required | Default | Meaning | Read by | Status |
|---|---|---|---|---|---|---|
| `schema` | str | no | — | always `"worldlines.template/1"`; anything else → `schema` (warn) | `template:lint` | implemented |
| `id` | str | no | folder name minus `.template` | template id, used by discovery, new runs and run folder names | `template:load` | implemented |
| `version` | str | no | `""` | template version; also the hash of a brought-in soul that has none | `template:load` / `build` | implemented |
| `card` | object | yes (`title`) | — | the card, see 3.2 | `template:lint` / `build` | implemented |
| `mode` | object | no | `{}` → `ending: open` | see 3.3 | `template:loop_problems` | implemented |
| `world` | object \| str | yes | — | world binding, see 3.4; a string means `{"path": …}` | `template:world_dir` | implemented |
| `pack` | object \| str | no | `rpg` | engine layer, see 3.5; a string means `{"name": …}` | `Template.pack_name` | implemented |
| `souls` | list | no | `[]` = all of the world's own souls | the cast, see 3.6; an item may be a plain sid string | `template:draw_souls` | implemented |
| `prompts` | list[str] | no | `[]` | prompt files / folders, see 3.7 | `template:prompt_layer` | implemented |
| `plots` | list[str] | no | `[]` | plot folders (relative to the template), see §5 | `template:build` | implemented |
| `recipe` | object | no | `{backend:"", style:""}` | global settings for asset recipes, see §6 | `template.v3:ui` | implemented |
| `ui` | object | no | inherited from the pack | slots / views / panels / prompts / budget, see §6 | `template.v3:ui` | implemented |
| `slots` `views` `panels` `budget` | — | no | — | may also sit at the top level; same as inside `ui` | `template.v3:ui` | implemented |
| `lint` | object | no | `{}` | lint rules, see 3.8 | `template:lint` | partly implemented |
| `models` | object | no | `{}` | recommended models, see 3.9 | `template:new_run` | implemented |
| `seed` | str | no | run folder name | seed for soul pools and shuffles; fix it and every build gets the same cast and roles | `template:build` | implemented |
| `play_contract` | str | no | — | the experience the template promises: `"<contract id>@<version>"`, see the `contract` spec; lint checks against it | `template.contract` | implemented |
| `uses` | obj | no | inferred from the contract | the orchestration template this world plays: `{"template": "<template id>", "version": "<x.y>", "soul": "<characters' orchestration>", "params": {…}}`. A template = a world orchestration (a single beat …) + parameters; `soul` is a separate axis: how the characters present act (legacy · S-judge · S-direct · S-free), left out = the template's default. The open engine ships `one_beat` (`neonrp/orchestrations/`), a private layer may add more; a template the engine lacks falls back to `one_beat`, keeping `soul`. Left out = an old package: a world with a contract plays as its contract used to turn it on | `core.orch_templates` | implemented |
| `orchestration` | object \| str | no | the pack's default graph | the orchestration graph: a patch on the default `{nodes, remove, add}`, or a path to `orchestration.json`; written by the `set_orchestration` op | `core.orchestration:graph` | implemented |
| `player` | object | no | — | the player: `player.builder` = the player makes their own character before the run (panel player), see 3.11; absent = the run opens as before | `template.builder` | implemented |
| `opening` | object | no | — | opening CG: `{"cg": [{image, video?, caption?, camera?, prompt?, id?}, …]}`, played in order before the first beat, see 6.6 | `core.scene_cg` / `template:build` | implemented |
| `milestones` | bool | no | true for an `open-adventure` contract, else false | open-adventure milestones on / off; the author only says yes or no, the engine finds them itself (a new place · a commission completed · a day gone by) and settles them when the player leaves, see contract spec 5.1 | `core.milestones` | implemented (10-15) |
| `realtime_art` | string | no | `off` | the world's switch for 「画这一幕」 (drawing a beat live while playing, paid in platform credits): `off` = nothing drawn live (the author's pictures still show as 「看这一幕」) · `scene_only` = the place, nobody in it · `full` = the place and who is in it; any other value → `meta.realtime_art` (block). Off by default (niko 10-16: API pictures do not match the pre-made art; turn it on once a world is checked) | `core.scene_art` | implemented (10-16) |
| `forkable` | bool | no | false | whether an official template offers 「Make a copy」 (niko 10-17): true on the two the local edition ships (Greyoak House · Stoneford); every other official world can be played, not copied or exported (`not_forkable`). The author's own works (in the write store) can always be copied — no need to say it; not a bool → `meta.forkable` (block), on a template outside the default zone → warn. An official world fetched with an account gets `official: true` / `hub_ref` / `hub_revision` from the engine (authors do not write them) | `template.can_fork` | implemented (10-17) |
| `achievements` | list | no | `[]` | this template's own achievements `[{id, title, desc?, when, points?}]` (title / desc may be four-language); `when` is one condition from a list: `ending:<id>` · `flag:<key>` · `stage:<plot>:<n>` · `places:<n>` · `character:<sid>` · `milestone:<n>` · `quiz_perfect` — no if / else; an id may not repeat a built-in | `core.achievements` | implemented (10-15) |
| `audio` | object | no | the contract's + a guess from place names | sound: theme / bed / tense & crisis tracks / per place / where the template's own audio comes from, see 6.7 | `core/audio` | implemented (10-15) |

> Note: top-level `prompts` is the **prompt file list**. Named prompts (text templates for asset recipes) live under `ui.prompts`.

### 3.2 `card`

| Key | Type | Required | Meaning | Status |
|---|---|---|---|---|
| `title` | str | **yes** | card title; missing → `meta.card` (block). Build writes it to `name` in `game/meta/game-start.json` | implemented |
| `pitch` | str | no | one-line pitch; missing → `meta.card` (warn) | implemented |
| `cover` | str | no | cover image relative to the template; build copies it to the run's `assets/template-cover.<ext>` | implemented |
| `lang` | str | no | card language (`zh` / `en` / `ja` …) | implemented (metadata) |
| `tags` | list[str] | no | tags | implemented (metadata) |

### 3.3 `mode`

| Key | Values | Default | Meaning | Status |
|---|---|---|---|---|
| `ending` | `open` \| `single` \| `multi` | `open` | `open`: endings are optional; `single`: exactly one reachable ending; `multi`: at least two. Anything else → `meta.mode` (block) | implemented |
| `freedom` | `free` \| `semi` \| `guided` | — | how free the player is. Unknown value → `meta.mode` (warn) | in design (not read at runtime yet) |
| `reveal` | bool | `false` | when on, every plot must carry a `reveal` (the solution), else `loop.reveal` (block) | implemented |

### 3.4 `world`

| Key | Type | Meaning | Status |
|---|---|---|---|
| `builtin` | str | bind a built-in world shipped with the `neonrp` package (e.g. `stoneford-elena`) | implemented |
| `path` | str | a world folder inside the template, relative (e.g. `"world"`). `path` wins over `builtin` | implemented |
| `overlay` | str | overlay folder name, default `world-overlay` (used if present, no need to declare it), see §4 | implemented |
| `prompts` | `"replace"` | drop the world's own `game/meta/prompt.json` and use only the template's prompt layer (for templates whose prompts were extracted out of the world data). Unset = the world's prompts are merged underneath | implemented |
| `shuffle` | object \| list | deal a property anew each run: `{"folder": "game/seats", "prop": "role"}` shuffles the `props.<prop>` values of every `*.json` in that folder (werewolf roles, Avalon sides, murder-mystery parts). Several entries allowed | implemented |

Give at least one of `builtin` / `path`, else `ref.world` (block).

### 3.5 `pack`

| Key | Type | Default | Meaning | Read by | Status |
|---|---|---|---|---|---|
| `name` | str | `rpg` | base pack: a built-in name, a `pack.json` folder path, `module:PACK`, or a name on `NEONRP_TEMPLATE_PATH` | `packs:load` | implemented |
| `mixins` | list[str] | `[]` | mixins layered on (built-in `economy`, `factions`, or a folder holding `mixin.json`). The engine resolves the name `rpg+economy+factions` | `packs:compose` | implemented |
| `engine` | object | `{}` | an engine config fragment, **deep-merged into the run's `game/meta/engine.json`** at build | `template:build` → `core.engine_config` | implemented |

**Mixins need world data.** A mixin's rules live in the engine; its data lives in the world:

| Mixin | World file it needs | Closed schema it installs | Open classes |
|---|---|---|---|
| `economy` | `game/world/economy.json` (`currency` / `goods` / `markets` / `routes` / `caravan_every`) | `stock.<T>.<g>`, `price.<T>.<g>`, `inv.<g>`, `econ.index` | `caravan` |
| `factions` | `game/world/factions.json` (`factions` / `relations` / `rumors` / `premiums` / `routes` / `strike` / `bounty`) | `faction.<k>.power\|wealth`, `rep.<k>`, `rel.<a>.<b>` | `faction`, `rumor`, `quest` |

If neither the world nor the overlay has the file → `pack.mixin.data` (warn) and the mixin stays inert; the mixin's own views then fail to bind and report `schema.view` (block). The usual move is to put the data in `world-overlay/game/world/<mixin>.json`. At build each mixin's `install(run)` registers its variables in `game/meta/variables.json` and seeds them (only when missing; installing twice changes nothing).

**Common `pack.engine` keys** (full defaults in `neonrp.core.engine_config.DEFAULTS`):

| Key | Values | Engine default | Meaning | Status |
|---|---|---|---|---|
| `turn.mode` | `v2b` \| `v3` | `v2b` (the `rpg` pack's loop sets `v3`) | the turn loop. Lint accepts only these two, else `pack.engine` (block) | implemented |
| `turn.solve.structured` | `adv` \| `narrate` \| `json_object` \| `json_schema` \| `split` \| `split2` \| `parallel` \| `prose_json` | `adv` | how the world side writes its output. `narrate` = prose with tools first, then one state transition (the external contract stays ADV) | implemented |
| `turn.parallel.souls.default_variant` | `legacy` \| `S-judge` \| `S-direct` \| `S-free` | `legacy` (the `rpg` pack sets `S-judge`) | the shape of a soul's step | implemented |

### 3.6 `souls`

Each item is **one soul** or **a pool**:

```json
"souls": [
  {"sid": "elena", "role": "npc"},
  {"sid": "guest", "path": "souls/guest", "instance_id": "si-guest-1"},
  {"lib": "mira", "role": "companion"},
  {"pool": [{"sid": "a"}, {"sid": "b", "path": "souls/b"}, "c"], "pick": 2, "role": "npc"}
]
```

| Key | Type | Meaning | Status |
|---|---|---|---|
| `sid` | str | soul id. Without `path` / `lib` it must be native to the world (`souls[]` in the world's `playthrough.json`); with `lib` it may be left out (taken from the library soul's `soul.json`) | implemented |
| `lib` | str | **a soul in the character library** (`~/.worldlines/souls/<lib>/`). The template only links it: it is copied into a run when the run is built, so a change in the library reaches the next run. See the soul spec, "Character library" | implemented |
| `path` | str | folder of a brought-in soul (relative to the template). Build copies it to the run's `souls/<sid>-<instance_id>/` | implemented |
| `instance_id` | str | instance id of a brought-in soul; default `si-<sid>-<template id>` (cut to 48 chars) | implemented |
| `role` | str | `npc` (default) · `companion` · `player`; at most one `player` | implemented (a linked `player` becoming the run's player: in design) |
| `pool` | list | candidates (items may be plain sid strings) | implemented |
| `pick` | int | how many to draw, default 1; larger than the pool → `ref.soul.pool` (block) | implemented |

Rules (`template:draw_souls` / `build`):

- A sid appears once; a `lib` that is not in the library → `ref.soul` (block).
- A soul in a world is a link, not a copy: what differs per world (who they are here, relations, portrait) goes in the
  template's `prompts/souls/<sid>/` (overrides `soul.md` · `persona/` · `rules/` · `agents/` only) and `world-overlay/`; the library soul is never changed.
- If `souls` is given it is authoritative: world-native souls not listed stay on disk, inactive. If not given, all of the world's souls play.
- Pools are seeded by `seed` (default: run folder name). Rebuilding the same run keeps the cast; a new run draws again. A sid never appears twice.
- Lint does a reference build with **every** candidate present, so plot references to pooled souls resolve; a plot that names a soul only a pool can bring → `loop.pool` (warn).
- In a run that did not draw a soul, the plot's `to: soul` emits addressed to it are dropped for that run (the trigger's other effects still fire), recorded in `built.dropped_soul_emits`.

### 3.7 `prompts` (the prompt layer)

`prompts` lists files or folders relative to the template (a folder expands to its `.json` / `.md` / `.txt`, sorted; its `souls/` subfolder is not world-side).

| File | Parsed as |
|---|---|
| `*.json` | a prompt spec (`neonrp.core.adv` shape: `entries` / `rules` / `voice` …; may be wrapped as `{"prompt": {…}}`) |
| `*.md` / `*.txt` | one entry: `id` = file stem, `when: always`. A first line `<!-- when: post -->` or `<!-- keyword: Rowan, Jade -->` changes the trigger |

**Merge order** (later wins; written to the run's `game/meta/prompt.json`):

```
world's own prompt.json (dropped when world.prompts = "replace")  <  template prompts (list order)  <  each plot's prompt
```

**Character prompt layer**: files under `prompts/souls/<sid>/` are copied into that soul's folder at the same relative path, but only under `soul.md`, `persona/`, `rules/`, `agents/` (`SOUL_PROMPT_PATHS`). Any other path is soul data: lint reports `prompt.soul.data` (block) and build skips it.

### 3.8 `lint`

| Key | Type | Default | Meaning | Status |
|---|---|---|---|---|
| `level` | `publish` \| `draft` | see below | release level: missing / stale required assets, a missing cover and an over-budget turn go from warn to block | implemented |
| `assets` | object `{cls: [kind, …]}` | `{soul:[portrait], card:[cover]}` | asset requirements; `"a\|b"` = either | partly: only `card: [cover]` is checked; other keys are accepted and merged but not enforced yet (in design) |

When `level` is unset there is an asymmetry: the slot checks (`asset.missing` / `asset.stale` / `token.over`) behave as **publish**; the cover check `asset.card` blocks only when `"publish"` is written explicitly, otherwise it warns.

### 3.9 `models`

| Key | Type | Meaning | Status |
|---|---|---|---|
| `play` | str | recommended play model. `new_run` writes it into the new run's config only when it has the `provider/model` form (contains `/`); otherwise the user's default model is used | implemented |

### 3.10 Smallest valid template

Verified in a temp folder (binding the built-in world `stoneford-elena`):

```json
{
  "schema": "worldlines.template/1",
  "id": "min",
  "card": {"title": "Smallest template"},
  "world": {"builtin": "stoneford-elena"}
}
```

`neonrp template lint` prints:

```
[warn ] meta.card        card.pitch: no pitch (one line on the card)
[warn ] asset.optional   slots: 14 个可选槽位没填(有兜底的用兜底)
[warn ] token.unmeasured budget: 还没有回合——用这个模板玩一回合才量得出每回合 token
[warn ] asset.card       card.cover: no cover file
publishable — 0 block, 4 warn
```

(Some lint messages are currently emitted in Chinese only: "14 optional slots unfilled (fallbacks used where available)", "no turns yet — play one turn with this template to measure tokens per turn".)

`neonrp template build` prints: `built min → run-min  pack=rpg souls=elena,rowan plots=- prompt-overlays=0`.
Only `card.title` and `world` are truly required; the pack defaults to `rpg`, the souls to the world's own.

### 3.11 `player.builder` (character builder · panel player)

The template declares which fields and rules the player's character has; the screen renders them; the player makes a
character before the run, it is written into the run's player files, then a companion is picked and the run opens.
**Absent = the run opens as before** (the world's own `game/player/*`). Every text may be a string or `{zh, en, ja, ko}`.

```json
"player": {"builder": {
  "title": {"zh": "捏一个读者", "en": "Make your reader"},
  "fields": [
    {"id": "name",   "kind": "text", "label": {"en": "Name"}, "required": true, "max": 24,
     "to": "player/profile.json:name", "random": ["Mashiro", "Haibara"]},
    {"id": "look",   "kind": "text", "multiline": true, "to": "player/profile.json:appearance"},
    {"id": "origin", "kind": "choice", "required": true, "to": "player/profile.json:origin",
     "options": [{"id": "student", "label": {"en": "Student"}, "desc": {"en": "…"},
                  "grants": {"set":    {"meta/run_state.json:location": {"node_id": "T001", "subnode_id": "campus"}},
                             "append": {"player/stats.json:skills": [{"name": "Stealth", "value": 40}]},
                             "add":    {"player/stats.json:attributes.ji": 1}}}]},
    {"id": "traits", "kind": "multi", "min": 0, "max": 2, "options": [{"id": "calm", "label": "Calm"}], "to": "player/profile.json:traits"},
    {"id": "attrs",  "kind": "points", "total": 20, "min": 1, "max": 8, "exact": true,
     "stats": [{"id": "ti", "label": {"en": "Body"}}, {"id": "ji", "label": {"en": "Craft"}}],
     "to": "player/stats.json:attributes", "var": "player.attr"},
    {"id": "face",   "kind": "portrait", "options": [{"id": "a", "src": "assets/player/a.png"}]}
  ],
  "companion": {"from": ["cast"], "role": "companion", "pick": 1, "required": true,
                "cards": {"<sid>": {"tier": {"en": "S"}, "blurb": {"en": "…"}}}}
}}
```

| key | meaning |
|---|---|
| `fields[].id` / `kind` | field id (unique) · `text` \| `choice` \| `multi` \| `points` \| `portrait` |
| `portrait`: `options[]` · `default` | `{id, src}` (images inside the template); `default` = an option id: the player's face when a run starts without the builder, or a draft picked none (the world's own player portrait is kept); not one of the options → `player.builder` block (10-15) |
| `label` / `desc` / `placeholder` | display text |
| `required` | must be filled (`multi`: at least 1 unless `min` says otherwise) |
| `to` | where it is written: `<.json file under the game dir>:<dotted key>`. The engine writes there and knows no world's words; no `..`, no absolute path |
| `text`: `max` · `multiline` · `random` | max length (capped at 4000) · multi-line · picks for "random" |
| `choice` / `multi`: `options[]` | `{id, label, desc?, grants?}`; `multi` also takes `min` / `max` |
| `options[].grants` | effects of a picked option, same addressing: `set` (replace) · `append` (to a list) · `add` (to a number). The opening place = `set` on `meta/run_state.json:location` |
| `points`: `stats[]` · `total` · `min` / `max` · `exact` | each stat in `min..max`, the sum ≤ `total`; `exact: true` = every point must be spent |
| `points`: `var` | registers an int variable `<var>.<stat id>` per stat (in `game/meta/variables.json`, bound to the `to` file) |
| `portrait`: `options[].src` | an image inside the template (png / jpg / webp); the picked one is copied to `game/player/assets/portrait.<ext>` — the play screen's player avatar |
| `companion.from` | candidates: `cast` = the template's `souls` rows whose `role` is `companion.role` (default `companion`); add `library` = every soul in the character library (a pick joins the cast as a link) |
| `companion.pick` / `required` | how many (default 1) / must pick (default yes) |
| `companion.cards.<sid>` | extra card text: `title` · `tier` · `blurb` · any other key; name / portrait / intro come from the soul folder |
| `companion.rows` | `[{key, label}]`: labels and order for the other keys of `cards` (book / finisher / weakness …) |
| `steps` | optional: `[{id, title}]`; a field's `step` / `companion.step` puts it there; an empty step = the confirm-and-open page. Absent = fields → companion → open |
| `fields[].hint` | help text under a field |
| `labels` | optional names for the numbers an option's `grants.add` raises (when not a points stat): `{"<target> or dotted key or its last part": label}`, e.g. `{"attributes.int": {"en": "INT"}}`; the card says "brings INT +1". Points stats name themselves; with neither the key shows and lint warns (`player.builder`). `GET …/builder` gives every option with grants its computed `brings` |
| `derive` | optional derived values: `[{to, also?, base, per: {stat id: factor}, div?, label?}]` = `base + floor(Σ stat×factor / div)`, from the stats as written **after** the grants (an origin's +1 counts); `also` writes the same value elsewhere (e.g. `hp.max`); with a `label` it shows on the panel. E.g. HP = 6 + 体×2 → `{"to": "player/stats.json:hp.current", "also": ["player/stats.json:hp.max"], "base": 6, "per": {"体": 2}}`; resonance = 2 + floor(魂/3) → `{"base": 2, "per": {"魂": 1}, "div": 3}` |
| `text`: `generate` · `example` | `generate: true` (or a prompt) = a "generate" button: the configured model writes the field from what the player already filled in (**no world lore**: the player's life is their own, anything goes, and it becomes this run's reality); with no model / the stub, `example` stands in (a string or four-language object, one or several). Long text up to 4000 characters |
| stat ids | may be any string (`体` `技` …); the engine writes them as they are |

At run start (`new_run(ref, player=…)` / `POST /api/v1/play/session {slug: "tpl--<id>", player: {fields, companion}}`):

1. **Check first**: required fields, legal options, multi counts, points (range, total, `exact`), the companion is a candidate and the count fits. Fails → `BuilderError` / HTTP 400 `{ok: false, errors: [...]}` and **nothing is built**.
2. Companion candidates not picked leave the cast; a library pick joins as `{sid, lib, role}`.
3. The usual build, then each field's `to` in order, then the picked options' `grants`, the `var` variables, the portrait copy.
4. The whole sheet goes to `game/player/card.json` (`worldlines.player-card/1`: `values` · `labels` · `companion` · the `builder` declaration), self-contained in the run; the play screen's panel reads it.

A draft: `{"fields": {"<id>": value}, "companion": "<sid>" | [sid…]}`; `text` → string, `choice` / `portrait` → option id, `multi` → list of ids, `points` → `{stat: int}`.

HTTP: `GET /api/v1/local/templates/<id>/builder` (declaration + resolved companion candidates; images as flags, never paths) ·
`GET …/builder/image?field=&option=` / `?sid=` · `POST …/builder/check {fields, companion}` → `{ok, errors}` · `POST …/builder/generate {field, fields, lang}` → `{text, source}` ·
`GET /api/v1/play/engine/player-card` (the run's card; `live` = current values read back from `to`, they change in play). Lint: `player.builder` (block).

---

## 4. world-overlay

An overlay is a data patch laid over the world, so one world plus another set of data becomes another template (e.g. `stoneford-market` adds an economy and factions to `stoneford-elena`).

| Rule | Detail |
|---|---|
| Location | the folder named by `world.overlay`; by default `world-overlay/`, used if present |
| When | after the world is copied into the run, before shuffle / casting / mixin install / plot install |
| Granularity | **whole-file replacement**, not a JSON merge: an overlay `game/meta/variables.json` replaces the world's copy entirely |
| What it may hold | any world path: `game/world/<mixin>.json`, `game/meta/variables.json`, `game/meta/classes.json`, `assets/…` (maps / scenes), `souls/<sid>-<iid>/assets/…` (portraits of world-native souls) |
| Where assets land | filling a slot of a built-in world writes the image into the overlay (inside the template), never into the built-in world |
| Own world | a template with `world.path` usually needs no overlay; it edits its own `world/` |

Because files are replaced whole, the authoring API starts an overlay JSON edit from the world's existing copy so nothing is lost.

## 4.1 Localization layers `i18n/<lang>/` (implemented)

A template is written in one language (`card.lang`, the main language). `i18n/<lang>/` holds the template's
**localized version** in another language — not only a translation: place names, the line, people's names, item names,
the opening, rules text, prompts, trigger narration and endings may all become what is natural in that country /
language. **Ids never change** (sid, place ids, item ids, flag / variable names), so triggers and rules keep working.
Code: `neonrp.template.i18n`.

```
<id>.template/
  i18n/
    glossary.json                  proper nouns: what each thing is called in each language (lint's residue check)
    ja/template.json               the card (card.title / pitch / tags)
    ja/world/game/towns/T001/npcs.json
    ja/plots/P01/plot.json
    ja/prompts/world.md
    zh/…                           the main language may have a layer too (e.g. romanized display names → Chinese)
```

| Rule | |
|---|---|
| Paths | **The same path** as the template's file (`world/…`, `prompts/…`, `plots/…`, `template.json`); a path the template lacks is added as is (lint warn `i18n.orphan`) |
| JSON | **Deep-merged** into the template's: objects key by key; same-length arrays item by item (`{}` keeps an item); anything else (an array of another length, a string, a four-language object) is replaced. A localized file may carry only the strings that change; `neonrp.template.i18n.tidy` shrinks a whole translated copy to a text-only layer |
| Keys are not localized | A key is an id (a skill table keyed by name `skills: {Search: 60}` too, and the `"key": "skills.Search"` that points at it) and stays as authored; what changes is the name shown: where the pack has a name table (pct's `rules.json` `skills.<id>.{zh,en,ja,ko}`) the run shows the run's language; the `name` in a `{name, value}` list is a value and may be localized |
| Other files | `.md` / `.txt` / images replace the template's |
| When | A run started in a language lays its layer over a scratch copy of the template, then builds (`build(t, dest, lang=…)` / `new_run(…, lang=…)`); from then on the engine and the prompts see one language |
| Four-language objects | After the build every `{zh,en,ja,ko}` text object in the run is narrowed to `{<the run's language>: text}` (lang → en → zh → any); a name table with other keys (`{zh,en,ja,ko,base}`) is left alone |
| No layer | The run plays the main language; lint warns `i18n.missing` (only for languages declared in `template.json["i18n"]["langs"]` or already having a layer) |
| The run's language | Written to `run_state.json["output_lang"]`; `game/meta/template.json["i18n"]` records the lang and the layer files used |
| Cards | `meta()` returns `langs` (languages a run can be localized in, main first) and `cards` (the card in each) for a launcher to show in the player's language |

`glossary.json`:

```json
{"terms": [
  {"id": "soul:xiacheng", "zh": "夏澄", "ja": ["夏川 澄", "夏川"], "ko": "서하진", "en": ["Clara Shaw", "Clara"],
   "also": ["Xia Cheng"]}
]}
```

`also` = old transliterations of the main-language name (no run should carry them). For each language lint checks the
localized copy for the other languages' spellings and the `also` ones (`i18n.residue`).

Starting a run: `POST /api/v1/play/session {"slug": "tpl--<id>", "output_lang": "ja"}` builds it in the player's
language; the TUI uses its UI language. Command line: `neonrp template build <id> <dest> --lang ja`;
`neonrp template lint <id> [--i18n-deep]` prints each language's coverage, `--i18n-deep` also builds and lints each
localized version (its blocks come back as `i18n.build`).

---

## 5. Plots

`plots` lists `plots/<id>/` folders, each with one `plot.json` (+ optional `assets/`). Parsed, checked and installed by `neonrp.packs.rpg.plot`.

### 5.1 `plot.json` fields

| Key | Type | Meaning | Status |
|---|---|---|---|
| `id` | str | **required**. plot id (e.g. `P10`) | implemented |
| `title` | str | **required** | implemented |
| `stages` | list[str \| {name, goal}] | stage names; declares the variable `<id>.stage` (int, 0..n-1) for you. A stage may be `{name, goal}`: `goal` is one line for the player — what this stretch is about, no spoilers (a string or `{zh, en, ja, ko}`; the language layer translates it as usual), given by `GET /api/v1/play/engine/objective` only once the stage is reached; the `audio` of `{name, goal, audio}` is 6.7 | implemented (goal 10-15 · audio 10-15) |
| `stage_var` | str | the plot's stage is another variable (the world's, or one of this plot's `vars`, e.g. `night`); unset = `<id>.stage`. The engine emits `stage.changed` when it moves | implemented |
| `stage_cg` | object | stage cut-scenes `{stage index \| stage name: {image, video?, caption?, camera?, prompt?}}`, paths relative to the plot folder; slot `stage.cg:<id>.<n>`, see 6.6 | implemented |
| `classes` | object | custom classes (ClassSpec) | implemented |
| `vars` | object | custom variables `{name: {type: int\|float\|bool\|str, min?, max?, doc?}}`, stored in `game/meta/plot_vars.json` by default | implemented |
| `entries` | object | new entries `{id: {class: item\|place\|npc\|<custom>, name, parent, links?, props?, assets?, clue?}}`. A place needs its town as parent. `clue: true` = a clue (gained with `gained[].kind` `clue`; `entities?clue=1` gives only found ones); a whole class of clues says `clue: true` in `classes` | implemented (clue 10-15) |
| `triggers` | object | WHEN / IF / THEN / ELSE rules, see 5.2 | implemented |
| `endings` | object | `{eid: {title, kind?, assets?: {image, video}, image_prompt?}}` | implemented |
| `notes` | any | author notes | implemented |
| `prompt` | object | **template-only**. an appended prompt spec; entry ids get the prefix `<plot id>.`. Build merges it into the run's prompt; it is not part of the installed plot.json | implemented |
| `reveal` | object | **template-only**. the solution, per language (`{en: …}`). Build stores it at `game/plots/<id>/reveal.json`; `run_view` returns it **only after an ending is reached** | implemented |
| `truth_quiz` | object | the sandbox mystery's three truth questions at the settlement: `{questions?: [{q, options: [..], answer: <right index>} ×3], reward_soul?: <sid>}` (q / options may be four-language). When the contract requires it (`mystery-trpg`'s `settlement.truth_quiz: required`) **`questions` must be written**, in all four languages (`{zh, en, ja, ko}` or `i18n/<lang>/` layers); `reward_soul` = who comes home with full memory on three right (a sid of the cast), default the companion at the ending. Without `questions` the engine writes three from the solution (`reveal`, else `gm-truth.md`) — only a fallback for the open zone / older templates. Lint `contract.truth_quiz` · `truth_quiz.*` (reviewed block, open warn). See contract spec §3 §4 §5.1 | implemented (10-15; required 10-16) |

Asset kinds (keys of `assets`): `image` `portrait` `video` `audio` `bgm` `sfx`; paths must be relative and stay inside the plot folder.

### 5.2 Triggers

```json
"P10.clue": {
  "when": {"text": "both"},
  "if":   [{"text": ["amulet", "crest"]}],
  "once": true,
  "then": [{"to": "var", "var": "P10.stage", "set": 1},
           {"to": "soul", "who": "Elena", "text": "The crest gives her a headache, as if she has seen it.", "important": true}]
}
```

| Part | Forms (as used by the reference templates) |
|---|---|
| `when` | `{"text": "player"\|"narration"\|"both"}` · `{"entry": "T004/chapel", "event": "enter"}` · `{"var": "player.hp"}` · `{"check": "First Aid"}` (the player rolled a check of that name this turn: a `/First Aid` command, `[dice First Aid]`, an rpg roll whose reason opens with the attribute; any language's name) |
| `if` | `{"text": [keywords…], "in"?: "player"}` · `{"var": "P10.stage", ">=": 1}` · `{"var": "a", ">": {"var": "b"}}` (against another variable) · `{"check": "First Aid", "passed": true, "level"?: "crit"}` · `{"who": "Hane", "at": "player", "is"?: false}` (at: player = where the player stands; is: false negates) |
| `then` / `else` | `{"to": "var", "var", "set"}` · `{"to": "narration", "text"}` · `{"to": "soul", "who", "text", "important"?}` · `{"to": "end", "ending": "E10"}` · `{"to": "move", "who": <soul>, "place"}` (the world moves a character) · `{"to": "status", "name", "remove"?: true}` (the player's status on / off) · `{"to": "audio", "mood"?, "bgm"?, "ambient"?}` (music / bed from now on, 6.7) |
| `once` | fire once only |
| `needs` | `<soul name>`: when this run did not cast that character, the whole trigger goes |

A place's way in lives in its `location.json`: `"enter_if": [trigger-style conditions…]` (all must hold; `at` reads where the player stands before the step) + `"enter_refused": {zh, en, ja, ko}` (the reason the host gets). Only the player's move_to is stopped (in verify).

### 5.3 Endings and `mode.ending`

- Reachable = at least one trigger branch emits `{"to": "end", "ending": …}` for it. The pack's own triggers (e.g. werewolf's "village wins / wolves win") count too, as `kind: rule`.
- `kind`: `true` / `alt` / `fail` / `fallback` / `rule`. In `single` / `multi` mode, no `fail` / `fallback` / `rule` ending → `loop.exit` (warn).
- One trigger branch emitting two different endings → `loop.distinct` (block): endings need different conditions.
- A plot with endings should have `stages` and a `prompt`, else `loop.guide` (warn).

---

## 6. Asset slots / ui

Effective ui = **pack (+ mixins) declarations < the template's `ui` (and top-level `slots` / `views` / `panels` / `budget`)**, computed by `template.v3:ui` and merged by `packs:merge_ui`:

| Part | Merge key | Removal |
|---|---|---|
| `slots` | `(cls, slot)` | `{"cls", "slot", "remove": true}` |
| `views` / `panels` | `id` | `{"id", "remove": true}` |
| `prompts` | key | value `null` |
| `budget` | replaced whole | — |

Build writes the effective ui to the run's `game/meta/template.json["ui"]`; the play UI reads views from there.

### 6.1 `slots` (asset slots)

| Key | Values | Meaning |
|---|---|---|
| `cls` | a registry class (`soul` / `place` / `item` / `caravan` / `faction` …) or the virtual class `level` (a level of the map tree) | the class the slot hangs on |
| `slot` | str | slot name (`map` / `portrait` / `sprite` / `scene` / `icon` / `emblem` …) |
| `kind` | `image` \| `icon` \| `audio` | asset kind |
| `required` | `publish` \| `optional` | `publish` = needed to publish |
| `recipe` | built-in `map` / `scene` / `portrait` / `sprite`, or a name in `ui.prompts` | generation recipe; neither → `schema.slot` (block) |
| `ratio` | `"3:2"` / `"3:4"` / `"16:9"` … | generation size |
| `scope` | `"class"` | one image shared by the whole class (instance id `*`) |
| `hotspots` | bool | the map has clickable hotspots |
| `from` | slot name | derived from another slot (sprite from portrait) |
| `fallback` | str | what is shown when unfilled |

`rpg` pack default slots: `level.map` (publish), `soul.portrait` (publish), `soul.sprite`, `place.scene`, `item.icon` (optional). `economy` adds `caravan.icon` (class-level), `factions` adds `faction.emblem`.

**Slot instance id**: `<cls>.<slot>:<instance>`, e.g. `level.map:T001`, `soul.portrait:elena`, `caravan.icon:*`; plus template-level `card:cover`, `plot:<rel>:ending:<eid>`, `plot:<rel>:entry:<id>` (a plot entry no class slot covers, e.g. guixiang's `cg` illustrations; the row carries `cls` / `parent`), `opening.cg:<n>` and `stage.cg:<plot>.<n>` (see 6.6).

**Where an image is written** (`template.v3:_target`; always inside the template folder, escapes are refused; PNG / JPEG / WebP, ≤ 8 MB):

| Slot | Destination |
|---|---|
| `card:cover` | `assets/cover.<ext>`, and `card.cover` is updated |
| ending art | `plots/<rel>/assets/ending-<eid>.<ext>`, recorded in plot.json |
| an entry a plot defines | `plots/<rel>/assets/entry-<id>.<ext>`, recorded in plot.json |
| opening CG | `assets/opening/cg-<n>.<ext>`, recorded in `opening.cg[i].image` |
| stage cut-scene | `plots/<rel>/assets/stage-<n>.<ext>`, recorded in plot.json `stage_cg` |
| a brought-in soul | `souls/<sid>/assets/<slot>.<ext>` |
| a world-native soul | `world-overlay/souls/<sid>-<iid>/assets/<slot>.<ext>` |
| the player (`cls: player`, e.g. `player.portrait:player` = the play screen's player avatar) | `world-overlay/game/player/assets/<slot>.<ext>` (lands in the run's `game/player/assets/`, where the character builder's portrait goes too) |
| a map level | the map image's own path inside the overlay (the current layout transform is frozen next to it, so hotspots follow the data) |
| a scene | `world-overlay/assets/places/<place>.<ext>` |
| other class instances / class-level | `world-overlay/assets/<cls>/<slot>/<inst or _class>.<ext>` |

**Stale**: assets are content-hashed by their resolved inputs (prompt etc.); when the inputs change, a filled image is marked stale.

### 6.2 Named `prompts` and `recipe`

A named prompt is a text template for recipes. Placeholders are `{name}`, where name is:

- a registered variable (e.g. `{town.alert}`, `{time.day}`);
- recipe context `PROMPT_CTX`: `world.name` `level.name` `nodes` `style` `place.name` `place.summary` `soul.name` `soul.persona` `time.day` `time.clock`;
- an instance property `{inst.<prop>}`.

An unknown placeholder in `ui.prompts` → `prompt.placeholder` (block); an unknown dotted placeholder inside a prompt-layer entry → `prompt.placeholder` (warn; it is printed as is).

`recipe`: `{"backend": "…", "style": "dark watercolor, fog"}`. `style` fills `{style}`; unset, the world's art style is used. An instance's own `props.image_prompt` beats the class recipe.

### 6.3 `views` (data views)

| Key | Meaning |
|---|---|
| `id` | view id |
| `title` | localized `{zh, en, ja}` |
| `bind` | variable patterns: exact name, `*` for one segment, `{town}` = the player's town; or `class:<cls>` to list that class's instances (last 30) |
| `widget` | `table` `gauge` `bars` `meter` `sparkline` `list` `number`; unknown → `schema.view` (warn) |
| `actions` | ops clickable from the view; no handler → `schema.view` (block) |
| `layout` | `{area: right\|center\|studio, order, cols?, range?}` |

A bind matching no registered variable → `schema.view` (block). `rpg` default views: `alert`, `purse`.

### 6.4 `panels`

What a layer or a tool draws (formation, map, character sheet). The pack gives defaults; a template may override the prompt and the format.

| Key | Meaning |
|---|---|
| `id` | panel id |
| `tag` | block tag in the model output (e.g. `formation`) |
| `tool` | the tool that draws it (e.g. `map`, `sheet`) |
| `format` | `text` \| `json` (with `schema`) \| `image` |
| `prompt` / `schema` / `layout` | how to write it / its structure / where it sits |

`rpg` default panels: `formation`, `map`, `sheet`.

### 6.5 `budget`

Per-turn world-side token budget, default 20000. Lint measures the average from the turn traces of recent local `tpl-<id>-*` runs: no turns → `token.unmeasured` (warn); over budget → `token.over` (block at publish level); above 80 % → `token.near` (warn).

### 6.6 Staging: opening / cut-scenes / plot pictures → engine events

There is no separate staging protocol: the slots decide which assets exist, and the engine says what happens **now** on the turn's event stream (local `/events`, the browser engine's `onEvent`, `/api/v1/play/engine/beats`); the front end plays it.

| Slot | When | Event |
|---|---|---|
| `opening.cg:<n>` (`template.json` `opening.cg`) | the opening, before the first beat, in order | the opening `plan.beat` carries `cg: [{slot, image, video?, caption?, camera?, template}]`; `run_view` also returns `opening` |
| `stage.cg:<plot>.<n>` (plot.json `stage_cg`) | the plot's stage variable reaches stage n | `stage.changed {plot, var, from, to, name, cg?: {slot, …}}` |
| `plot:<rel>:entry:<id>` (the entry has `assets.image` and a place as `parent`) | the player first walks into `parent` (once per run) | `show {slot, template, cls, inst, label, by: "arrive"}` |
| any slot of the template | the host writes `[~show <slot \| entry id \| name>]` in the prose | `show {…, by: "host"}`; a slot the template does not have is refused (a `tool` event stays) |

The `show` op is registered only when the template has pictures to show at a moment (the three kinds above), and the prompt lists them; other worlds' prompts are unchanged. Files: `GET /api/v1/local/templates/<template>/assets/file?slot=<slot>[&part=video]`.

**A picture per companion (10-15)**: an ending picture, an opening CG or a stage cut-scene that draws one particular companion switches to the version of the companion the player picked in the builder (`companion` in `game/player/card.json`; no builder → the run's only companion); no version for them → the generic one.

```jsonc
// plot.json
"endings": {"E02": {"title": "…", "assets": {"image": "assets/ending-E02.webp",
                                            "variants": {"isse": "assets/ending-E02-isse.webp", "yomi": "assets/ending-E02-yomi.webp"}},
                    "image_shows": "isse"}}           // optional: whom the generic picture actually draws (lint reminds the others lack theirs)
"stage_cg": {"1": {"image": "assets/stage-1.webp", "variants": {"yomi": "assets/stage-1-yomi.webp"}}}
// template.json
"opening": {"cg": [{"image": "assets/opening/cg-7.webp", "variants": {"isse": "assets/opening/cg-7-isse.webp"}}]}
```

- Slots: `<slot>@<sid>` (`plot:plots/P01:ending:E02@yomi`, `opening.cg:7@isse`, `stage.cg:P01.1@yomi`), listed in `asset_slots` (rows carry `variant` / `variant_of`); an upload / generation into one is recorded under `variants` (file name = the generic one + `-<sid>`).
- Files: `assets/file?slot=<generic slot>&variant=<sid>` (no variant while the bound run plays this template = the run's companion); that version not filled yet → the generic one.
- A run: `run_view` carries `companion`, and `opening.cg[]` / `plots[].stage_cg[]` / `plots[].endings.<id>.slot` / `ending.slot` are already this run's; the opening `plan.beat.cg[]` and `stage.changed.cg` carry `{slot, image, variant}` (`variant: null` = generic); the settlement's `ending_cg = {id, slot, variant, image}`.
- Lint: a `variants` key that is not a soul of the template → `asset.variant` (warn); `image_shows` while other candidate companions have no version of their own → `asset.variant` (warn); `variants` not shaped `{sid: picture}` → a plot lint error.

Also on the same stream (10-14):

- `state.changed` carries `gained` / `lost`: `[{who, id, cls, name, kind: item|effect, from|to, how}]`; `how`: gained `new` (made in someone's hands) · `picked` (from a place / from nobody) · `given` (from another person); lost `gone` (used up / ran out) · `dropped` (left at a place) · `given` (to another person) — whoever made the change (the model's op, a template handler, a tick, a trigger, an effect running out).
- `party.join` / `party.leave` `{sid, iid, name, why}`: a `companion` from the builder standing with the player at the start is in the party (`why: companion`); landing with the player on the player's move joins (`follow`); not coming along leaves (`stayed`), walking off leaves (`left`). Kept in `game/meta/party.json`.
- `plan.beat` / `resolve.beat` carry `mentions: [{id, cls, name, span: [start, end], alt?}]`: the people / things / places the beat's prose names and where in `text`.
- The player's structured actions: `POST /cmd {"action": "inspect" | "pick", "target": <entry id or name>}` (also `/session/<sid>/turn[/stream]`) → one `resolve.beat {advanced_by: inspect|pick, action: {kind, target, ok, why?}}`, no model, no line said for the player. The world's own rules apply: triggers `when: {"entry": "I701", "event": "pick"}`; `text` rules see the thing's name as what the player turned to; a pack's own `inspect` / `pick` op lands it when registered. Defaults: inspect = the thing's own `summary` / `desc` …; pick = a thing where the player stands (not a person / place / effect, not `fixed`) goes into the player's hands → `gained` (`picked`).
- Skill commands: `POST /cmd {"action": "skill", "skill": "侦查", "target": "井口"}`, or plain text 「/侦查 井口」 (any of the skill's / attribute's names; multi-word names such as 「/First Aid her」 too). With a pack `skill_check` seam the engine rolls **right away** (pct: d100 ≤ the skill) — the beat's first `dice` event — and the result goes to the host as a fact; a pack without the seam, or a name it does not know → the host is told the player used the skill and rolls by the world's own rules. The beat reads the player's words as 「我用「侦查」:井口。」; `resolve.beat.action = {kind: skill, skill, key?, target, rolled, total?, vs?, passed?, level?}`. Text 「/go 3车」 = the world action's prompt (`actions.json` `actions`).
- Reads for a front end (in the run's language): `GET /api/v1/play/engine/sheet` → `{lang, name, hp?, system?, attrs: [{key, label, value, desc, check?}], skills: [{key, name, label, value, desc, check?}]}`; `GET /api/v1/play/engine/actions` → `{lang, actions, verbs, skills, attrs, items, places, people, quick}` (the `/` `@` `#` candidates and the quick bar, common ones flagged `common`); `GET /api/v1/play/engine/template` carries `lang`.
- The people the player knows (10-15): `GET /api/v1/play/engine/people` → `{lang, people: [{id, sid?, kind: soul|npc, name, role_label, met, here, companion, addr, place, where, portrait_slot, last_seen?, mood_label?, trust?, relation?}]}`. Only who stands with the player and who they have met; an NPC whose name they do not know yet has `name: ""` (just `role_label`). A character sharing a place with the player (before or after a beat) gets `status.met_player` and `last_seen {addr, turn}` in `souls/<…>/run_state.json`, so they stay on people / the map after parting. The play-side `entities?cls=soul|npc` gives only what the player may see (`core/people.PLAY_PROPS` + `mood_label` / `role_label`); `persona` / `rules` / `goals` / `relationships` (incl. `truth`) are in the debug read `GET /api/v1/play/engine/debug/entities?cls=…` only.
- `soul.mind {turn, iid, sid, name, attitude, attitude_label, thought?, intent, move_to?, follow, stay, trust_delta?}`: what a character present made of the beat (her own turn's judgment), after each beat's event, in `/engine/beats`. `<fields>` may carry a `thought:` line (one line, the run's language).
- Objective and map (10-15): `GET /api/v1/play/engine/objective` → `{lang, now: {plot, stage, name, goal}, plots: [{plot, title, stage, steps: [{index, name, goal, state: done|current|hidden}]}], jobs: [{id, name, summary, state: offered|active|done|failed|abandoned, state_label, active}], exit: {on, label}}` (a stage not reached has no name; a commission's word is folded by `core/objective.JOB_STATES`, `locked` ones are not listed, nor offers the player has not come across). Every `/api/v1/play/map` node carries `pos100` (its 0–100 spot on its level); a place with no position or on top of another gets one beside the place it links to or in free space (`pos_guess`); every level's `hotspots` stay within 2–98, the guessed ones listed in `hotspot_guess`. `place.discovered {turn, addr, name, parent, by: grow|arrive|reveal}`: a place the engine grew, walked into for the first time, put on the player's map or named by the prose — in `/engine/beats` (not on the first look at a run).
- Player view vs debug (10-15): the play-side reads give only what the player may know — `/state` (and the `/events` hello / positions) lists the characters they know; `/trace?i=` is the player's view (prose, options, dice, what landed, what the characters present said and made of it; no `bus_messages` / `plan` / `spans` / planning board / variable table / far-away characters); `/api/v1/play/schema` has no triggers and no variable docs, and its `entries` (like `entities?cls=…`) list only what the player has come across (places on their map, people they know, things in view / on them / named by the prose, kept in `game/meta/seen.json`) — an undiscovered clue keeps its name; the plan board `plan.beat.board` is what each one at the table said they will do and stays; `/events` sends no thinking and no psyche of characters the player does not know. The full records are at `/api/v1/play/engine/debug/{state,traces,trace?i=,schema,entities?cls=}` and `/events?debug=1`, on the local engine only (`NEONRP_DEBUG_ROUTES=1|0`; unset = on locally, off in the browser build; the bench.html test bench turns it on). Reader: `src/neonrp/core/play_view.py`.

### 6.7 Sound: theme · mood · ambience (10-15, implemented)

A run has two channels: **music** (one track at a time) and an **ambient bed**. The engine decides what plays and the front end only plays it (`core/audio.py`); a template that **writes nothing still sounds right**, and whatever the author writes overrides the default.

| Where | Shape | Effect |
|---|---|---|
| `template.json` `audio` | `{"theme": <music>, "ambient": <bed>, "moods": {"tense": <music>, "crisis": <music>}, "places": {<addr>: {"ambient", "bgm"}}, "credits": "assets/audio/CREDITS.md"}` | the world's theme (plays while calm) · the bed when no place name fits · other tense / crisis tracks · sound per place by address · where the template's own audio comes from |
| `location.json` `audio` | `{"ambient": …, "bgm": …}` | this place (and the places inside it) |
| `plot.json` `stages[n].audio` | `{"mood"?: calm\|tense\|crisis, "bgm"?, "ambient"?}` | while that stage is current |
| trigger `then` | `{"to": "audio", "mood"?, "bgm"?, "ambient"?}` | from that beat on; `default` clears that part |

Values: a pool id (`worldlines/audio/catalog.json`: music `calm` `tense` `crisis` `guixiang` `wuwu` `whitechapel` `divergence` `firstsnow` `emberglass` `mandongbu`; beds `rain` `fireplace` `cellar-drip` `storm` `snow-wind` `harbor-waves` `library` `city-night` `office-night` `cave-drip` `tavern-chatter` `cafe-murmur` `bell-church` `forge`) · a template file `assets/audio/x.mp3` (mp3 / ogg / m4a / wav) · `silence` (no music, the theme rests too) / `none` (no bed) · `default` (as if not written).

**How the engine decides**
- Mood `calm` / `tense` / `crisis`: the author's (trigger > stage) is the floor; the plot's last stage floors at `tense`; what landed this beat raises it — a combat-like mode layer (`combat` …) or the player's hp ≤ 30% → `crisis`, hp / sanity lost this beat → `tense`; a raised mood holds 2 beats before it comes down.
- Music: `calm` plays the trigger's / stage's / place's own track, else the theme, else the contract's (`mystery-trpg` → `tense`, `open-adventure` → `emberglass`, `romance-companion` → `calm`, `murder-mystery` → `whitechapel`); `tense` / `crisis` play `moods` or the pool track of that name. `silence` anywhere = no music.
- Bed: trigger > stage > the place (inherited upward; `places` fills what `location.json` left out) > a guess from the place's name / address / kind against the pool's keywords (data in the pool catalog, never engine code) > `audio.ambient`.

**For the front end**: beat event `audio.cue {turn, music: {id, url, mood, title?} | null, ambient: {id, url} | null, mood, by: default|place|stage|trigger|mood, fade_ms, place}`, sent only when what plays changed; `GET /api/v1/play/engine/audio` = the current one + `credits` (title / artist / license / source of every pool track, CC BY first) + `template_credits`. URLs carry a content hash: pool `/api/v1/audio/<kind>/<id>.<hash>.mp3`, template `/api/v1/local/templates/<id>/audio?path=…&h=<hash>`; a matching hash = `Cache-Control: public, max-age=31536000, immutable`, otherwise an ETag; both answer Range requests (Safari / WKWebView need them for media).

**The pool ships with the product**: local = `worldlines_shim/audio/` in the worldlines wheel (~21 MB; `NEONRP_AUDIO_DIR` overrides); browser = static `play/audio/<kind>/<id>.<hash>.mp3` (in no engine / world zip, shared by every world; the Service Worker maps `/api/v1/audio/` there); iOS = served same-origin by the app's local engine; a Hub template package carries only the template's own audio and names pool tracks by id. The pool holds only redistributable audio: CC0, or CC BY 4.0 (three tracks, credited in the standard player under Menu → Sound → Music credits); no MaouDamashii, Suno or licensed tracks.

---

## 7. Lint (every code)

`neonrp template lint` aggregates every check as `{level: block|warn, code, where, msg}`; any block makes the template unpublishable (exit code 1). Lint does a reference build (every pool candidate present) in a temp folder so plot and slot checks run against the real world.

| code | level | Meaning |
|---|---|---|
| `schema` | block / warn | template.json missing or not JSON (block); `schema` is not `worldlines.template/1` (warn) |
| `meta.card` | block / warn | no `card.title` (block); no `card.pitch` (warn) |
| `meta.mode` | block / warn | invalid `mode.ending` (block); unknown `mode.freedom` (warn) |
| `ref.world` | block | no world given, or the folder does not exist |
| `ref.pack` | block | the pack (incl. its mixin composition) does not load |
| `pack.mixin` | block | a mixin name does not resolve |
| `pack.mixin.data` | warn | `economy` / `factions` without `game/world/<mixin>.json`; the mixin stays inert |
| `pack.engine` | block | `pack.engine.turn.mode` is not `v2b` / `v3` |
| `ref.souls` | warn | neither the template nor the world has souls |
| `ref.soul.pool` | block | `pick` larger than the pool |
| `ref.soul` | block | a soul without sid, or not found (not native, no valid `path`) |
| `ref.prompt` | block | a file listed in `prompts` does not exist |
| `prompt.parse` | block | a prompt file fails to parse |
| `prompt.empty` | warn | an empty entry |
| `prompt.soul` | warn | `prompts/souls/<sid>` for a soul the template does not cast |
| `prompt.soul.data` | block | the character prompt layer writes a soul-data path |
| `build` | block | the reference build fails |
| `ref.plot` | block | a plot folder has no plot.json |
| `plot.parse` | block | plot.json fails to parse |
| `plot.lint` | block | the plot check itself crashed |
| `plot` | block / warn | results of the plot check (error → block, warn → warn): missing id/title, unknown class, place without parent/links, variable without type, undeclared ending / unknown soul in an emit, unreachable ending, stages nothing advances, wrong asset kind/path/file, unreferenced asset, unknown top-level key |
| `loop.pool` | warn | a plot talks to a soul only a pool may bring; silent in runs that don't cast it |
| `v3.lint` | block | the ui check itself crashed |
| `schema.view` | block / warn | a view binds no variable / a missing class / an action without handler (block); unknown widget (warn) |
| `schema.slot` | block / warn | recipe is neither built-in nor a named prompt (block); slot on a class the world does not have (warn) |
| `schema.opening` | block | `opening.cg` malformed: an entry without an image or a video, a path outside the template, a wrong file kind (one not filled yet is `asset.optional`, warn) |
| `audio.schema` | block / warn | `audio` malformed (block); an unknown key (warn) |
| `audio.ref` | block | an audio value does not resolve: no pool track of that id / no such template file / outside the template / not mp3·ogg·m4a·wav |
| `audio.size` | warn | a template's own track over 4 MB (players download it) |
| `audio.credits` | block / warn | the template ships its own audio without `audio.credits`: default zone (`zone: reviewed`) block, open zone warn |
| `asset.stale` | block / warn | inputs of a filled asset changed (block when publish and required) |
| `asset.missing` | block / warn | a required slot is unfilled (block at publish) |
| `asset.optional` | warn | N optional slots unfilled |
| `prompt.placeholder` | block / warn | unknown placeholder in a named prompt (block); unknown dotted placeholder in a prompt-layer entry (warn) |
| `token.unmeasured` | warn | no turns to measure yet |
| `token.over` | block / warn | average per turn over budget (block at publish) |
| `token.near` | warn | above 80 % of budget |
| `asset.card` | block / warn | no cover file (block with `lint.level: "publish"`, else warn) |
| `loop.single` | block | `single` mode without exactly one reachable ending |
| `loop.multi` | block | `multi` mode with fewer than two reachable endings |
| `loop.reach` | block / warn | an ending no trigger emits, in `single`/`multi` (block); endings declared but none reachable, in `open` (warn) |
| `loop.distinct` | block | one trigger branch emits two endings |
| `loop.guide` | warn | a plot with endings has no stages or no appended prompt |
| `loop.exit` | warn | `single`/`multi` without a `fail`/`fallback`/`rule` ending |
| `loop.epilogue` | warn | an ending without a title |
| `loop.reveal` | block | `mode.reveal` is on but a plot has no `reveal` |
| `player.builder` | block | a bad builder declaration: a field without id / duplicate / unknown kind, `to` outside the game dir, an option without id, grants other than set/append/add, points that cannot be spent, a portrait image not inside the template, fewer companion candidates than `pick` |
| `i18n.id` | block | A localization layer changes an id (an ASCII id / sid / place / flag / variable reference); ids stay as authored |
| `i18n.parse` | block | A localization layer's JSON does not parse |
| `i18n.build` | block | (`--i18n-deep`) a language's localized version builds / lints with a block |
| `i18n.missing` | warn | A declared language has no layer: its runs play the main language |
| `i18n.partial` | warn | The layer still lacks N files / strings (they fall back to the main language) |
| `i18n.residue` | warn | That language's localized version still holds another language's proper nouns (the glossary) |
| `i18n.key` / `i18n.list` / `i18n.orphan` | warn | A key the template lacks (a typo? keys are ids and are not localized) / an array of another length replaced whole / a file the template lacks |

---

## 8. From template to a run

### 8.1 What `build(template, dest)` does (`neonrp.template:build`)

0. Given a `lang`: lay `i18n/<lang>/` over a scratch copy of the template first (see 4.1); the steps below work on that copy; at the end four-language objects are narrowed and `output_lang` is written.
1. `dest` must not exist or be empty.
2. Copy the world (`world.path` or `world.builtin`), skipping `.neonrp/` and `__pycache__`.
3. Lay the overlay over it (whole-file replacement).
4. `world.shuffle`: deal properties with `seed`.
5. Casting: draw from pools / copy brought-in souls; write `souls` and `active_souls` in `playthrough.json`.
6. Character prompt layer: overlay only `soul.md` / `persona/` / `rules/` / `agents/`.
7. Bind the pack: write `"template": "<pack name>"` into `playthrough.json` (root and `.neonrp/`) and `manifest.json`; the engine resolves the pack from it.
8. Run each mixin's `install(run)`: register and seed its closed-schema variables.
9. Deep-merge `pack.engine` into `game/meta/engine.json`.
10. Merge the prompt layer into `game/meta/prompt.json`.
11. Install plots (registered into the world with `prompt` / `reveal` removed, copied to `game/plots/<id>/`; `reveal` stored as `reveal.json`).
12. Copy the cover to `assets/template-cover.<ext>`; write `card.title` to `name` in `game/meta/game-start.json`.
13. Write `game/meta/template.json`: template meta + `built` (souls / cast / plots / prompt_overlays / shuffled / mixins / dropped_soul_emits) + the effective `ui`. `neonrp template show` and the play UI read this record.

### 8.2 How engine config takes effect

```
builtin defaults  <  pack.loop  <  the contract's engine block  <  game/meta/engine.json  <  .neonrp/playthrough.json["engine"]  <  env
```

The template's `pack.engine` lands in `game/meta/engine.json` (step 9), so it **overrides the pack's own loop** but can still be overridden by a run's playthrough or by experiment env vars. Measured on a run built from `stoneford-elena`:

| Key | Value | Source layer |
|---|---|---|
| `turn.mode` | `v3` | world (from the template's `pack.engine`) |
| `turn.parallel.souls.default_variant` | `S-judge` | pack (the `rpg` loop) |

The reference templates' `pack.engine` only sets `turn.mode: v3`; `werewolf-night-village` sets no `pack.engine` and uses the `werewolf` pack's own loop. Which beats a turn has, and how the narration becomes state, is the orchestration graph's job (3.1 `orchestration`), not `pack.engine`'s.

### 8.3 New run

- `neonrp.template:new_run(ref)`: `ref` is a folder or a template id; builds into `~/.worldlines/plays/tpl-<id>-<YYYYMMDD-HHMMSS>/`, initializes the manifest, seeds the model (see 3.9). A failed build is removed.
- HTTP: `POST /api/v1/play/session {"slug": "tpl--<id>"}` starts a fresh run of that template.
- A template with `player.builder` (3.11): add `player: {fields, companion}` to start with the character the player made; without it the run opens as before.
- Discovery order (`template:search_dirs` / `discover`): `NEONRP_TEMPLATE_PATH` (OS path separator) → the repo's `worldlines/templates/` when running from source. First hit per id wins.

---

## 9. Command line

```
neonrp template list                        discoverable templates: id, pack name, ending mode, title, folder
neonrp template lint <dir|id> [--json]      every check; exit 1 when not publishable
neonrp template build <dir|id> <dest> [--force]
                                            lints first and refuses on any block (--force builds anyway)
neonrp template show [--world <run dir>]    a built run: card / mode / plot stages / ending; the reveal only after the ending
neonrp template slots <dir|id>              every asset slot instance: ok / stale / MISSING (required, unfilled) / - (optional, unfilled)
neonrp template contract <dir|id> [--ts|--gd]
                                            worldlines.contract/0.1 (vars / classes / ops / events / triggers /
                                            slots / views / panels), or generated TypeScript / GDScript bindings
neonrp template contracts                   the official play contracts, and which templates promise each
neonrp template fork <dir|id> <new-id>      copy a template into your store to edit it (built-ins are read-only)
neonrp template set-contract <id> <contract[@v]>|--clear
                                            declare the experience it promises; re-linted
neonrp template export <dir|id> [-o FILE]   a package (.zip); the library souls it links come along
neonrp template export --soul <name> [-o]   one character-library soul as a package
neonrp template import <FILE> [--id NEW] [--store DIR]
                                            bring a package back: the template into your store, its souls into the library (9.2)
```

`lint` text output, one line per problem: `[level] code where: msg`, then `publishable|NOT publishable — N block, M warn`. With `--json`:

```json
{
  "problems": [{"level": "warn", "code": "meta.card", "where": "card.pitch", "msg": "no pitch (one line on the card)"}],
  "publishable": true,
  "meta": {"schema": "worldlines.template/1", "id": "min", "version": "", "card": {…}, "mode": {},
           "pack": "rpg", "plots": [], "souls": [], "models": {}},
  "counts": {"block": 0, "warn": 4}
}
```

Current lint results of the reference templates: the three stoneford templates are `publishable — 0 block, 1 warn` (`asset.optional`); `werewolf-night-village` (`lint.level: draft`) is `0 block, 3 warn` (`ref.souls`, `token.unmeasured`, `asset.card`).

### 9.1 Authoring API (brief)

`neonrp.template.author` provides creator edits:

- Only templates under `NEONRP_TEMPLATE_WRITE_DIR` are writable; built-in / example templates are read-only, `fork(src, new_id)` first.
- `apply_ops(t, ops)`: every op is verified first; one refusal and nothing is written; the template is re-linted afterwards. Ops: `edit_card` `set_mode` `set_mixins` `add_slot` `remove_slot` `edit_prompt` `edit_recipe` `set_view` `remove_view` `set_budget` `register_class` `set_policy` `set_world_data` `set_orchestration` `set_play_contract` `set_cast`. Each op's fields: `neonrp spec authoring`.
- `set_cast {souls: [...]}`: the whole cast (rows as in 3.6); a broken link / a duplicate / an unknown role / two players → the batch is refused.
- With `WORLDLINES_ASSETS_DIR` set, every image that lands in a slot is also copied to the asset workshop, which keeps the history.
- HTTP: `/api/v1/local/templates/<id>/{lint,cover,contract,assets,ui,fork,ops,plots,graph-lint,export}`; which templates link a soul: `GET /api/v1/local/souls/<name>/bindings`.

### 9.2 Packages: export / import (`neonrp.template.package`)

One format for everything: a zip with `pack.json` at its root:

```json
{"schema": "worldlines.package/1", "kind": "template", "id": "pct-house", "title": "Greyoak House",
 "exported": "2026-10-08T09:00:00+00:00", "links": ["mira"]}
```

| kind | holds | imported into |
|---|---|---|
| `template` | `<id>.template/…` (the folder as on disk) + `souls-lib/<name>/…` (every soul it `lib`-links) | template → `NEONRP_TEMPLATE_WRITE_DIR`; souls → the library, rows still link |
| `soul` | `soul/…` (one library soul) | the library |

- A taken id → the next free `-2`, `-3` … (with `--id`, a taken id is refused).
- A library soul of the same name: identical content → reused; different → installed under a new name and the rows repointed; yours is left alone.
- Unpacked into a scratch dir and checked first: absolute / `..` paths, links, code files (`.py` `.js` `.sh` …), over 5000 files or 300 MB → the whole package is refused.
- HTTP: `GET /api/v1/local/{templates|souls}/<id>/export` · `POST /api/v1/local/import/package[?id=]` (body = the zip).

---

## 10. Reference implementation

| What | Where |
|---|---|
| load / build / lint / discovery / new run / slot upload & generation | `src/neonrp/template/__init__.py` |
| effective ui, slot instances, view binding, ui lint, contract & codegen | `src/neonrp/template/v3.py` |
| creator ops, fork, asset workshop | `src/neonrp/template/author.py` |
| pack loading, mixin composition, ui merge | `src/neonrp/packs/__init__.py` |
| mixins: economy / factions | `src/neonrp/packs/mixins/economy.py`, `factions.py` |
| plot parsing, checks, install | `src/neonrp/packs/rpg/plot.py` |
| engine config layering | `src/neonrp/core/engine_config.py` |
| CLI | `src/neonrp/commands/template_cmd.py` |
| packages: export / import | `src/neonrp/template/package.py` |
| player builder (player.builder): declaration check / draft check / write into the run / player card | `src/neonrp/template/builder.py` |
| specs for agents (`neonrp spec` · `/api/v1/spec` · `/llms.txt`) | `src/neonrp/spec.py` |
| HTTP | `src/neonrp/webui/template_routes.py` |
| built-in worlds | `src/neonrp/templates/<world id>/` |
| reference templates | `worldlines/templates/{pct-house,stoneford-elena,stoneford-market,stoneford-three-towns,werewolf-night-village}.template/` |
