---
title: "Lint: checks before publishing"
description: "The template is built into a run first, then checked: references, assets, prompts, tokens, plots, contract, languages. Any block stops publishing."
---

<!-- section: what -->
## When it runs

> **Status: ships with 1.0** — `neonrp template lint`, the "Lint" column on the Template page; every code is listed in `spec/template.md` §7 inside the template folder.

```bash
neonrp template lint stoneford-town            # one line each: [level] code where: message; last line publishable / NOT publishable
neonrp template lint stoneford-town --json
```

The engine first **builds the template into a run** in a scratch folder (every pool candidate present, plot packs installed) and checks against that run, so plots and asset slots are checked against the real world. Each problem is **block** (stops publishing) or **warn** (a reminder). Every creator op that changes the template runs it again.

<!-- section: level -->
## `lint.level`: draft or publish

With `"lint": {"level": "draft"}` in `template.json`, missing pictures (a required slot empty or stale), a missing cover and a per-turn token count over budget are only warnings; unset or `"publish"`, they block. Both built-in templates are `draft` for now.

<!-- section: checks -->
## What it checks

| Area | What | Example |
|---|---|---|
| **Card and mode** | there is a title; `mode.ending` is open / single / multi; `zone` and `forkable` are well-formed | no title → block |
| **World and rules pack** | the world is found; the pack and fragments load; the world data a fragment needs is there | `economy` installed without `game/world/economy.json` → warn (the fragment stays inert) |
| **Characters** | every cast row finds its character (a broken library link counts); a pool's `pick` fits the pool | `{"lib": "mira"}` without a `sid` → block |
| **Prompts** | prompt files exist; `prompts/souls/<sid>/` holds only the persona layer (`soul.md` · `persona/` · `rules/` · `agents/`); every `{placeholder}` resolves | an image prompt uses `{weather}`, which is not registered → block |
| **Schema** | variables bound by views are registered; actions in views have handlers | the "Market" view binds `price.{town}.*` but the economy fragment isn't installed → block |
| **Assets** | every required slot has a file and it isn't stale | the map is stale: a new place grew on a road, hotspots no longer match |
| **Token budget** | reads this template's recent real runs and averages tokens per turn; with no runs yet it only reports `token.unmeasured` | average 24,000 per turn, budget 20,000 |
| **Plots** | plot packs parse, referenced files exist, endings are reachable | no trigger reaches any ending |
| **Contract** | against the [play contract](/docs/creators/contracts) you declared: opening, cast, number of endings, truth, ending CGs, truth quiz | `mystery-trpg` with fewer than 3 endings → block |
| **Orchestration** | `uses` is well-formed; its parameters are choices that orchestration has. An orchestration this engine doesn't have is not an error (it falls back to the single beat) | |
| **Other** | opening CGs, reward cards, audio, the `creation` layer, the player builder, the map | |
| **Languages** | structure and coverage of the English / Japanese / Korean layers (`--i18n-deep` goes further) | |

<!-- section: zone -->
## Graded by zone

A few checks take their level from the template's `zone`: the truth quiz and audio credits block in the Default Zone and warn in the Free Zone. See [Publish to the Hub](/docs/creators/publish).

<!-- section: after -->
## After it passes

No block means `publishable`. Before publishing, the engine also checks linked characters, secrets, the four-language card and the cover — see [Publish to the Hub](/docs/creators/publish). To generate the interface contract for a game client, use `neonrp template contract` (see [Interface contract](/docs/developers/contract)).
