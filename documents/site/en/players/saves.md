---
title: "Save · branch · undo"
description: "Every step can be undone, or branched to try another path."
---

<!-- section: cmds -->
## In game

> **Status: ships with 1.0**

| Command | Does |
|---|---|
| `/save <name>` | make a checkpoint |
| `/branch <name>` | split off a new world line here and try another path on it |
| `/undo` | roll back one step |

Branches never affect the main line.

<!-- section: under -->
## Behind it: the commit graph

Every turn is a commit — see [World lines](/docs/concepts/worldlines). From a terminal: `neonrp commit log`.
