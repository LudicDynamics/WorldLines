---
title: "Lint: checks before publishing"
description: "Checks that references resolve, assets are filled, prompt placeholders resolve, and the token budget holds. If it fails, you cannot publish."
---

<!-- section: what -->
## When it runs

> **Status: ships with 1.0** — `neonrp template lint`, the "Lint" tab on the Template page; every code is in `spec/template.md` §7 in the template folder.

WorldLines first **assembles** the template pack + fragments + world content + protagonists + assets + prompts + rules, then runs **Lint**. If Lint fails, the world cannot be published. Every item has two levels: **block**, or **warn**.

<!-- section: checks -->
## Four kinds of checks

| Kind | Checks | Example of a block |
|---|---|---|
| **references** | variables used by rules, triggers and views are registered; every op has a handler; variables and ops of an uninstalled extension can't be referenced | the "Market" view binds `price.{town}.*` but the economy fragment isn't installed |
| **assets** | every `required: publish` slot has a file that isn't stale | the Stoneford map is stale: a new place grew on the road and the hotspots no longer match |
| **prompts** | every `{placeholder}` resolves from a variable or the recipe context | a prompt references `{weather}` which isn't registered |
| **token budget** | dry-run turns, average tokens per turn; over the template's declared budget → block | 24,000 per turn against a budget of 20,000 |

<!-- section: today -->
## What it checks today

Beyond the four kinds above: the **world and play pack** load, every **character** resolves (a broken library link included), **plots** parse and their endings are reachable, the **ending mode** (single / multi / open) holds, the **card** has a title and a cover, and — against the [play contract](/docs/creators/contracts) you declared — the opening, the cast, the number of endings, the truth, the ending CGs.

```bash
neonrp template lint <template>          # one line per problem: [level] code where: msg; last line publishable / NOT publishable
neonrp template lint <template> --json
```

The engine builds a throwaway run with everyone present, so plots and asset slots are checked against the real world.

<!-- section: after -->
## After it passes

Passing Lint exports the [interface contract](/docs/developers/contract) `world.contract.json`, then goes through [local approval → Hub](/docs/creators/publish).
