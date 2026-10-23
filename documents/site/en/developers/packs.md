---
title: "Template pack development"
description: "Pack = classes / actions / variables / triggers / mechanics / prompt. A Python pack or a JSON pack."
---

<!-- section: pack -->
## Pack

> **Status: ships with 1.0**

```python
Pack(name, classes, actions, variables, triggers, mechanics, prompt, doc)
```

| Field | Goes into |
|---|---|
| `classes` | open-schema classes (ClassSpec) |
| `actions` | allowed ops (ActionSpec: handler + validator) |
| `variables` | closed-schema variables |
| `triggers` | WHEN / IF / THEN / ELSE |
| `mechanics` | seams: `contract` · `soul_turn` · `observe` · `settle` · `participation` |
| `prompt` | the template's own world-side contract text |

Four are built in:

- `rpg` (default, open-world RPG);
- `pct` (sandbox tabletop: built on `rpg` — map, people and the combat layer carry over — with BRP percentile dice instead: a check is d100 under a skill or an attribute × 5, plus sanity and dying checks);
- `werewolf` (no map; seats are a registered class; `vote` / `kill` are template ops; the world side is a judge);
- `monopoly` (a ring board; dice, rent and tax are settled by procedure; the narrator only narrates and decides whether to buy).

Werewolf and Monopoly prove the point: **the engine contains no gameplay.**

How to write rules tables, the rules panel, checks and contests, the status table and clocks: see "RPG Pack" in [Specs](/docs/developers/specs).

<!-- section: json -->
## JSON packs

A folder holding `pack.json`; handlers named `builtin:…` or `module:function`; `extends` inherits and `null` removes something from the parent:

```json
{
  "name": "stoneford-trade", "extends": "rpg",
  "classes": {"caravan": {"required": ["from", "to", "cargo"], "folder": "game/caravans"}},
  "actions": {"new_npc": null,
              "trade": {"kind": "action", "handler": "mytrade:apply_trade", "validator": "mytrade:judge_trade",
                        "fields": ["town", "good", "qty"], "doc": "the player buys or sells at a market"}},
  "variables": {"price.T001.grain": {"type": "int", "min": 1, "path": "game/towns/T001/market.json", "key": "price.grain"}}
}
```

<!-- section: resolve -->
## Which pack a world uses

`manifest.json["template"]` > `playthrough.json["template"]` (root or `.neonrp/`) > the default `rpg`. Names resolve in order: built-in packs → a path or `module:PACK` → the world's own `<world>/template/` → folders on `NEONRP_TEMPLATE_PATH` (the WorldLines template store).

<!-- section: mixins -->
## mixins (in design)

Today a pack supports one `extends`. `mixins: [...]` is planned: one base template plus several fragments merged, with conflicts reported as errors. See [Write a fragment](/docs/developers/fragment).
