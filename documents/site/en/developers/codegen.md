---
title: "Code generation"
description: "Clients for every target, generated from the same contract."
---

<!-- section: targets -->
## Targets

> **Status: in design · interfaces are provisional** — the settled 3.0 design; names and fields may still change before it ships.

| Target | Generated |
|---|---|
| TypeScript | `stoneford.world.ts`: a typed client used directly by the WorldLines UI and studio |
| Godot | `stoneford_world.gd`: a typed property per variable, a `signal` per hook, a method per op |
| Python | a typed wrapper for tests and benchmarks |
| LLM | the text form of the same contract |

<!-- section: ts -->
## TypeScript

```ts
const w = await StonefordWorld.connect("http://localhost:8788");
w.on("price.T001.jade", (v) => hud.set(v));
const r = await w.trade({ town: "T001", good: "grain", qty: 3 });
if (!r.ok) toast(r.refused[0].why);   // "Not enough money: need 36 copper, you have 20"
```
