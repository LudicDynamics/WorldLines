---
title: "Specs"
description: "The full specs for worlds, characters (souls), templates, rules packs and play contracts: what goes where and how the engine reads it."
---

<!-- section: specs -->
## Specs

Read the matching spec before you write a world, a character, a template or a rules pack. Agents (Claude Code / Codex)
read the same files when they author.

| Spec | What it covers | English | 中文 |
|---|---|---|---|
| World | The world folder: map, places, people, items, rule tables, opening | [world.en.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/world.en.md) | [world.zh.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/world.zh.md) |
| Soul (character) | The character bundle: identity, persona, memory, RPG body, portrait | [soul.en.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/soul.en.md) | [soul.zh.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/soul.zh.md) |
| Template | A world + characters + a rules pack bound into one playable, publishable package | [template.en.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/template.en.md) | [template.zh.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/template.zh.md) |
| RPG Pack | Rule tables, rule panels, checks and contests, the status table, the clock (`rpg` / `pct`) | [pack.en.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/pack.en.md) | [pack.zh.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/pack.zh.md) |
| Contract | The play contract: turns, deaths, endings | [contract.en.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/contract.en.md) | [contract.zh.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/contract.zh.md) |

With the engine installed you can read them in the terminal:

```bash
neonrp spec                 # list every spec
neonrp spec pack            # print one (--lang en for English)
neonrp spec ops --pack rpg  # the ops, classes and variables a rules pack offers
```
