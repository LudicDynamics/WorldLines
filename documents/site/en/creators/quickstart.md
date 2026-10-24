---
title: "Creator quickstart"
description: "Build a world in WorldLines: copy a template → schema → rules and plots → fragments → assets → Lint → publish."
---

<!-- section: path -->
## The whole path

> **Status: ships with 1.0**

| Step | What you do | Page |
|---|---|---|
| 1 | Copy a built-in template and edit `template.json`: card, mode, rules pack and fragments | [Templates](/docs/creators/template-card) |
| 2 | Register variables, define classes, add instances | [Register and subscribe](/docs/creators/schema) |
| 3 | Decide what may grow during play | [Growth policy](/docs/creators/growth) |
| 4 | Write rules | [Triggers](/docs/creators/triggers) |
| 5 | Plot packs and endings | [Plot packs](/docs/creators/plot-packs) · [Endings](/docs/creators/endings) |
| 6 | Economy, factions and other systems | [Fragments](/docs/creators/fragments) |
| 7 | Assets | [Assets: slots · recipes · views](/docs/creators/assets) |
| 8 | Check and publish | [Lint](/docs/creators/lint) · [Publish to the Hub](/docs/creators/publish) |

Worlds, characters, templates, rules packs and play contracts each have a spec — what to write, where it goes, how the engine reads it: see [Specs](/docs/developers/specs).

<!-- section: copy -->
## Step one: copy a template

The built-in Greyoak House (`pct-house`) and Stoneford (`stoneford-town`) are read-only but can be copied:

```bash
neonrp template fork stoneford-town my-town --store ~/.worldlines/templates
```

The copy is your own work (Free Zone): edit it, export it, publish it. "Make a copy" on the Template page of the local creation desk does the same thing.

<!-- section: try -->
## Try the schema in five minutes

Try it inside a run's folder (start a Stoneford run from the local home page; each run's folder is under `~/.worldlines/plays/`):

```bash
neonrp schema list variables
neonrp schema register variables town.T001.lanterns \
  --spec '{"type":"int","path":"game/towns/T001/town.json","key":"lanterns","min":0,"max":20,"doc":"Lanterns still lit at Stoneford North Gate. The thicker the fog, the more go out"}'
neonrp schema get town.T001.lanterns
```

Don't try names like `price.T001.grain`: Stoneford has the economy fragment, which already owns the market price variables, and registering the same name would overwrite it.

<!-- section: studio -->
## Creator ops

The workbenches and coding agents editing a template use the same set of **creator ops**. Every op is verified first and they are written in one go (one refused → nothing is written); Lint runs again afterwards:

| Area | Ops |
|---|---|
| Card and mode | `edit_card` · `set_mode` · `set_play_contract` |
| Rules pack | `set_mixins` · `set_world_data` (a fragment's world data) |
| Classes and growth | `register_class` · `set_policy` |
| Assets and views | `add_slot` · `remove_slot` · `edit_recipe` · `edit_prompt` · `set_view` · `remove_view` · `set_budget` |
| Casting | `set_cast` |
| Orchestration | `set_orchestration` · `set_soul_orchestration` · `set_soul_ambient` · `set_engine_setting` |

HTTP: `POST /api/v1/local/templates/<id>/ops {ops: [...]}`. Only templates in your own template store can be edited; copy a built-in one first.
