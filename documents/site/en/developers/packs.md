---
title: "Rules pack development"
description: "A rules pack decides which classes, ops, variables, triggers and seams a run has. A Python pack or a JSON pack, with mixins on top."
---

<!-- section: template -->
## Choosing one in a template

A template says, in `template.json`:

```json
"pack": {"name": "rpg", "mixins": ["economy"], "engine": {"turn": {"mode": "v3"}}}
```

- `name`: the base rules pack;
- `mixins`: mixins laid on top, see [Write a mixin](/docs/developers/fragment);
- `engine`: engine settings for the run, merged into `game/meta/engine.json` when the run is built.

A built run records the combined name in `manifest.json` under `template`, e.g. `rpg+economy`.

<!-- section: pack -->
## Pack

```python
Pack(name, classes, actions, variables, triggers, mechanics, prompt, doc,
     flags=…, blocks=…, prompt_spec=…, modes={}, loop={}, ticks=[], mixins=(),
     base="", orchestration={}, ui={}, cast_class="")
```

| Field | Fills |
|---|---|
| `classes` | open-schema classes (ClassSpec) |
| `actions` | the allowed ops (ActionSpec: handler + validator) |
| `variables` | closed-schema variables |
| `triggers` | WHEN / IF / THEN / ELSE |
| `mechanics` | seam → handler name (see below) |
| `modes` | mode layers (e.g. combat): their own prompt, usable ops, exit op |
| `loop` | the pack's turn settings (an engine-config fragment) |
| `ticks` | world rules run after every landing, `module:function` |
| `mixins` · `base` | the mixins laid on; the built-in pack it is built on (pct → rpg) |
| `orchestration` | nodes and edges the pack adds to the orchestration graph |
| `ui` | asset slots, views, panels, how beats are shown |
| `cast_class` | when the cast is not souls, the class whose instances are the cast (e.g. werewolf seats) |
| `prompt` · `prompt_spec` | the pack's own world-side text and prompt entries |

Four are built in:

- `rpg` (the default, open-world RPG);
- `pct` (sandbox tabletop: built on `rpg`, keeping its map, people and combat layer, with percentile dice — a check is d100 against a skill or attribute, plus sanity checks);
- `werewolf` (no map, the seats are a registered class, `vote` / `kill` are the pack's own ops, the world side is the judge);
- `monopoly` (a ring board; dice, rent and tax are settled by code, the narrator only narrates and decides whether to buy).

Werewolf and Monopoly exist to prove it: **the engine contains no game.** The ops, classes and variables of each pack: `neonrp spec ops --pack <name>`.

How to write rule tables, rule panels, checks and contests, the status table and the clock: the "Rules pack" spec in [Specs](/docs/developers/specs).

<!-- section: seams -->
## Seams

The engine core only knows these seams exist; which function fills each one is registered by the pack (and can be overridden in a world's `manifest.json["mechanics"]` or `game/meta/mechanics.json`). There are 18:

`contract` · `soul_turn` · `observe` · `settle` · `participation` · `load` · `pack_hints` · `companions` · `speech_rule` · `gate` · `post_solve` · `understand` · `after_turn` · `roll_check` · `plan_event` · `run_outputs` · `sheet` · `skill_check`

Signatures and defaults are in the header of `neonrp/core/mechanics.py`. An op's `validator` / `handler` is the other kind of seam, registered with the action.

<!-- section: json -->
## JSON packs

A folder holding `pack.json`; handlers are written `builtin:…` or `module:function`; `extends` inherits, `null` removes something from the parent; `mixins` can go here too:

```json
{
  "name": "stoneford-guilds", "extends": "rpg", "mixins": ["economy"],
  "classes": {"guild": {"required": ["name"], "folder": "game/guilds", "scope": "town"}},
  "actions": {"new_npc": null,
              "pay_dues": {"kind": "action", "handler": "myguilds:pay_dues", "validator": "myguilds:judge_dues",
                           "fields": ["guild", "amount"], "doc": "The player pays the guild its dues"}},
  "variables": {"guild.T001.dues": {"type": "int", "min": 0, "path": "game/towns/T001/guild.json", "key": "dues"}}
}
```

<!-- section: resolve -->
## How a name resolves

Which pack a run uses: `manifest.json["template"]` > `playthrough.json["template"]` (root or `.neonrp/`) > the default `rpg`.

A name is looked up in this order:

1. with a `+` (`rpg+economy`): split into the base pack + mixins;
2. `module:PACK`: that object is imported;
3. a path to a folder holding `pack.json`;
4. the built-ins `rpg` / `werewolf` / `monopoly` / `pct`;
5. the world's own `<world>/template/`, then a folder of that name with `pack.json` on `NEONRP_TEMPLATE_PATH`.

<!-- section: config -->
## Settings layers

A run's engine settings merge in layers, later ones winning:

built-in defaults < the pack's `loop` < the play contract < the orchestration (the one the template's `uses` picks) < the world's `game/meta/engine.json` (including the template's `pack.engine`) < orchestration-graph step parameters < this run's `playthrough` < environment variables

Run `neonrp engine explain` in a world folder to list each setting's effective value and the layer it comes from.
