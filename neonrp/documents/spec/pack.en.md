# Pack spec (rule pack / play pack)

> For the NeonRP engine as currently implemented. The minimum that runs = **pack** (engine rules) + **world** (data) + **souls** (data); a **template** optionally binds the three. This page covers the pack only, focused on the two RPG-family packs `rpg` and `pct`. World: [world.en.md](world.en.md); soul: [soul.en.md](soul.en.md); template: [template.en.md](template.en.md).
>
> Status: **implemented** = in the code and in effect today; **in design** = the field / key is reserved or declared, but the engine does not fully use it yet.
>
> The engine reads a pack's ops, classes, variables, triggers and seams off the code for you: `neonrp spec ops --pack rpg` (or `pct` / `werewolf` / `monopoly`). This page covers what that list does not: rule tables, panels, checks, statuses, the clock, and how to write / change a pack.

---

## 1. What it is

**A pack decides "what rules this world runs on"**: which classes exist (places, people, items, statuses …), which ops the model may write, which deterministic rules run in the background each turn (ticks), how checks are rolled, and which prompts the sub-layers (combat, referee) use. A world is only data; the same world on another pack is another game.

### 1.1 Built-in packs

| Pack | What | Built on | Status |
|---|---|---|---|
| `rpg` | open-world RPG: a graph of towns / places, together only when in the same place, d20 checks, combat layer, travel, going down, status table, rule panels. **The default pack** | — | implemented |
| `pct` | percentile investigation (the BRP family): d100 skill checks, sanity, dying CON checks, percentile combat | `rpg` | implemented |
| `werewolf` | werewolf: no map, one table, seats are a class, `vote` / `kill`, endings are triggers | — | implemented |
| `monopoly` | a board game: a ring board, roll and advance, rent / tax settled by procedure | — | implemented |

Built-in mixins (plug-ins on top of a pack): `economy` (markets, prices, caravans), `factions` (factions, relations, rumors). Written `rpg+economy+factions`; their data lives in the world (see [template.en.md](template.en.md) §3.5).

`pct` keeps everything `rpg` has (map, places, people, items, plot packs, status table, character state, the combat layer's machinery) and changes only the dice: checks become d100 ≤ skill, a `[san]` tool is added, the down rule becomes a CON check, and the combat layer gets a percentile prompt.

### 1.2 Pack fields

Defined in `src/neonrp/packs/__init__.py:Pack`. A JSON pack (`pack.json`) uses the same keys.

| Field | Type | Default | Meaning | Status |
|---|---|---|---|---|
| `name` | str | folder name | pack name; composed with mixins it becomes `base+m1+m2` | implemented |
| `classes` | {class: definition} | `{}` | open-schema classes (`parent_class` / `required` / `props` / `mutable` / `folder` / `effect` …, same shape as `game/meta/classes.json`) | implemented |
| `actions` | {op: definition} | `{}` | ops the model may write (`kind` / `handler` / `fields` / `validator` / `doc` / `alias` / `wait` …, same shape as `game/meta/actions.json`) | implemented |
| `variables` | {name: {type, path, key, min, max, max_step, monotonic, carry, …}} | `{}` | closed-schema variables (which key in which file) | implemented |
| `triggers` | {id: {when, if, then, else}} | `{}` | when / if / then rules | implemented |
| `mechanics` | {seam: handler} | `{}` | seam → `module:function` or `builtin:…` (seam list in §2.3) | implemented |
| `prompt` | str or object | `""` | a string = world-side contract text; an object = prompt entries (rules / voice / entries / ops_docs), same shape as a world's `prompt.json` | implemented |
| `doc` | str | `""` | one-line description | implemented |
| `flags` | {path, key} | `game/meta/flags.json` · `flags` | where story flags live (`rpg`: `game/player/flags.json` · `story_flags`) | implemented |
| `blocks` | [str] | `["lines","ops","options"]` | the blocks the model writes each turn | implemented |
| `modes` | {layer: definition} | `{}` | sub-layers (combat, dungeon, referee): `prompt` / `reads` / `ops` / `exit` / `state` / `one_shot` / `output` / `tail` … | implemented |
| `loop` | object | `{}` | a turn-loop config fragment; layered builtin defaults < `pack.loop` < `game/meta/engine.json` < playthrough < environment | implemented |
| `ticks` | ["module:function"] | `[]` | deterministic rules run inside every apply, after the turn's ops | implemented |
| `mixins` | [str] | `[]` | mixins composed in | implemented |
| `base` | str | `""` | the built-in pack this one is built on (`pct` → `rpg`): its layer prompts are the fallback | implemented (set only by Python packs, see §2.4) |
| `ui` | object | `{}` | declared presentation: `slots` / `views` / `panels` / `prompts` / `budget` / `beats` (see [template.en.md](template.en.md) §6) | implemented |
| `orchestration` | {nodes, edges} | `{}` | the pack's own part of the orchestration graph (e.g. `rpg`'s "room encounter → combat layer" edge) | implemented |
| `cast_class` | str | `""` | when the cast is not souls, the class whose instances are the cast (`werewolf` = `seat`) | implemented |

