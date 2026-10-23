---
title: "Fragments: economy · factions"
description: "Common systems as stackable fragments. Each does three things: register variables, register classes, register ops and rules."
---

<!-- section: what -->
## Stacking

> **Status: in design · interfaces are provisional** — the settled 3.0 design; names and fields may still change before it ships.

```yaml
template: rpg
mixins: [space, tick, economy, factions]
```

Fragment rules are T2 (no tokens), and what they propose goes through verify just like a player's proposals. A fragment declares which classes and ops exist and what their growth policies are; the world agent may only add instances within that scope — this is the agreement between the world agent and the World Schema.

<!-- section: economy -->
## The economy fragment

| Part | Content |
|---|---|
| variables | `stock.{town}.{good}` · `price.{town}.{good}` · `inv.{good}` · `econ.index` |
| classes | `caravan` (keeps growing during play) |
| ops | `trade` · `new_caravan` · `deliver` · `rob` |
| rules | production − consumption; pricing `price = base × (target stock / stock)^0.55 × (1 + rumor premium)`; a spread > 35% sends a caravan; roads marked "bandits" may see robberies |

Three markets — Stoneford, Jadestone, Windstack — trading grain, salted fish, herbs, jade and ironware. "Buy 3 measures of grain", "sell jade", "check the prices" become `trade`; verify checks your money, the stock, and whether you are in town. Walking next to a caravan is escorting it.

<!-- section: factions -->
## The factions fragment

| Part | Content |
|---|---|
| variables | `faction.{id}.power` · `faction.{id}.wealth` · `rep.{id}` (player reputation) · `rel.{a}.{b}` (relations) |
| classes | `faction` · `quest` · `rumor` |
| ops | `new_quest` · `quest` · `rumor` · `spread` · `strike` |
| rules (every 4 ticks) | the guard patrols when alert is high; the One-Eyed Tiger robs, recruits with its loot, and raids the Jadestone mine when strong; the guild posts bounties and escort jobs; miners strike when jade is too cheap |

**Rumors** spread along roads, with caravans, and with travelling protagonists (Rowan walking from Jadestone to Stoneford brings Jadestone's rumors with him); when a town hears "bandits on the north road", goods from the north road get pricier.

**Escort jobs**: the guild posts one for a caravan heading to Jadestone; the caravan waits at the gate, follows you when you leave, you can drive off bandits if you're beside it, and you collect the reward and reputation on arrival.

<!-- section: write -->
## Write your own

See the developer page [Write a fragment](/docs/developers/fragment).
