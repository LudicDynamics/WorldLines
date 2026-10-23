---
title: "Endings: two kinds of sandbox"
description: "With an ending and open-ended are configurations of the same thing — and they nest."
---

<!-- section: emit -->
## An ending = one kind of trigger output

> **Status: ships with 1.0**

```json
{"when": {"var": "P01.stage"}, "if": [{"var": "P01.stage", ">=": 3}], "then": [{"to": "end", "ending": "E01"}]}
```

When it fires the run is marked as ended, the ending and epilogue are written, and the ledger records `turn.ended`.

<!-- section: two -->
## Two sandboxes (in design)

| | Open-ended | With an ending |
|---|---|---|
| The world | keeps moving and growing | holds a sealed truth (the answer) |
| When it ends | you decide | an ending rule fires |
| New instances in play | on by default | off, or allow-listed |
| Example | Stoneford | Kagura Island (mystery · time loop) |

**Sealed truth**: the answer is written at creation, compiled into sealed facts committed by hash, and checked for solvability and leaks before publishing. Trust decides how many clues players and protagonists get.

<!-- section: nest -->
## Nesting

An open world can hold a plot pack with an ending (e.g. "The Key in the Fog" inside Stoneford); the ending closes that plot pack and the world keeps going.
