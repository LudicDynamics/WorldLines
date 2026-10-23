---
title: "Write a fragment"
description: "Using the economy fragment as the example: register variables, register classes, register ops and T2 rules."
---

<!-- section: shape -->
## The shape of a fragment

> **Status: in design · interfaces are provisional** — the settled 3.0 design; names and fields may still change before it ships.

A fragment does three things, all through public entry points:

1. **register variables** — `stock.{town}.{good}`, `price.{town}.{good}`, `inv.{good}`, `econ.index`;
2. **register classes** — `caravan` (with a growth policy);
3. **register ops and rules** — each op is a verify / apply pair; T2 rules that run every tick can only **propose** ops.

<!-- section: op -->
## An op: verify + apply

```python
def judge_trade(root, op, reg):
    town, good, qty = op["town"], op["good"], op["qty"]
    if player_town(reg) != town:
        return Verdict.refuse(f"you are not in {town_name(reg, town)}")
    if qty > 0 and gold(reg) < price(reg, town, good) * qty:
        return Verdict.refuse(f"not enough money: need {price(reg, town, good) * qty} copper")
    return Verdict.ok()

def apply_trade(root, op, reg, res):
    ...  # change stock / inv / the purse, record in res (the engine writes var.changed from it)
```

Signatures follow the engine's `core/handlers.py`; this is a sketch.

<!-- section: rule -->
## A T2 rule: propose only

```python
def economy_tick(root, reg):
    ops = []
    for town, good in markets(reg):
        p = round(base(good) * (target(town, good) / max(1, stock(reg, town, good))) ** 0.55)
        if p != price(reg, town, good):
            ops.append({"op": "set", "var": f"price.{town}.{good}", "value": p})
    return ops            # handed to verify, exactly like a player's proposal
```

The factions fragment works the same way: `faction.*.power`, `rel.a.b`, classes `quest` / `rumor`; rules act every 4 ticks (patrols, robberies, quests, strikes), and rumors spread along edges through the `spread` op. A complete runnable version lives in the 3.0 mock.
