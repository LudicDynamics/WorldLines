---
title: "Interface contract: world.contract.json"
description: "Exported for each world once Lint passes. Every client is generated from it."
---

<!-- section: what -->
## What a contract is

> **Status: in design · interfaces are provisional** — the settled 3.0 design; names and fields may still change before it ships.

The protocol is *how to talk*; the contract is *what this world has to talk about*. Assembly and Lint have already resolved the pack, fragments, content and slots, so a world-specific contract can be exported:

```json
{
  "world": "stoneford-elena", "version": "1.2", "hash": "sha256:…",
  "template": "rpg", "mixins": ["space", "tick", "economy", "factions"],
  "variables": {"price.T001.jade": {"type": "int", "min": 1, "max": 999, "on": "T001"}},
  "classes":   {"caravan": {"required": ["from", "to", "cargo"], "policy": "auto"}},
  "ops":       {"trade": {"fields": {"town": "str", "good": "enum", "qty": "int"}, "from": "economy"}},
  "events":    ["var.changed", "entity.created", "trigger.fired", "turn.ended"],
  "slots":     {"place.scene": {"kind": "image", "ratio": "16:9"}},
  "views":     {"market": {"bind": ["price.{town}.*", "inv.*"], "widget": "table", "actions": ["trade"]}}
}
```

<!-- section: hash -->
## Hash and compatibility

When the contract changes, so does its hash. Clients regenerated from a new contract **fail to compile** on removed variables, and a Godot client refuses to connect when `CONTRACT_HASH` doesn't match — instead of silently breaking at runtime.
