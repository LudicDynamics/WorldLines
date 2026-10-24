---
title: "How a turn runs"
description: "What the engine does in the resolve beat after the player speaks: what each step takes, what it returns, and who does it."
---

<!-- section: what -->
## The short version

How a turn runs is decided by the **orchestration** the template picks (`uses` in `template.json`). Both built-in templates (Greyoak House, Stoneford) use two beats:

- **Planning beat**: the world acts as host — it places your words in the scene, asks the characters present, and lays out costs and checks. The world does not change during this beat. See [Talk it over, then resolve](/docs/concepts/planning-resolve).
- **Resolve beat**: writes the beat out as agreed and commits the result to the world. **This page is about the resolve beat.**

The `worldlines` / `neonrp` packages on PyPI include the full two-beat orchestration. An engine built from the open-source repository has one beat only (orchestration `one_beat`): no talk — each line you say is resolved straight away. When a template asks for two beats and the engine does not have them, it falls back to one beat and the world still plays.

Three principles run through every step:

1. **Player, characters and world each have their own agency, kept apart.** Characters receive the scene as the engine understood it, not the player's raw words; the world decides consequences.
2. **What the player says is an attempt, not a fact.** "A genie lamp appears in front of me" is what the player wants; whether the world has one is checked by the engine. Any side's action can be overruled.
3. **Effects come from mechanics, not long prompts.** With zero configuration and a one-line base prompt, a robbery still gets you surrounded and eating something odd still makes you sick; a creator's tables and rules only **change** outcomes.

<!-- section: stages -->
## The steps of the resolve beat

These are the step names the orchestration bench shows (`core/turn_steps.py`), in the order they run:

```text
one line from the player (= an attempt)
  clock         the world clock moves one step
  scene_route   find the characters at the player's place
  s1_plan       Jev forecast: what the player means, who moves, how deeply (no Jev = everyone present acts)
  player_gate   treat the player's words as an attempt: what they try, whether they can know what they mention
  s2_souls      characters present act in parallel; characters elsewhere take a beat where they are
  followups     after the characters answer, judge once more: does anyone still need to be asked
  pack          pack what matters right now for the narrator
  understand    for each thing the player mentions: is it in the world
  gate          rules rule in advance; force a layer when needed (ambushed on the road → combat)
  mode_layer    inside a layer (combat, a dungeon) the layer's prompt and state take over
  solve         ① write the prose, calling tools where results matter → ② write the state <vars> <files>
  verify        check each change against the registry and the rules
  apply         write the changes that passed into the world
  deferred_fire draw the tools that are not waited for (map, panels) after landing
  settle        each character present records the beat
  after_turn    pictures for new things, triggers
  ticks         background units: economy, effect countdowns, characters elsewhere, the pack's own rules
  land          the turn becomes one world commit; beat events go to the front ends
```

| Steps | Who | Typical time |
|---|---|---|
| clock · scene_route · pack · understand · gate | engine | milliseconds |
| s1_plan · followups | Jev (one multiple-choice question) | ~0.3 s |
| player_gate | one short LLM call (can be turned off) | short |
| s2_souls | one LLM call per character present, in parallel | ~2 s |
| solve ① prose | one LLM call (tools make it continue) | ~4–9 s |
| solve ② state | one LLM call, clean context | ~1–3 s (see "Fast first, corrected later") |
| verify · apply · ticks · land | engine | milliseconds |

A turn has a time budget by default (30 s per turn, 20 s per beat, 10 s kept for the world); a beat that runs over is wrapped up and landed, and prose already shown is never lost.

<!-- section: io -->
## What goes in and out of each step

One turn in Stoneford (`stoneford-town`, the north gate, Elena with you). The player says:

```text
I pick up a stone and throw it at Kas the gate guard to see how he reacts.
```

**understand** (engine). In: the raw line + the world index. Out: whether each thing mentioned is here, written as an "understanding" for the characters and the narrator:

```text
# This turn as understood (engine, by the world's facts)
The player attempts: I pick up a stone and throw it at Kas the gate guard (an attempt; the outcome is not decided)
- Kas (north gate guard): right here
```

Things that do not exist are written as "not here (reason). Do not make it appear."

**s1_plan** (Jev). In: the line + the scene. Out: intent, tension, whether each character reacts and how deeply:

```json
{"source": "jev", "intent": {"kind": "move", "confidence": 0.99}, "tension": 0.653,
 "souls": {"si-elena0001": {"present": true, "reacts": 0.72, "depth": "speak"},
           "si-rowan0001": {"present": false, "reacts": 0.0, "depth": "silent"}}, "ms": 306}
```

