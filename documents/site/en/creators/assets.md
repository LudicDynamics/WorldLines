---
title: "Assets: slots · recipes · views"
description: "Slots say which pictures are needed, recipes say how they are made, views say how state is shown. All live under ui in template.json."
---

<!-- section: slots -->
## ① Slots: what is needed

> **Status: ships with 1.0** — `neonrp template slots <template>` lists every slot and whether it is filled; the "Assets" column on the Template page uploads or generates.

Slots are a list, declared per **class**: every instance of the class needs one. The rules pack brings a set; a template overrides or adds by `cls` + `slot` under `ui.slots`. The `rpg` pack's own:

```json
[
  {"cls": "level", "slot": "map",      "kind": "image", "ratio": "3:2",  "hotspots": true, "required": "publish", "recipe": "map"},
  {"cls": "soul",  "slot": "portrait", "kind": "image", "ratio": "3:4",  "required": "publish", "recipe": "portrait"},
  {"cls": "soul",  "slot": "sprite",   "kind": "image", "required": "optional", "recipe": "sprite"},
  {"cls": "place", "slot": "scene",    "kind": "image", "ratio": "16:9", "required": "optional", "fallback": "map_crop", "recipe": "scene"},
  {"cls": "item",  "slot": "icon",     "kind": "icon",  "required": "optional", "recipe": "item_icon"}
]
```

| Field | Meaning |
|---|---|
| `cls` · `slot` | which class, which slot |
| `kind` | `image` · `icon` and so on |
| `required` | `publish` = needed to publish; `optional` = may stay empty |
| `recipe` | how it is generated (below) |
| `ratio` · `fallback` | aspect ratio; what stands in when there is no picture |
| `scope` | `class` = one picture shared by the whole class instead of one per instance |

A `required: publish` slot that is empty or stale blocks publishing in [Lint](/docs/creators/lint) under `lint.level: publish`, and only warns under `draft`.

Besides these class slots, the cover, the item / place / ending pictures in plot packs, opening CGs and reward card pictures are slots too, filled in the same column.

**Use the portrait as the sprite**: when a character's portrait is already a full-body picture, write this in its `soul.json`:

```json
"assets": {"sprite": "portrait"}
```

The sprite slot then points at the portrait; no file is copied.

<!-- section: recipe -->
## ② Recipes: how it is made

`recipe` is a built-in recipe (`map` · `scene` · `portrait` · `sprite`) or a named prompt in the template's `ui.prompts`. Generation goes to the configured image backend: `openai` · `codex` · `comfyui`.

- **The map** (`map`) first draws a layout guide from the coordinates in the world files, then hands it to the image model; the points on the map use the same coordinates, so they line up. When places change, the map is marked stale.
- **Portraits / sprites** are prompted from the character's persona.
- **Named prompts** may use placeholders like `{inst.name}` and `{style}`; Greyoak House's player portrait is the named prompt `player_portrait`.

<!-- section: view -->
## ③ Views: how it is shown

A view only says **which variables it binds, which widget, and layout hints** — no HTML. The economy fragment's own "Market":

```json
{"id": "market", "title": {"zh": "集市", "en": "Market"}, "bind": ["price.{town}.*", "stock.{town}.*", "inv.*"],
 "widget": "table", "actions": ["trade"], "layout": {"area": "right", "order": 3}}
```

`{town}` = the town the player is in, `*` = one segment. A view may also bind a class: `"class:quest"`. Widgets: `table` · `gauge` · `bars` · `meter` · `sparkline` · `list` · `number`.

During play, `GET /api/v1/play/engine/views` returns each view with the current values it binds; the front end draws it its own way.
