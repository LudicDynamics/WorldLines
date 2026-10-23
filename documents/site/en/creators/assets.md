---
title: "Assets: slots · recipes · views"
description: "Assets are a view of the schema. All three stages are keyed by the same schema address."
---

<!-- section: slots -->
## ① Slots: what is needed

> **Status: in design · interfaces are provisional** — the settled 3.0 design; names and fields may still change before it ships.

Classes declare which assets they need:

```yaml
level:   { map:      {kind: image, ratio: "3:2", hotspots: true, required: publish} }
soul:    { portrait: {kind: image, ratio: "3:4", required: publish},
           sprite:   {kind: image, from: portrait} }
place:   { scene:    {kind: image, ratio: "16:9", fallback: map crop} }
faction: { emblem:   {kind: icon} }
```

If a `required: publish` slot is empty, [Lint](/docs/creators/lint) blocks publishing.

<!-- section: recipe -->
## ② Recipes: how it is made

A recipe is a small node graph; templates ship defaults and instances may override them:

```text
read data (coordinates / props / style refs) → layout guide → prompt → generate (openai / codex / comfy)
      → post-process (crop / cut a sprite) → bind (write hotspot coordinates back)
```

That is how the Stoneford map is made: coordinates from the files become a layout guide handed to the image model; pins on the map use the same coordinates, so they always line up. Every node hashes its inputs — when places change, the map is marked "stale".

<!-- section: view -->
## ③ Views: how it is shown

A view only says **which variables it binds, which widget, and layout hints** — no HTML:

```json
{"id": "market", "title": "Market", "bind": ["price.{town}.*", "stock.{town}.*", "inv.*"],
 "widget": "table", "actions": ["trade"], "layout": {"area": "right", "order": 3}}
```

WorldLines renders it as `*.panel.html`; for Godot the code generator renders it as a control scene. **HTML is just one renderer.**
