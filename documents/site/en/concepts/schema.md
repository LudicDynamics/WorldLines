---
title: "Open schema and closed schema"
description: "All world state comes in two kinds: classes whose instances keep being added, and variables that are registered first and then only change value."
---

<!-- section: two -->
## Two kinds of state

> **Status: ships with 1.0**

| | Open schema | Closed schema |
|---|---|---|
| What | **classes + instances**: places, NPCs, items, quests, factions, rumors, caravans… | **registered variables**: gold, alert, prices, trust, faction power… |
| During play | new instances can keep being added (subject to the class's growth policy) | only values change; unregistered variables cannot be written |
| Example | class `faction`, instance "One-Eyed Tiger bandits" | `player.gold` = 18, `price.T001.grain` = 12 |

The engine has five registry tables: `variables` · `classes` · `entries` · `actions` · `triggers`. The two kinds of state use the first three; `actions` decides which changes are allowed, and `triggers` are the rules creators write.

<!-- section: relations -->
## Relationships are variables

Social relationships need no special system: they are closed-schema numbers attached to entities — `elena.trust` (on a protagonist), `town.alert` (on a town), `rel.guard.bandits` (between two factions).

<!-- section: howto -->
## How to register and subscribe

- Creators: [Register & subscribe (CLI)](/docs/creators/schema)
- Developers: [Register & subscribe (Python)](/docs/developers/schema-api)
