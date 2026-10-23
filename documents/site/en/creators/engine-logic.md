---
title: "How the engine thinks"
description: "For creators: you write the world, the engine makes it hold together. What you never write, and what you can change."
---

<!-- section: one -->
## In one line

> **Status: mixed** — each stage is marked *implemented* (ships with 1.0) or *designed* (settled, not coded yet).

**You write the world; the engine makes it hold together.** A world with only setting text and no rule tables should still keep things from appearing out of nowhere, keep money from multiplying, bring someone in when the player goes too far, and let characters refuse the player in their own voice. If it can't, that is an engine problem, not a prompt that is too short.

Your tables, rules and prompts only **change results**: weaker guards, "homesick stomach" instead of "food poisoning", a genie lamp that is real in your world.

<!-- section: free -->
## What you never have to write

| What the engine does | How | Status |
|---|---|---|
| The player's words are an attempt | every turn the people, things and places mentioned are checked against the world; characters and narrator are told what is and isn't here | implemented (people, foes, places); conjured objects (a genie lamp) still slip through sometimes |
| Characters have their own minds | each present character gets its own call with the understood scene and decides what to say and whether to follow | implemented |
| Uncertain things go to a referee and dice | the narrator writes `[referee …]`; the referee picks attribute and difficulty; the engine rolls from the sheet | implemented |
| Fights have their own layer | `[combat bandit×3]` switches to the combat layer; foes come from the table; every round must roll; hp goes into state | implemented |
| Maps come from real state | when the player looks at the map or asks the way the engine draws it; the narrator neither draws nor waits | implemented |
| Prose can't quietly change state | every change is validated: who is present, variable ranges, whether a class may grow | implemented |
| Going too far has consequences | behaviour categories (robbery, harming others, eating something harmful …) map to default consequences: hostility, a shout for help, the authorities, sickness | designed |

<!-- section: change -->
## Four things you can change

1. **Tables**: `game/rules/<table>.json` overrides the engine's own — `hazards` (things on the road), `foes` (stat tiers), `rules` (difficulty tiers, checks).
2. **Prompts**: overridden per stage · layer · slot, in three layers: the template's `pack.json` < the world's `manifest.json` → `prompt` < play-time `game/meta/prompt.json`. Slots: `rules` · `voice` · `blocks` · `ops_docs` · `entries` (always / on keyword / at a place / on a variable / on a flag).
3. **Triggers**: WHEN → IF → THEN / ELSE, written in the world, checked after every apply, cascading.
4. **Ops and panels**: a new action or tool declares whether it waits (`wait`) and how it shows (text / JSON / image panel).

How a check works: the GM only picks who rolls, against whom, which attribute or skill, and which difficulty tier — **no numbers**; the engine reads the rules panel, adds status modifiers, rolls and judges. `rpg` is 1d20 + modifier against a DC; `pct` is d100 against a target (attribute × 5 or a skill value), graded `crit` · `special` · success · fail · `fumble`. Attributes use short keys such as `str` `dex` `int` `cha` (`app` on older character sheets reads as `cha`). The full shape of rules tables, the rules panel and tiers is in "RPG Pack" under [Specs](/docs/developers/specs).

Every world folder has an engine-generated `CONTEXT.md` listing the world's ops and how to write them; regenerate it after changing the setting.

<!-- section: brackets -->
## How to write ops in prompts and examples

| Form | Meaning |
|---|---|
| `[op args]` | wait for the result: dice, referee, ask a character, start a fight |
| `[~op args]` | don't wait: move, change a variable, set a flag, draw the map |
| `<…>` | the engine speaking to the model (lines, events, answers, refusals); never ask the model to write these in your examples |

The registry has the final say on what waits; a wrong bracket does no harm but is logged.

<!-- section: examples -->
## Four examples, zero configuration

| The player says | What the engine does | Status |
|---|---|---|
| I go to the inn and ask for a room | the inn is reachable in town → move; Mira names the price; payment goes into the wallet | implemented |
| I throw a stone at the old gate guard | the narrator calls the referee → the roll fails → the stone misses, the guard notices and shows his knife | implemented |
| A genie lamp appears; I wish for ten thousand gold | there is no lamp → nothing happens; the gold op is refused | partly: people and foes are caught; conjured objects sometimes slip (one test run paid out), being fixed |
| I draw my sword and make the grocer hand over his money | robbery → contested check → he shouts → guards arrive, alert rises, combat layer | designed (today the narrator calls the referee and combat; no default consequence table yet) |

<!-- section: next -->
## Read next

The full six stages with every input and output: [How a turn runs](/docs/concepts/turn-flow) · [Triggers](/docs/creators/triggers) · [Schema & subscriptions](/docs/creators/schema)
