---
title: "Creator quickstart"
description: "Build a world in WorldLines: template card → template & fragments → schema → rules → assets → Lint → publish."
---

<!-- section: path -->
## The whole path

> **Status: mixed** — each section says what ships with 1.0 and what is still in design.

| Step | What | Page | Status |
|---|---|---|---|
| 1 | Fill in `card.yaml`, pick a template and fragments | [Template card](/docs/creators/template-card) | in design |
| 2 | Register variables, define classes, add instances | [Register & subscribe](/docs/creators/schema) | ships with 1.0 |
| 3 | Decide what may grow during play | [Growth policy](/docs/creators/growth) | in design |
| 4 | Write rules | [Triggers](/docs/creators/triggers) | ships with 1.0 |
| 5 | Plot packs and endings | [Plot packs](/docs/creators/plot-packs) · [Endings](/docs/creators/endings) | ships with 1.0 |
| 6 | Systems such as economy and factions | [Fragments](/docs/creators/fragments) | in design |
| 7 | Assets | [Assets: slots · recipes · views](/docs/creators/assets) | in design |
| 8 | Check and publish | [Lint](/docs/creators/lint) · [Publish to Hub](/docs/creators/publish) | in design |

Worlds, characters, templates, rule packs and play contracts each have a spec — what to write, where it goes, how the engine reads it: see [Specs](/docs/developers/specs).

<!-- section: try -->
## Five minutes

Install [WorldLines](/docs/players/quickstart) first, then inside a Stoneford world folder (start a game from the local home page; each game's folder lives under `~/.worldlines/plays/`) try:

```bash
neonrp schema list variables
neonrp schema register variables price.T001.grain \
  --spec '{"type":"int","path":"game/towns/T001/market.json","key":"price.grain","min":1,"max":99,"doc":"Stoneford grain price, copper per measure"}'
neonrp schema get price.T001.grain
```

> `neonrp schema` ships with 1.0.

<!-- section: studio -->
## The studio

In 3.0 the studio and the creation agent share one set of **creator ops** (`register_class` · `register_var` · `set_policy` · `add_slot` · `edit_recipe` · `fill_asset` · `edit_prompt` · `set_rule` · `cast`). Creating also goes through propose → verify → apply, and changes land in the commit graph — so edits to a template can be branched, compared and rolled back too. (In design)
