---
title: "Growth policy"
description: "Who may add instances of a class during play: auto / approve / forbid / creator only."
---

<!-- section: policy -->
## Four policies

> **Status: in design · interfaces are provisional** — the settled 3.0 design; names and fields may still change before it ships.

| Policy | Meaning | Stoneford |
|---|---|---|
| `auto` | the world agent may propose new instances directly | `place` (with a daily budget), `caravan` |
| `approve` | proposals go to "pending"; you approve them in the studio | `npc` |
| `forbid` | no new instances during play | common in worlds with an ending |
| `creator` | only you add them, while creating | `faction` |

Switch `caravan` to `approve` and every caravan the economy rules want to send waits for you.

<!-- section: grow -->
## New places on an edge

While you travel, the world may discover a new place on the road: **insert** (A–C–B, splitting the road in two) or **branch** (a waypoint W first, then a new place C connected to it). Every new instance records where it came from: day and time, who proposed it, which commit.

<!-- section: today -->
## What exists today

Adding instances during play is implemented: `new` (a new instance of a registered class that has a folder), `new_location`, `new_npc`; worlds with an ending can switch the writers off through the manifest mode. The policy table itself is in design.
