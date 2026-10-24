---
title: "How the engine thinks"
description: "For creators: you write the world, the engine makes it hold together. What you never write, and what you can change."
---

<!-- section: one -->
## In one line

**You write the world; the engine makes it hold together.** A world with only setting text and no rule tables should still keep things from appearing out of nowhere, keep money from multiplying, bring someone in when the player goes too far, and let characters refuse the player in their own voice. If it can't, that is an engine problem, not a prompt that is too short.

Your tables, rules and prompts only **change results**: weaker guards, "homesick stomach" instead of "food poisoning", a genie lamp that is real in your world.

<!-- section: free -->
## What you never have to write

| What the engine does | How |
|---|---|
| The player's words are an attempt | every turn the people, things and places mentioned are checked against the world; characters and narrator are told what is and isn't here. People, foes and places are checked most reliably; an object conjured out of nowhere is not always caught |
| Characters have their own minds | each present character gets its own call with the understood scene and decides what to say and whether to follow |
| Uncertain things go to a referee and dice | the narrator writes `[referee …]`; the referee picks attribute and difficulty; the engine rolls from the sheet |
| Fights have their own layer | `[combat bandit×3]` switches to the combat layer; foes come from the table; every round must roll; hp goes into state |
| Maps come from real state | when the player looks at the map or asks the way the engine draws it; the narrator neither draws nor waits |
| Prose can't quietly change state | after the prose is written, a separate call writes the turn's changes as state; every change is validated (who is present, variable ranges, whether a class may grow); where it disagrees with a tool's or the engine's ruling, the ruling wins |
| Status effects run themselves | an effect like "poisoned for 3 turns, hp −1 each turn" is one line; the engine recognises the countdown, the per-turn change and any check modifier, counts it down and removes it |

Not there yet: a table that maps kinds of behaviour (robbery, harming others …) to default consequences. Today the narrator calls the referee or the combat layer for these.

<!-- section: turn -->
## How many beats a turn has

WorldLines from PyPI includes the full two-beat orchestration: first **planning** (the host takes up what you said, the characters present respond, the world doesn't move), and once it is agreed, **resolve** (it actually happens and is written into state). An engine built from the open-source repository runs single-beat turns, resolving straight away. Both built-in templates use two beats. See [How a turn runs](/docs/concepts/turn-flow) and [Planning and resolve](/docs/concepts/planning-resolve).

<!-- section: change -->
## Four things you can change

1. **Tables**: `game/rules/<table>.json` overrides the engine's own — `hazards` (things on the road), `foes` (stat tiers), `rules` (difficulty tiers, checks). Status effects go in `game/rules/status.md`, one per line.
2. **Prompts**: overridden per stage · layer · slot. At run time three layers stack: the rules pack's own < the world's `manifest.json` → `prompt` < the run's `game/meta/prompt.json`. When a run starts, the template's `prompts/` and the plot packs' `prompt` are merged into `game/meta/prompt.json`; with `world.prompts: "replace"` in the template, the world's own copy is dropped and only the template's is used. Slots: `rules` · `voice` · `blocks` · `ops_docs` · `entries` (always / on keyword / at a place / on a variable / on a flag).
3. **Triggers**: WHEN → IF → THEN / ELSE, written in the world or a plot pack, checked after every apply, cascading. See [Triggers](/docs/creators/triggers).
4. **Ops and panels**: a new action or tool declares whether it waits (`wait`) and how it shows (text / JSON / image panel).

How a check works: the host only picks who rolls, against whom, which attribute or skill, and which difficulty tier — **no numbers**; the engine reads the rules panel, adds status modifiers, rolls and judges. `rpg` is 1d20 + modifier against a DC; `pct` is d100 against a target (attribute × 5 or a skill value), graded `crit` · `special` · success · fail · `fumble`. Attributes use short keys such as `str` `dex` `int` `cha` (`app` on older character sheets reads as `cha`). The full shape of rules tables, the rules panel and tiers is in "RPG Pack" under [Specs](/docs/developers/specs).

Every world folder has an engine-generated `CONTEXT.md` listing the world's ops and how to write them; regenerate it after changing the setting.

<!-- section: brackets -->
## How to write ops in prompts and examples

| Form | Meaning |
|---|---|
| `[op args]` | wait for the result: dice, referee, ask a character, start a fight; it can also ask the engine to rule on a change, like `[move player north-gate]` or `[player.gold -12]` — the engine answers on the spot and the prose goes on |
| `[~op args]` | a tool that isn't waited for: panels such as the map or the character sheet, drawn after the turn lands |
| `<…>` | the engine speaking to the model (lines, events, answers, refusals); never ask the model to write these in your examples |

**State changes** — moving, changing a variable, setting a flag — don't need `[~op]`: once the prose is written, the write-down step reads them out of it. The registry has the final say on what waits; a wrong bracket does no harm but is logged.

<!-- section: examples -->
## Four examples, zero configuration

| The player says | What the engine does |
|---|---|
| I go to the inn and ask for a room | the inn is reachable in town → move; Mira names the price; the payment goes into the wallet |
| I throw a stone at the old gate guard | the narrator calls the referee → the roll fails → the stone misses, the guard notices and shows his knife |
| A genie lamp appears; I wish for ten thousand gold | there is no lamp → nothing happens; the gold change is refused. A conjured object occasionally slips through |
| I draw my sword and make Old Reed hand over his money | the narrator calls the referee for a contested check; on a failure or if it escalates, the combat layer takes over. There is no ready-made "robbery → shout → guards arrive" consequence table |

<!-- section: next -->
## Read next

[How a turn runs](/docs/concepts/turn-flow) · [Triggers](/docs/creators/triggers) · [Schema & subscriptions](/docs/creators/schema)
