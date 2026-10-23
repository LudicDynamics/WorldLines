---
title: "Godot integration"
description: "A local engine process + a generated GDScript client + assets mapped into res://."
---

<!-- section: arch -->
## Architecture

> **Status: in design · interfaces are provisional** — the settled 3.0 design; names and fields may still change before it ships.

```text
Godot game  ── WebSocket / HTTP ──>  local engine process
    ^                                   |
    └── generated GDScript client <── world.contract.json
```

Godot connects to a local process (like a language server) rather than embedding the engine in the game: the NeonRP kernel is proprietary and isn't shipped with the game — only the contract and the generated client are.

<!-- section: gd -->
## The generated GDScript

```gdscript
# generated from world.contract.json · stoneford-elena · do not edit
class_name StonefordWorld
extends Node

const CONTRACT_HASH := "ae5debb"

signal changed(var_name: String, from, to)
signal refused(op: String, why: String)
signal hook_h1(payload: Dictionary)   # town.alert >= 3 → the town hall posts a curfew

var player_gold: int                   # 0…
var price_T001_grain: int              # 1…999

func trade(town: String, good: String, qty: int) -> Dictionary:
    return await propose([{"op": "trade", "town": town, "good": good, "qty": qty}])
```

<!-- section: assets -->
## Assets

Slot folders `assets/{class}/{slot}/` are copied as-is into `res://worldlines/stoneford-elena/`; map hotspots become `.tres`. Recipe graphs run on the WorldLines side and Godot only consumes their outputs; view descriptions can generate default control scenes, or you build your own UI.