### 1.3 Two forms

- **Python pack**: `PACK` in `neonrp.packs.<name>.pack` (all four built-ins), or any importable `module:PACK`.
- **JSON pack**: a folder holding `pack.json` — the form a creator or an agent writes. Handlers are `builtin:…` or `module:function`.

A `pack.json` may **`extends`** an existing pack and write only the difference:

```json
{
  "name": "grim-rpg",
  "extends": "rpg",
  "doc": "a low-magic rpg variant where wounds hurt",
  "actions": { "new_town": null, "sheet": { "enabled": false } },
  "classes": { "curse": { "title": "Curse", "effect": true, "props": { "turns": { "type": "int", "min": 0 } } } },
  "ui": { "prompts": { "modes.combat": { "zh": "你是战斗裁判……", "en": "You run the fight…" } } },
  "mixins": ["economy"]
}
```

Merge rules (`Pack.from_dict`):

| Key | How it layers |
|---|---|
| `classes` / `actions` / `modes` | by key, same key merged field by field; **`null` deletes** the entry |
| `variables` / `triggers` / `mechanics` | by key |
| `flags` | by key |
| `blocks` | replaced whole |
| `prompt` (object) | merged by entry |
| `loop` | deep merge |
| `ticks` | appended after the base's |
| `ui` | `slots` by (cls, slot), `views` / `panels` by id, `"remove": true` drops one; `prompts` by key, `null` drops; `budget` replaces |
| `orchestration` | `nodes` by key, `edges` appended (same id replaces) |
| `mixins` | composed in last, in order |

---

## 2. Resolution and layering

### 2.1 Which pack a world uses · implemented

`src/neonrp/packs/__init__.py:template_of`, first hit wins:

1. `"template"` in the world root's `manifest.json`;
2. `"template"` in `game/playthrough.json`;
3. `"template"` in the root `playthrough.json`;
4. none → `"rpg"`.

The key is named `template` (for historical reasons); its value is a pack name. A template build writes it into `manifest.json` and the playthrough (see [template.en.md](template.en.md) §8).

### 2.2 How a name resolves · implemented

`packs.load(name, root)`:

| Written as | Resolves to |
|---|---|
| `rpg+economy+factions` | `rpg` first, then the mixins composed in order |
| `pkg.module:PACK` | that object, imported (a `Pack` or a dict) |
| a folder path holding `pack.json` | that JSON pack |
| `rpg` / `pct` / `werewolf` / `monopoly` | the built-in |
| any other name | `<world>/template/<name>/pack.json`, then `<name>/pack.json` in each folder on `NEONRP_TEMPLATE_PATH`, finally `<world>/template/pack.json` |

None found → `PackError`; template lint reports `ref.pack` (block).

### 2.3 Layering of each part · implemented

Later wins.

