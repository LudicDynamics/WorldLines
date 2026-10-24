---
title: "Fragments: economy · factions"
description: "Common systems as fragments you can stack. Each one registers variables, classes and ops, and brings a rule that runs by itself every turn."
---

<!-- section: what -->
## How they stack

> **Status: ships with 1.0**

In `template.json`, under `pack`:

```json
"pack": {"name": "rpg", "mixins": ["economy"]}
```

That is what Stoneford says. A fragment only moves when it has its own world data: `economy` reads `game/world/economy.json`, `factions` reads `game/world/factions.json` (usually placed in `world-overlay/`); without it the fragment does nothing and Lint warns.

Each fragment does four things: registers variables (closed schema), registers classes (open schema), registers ops (with validators), and adds a **per-turn rule** (a tick). The tick runs after the turn lands and calls no model; the changes it proposes land like any other change, go into the ledger and can wake triggers. The engine checks two things about them: the op is registered, and what it changes is inside what the fragment declared.

<!-- section: economy -->
## The economy fragment `economy`

| Part | Contents |
|---|---|
| Variables | `stock.<town>.<good>` · `price.<town>.<good>` · `inv.<good>` (the player's goods) · `econ.index`, all read-only: only the fragment writes them |
| Class | `caravan` (caravans, new ones keep appearing during play) |
| Ops | `trade` (the player buys or sells) · `new_caravan` · `haul` · `deliver` · `rob` |
| Every turn | production − consumption; price `base × (target stock / stock)^0.55`, clamped to 0.45–3.2×, times any rumor premium; a caravan sets out when two towns differ by more than 35%; caravans travel by route length and deliver on arrival; with the factions fragment also installed, bandits may rob them on the road |

Stoneford's data has three markets (Stoneford, Jadestone, Windstay Keep) and five goods: grain, salt fish, herbs, jade, ironware. "Buy 3 measures of grain" or "sell the jade" becomes `trade`; the validator checks that you are in a town with a market, that the good exists and the quantity is above 0. The "Market" view on the right shows local prices, stock and your goods.

<!-- section: factions -->
## The factions fragment `factions`

| Part | Contents |
|---|---|
| Variables | `faction.<id>.power` · `faction.<id>.wealth` · `rep.<id>` (the player's standing) · `rel.<a>.<b>` (relations between two sides) |
| Classes | `faction` · `quest` · `rumor` |
| Ops | `take_quest` (the player takes a quest) · `new_quest` · `quest` · `rumor` · `spread` · `strike` |
| Every turn | rumors spread along routes by heat and cool down every 4 turns; the guard patrols when alert is high or bandits are strong; bandits recruit with loot and raid when they out-muscle the guard; the guild posts a bounty when bandits grow and pays out when they shrink; workers strike when their good stays too cheap |

A faction's behavior comes from its `role` in the data: `bandits`, `guard`, `labor`. A tagged rumor can put a premium on some goods (`premiums`), which ties it to the economy: once a town hears "bandits on the north road", goods from the north get dearer.

`take_quest` needs you to be where the quest giver is; the "Quests" view lists the current quests.

<!-- section: write -->
## Write your own

See the developer page [Write a fragment](/docs/developers/fragment).
