---
title: "Open schema and closed schema"
description: "All world state comes in two kinds: classes whose instances keep being added, and variables that are registered first and then only change value."
---

<!-- section: two -->
## Two kinds of state

| | Open schema | Closed schema |
|---|---|---|
| What | **classes + instances**: places, NPCs, items, quests, factions, rumors, caravans… | **registered variables**: gold, alert, prices, faction power, relations between two sides… |
| During play | new instances can keep being added (subject to the class's growth policy) | only values change; unregistered variables cannot be written |
| Example | class `faction`, instance "One-Eyed Tiger bandits" | `player.gold` = 18, `price.T001.grain` = 12 (a read-only variable registered by the economy fragment; only the engine changes it) |

The engine has five registry tables: `variables` · `classes` · `entries` · `actions` · `triggers`. The two kinds of state use the first three; `actions` decides which changes are allowed, and `triggers` are the rules creators write.

<!-- section: relations -->
## Relationships are variables

Social relationships need no special system: they are closed-schema numbers attached to entities — `town.alert` (on a town), `rel.guard.bandits` (between two factions).

A character's own side (mood, trust, intent, goals, memory) is not here: it is settled by the character's own replies, and the world does not write it.

<!-- section: howto -->
## How to register and subscribe

- Creators: [Register & subscribe (CLI)](/docs/creators/schema)
- Developers: [Register & subscribe (Python)](/docs/developers/schema-api)
