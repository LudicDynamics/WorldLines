---
title: "Code generation"
description: "Generate TypeScript and GDScript types and a small client from the interface contract."
---

<!-- section: targets -->
## Targets

```bash
neonrp template contract stoneford-town --ts > stoneford-town.world.ts
neonrp template contract stoneford-town --gd > stoneford_town_world.gd
```

Or `GET /api/v1/local/templates/<id>/contract?fmt=ts|gd`. Output goes to stdout; name the file yourself. The class name comes from the template id: `stoneford-town` → `StonefordTownWorld`, `pct-house` → `PctHouseWorld`.

| Target | What you get |
|---|---|
| TypeScript | types for variables, ops, classes and beat events, plus a very small HTTP client class |
| GDScript | one typed property per variable, a variable-name table, an op-name list, three signals |

Those are the only two. For a full connection (handshake, streamed prose, reconnects) use the example clients: `worldlines/examples/clients/ts/src/client.ts` and `worldlines/examples/clients/godot/addons/worldlines/client.gd` (see [Protocol](/docs/developers/protocol)). The generated types work alongside them.

<!-- section: ts -->
## TypeScript

You get: `CONTRACT_HASH`; `StonefordTownWorldVars` (variable name → type); `StonefordTownWorldOps` (op → fields); `StonefordTownWorldClass`; `ProposeResult`; `BeatEvent`; and:

```ts
export class StonefordTownWorld {
  constructor(private base = '') {}
  schema()                 // GET  /api/v1/play/schema
  say(text: string)        // POST /cmd
  tick(turns = 1)          // POST /api/v1/play/engine/tick
  on(pattern, fn)          // SSE  /api/v1/play/schema/stream?pattern=…  → returns an unsubscribe function
}
```

```ts
const w = new StonefordTownWorld("http://127.0.0.1:8788");
const off = w.on("var.changed:price.T001.*", (e) => hud.update(e));
await w.tick(3);
```

<!-- section: gd -->
## GDScript

```gdscript
# generated from worldlines.contract/0.1 · stoneford-town 0.1 · hash 1a8b17c389cd — do not edit
class_name StonefordTownWorld
extends Node

const CONTRACT_HASH := "1a8b17c389cd"

signal changed(var_name: String, from, to)
signal ended(ending: Dictionary)
signal beat(event: String, data: Dictionary)

var player_gold: int  # 0…
var price_T001_grain: int  # 1…9999
const VAR_NAMES := { "player.gold": "player_gold", … }
const OPS := ["move_to", …, "trade", "haul"]

func apply_change(var_name: String, value) -> void   # sets the property and emits changed
```

The GD version does no networking: it is a typed mirror of the state. Feed it the `var.changed` events you receive (or the variables inside `state.changed`) through `apply_change`, and connect your UI to the `changed` signal.
