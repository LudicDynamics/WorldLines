---
title: "Plot packs"
description: "Key items, new places, if/else, endings, and the assets the front end shows — one checkable bundle."
---

<!-- section: what -->
## What it is

> **Status: ships with 1.0**

Stored in `plots/<id>/plot.json`: `stages` (a `<id>.stage` variable is declared for you) · `classes` / `vars` · `entries` (key items, new places, NPCs, each with optional `assets`) · `triggers` · `endings`.

Also available: `stage_var` (another variable serves as the stage) · `stage_cg` (a picture shown when a stage is reached) · `prompt` (text appended for the narrator) · `reveal` (the solution, revealed at the ending) · `truth_quiz` (the truth quiz after settlement) · `collect` (which of the world's characters can be collected, and when). Stoneford's `plots/P20` and Greyoak House's `plots/P01` are two complete examples.

<!-- section: example -->
## Example

```json
{
  "id": "P01", "title": "The Key in the Fog", "stages": ["setup", "rise", "turn", "close"],
  "entries": {
    "I900": {"class": "item", "name": "Rusty key", "parent": "T001/well", "assets": {"image": "key.png"}},
    "T001/crypt": {"class": "place", "name": "Crypt", "parent": "T001", "links": ["T001/well"],
                   "assets": {"image": "crypt.png", "bgm": "crypt.mp3"}}
  },
  "triggers": {
    "P01.end_fog": {"when": {"var": "P01.stage"}, "if": [{"var": "P01.stage", ">=": 3}],
                    "then": [{"to": "end", "ending": "E01"}],
                    "else": [{"to": "narration", "text": "The fog has not lifted yet."}]}
  },
  "endings": {"E01": {"title": "The Fog Lifts", "assets": {"image": "e01.png", "video": "e01.mp4"}}}
}
```

<!-- section: lint -->
## Checks and install

A plot pack checks itself: every referenced file must exist and be a kind the front end can show (image / portrait / video / audio / bgm / sfx). Installing registers it into the world through the same entry point as `neonrp schema register`, and copies the folder into `game/plots/<id>/` so it travels with the world.
