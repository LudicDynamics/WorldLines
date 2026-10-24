---
title: "Recipes"
description: "New template, casting, declaring a contract, adding an ending, exporting — which file to change and which command to run."
---

<!-- section: new -->
## Start from an existing template


```bash
neonrp template list                              # what there is
neonrp template fork pct-house my-house --title "My House"
cd <template store>/my-house.template && cat AGENTS.md
```

<!-- section: cast -->
## Put a library character in

`souls` in `template.json` (`spec/template.md` §3.6):

```json
"souls": [
  {"sid": "chara", "role": "npc"},
  {"lib": "mira", "role": "companion"}
]
```

`lib` is the folder name in the library. Who she is in this world goes in `prompts/souls/mira/soul.md` (only `soul.md` · `persona/` · `rules/` · `agents/` may be overridden). Then `neonrp template lint .`: a broken link reports `ref.soul`.

<!-- section: contract -->
## Declare a contract

```bash
neonrp template contracts                         # the four official contracts, and who declares each
neonrp template set-contract my-house mystery-trpg
neonrp template lint .                            # checked against it: opening · cast · endings · truth · ending CGs
```

What each `contract.*` code means: `spec/contract.md` §4.

<!-- section: ending -->
## Add an ending

Add one under `endings` in the plot pack `plots/<id>/plot.json` (`spec/template.md` §5): `title`, `kind` (`true` / `fail` / …), `text`; if the contract rewards ending CGs, add `assets.image` and put the image in `plots/<id>/assets/`; then a trigger with `"then": [{"to": "end", "ending": "<id>"}]` so it is reachable. Lint checks "reachable", "one ending per branch", "endings have titles".

<!-- section: map -->
## Add a place, connect a road

Places are folders (`spec/world.md`): `world/game/locations/<town>/<place>/location.json`; the folder it sits in is its level, `connections` lists its neighbours. Then run `neonrp validate` inside `world/`.

<!-- section: share -->
## Take it with you

```bash
neonrp template export my-house                   # → my-house.template.zip (with the characters it links)
neonrp template import my-house.template.zip --id my-house-2
```