**s2_souls** (LLM). In: her own persona and memory + the understanding above (not the player's raw words). Out: her words, action and intent:

```text
<say Elena attitude=oppose>"If you want to talk to the gatekeeper, use your mouth. If you want a beating, leave me out of it."</say>
```

**solve ① prose** (LLM). The narrator writes only the prose. The consequence of the throw is not its to decide, so it writes a tool on that line and stops there:

```text
You crouch and pry a wet stone out of a crack at the roadside.
Before it leaves your hand, Elena grabs your wrist.
"If you want to talk to the gatekeeper, use your mouth. If you want a beating, leave me out of it."
You shake her off.
[referee the player throws a stone at Kas the gate guard: does it really fly, does he notice, does it turn into a fight right here]
```

**The engine answers the tool.** The referee only returns a structured ruling (which attribute, difficulty, situational modifiers); the engine rolls the dice from the character sheet and the difficulty table, and sends the result back:

```text
<referee the player throws a stone…>ruling: allowed_with_consequences; check throw d20 + DEX -1: 3+1=4 vs DC 12 → failed; outcome: the throw is clumsy and loud; Kas turns toward the sound — a standoff, right here.</referee>
```

**solve ① continues.** What the player has already seen is final; the narrator continues from the stop, and the last line hands the next move to the player:

```text
The stone flies half a foot low and cracks against the gatepost.
Kas turns and levels his spear; his helmet slips down an inch.
"No guild commission, not one step north — and no throwing rocks at the gate either."
[options Drop it and ask about the north road instead | @Elena smooth this over for me | Turn and walk away]
```

**solve ② state** (LLM, clean context). In: all of this beat's prose + every tool answer + the table of variables it may change. Out, in two parts:

```text
<vars>
town.alert = 2
</vars>
<files>
</files>
```

- `<vars>`: new values of registered variables (closed schema), only the ones that changed this beat.
- `<files>`: file-system changes (open schema): new instances, people who just appeared, where others went, text that was written down, new places that were only heard of. Nothing this beat, so it is empty; if a stranger turned up by the road it would hold a line like `new_npc name T001/gate_north role`.

**verify** (engine). Each change is checked: syntax → do the names and variables exist, are the types right → world rules (who is present, the class's growth policy, grounds for entering a layer). Whatever a tool or the engine already ruled stands; a line of ② that conflicts with it is dropped. A fixable refusal goes back with its reason **to ② only** (by default at most once); the prose does not change by a word. A name that does not land on exactly one entry gets one pick from Jev. If the player changed place, companions follow as agreed. The prose may not name a success tier the dice did not give.

**apply · land** (engine). Changes that passed are written into the world → triggers fire (they can cascade) → the layer's per-turn step runs (combat: next round) → tools that were not waited for are drawn → background units → the turn becomes one world commit.

<!-- section: writedown -->
## Writing the state: fast first, corrected later

On providers that can switch thinking off per request (DeepSeek, for example), ② is sent twice at once:

- **the call without thinking** comes back first and lands immediately; the beat ends and you can go on;
- **the thinking call** finishes in the background and corrects the state: each variable goes to its value; a variable something else changed in the meantime is left alone; the engine's own rulings (tool results, agreed payments) still win.
- The background call gets at most 90 s (`turn.transition_slow_timeout_s`); after that the fast answer stays. If you send your next line first, the background call is cancelled.
- Front ends receive `write_down.pending`, then `write_down.corrected` (with what changed), `.same`, `.cut`, `.timeout` or `.failed`.

On providers without that switch, only one call is made.

<!-- section: brackets -->
## Bracket convention: the shape says whether to wait

| Form | Meaning | Examples |
|---|---|---|
| `[op args]` | **Synchronous tool**: stop at this line, continue after the engine answers | `[dice 1d20+2 vs 12]` · `[referee what the player tries]` · `[ask Elena]` · `[move player Jadestone]` · `[player.gold -12]` · `[combat bandits×3 \| what each one does]` |
| `[~op args]` | **Tool not waited for**: the engine does it, the narrator keeps writing; drawn after landing | `[~map]` · `[~sheet]` |
| `[options a \| b \| c]` | On the last line: hand the next move to the player | see above |
| `<…>` | **Engine-to-model message**; the model never writes these | `<say>` a character's words · `<referee>…</referee>` a tool answer · `<refused>` a refusal reason |

**Whether to wait is decided by the engine, not by the bracket.** Each op declares `wait` when it is registered; a mis-bracketed call runs as registered and the mismatch is recorded in the trace. Changes to the world — moves, variable changes — go either into ②'s `<vars>` / `<files>`, or, when their result decides what comes next, into a synchronous tool the engine rules on. `[~ ]` is only for tools that just show something to the player, like the map or the character sheet.

<!-- section: effects -->
## Status effects

Lasting consequences — poisoned, wounded, wanted — are open-schema status instances: the world registers a class with `effect: true`, and an instance may carry `turns` (turns left), `check` (a modifier to checks) and `each` (per-turn variable changes such as `player.hp:-1`). The engine counts down, applies and removes them at 0. No specific effect name is written in engine code.

<!-- section: next -->
## Related

[Talk it over, then resolve](/docs/concepts/planning-resolve) · [Propose → verify → apply](/docs/concepts/ops) · [Characters and NPCs](/docs/concepts/souls) · For creators: [The engine's logic](/docs/creators/engine-logic)
