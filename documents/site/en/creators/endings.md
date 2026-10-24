---
title: "Endings"
description: "An ending is one kind of trigger output. When it fires, the run has reached its exit: epilogue, then settlement."
---

<!-- section: emit -->
## An ending is a trigger's output

> **Status: ships with 1.0**

One rule from Stoneford's plot pack `P20`:

```json
"P20.E1": {"when": {"flag": "coffin_answered"}, "if": [{"flag": "amu_found"}],
           "then": [{"to": "end", "ending": "E1"}], "once": true}
```

When `{"to": "end"}` fires, the **whole run** reaches its exit:

- `game/meta/ending.json` is written, the `ended` flag is set, the ledger records `turn.ended`;
- the next narration is the epilogue: it closes this thread and opens nothing new;
- the engine writes a settlement `game/meta/settlement.json` according to the [play contract](/docs/creators/contracts) (exit, unlocked CGs, deaths, rewards, truth), and the play screen draws the ending card from it.

A run has one ending: the first one to fire counts.

<!-- section: modes -->
## Three ending modes

`mode.ending` in `template.json`:

| Mode | Meaning | Example |
|---|---|---|
| `open` | no required ending; play on as long as you like | |
| `single` | one ending | |
| `multi` | several endings | Stoneford (4: the true ending E1, two other endings E2 / E3, the fail ending E9); Greyoak House (3) |

Endings are defined under `endings` in a plot pack, with `kind` set to `true` (the true ending), `alt` or `fail`. The number and kinds a contract requires are checked by [Lint](/docs/creators/lint) — `mystery-trpg`, for example, needs at least 3, one of them a true ending.

<!-- section: segment -->
## Open worlds: settling by segment

The `open-adventure` contract's exit is a **segment** (`exit.on: segment`, one segment = one day): each day the engine records a segment's settlement, and the run goes on.

But whenever a plot pack's `{"to": "end"}` fires, the run ends, whatever the mode. Stoneford uses the open-adventure contract and also has 4 endings: reaching day 8 before the last stage, or the player falling, fires the fail ending E9.

<!-- section: truth -->
## The truth

A plot pack writes `reveal` (the solution, per language), revealed at the ending. The `mystery-trpg` contract also asks for a "truth quiz" after settlement: three questions in the plot pack's `truth_quiz.questions`; right answers earn credits, and all three right can bring a named character home. See [Plot packs](/docs/creators/plot-packs).
