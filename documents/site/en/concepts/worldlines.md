---
title: "World lines"
description: "Every turn is a commit; roll back, branch from anywhere, compare with another line."
---

<!-- section: dag -->
## The commit graph

> **Status: ships with 1.0**

Every playthrough has a **commit graph (DAG)**: each turn lands a commit with its parent and a snapshot. `neonrp commit` provides `log` · `checkout` · `branch` · `gc` · `verify`; commits are stored in `~/.worldlines/commits` by default. In game, players use `/save` `/branch` `/undo` — see [Save · branch · undo](/docs/players/saves).

<!-- section: why -->
## Why it matters

Worlds grow things by themselves (new places, caravans, rumors). The same opening can grow into two different worlds on two lines and be compared item by item — the basic tool for simulating and testing world rules.

> In design: a visual commit graph in the studio, one-click branching from any commit, item-by-item diff of two lines (see the 3.0 mock).