| Part | Order | Read by |
|---|---|---|
| rule tables (`rules` / `foes` / `hazards`) | `packs/rpg/data/<table>.json` < a built-in pack's own `packs/<pack>/data/<table>.json` (e.g. `pct`) < an older world's `world_map.json` `travel` / `foes` < the world's `game/rules/<table>.json` | `packs/rpg/data.py:table` |
| status table | a built-in pack's `packs/<pack>/data/status.<lang>.md` (else `.en` → `.zh`) < the world's `game/rules/status.md` (the world's line wins on the same name) | `core/effect_rules.py:table` |
| layer prompts (combat / dungeon / referee) | template / world override (`ui.prompts["modes.<layer>"]` or `modes.<layer>` in `game/meta/prompt.json`) → the world's own `agents/<id>/system.md` → the pack's `prompts/<layer>.<lang>.md` → the base pack's file of the same name | `core/modes.py:prompt_source` |
| mechanics seams | the engine's generic defaults < `pack.mechanics` < `mechanics` in `manifest.json` < `game/meta/mechanics.json` | `core/mechanics.py` |
| prompt entries | `pack.prompt` < `prompt` in `manifest.json` < `game/meta/prompt.json` | `core/adv.py:prompt_spec` |
| turn loop | builtin defaults < `pack.loop` < `game/meta/engine.json` < the playthrough's `engine` < environment | `core/engine_config.py` |
| ui | pack (+ mixins) < template `ui` | `packs:merge_ui` |

Seams (`core/mechanics.py:SEAMS`): `contract` · `soul_turn` · `observe` · `settle` · `participation` · `load` · `pack_hints` · `companions` · `speech_rule` · `gate` · `post_solve` · `understand` · `after_turn` · `roll_check` · `plan_event` · `run_outputs`. `rpg` fills 15 of them; `pct` replaces only `roll_check` and `load`.

### 2.4 Your own JSON pack extending rpg · implemented (this is how it behaves)

- **Rule tables** always start from `rpg`'s defaults; a `data/` folder inside a JSON pack is **not read** (only the built-in pack folders `packs/<pack>/data/` are). Change numbers in the world's `game/rules/rules.json` (in a template: `world-overlay/game/rules/rules.json`).
- **The status table** is looked up as `packs/<pack name>/data/`; a JSON pack has no such folder, so the pack layer is empty and `rpg`'s default lines are **not inherited**. Put the lines you want into the world's `game/rules/status.md`.
- **Layer prompts**: `extends` does not set `base`, so `rpg`'s `prompts/combat.md` etc. are **not a fallback**. Give each layer you use an override: `ui.prompts["modes.combat"]` in `pack.json` (a string or `{zh,en,ja,ko}`), or `agents/combat-referee/system.md` in the world.
- Classes, ops, seams, ticks, mode definitions, loop and ui are inherited as usual.

---

## 3. Rule tables (the rulebook)

The rulebook is `data/rules.json`. Engine code knows no particular attribute, skill or role — they are rows of the table.

### 3.1 `rpg`'s `data/rules.json` · implemented

| Key | Default | Meaning | Read by |
|---|---|---|---|
| `attr_mod_base` | `5` | attribute modifier = value − this (5 = +0, 8 = +3) | checks, referee, combat, down rule (simple) |
| `referee_difficulty` | `{easy: 8, normal: 12, hard: 15, very_hard: 18, extreme: 21}` | difficulty tier → DC | checks, rules referee |
| `actions` | 11 rows (below) | what a check names → the attribute it rolls on | checks |
| `fallback_attr` | `"int"` | the attribute when nothing matches | checks |
| `dc_numbers` | `"tier"` | when the GM writes a number as DC: `tier` = read as the nearest tier; `keep` = use the number | checks |
| `baseline` | `{attributes: {str:5, dex:5, int:5, vit:5, cha:5}}` | the plain person's rule panel (bottom of the fallback chain) | panel |
| `role_panels` | `{}` | role → panel; written by the world / template author | panel |
| `generate_panels` | `false` | reserved: whether the engine generates a missing panel | in design (not read by the engine yet) |
| `down_rule` | `"srd"` | the down rule: `srd` / `simple` / `pct` (old ids `dnd`→`srd`, `coc_simple`→`simple` still read) | down tick |
| `down_names` | — (`pct` has it) | names of the three states down / stable / dead (four languages) | down tick |
| `npc_hp_default` | `8` | starting hp for a class with hp whose record has none | character state |
| `def_base` | `10` | defense = this + armor def + VIT modifier | combat state block |
| `hit_die` / `damage_die` | `"1d20"` / `"1d6"` | hit die / default damage die (written into the combat state block) | combat layer |
| `unit_labels` | `{zh:"甲乙丙丁戊己", en:"ABCDEF", ja:…}` | labels for several foes of one kind | combat layer |
| `travel_per_day` | `20` | distance units covered per day | travel |

Keys starting with `_` are comments; the engine skips them.

**`actions` rows** (check name → attribute):

```json
"persuade": {
  "zh": "说服", "en": "Persuade", "ja": "説得", "ko": "설득",
  "attr": "cha",
  "aliases": ["交涉", "砍价", "讲价", "negotiate", "haggle", "値切り", "흥정"]
}
```

The 11 built-in rows: `persuade` `deceive` `intimidate` (cha) · `insight` `search` `recall` (int) · `stealth` `sleight` `dodge` (dex) · `athletics` (str) · `endure` (vit).

Matching (`packs/rpg/panel.py:find`): searched in the check's **own words** (its reason is left out, so "in order to search the study" does not turn a persuade check into a search); the row key, the four language names and the aliases all count as names, and **the longest name wins**; pure-ASCII names match on word boundaries, others as substrings.

**`dc_numbers`**: with `tier`, a number reads as the nearest tier; exactly halfway between two, **the harder one** — reading the GM's number never makes a task easier than it asked.

### 3.2 `pct`'s `data/rules.json` · implemented

Layered over `rpg`'s table (so `referee_difficulty`, `actions`, `attr_mod_base` etc. are still there; percentile checks just do not read them).

| Key | Value | Meaning |
|---|---|---|
| `attr_x` | `5` | attribute check target = attribute × this |
| `attrs` | `str con siz int pow dex cha edu` | attribute table: four language names + `aliases`. `con`'s aliases include `vit`; `cha`'s include `app` / `appearance` |
| `skills` | 33 rows | the skill table (below) |
| `difficulty` | `{easy: 2, normal: 1, hard: 0.5}` | tier = multiplier on the target (easy ×2, hard ×½); a tier not in the table is ×1 |
| `crit_div` / `special_div` | `20` / `5` | critical ≤ ⌈target/20⌉, special ≤ ⌈target/5⌉ (rounded up, at least 1) |
| `fumble_min` | `99` | a roll of 99 / 00 fumbles; with a target of 99 or more only 00 fumbles |
| `fallback_attr` | `"int"` | the attribute (× `attr_x`) when no skill matches |
| `baseline` | all 8 attributes `10` | the plain person's panel |
| `down_rule` | `"pct"` | dying: each resolve d100 ≤ CON × 5; one failure is death; three successes stabilize |
| `down_names` | Dying / Stabilized / Dead (four languages) | names of the three down states |
| `npc_hp_default` | `11` | |
| `major_wound_ratio` | `0.5` | one blow of half the max hp or more → a "Major wound" status |
| `san_max` | `99` | sanity cap |
| `san_insane_ratio` | `0.5` | losing half the SAN the scene began with within one resolve → temporary insanity |
| `damage_bonus` | `[{max:12, db:"-1d6"}, {max:16, db:"-1d4"}, {max:24, db:"0"}, {max:32, db:"+1d4"}, {max:40, db:"+1d6"}, {max:99, db:"+2d6"}]` | damage bonus looked up by STR + SIZ |
| `effect_names` | Major wound / Temporary insanity / Permanent insanity (four languages) | statuses the pct tick creates |
| `weapons_default` | `{brawl:"1d3", melee:"1d6", firearms:"1d10", throw:"1d4"}` | default weapon damage dice (in design: not read by the engine yet) |
| `system` | `"pct"` | a marker (not read; check results carry `system: "pct"` themselves) |

Derived values (`packs/pct/rules.py`): hp = ⌈(CON + SIZ) / 2⌉ when the sheet has none; sanity starts from the sheet's `san`. An older sheet's `app` reads as `cha`.

**`skills` rows**:

```json
"persuade": { "zh": "说服", "en": "Persuade", "ja": "…", "ko": "…",
              "base": 15, "attr": "cha", "opposed": "insight" },
"dodge":    { "zh": "闪避", "en": "Dodge", "base": "dex*2", "attr": "dex" },
"spot":     { "zh": "察觉", "en": "Spot", "base": 25, "attr": "int",
              "aliases": ["侦查", "搜查", "search", "탐색"] }
```

| Field | Meaning |
|---|---|
| `zh` / `en` / `ja` / `ko` | display name (in the run's language); every one of them is also a name that matches |
| `base` | the base value when the character has none: a number, or `<attr>*n` (e.g. `dex*2`; the attribute goes down the panel chain) |
| `attr` | which attribute the skill belongs to (for people and the model; the engine computes the base from `base` only) |
| `opposed` | the skill the other side rolls in a contest (persuade ↔ insight, stealth ↔ listen); none → the same skill |
| `aliases` | old names, colloquial names, other languages; a sheet written with an old name still matches, and shows today's name |

### 3.3 Other tables · implemented

| Table | Each row | Used for |
|---|---|---|
| `foes.json` | stable id → `hp` / `def` / `atk` / `dmg` / `names{lang}` / `aliases` / `traits{lang}` (`pct` adds `skill` attack % / `dodge` %) | the combat layer's roster; the `foe` row is the fallback |
| `hazards.json` (`rpg` only) | route tag → `p` chance per journey / `dc` (1d6 target) / `fail_days` / `foes {foe: [min, max]}` / `also` / `text` `pass` `fail`{lang} | what happens on the road |

### 3.4 How a world changes a table · implemented

Put `game/rules/<table>.json` in the world; it overrides **key by key**:

- objects deep-merge level by level: write only the keys you change;
- lists, numbers and strings replace whole (`damage_bonus` must be written in full);
- `null` disables a row (e.g. `"skills": {"firearms": null}`);
- keys starting with `_` are ignored — use them as comments.

```json
{
  "referee_difficulty": { "hard": 16 },
  "dc_numbers": "keep",
  "actions": { "pray": { "zh": "祈祷", "en": "Pray", "attr": "cha", "aliases": ["祷告"] } },
  "role_panels": { "gate_guard": { "attributes": { "str": 7, "vit": 7, "int": 4 } } }
}
```

Reference: the built-in world `src/neonrp/templates/stoneford-elena/game/rules/rules.json` (13 role panels).

---

## 4. The rule panel and its fallback chain · implemented

The rule panel = the numbers a check reads (attributes, skills). The player, souls and NPCs share one system (`packs/rpg/panel.py`). **A missing value never refuses a check**; it is looked up down this chain:

| Layer | From | Recorded `source` |
|---|---|---|
| 1 sheet | the character's own record: the player's `game/player/stats.json`; a soul's `character/stats.json`; an NPC's row in `npcs.json` (`attributes` / `skills`) | `sheet` |
| 2 filled this run | a value filled earlier in this run: `panel` in `game/states/<id>.json` | the layer it was first filled from |
| 3 role panel | the rulebook's `role_panels[<role>]`; role = the record's `role` (a soul's comes from its playthrough souls row). Exact key first, else the **longest** key the role contains ("north gate gatekeeper" → `gatekeeper`) | `role:<key>` |
| 4 baseline | the rulebook's `baseline` | `baseline` |

- An attribute the rulebook never names: the median of the baseline attributes, still recorded as `baseline`.
- Skills (pct): her own value (by any name) → filled this run → the role panel's `skills` → the row's `base` (`dex*2` goes down the attribute chain; source `base(<the attribute's source>)`) → a skill the table does not have: `fallback_attr` × `attr_x`, with `via: fallback_attr:<attr>`.
- A sheet written with an alias (`app`, `vit`): read as the proper name through `attrs` aliases.

**Write-back**: a value filled from layer 3 or 4 (or a base) is written into `game/states/<id>.json`:

```json
{ "panel": { "attributes": { "cha": 7 }, "skills": { "spot": 25 },
             "source": { "attributes.cha": "role:shopkeeper", "skills.spot": "baseline" } } }
```

The same character reads the same number next time, and the player can see where it came from. The author's record (the sheet) is **never rewritten** in play; a soul's folder stays clean and can travel to another world.

`game/states/<id>.json` also holds the run's character state: `hp` / `max_hp` (only when the class's schema declares `hp`), `down` / `dead` / `stable` / `down_pass` / `down_fail` (`packs/rpg/character_state.py`).

---

## 5. Checks and contests

### 5.1 Who does what · implemented

- **The GM picks, never writes numbers**: who rolls, against whom (a contest), on what (an attribute, or a skill / check name), which difficulty tier, which statuses count, and why.
- **The engine writes the numbers**: reads the panel, adds status modifiers, rolls, judges. Every roll goes through one dice tool (one random-number backend, the ledger, the dice line on screen), seeded by turn and by the check: a replayed run rolls the same faces.

Checks the GM agreed are handed to the `roll_check` seam at resolve (`rpg` → `packs/rpg/referee.py:roll_check`, `pct` → `packs/pct/rules.py:roll_check`). A check is written:

```
<who> [vs <whom>] <attribute | skill / check name> <tier> [status:<name>] to <reason>
玩家 DEX normal 状态:扭伤 为了翻过矮墙
玩家 察觉 为了找暗门
旅人 vs 艾琳娜 力量 甩开她
```

A tier is a key of the rulebook (`easy` / `normal` / `hard` …); the reason is not searched for a skill. If the GM writes a modifier number (`-9(sprain)`), it is only recorded as `host_adj` and **does not count**; what counts is the status's own line (§6.3).

### 5.2 `rpg`: d20 · implemented

- Attribute: the one the check names; else the `actions` row found in the check's words; else `fallback_attr`.
- Modifier = panel attribute value − `attr_mod_base` + status modifiers.
- DC: tier → `referee_difficulty`; a number per `dc_numbers` (§3.1); none written → `normal`.
- Success: 1d20 + modifier ≥ DC.
- **Contest** (`vs`): each side rolls 1d20 + its own modifier on the same attribute; the initiator succeeds when its total ≥ the other's (a tie goes to the initiator).

### 5.3 `pct`: d100 · implemented

- Target: a named attribute → attribute × `attr_x`; else the skill (the skill chain in §4).
- The difficulty tier multiplies the target (`difficulty`); a number is not scaled.
- Status modifiers are added to the target (percentage points), then clamped to 1–99.
- Level (`level`): `fumble` (99 / 00) → `crit` (≤ ⌈target/20⌉) → `special` (≤ ⌈target/5⌉) → `success` (≤ target) → `fail`. A fumble is judged first.
- **Contest**: the other side rolls the `opposed` skill of the initiator's row, else the same skill; the better level wins; the same successful level goes to the larger margin (target − roll); a full tie, or both failing, does not count as a win for the initiator.

### 5.4 What a result holds · implemented

Each side: `who` / `roll` / `mod` / `total` / `value` (panel value) / `source` (§4) / `effects` (the statuses that counted, e.g. `["Sprain-2"]`); `pct` adds `target` / `level` / `label`, possibly `via`. Overall: `result` (`success` / `fail`), `dc` or the other side's `b`, `tier`, `attr_how` (`named` / `action:<row>` / `fallback_attr`).

The words for sources are `panel_src_*` in `src/neonrp/prompts/rpg_pack.<lang>.json` (sheet / filled / role panel / rulebook baseline / from attribute); `panel.source_text` builds the note shown next to the dice line.

### 5.5 Dice tools the narrator writes directly · implemented

| op | Written | `rpg` | `pct` |
|---|---|---|---|
| `roll` | `[roll 1d6]` | a plain roll; while a road stop is pending, this die settles it | same |
| `dice` | `[dice 1d20+2 vs 12]what is tested and why[/dice]` | roll + pass / fail (total ≥ vs) | `[dice 1d100 vs 60]` roll-under with a level; `[dice Spot]` finds the player's skill / attribute by name; `[dice 1d6+1d4]` a sum |
| `referee` | `[referee what the player attempts]` | the rules-referee layer returns a JSON ruling; for a check it gives a difficulty tier (or DC) and an attribute, the engine rolls | the ruling gives `{skill, modifier}` (percentage points), the engine rolls; the referee never writes a DC |
| `san` | `[san 0/1d6 seeing the body]` | — | d100 ≤ current SAN: success loses the first amount, failure the second; written back into the sheet |

The engine always writes the number; the model writes only what is rolled and why.

---

## 6. The status table

### 6.1 Line grammar · implemented

A built-in pack's `data/status.<lang>.md`, or the world's `game/rules/status.md`. One per line; `#` starts a comment:

```
<name>: <the rule, written however you like, clauses separated by ·>
Light wound: lasts 3 turns · check -1, only for actions using the hurt part · flesh wound, pulls when moving · gone the resolve after it is bandaged
Exhausted: lasts 8 hours · check -1 on all actions · heavy legs, slow reactions · a sleep clears it
Bleeding: lasts 2 turns · each resolve player.hp -1 · the wound keeps seeping · a bandage or a staunching herb stops it at once
```

Half- or full-width colon. The engine reads only these four mechanisms (`core/effect_rules.py:parse_rule`); the rest of the line is for the narrator and the GM:

| Mechanism | Written as (any of the four languages) | Becomes |
|---|---|---|
| countdown in resolves | `lasts 3 turns` / `持续 3 次结算` / `3ターン` / `3턴` | `turns` |
| countdown in game time | `lasts 8 hours` / `持续 12 小时` / `持续 2 天` | `hours` (days × 24) |
| per-resolve change | `each resolve player.hp -1` / `每次结算 player.hp -1` (in the same clause) | `each` = `player.hp:-1` |
| check modifier | `check -2` / `checks -2` / `检定 -2` / `判定 -10` / `판정 -10` | `check` |

Clause separators: `·` `;` `,` `。` `、` `|` or ` - `. The unit words of the four languages are in `src/neonrp/prompts/effect_rules.<lang>.json`; a line in any language is read with the words of all four.

### 6.2 Status instances · implemented

A status is an instance of an **effect class** (`rpg`'s `status`, stored in `game/player/stats.json#status_effects`). The narrator writes `new status <name>`; the engine completes it from the table (`effect_rules.fill`): the name loses a trailing number, `turns` / `hours` / `each` come from the rule line, the whole line is kept as `rule`.

| Prop | Meaning |
|---|---|
| `on` | who it sits on (default the player) |
| `turns` | resolves left; minus 1 each resolve, removed at 0 |
| `hours` → `until` / `until_text` | expiry in game time (see §7) |
| `each` | per-resolve variable change; on someone else `player.*` becomes `char.<id>.*` |
| `check` | an explicit check modifier (wins over the rule line) |
| `rule` / `note` | the rule text / a note |

A name not in the table: the model's own rule line is used, and **appended to the world's `game/rules/status.md`**, so the same name reads the same rule next time. The table is re-read when the world's file changes.

### 6.3 Statuses in a check: `status:<name>` and ±n · implemented

- The **number is the rule line's** (`check -2`), added by the engine; an explicit `check` on the instance wins. A corrected line counts from the next roll on.
- **Which statuses apply to this roll is the GM's call** (the engine does not parse phrases like "only for actions using the hurt part"): the GM writes `status:<name>` in the check (several names for several), and only those named count.
- A check that names none → every status with a modifier on that character counts.
- In a contest, the other side counts every status with a modifier on it.

---

## 7. The clock only moves forward · implemented

`rpg`'s time is two variables, stored under `time` in `game/meta/run_state.json`:

| Variable | Type | Rule |
|---|---|---|
| `time.day` | int | never goes down (`monotonic`); one turn's ops move it by at most 1 (`max_step: 1`) |
| `time.clock` | `"HH:MM"` | never goes down; set to an earlier time: 4 hours or more earlier = the next day (`time.day` +1 automatically, `carry`), less than 4 hours = refused |

- Setting it back is refused, and the model is told "write what happens at this moment; the engine moves time forward". A player saying "three days later" is an intent, not time that has passed.
- Multi-day travel advances the calendar itself (§8.3); it is not an op.
- Game-time countdowns on statuses (the `effects_clock` tick): the first resolve turns `hours` into an `until` on the world clock (minutes) and `until_text` (e.g. `D2 15:00`); once the clock passes it, the status is removed — a long sleep wears off several hours at once. A world without a clock uses only resolve countdowns.
- Your own variables may declare `monotonic` / `carry` / `max_step` too (`game/meta/variables.json` or `pack.variables`).

---

## 8. Combat / going down / travel / gates

### 8.1 The combat layer · implemented

- Entering: the narrator writes `[combat bandit×5 boss×1]why it starts[/combat]`; the `name×count` in the tag is the roster (by the `foes` table's names / aliases, in any language, at most 6 of a kind). Someone the world already has (a soul / NPC) named in the roster fights as herself, with her own hp.
- Without a roster, in order: a pending road stop's `hazards.foes` → the current room's encounter table (`encounters: [{enemy, count: "1-3", chance}]`) → names in the hand-off note → one `foe`.
- Inside the layer: foes are variables `foe.<id>.hp` / `foe.<id>.status`; only the layer's ops can be written (`dice` `roll` `flag` `end_combat` `need` `map`; `pct` adds `san`), and every result needs a `[dice]`.
- Leaving: `end_combat outcome=won|fled|lost`; a pending road stop is settled with it (won = through; otherwise at a price). The last fight's summary stays in `run_state.json` as `last_combat`.
- Stepping into a dungeon room with an encounter table rolls it once (seeded, by `chance`); a hit puts the world into the combat layer for the next turn; a cleared room never rolls again.

### 8.2 Going down and death (the `downed` tick) · implemented

Runs after every resolve, for the player and every soul / NPC:

- hp reaches 0 (a class with hp) → down: `down = 1` and a "Down" status; no roll on that resolve. A class without hp goes down when the prose sets `char.<id>.down` to 1.
- Down, not stable, not dead: one roll per resolve by `down_rule`:

| `down_rule` | Rule |
|---|---|
| `srd` | d20 ≥ 10 is a success; a 1 counts two failures; a 20 gets up at 1 hp; three successes stabilize, three failures die |
| `simple` | d20 + VIT modifier ≥ 12 survives; one failure is death; three successes stabilize |
| `pct` | d100 ≤ CON × `attr_x`; one failure is death; three successes stabilize |

- hp back above 0 → up, counters cleared, status removed.
- Dead: `dead = 1`, "Dead" replaces "Down"; her agent takes no more turns. The three names can be changed with `down_names`.

`pct` has its own tick as well: one blow of `major_wound_ratio` of the max hp or more → "Major wound"; temporary / permanent insanity left by the sanity tool become statuses; SAN at 0 → one `insane` event (the contract's death rules decide what it means).

### 8.3 Travel · implemented

- Routes on the world map carry a `distance`; days = ⌈distance / `travel_per_day`⌉ (less than half a day's distance is the same day).
- A route's `tags` match the `hazards` table: seeded by `p`, the engine decides which events happen on this journey and on which day. When one does, the party stops on that day and the narrator gets an `<event>`; the prose goes up to the stop and does not arrive.
- A pending stop is settled by the narrator writing `[roll 1d6]` (≥ `dc` passes, otherwise `fail_days` extra days), or `[referee …]`, or a fight (its outcome decides).
- The calendar is moved by the engine, not by an op.

### 8.4 Gates (before the turn) · implemented

The `gate` seam (`packs/rpg/gates.py:pre_turn`):

- a road stop is pending and the player attacks → the turn starts inside the combat layer;
- the player asks for the map / the way → the engine fires `map` itself; the player asks to see stats / the bag → the engine fires `sheet` itself (a panel for the player; no numbers are read into the prose).

---

## 9. Prompts and the four languages · implemented

| Part | Where | Language fallback |
|---|---|---|
| layer prompts | `packs/<pack>/prompts/<layer>.md` (Chinese original) + `<layer>.en.md` / `.ja.md` / `.ko.md` | run language → en → zh |
| the pack's strings (op docs, class titles, state blocks) | `src/neonrp/prompts/rpg_pack.<lang>.json`, `rpg_i18n.<lang>.json`, `pct.<lang>.json` etc. | run language → en → zh |
| status table | `packs/<pack>/data/status.<lang>.md` | run language → en → zh |
| status-table unit words | `src/neonrp/prompts/effect_rules.<lang>.json` | all four read together |
| names in rule tables | the row's own `zh` / `en` / `ja` / `ko` | run language → zh / en |

- An op's description is `doc` (Chinese / default) plus `doc_i18n` (`{en, ja, ko}`); in `pack.json`, `doc` may also be written as `{zh, en, ja, ko}`.
- Rule tables, status tables and skill names are **data**, written natively in each language, not translated from Chinese; give all four languages when you add a row.
- The status table goes into the narrator's world context every turn (a "status table" section); rules text in `game/rules/*.md` goes into the combat / referee layers' reading block.

---

## 10. Licensing

| Rules from | Used in | License |
|---|---|---|
| **SRD 5.2** (System Reference Document 5.2, Wizards of the Coast LLC) | `rpg`'s d20 checks and down rule (`down_rule: srd`), the `srd` ruleset in `core/dice.py` | CC-BY-4.0 |
| **BRP** (*Basic Roleplaying: Universal Game Engine*, Chaosium Inc.) | the `pct` pack's percentile rules and the rules tables in its `data/`, the `brp` ruleset in `core/dice.py` | ORC License |

- The pack id is still `pct` (percentile); the dice core's ruleset ids are `srd` / `brp`, and the old ids `5e` / `coc` are still accepted, read as `srd` / `brp` (`core/dice.py:canonical_ruleset`).
- Full attributions: `src/neonrp/templates/CONTENT-LICENSE.md` and `src/neonrp/packs/pct/NOTICE.md`. "Basic Roleplaying" and "BRP" are trademarks of Chaosium Inc.; this pack is not affiliated with or endorsed by Chaosium.
- Your own rule pack: attribute open rules as above; do not use a commercial rulebook's trademarks in pack names, prompts or display names — use generic words (d20, percentile dice, sandbox tabletop).

---

## 11. Writing a rule pack: the shortest path

**Only numbers (the common case)** — no pack, change the world:

1. The world's `manifest.json`: `{"template": "rpg"}` (or `pct`).
2. `game/rules/rules.json`: the tiers, check names and role panels you change (§3.4).
3. `game/rules/status.md`: this world's status lines (§6.1); same name overrides the pack's.
4. `game/rules/*.md`: rules text for the combat / referee layers to read.

**A different game** — write a JSON pack:

1. `<world>/template/<name>/pack.json` with `"extends": "rpg"`, writing only the difference (§1.3).
2. New check names, skills and roles still go into the world's `game/rules/rules.json`; status lines into `game/rules/status.md` (§2.4).
3. A prompt for each layer you use (combat / referee / dungeon): `ui.prompts["modes.<layer>"]` (§2.4).
4. The world's `manifest.json`: `{"template": "<name>"}`.

Check:

```
neonrp spec ops --pack <name>      # does the pack load; its ops / classes / variables / seams
neonrp validate                    # the world (JSON parses, references resolve)
neonrp template lint <dir>         # a template: ref.pack / pack.mixin / pack.engine
```

---

## 12. Reference implementation

| Topic | Where |
|---|---|
| Pack definition, JSON packs, extends, mixin composition, ui merge, resolution | `src/neonrp/packs/__init__.py:Pack`, `from_dict`, `compose`, `merge_ui`, `load`, `template_of`, `resolve` |
| rpg's classes / ops / modes / seams / ticks | `src/neonrp/packs/rpg/pack.py:CLASSES`, `ACTIONS`, `MODES`, `MECHANICS`, `LOOP` |
| what pct changes on top of rpg | `src/neonrp/packs/pct/pack.py` |
| rule tables and layering | `src/neonrp/packs/rpg/data.py:table`, `rules`; `packs/rpg/data/rules.json`, `foes.json`, `hazards.json`; `packs/pct/data/rules.json`, `foes.json` |
| rule panel and fallback chain | `src/neonrp/packs/rpg/panel.py:attr`, `skill`, `action_attr`, `find`, `status_mod`, `nearest_tier`, `source_text` |
| character state file | `src/neonrp/packs/rpg/character_state.py` |
| d20 checks / rules referee | `src/neonrp/packs/rpg/referee.py:roll_check`, `ruling` |
| d100 checks / levels / contests / damage bonus | `src/neonrp/packs/pct/rules.py:roll_check`, `level`, `better`, `damage_bonus`, `down_roll`; `packs/pct/tools.py:dice`, `san`; `packs/pct/referee.py` |
| dice core and rulesets | `src/neonrp/core/dice.py:roll_check`, `canonical_ruleset`, `roll_expr`, `rng_for` |
| dice tools | `src/neonrp/packs/rpg/tools.py:roll`, `dice`, `sheet` |
| status line grammar | `src/neonrp/core/effect_rules.py:parse_rule`, `table`, `lookup`, `fill`, `check_of`; `src/neonrp/prompts/effect_rules.<lang>.json` |
| status countdowns and per-resolve changes | `src/neonrp/core/effects.py:tick_ops`, `instances` |
| the clock only moves forward | `src/neonrp/packs/rpg/loaders.py:_load_variables` (`time.day` / `time.clock`), `src/neonrp/core/sdk.py:_clock_back`; `src/neonrp/core/registry.py:VarSpec` |
| game-time expiry of statuses | `src/neonrp/packs/rpg/effects_clock.py:tick` |
| going down / death | `src/neonrp/packs/rpg/downed.py:tick` |
| pct's major wounds / insanity | `src/neonrp/packs/pct/tick.py:tick` |
| combat layer | `src/neonrp/packs/rpg/combat.py:spawn`, `end`, `maybe_encounter`; `src/neonrp/packs/pct/combat.py` |
| travel | `src/neonrp/packs/rpg/travel.py:plan`, `referee`, `resolve`, `route_days` |
| pre-turn gates | `src/neonrp/packs/rpg/gates.py:pre_turn` |
| layer prompt resolution | `src/neonrp/core/modes.py:prompt_source`, `layer_system`; `packs/rpg/prompts/`, `packs/pct/prompts/` |
| seams | `src/neonrp/core/mechanics.py:SEAMS` |
| mixins | `src/neonrp/packs/mixins/economy.py`, `factions.py` |
| licensing | `src/neonrp/templates/CONTENT-LICENSE.md`, `src/neonrp/packs/pct/NOTICE.md` |
