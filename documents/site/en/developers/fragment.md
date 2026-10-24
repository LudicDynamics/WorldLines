---
title: "Write a mixin"
description: "The built-in economy mixin as the example: classes, ops (check + land), ticks that run every step, views. The rules live in the mixin, the data in the world."
---

<!-- section: shape -->
## The shape of a mixin

A mixin sits on top of a base rules pack: a template writes `"pack": {"name": "rpg", "mixins": ["economy"]}` and the run's pack is `rpg+economy`. Two are built in: `economy` (markets, prices, caravans, trade) and `factions` (factions, relations, rumors, quests). Source: `neonrp/packs/mixins/`.

A mixin is one dict, `MIXIN`, with the same keys as a pack:

| Key | What it does |
|---|---|
| `classes` | open-schema classes, e.g. `caravan` |
| `actions` | ops: `handler` (lands it) + optional `validator` (checks it) + `fields` + `doc` (the line the model reads each turn) |
| `variables` · `triggers` | closed-schema variables and triggers |
| `ticks` | world rules run after every landing (no model call) |
| `ui` | asset slots, views, panels |
| `prompt` | prompt entries for the model |
| `mechanics` · `loop` · `orchestration` | seams (only the ones the base left empty), turn settings, additions to the orchestration graph |

Merging: classes / ops / variables / triggers with the same name — the later one wins, no error; ticks append; seams only fill what the base left empty.

**Rules in the mixin, data in the world.** economy reads `game/world/economy.json` (goods, each town's market, routes); without that file the mixin does nothing and lint warns `pack.mixin.data`. Stoneford ships its data in `world-overlay/game/world/economy.json`.

<!-- section: install -->
## Install: register the variables

When a run is built (`template build` / a new game), the engine calls `install(root)` on each built-in mixin. economy registers its closed-schema variables from the world data and seeds their values:

```python
def install(root):
    d = data(root)                                   # game/world/economy.json
    specs = {}
    for t, m in d["markets"].items():
        for g in d["goods"]:
            specs[f"price.{t}.{g}"] = {"type": "int", "path": f"game/towns/{t}/market.json", "key": f"price.{g}",
                                       "min": 1, "max": 9999, "readonly": True, "seed": …, "doc": …}
            ...                                      # stock.<T>.<g> · inv.<g> · econ.index the same way
    return register_vars(root, specs)                # writes game/meta/variables.json, only what is missing
```

The model cannot change a `readonly` variable directly; only the mixin's own ops and ticks change it.

<!-- section: op -->
## An op: check + land

```python
from neonrp.core.handlers import Verdict

def judge_trade(root, reg, op) -> Verdict:
    t = town_of(reg, reg.player_location)
    g, qty = str(op.get("good") or ""), int(op.get("qty") or 0)
    if t not in data(root)["markets"]:
        return Verdict(False, reason="There is no market here")
    if qty > 0 and coins(reg) < price(reg, t, g) * qty:
        return Verdict(False, reason=f"Not enough money: {price(reg, t, g) * qty} copper needed", scope="field", field="qty")
    return Verdict(True, data={"good": g, "qty": qty, "town": t})   # data is merged into the accepted op

def trade(root, reg, op, res):
    ...                    # change the wallet, stock, inv (set_var)
    return {"town": t, "unit": unit, "total": total, "side": "buy" if qty > 0 else "sell"}
```

- validator `validator(root, reg, op) -> Verdict`, handler `handler(root, reg, op, res) -> dict`;
- `Verdict(ok, to=None, clamped=False, reason="", allowed=[], data={}, scope="world", field="op", fixable=True)` is a dataclass; build it with the constructor;
- a refusal's `reason` goes back to the model (a fixable refusal makes it rewrite the state), so write it in plain words; `fixable=False` means don't propose it again;
- registration: `"trade": {"kind": "action", "handler": "neonrp.packs.mixins.economy:trade", "validator": "neonrp.packs.mixins.economy:judge_trade", "fields": ["good", "qty"], "doc": …}`.

<!-- section: rule -->
## A tick: it only proposes

```python
def tick(root, reg, *, turn, res) -> list[dict]:
    ops = []
    for t, g in markets(reg):
        p = price_from_stock(...)
        if p != vint(reg, f"price.{t}.{g}"):
            ops.append({"op": "set", "var": f"price.{t}.{g}", "value": p})
    return ops

tick.unit = {"on": "apply", "llm": False,
             "writes": ["var:stock.*", "var:price.*", "var:econ.index", "op:new_caravan", "op:haul", "op:deliver", "op:rob"]}
```

Register it in `MIXIN["ticks"]`: `["neonrp.packs.mixins.economy:tick"]`. It runs on every landing, after the turn's own ops and before the triggers. Ops a tick returns skip the checks the model's ops go through, but the engine refuses two kinds: an unregistered op, and a write outside what `tick.unit["writes"]` declares. Refusals are recorded in the beat's `refused` and never break the turn. For randomness use `rng(...)` seeded by `(turn, event)`, so replaying a turn gives the same result.

economy's tick, in order: production minus consumption → prices follow stock → caravans on the road move, get robbed or arrive → new caravans leave on routes where the price spread is wide enough.

<!-- section: own -->
## Your own mixin

A mixin name is looked up two ways: a built-in name is imported from `neonrp.packs.mixins.<name>`; otherwise it is taken as a path, and the `mixin.json` in that folder (or that JSON file) is read — same shape as above, handlers written as `module:function` (the module must be importable).

- `install` is only called for mixins under `neonrp.packs.mixins`; a JSON mixin writes its variables out in `variables`.
- The path resolves against the engine process's working directory, so for now use an absolute path; this suits local experiments.
- After a change run `neonrp template lint <template>`: a mixin that cannot be found is a block, a world missing its data file is a warn.
