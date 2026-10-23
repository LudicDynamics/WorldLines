---
title: "How a turn runs"
description: "The six things the engine does after the player speaks: what each step takes, what it returns, and who does it."
---

<!-- section: what -->
## The short version

> Around the turn there is one more layer: the world first hosts a **talk**, and only once it is agreed does it **resolve** — see [Talk it over, then resolve](/docs/concepts/planning-resolve) (implemented, off by default). This page covers what the engine does inside that resolve beat.
>
> **Change of 10-04 (designed · being implemented):** 4 SOLVE no longer writes lines · ops · options in one go. It writes only the prose (anything whose result decides what follows is a tool call in the prose) → 4b one clean-context call writes the state transition (`<vars>` new values of registered variables · `<files>` file-system changes) → 5 reconciles. Options become a tool.

> **Status: mixed** — each stage is marked *implemented* (runs on the NeonRP development branch with tests, not released) or *designed* (settled, not coded yet).

A turn has six stages: **plan → souls → resolve → solve → validate → apply**. Only *solve* is a heavy LLM call; *plan* is one cheap multiple-choice call (Jev); *validate* and *apply* are plain engine code.

Three principles run through all six:

1. **Player, characters and world each have their own agency, kept apart.** Characters receive the scene as the engine understood it, not the player's raw words; the world decides consequences.
2. **What the player says is an attempt, not a fact.** "A genie lamp appears in front of me" is what the player wants; whether the world has one is checked by the engine. Any side's action — the player's included — can be overruled.
3. **Effects come from mechanisms, not long prompts.** With zero configuration and one plain prompt, robbing a shop still brings the guards and eating filth still makes you sick; a creator's tables and rules only *change* results, they never *supply* the ability.

<!-- section: stages -->
## The six stages

```text
the player's line (= an attempt)
  1 PLAN     resolve references · one Jev call · gate rules · pick the layer · build each character's view
  2 SOULS    present characters in parallel: line + intent + judgment
  3 RESOLVE  player and characters at one table; any side can be overruled; default consequences
  4 SOLVE    the heavy call: only the prose, from the settled facts (streamable)
             [request] stop → engine runs it → answer → continue     [~action] not awaited (run after 4)
  4b TRANSITION one call, a clean context (all prose + every tool result + the registers):
             <vars> new values of registered variables · <files> file-system changes
  5 VALIDATE 4b reconciled against the world-changing tools of 4 (conflict: Jev if there is one, else the tool);
             every op checked against the full registry; refused ones send back only 4b — the prose does not change
  6 APPLY    write the world → triggers → the layer's per-turn tick → panels
```

| Stage | Who | Status | Typical time |
|---|---|---|---|
| 1 Plan | engine + Jev | partly implemented: reference check, Jev forecast, gate rules and layer choice run; one Plan object, a single Jev call for every judgment, and per-character views are designed | ~0.3 s |
| 2 Souls | one LLM call per present character, in parallel | implemented | ~2 s |
| 3 Resolve | engine; a referee only when contested | designed. Today the narrator writes `[referee …]` / `[dice …]` requests and continues after the ruling | 0 s without conflict |
| 4 Solve | one LLM call (requests make it continue) | implemented (today it still writes lines · ops · options at once; the prose-only version is being implemented) | ~4–9 s |
| 4b Transition | one LLM call, same prefix as 4 (cache hits) | designed · being implemented | ~3 s |
| 5 Validate | engine | implemented | ms |
| 6 Apply | engine | implemented; generic status effects (poisoned, sick, wanted) are designed | ms |

<!-- section: io -->
## Input, output and format of every step

One real turn (Stoneford north gate, the player a traveler, Elena along). The player says:

```text
I pick up a stone and throw it at the old gate guard to see what he does.
```

**1 Plan · references** (engine, implemented). In: the line + the world index. Out: whether each thing mentioned is here, as a short "understanding" for characters and narrator:

```text
# This turn, understood (engine, from the world's facts)
The player attempts: throw a stone at the old gate guard (an attempt; the outcome is not decided)
- the old gate guard: here
```

Something that does not exist is written as "not here (why). Do not make it appear".

**1 Plan · Jev forecast** (Jev, implemented). In: the line + the scene. Out: intent, tension, whether and how deeply each character reacts (shape below; numbers from a real run):

```json
{"source": "jev", "intent": {"kind": "move", "confidence": 0.99}, "tension": 0.653,
 "souls": {"si-elena0001": {"present": true, "reacts": 0.72, "depth": "speak"},
           "si-rowan0001": {"present": false, "reacts": 0.0, "depth": "silent"}}, "ms": 306}
```

**1 Plan · gate rules** (engine, implemented). Decided before the narrator writes: a fight during a road stop → this turn starts in the combat layer; the player looks at the map or asks the way → the engine draws a map for the player (async, the narrator is not asked).

**2 Souls** (LLM, implemented). In: her own persona and memory + the understanding above (not the raw line). Out: her line, action and intent:

```text
<say Elena attitude=oppose>"If you want to talk to the guard, use your mouth. If you want a beating, leave me out of it."</say>
```

**4 Solve** (LLM, implemented). In: the solve pack (entries relevant now) + character replies + the player's line. Out: `lines` (what the player reads), `ops` (state changes), `options` (choices). The narrator decides the stone's outcome is not its call and writes a **sync request** (excerpt, default XML sections):

```text
<lines>
You crouch and pry a wet stone from the gutter.
Before it leaves your hand, Elena catches your wrist.
"If you want to talk to the guard, use your mouth."
</lines>
<ops>
[referee the player throws a stone at the guard: does it fly, does he notice, does it start a fight]
</ops>
```

A square-bracket request is a stop point: the narrator stops there and the engine runs it first.

**The engine runs the request** (engine + referee sub-call, implemented). The referee only rules on structure (which attribute, difficulty tier, situation modifier); the engine rolls from the sheet and the difficulty table. The answer goes back in angle brackets:

```text
# Tool results (your requests, already run; continue from that line)
<referee the player throws a stone…>ruling: allowed_with_consequences; check throw (DEX) d20 -1: 3+1=4 vs DC 12 → fail; outcome: it makes noise; the guard looks straight your way.</referee>
```

**4 Solve · continuation.** What the player already saw is final; the narrator writes on from the stop point:

```text
<lines>
The stone drops half a foot, slips, and cracks against the gatepost.
The old guard turns. He pushes his cloak back; a short knife on his belt.
</lines>
<ops>
new_npc gate_guard T001/gate_north guard
</ops>
```

**5 Validate** (engine, implemented). In: ops + the full registry. Checks schema, ranges, who is present, each class's growth policy, and a layer's grounds (a fight needs someone to fight). A refusal goes back to the narrator with the reason:

```text
<refused combat roster>nobody to fight here: no stop on the road, no encounter here</refused>
```

**6 Apply** (engine, implemented). Accepted ops are written to the world folder → triggers (if / then, cascading) → the current layer's tick (combat: next round) → panels (map, formation) → the request ids of every call this turn. Out: the new state and the screen.

<!-- section: brackets -->
## Brackets: the shape says whether the turn waits

> **Status: implemented, not released** (settled 10-01)

| Form | Meaning | Examples |
|---|---|---|
| `[op args]` | **sync request**: stop at this line, continue after the engine answers | `[dice 1d20+2 vs 12]why[/dice]` · `[referee what the player attempts]` · `[ask Elena]` · `[combat bandit×3]hand-off[/combat]` |
| `[~op args]` | **async action**: not awaited; the engine does it and the narrator keeps writing | `[~map]` · `[~sheet]` (shown to the player only; drawn after the write-down) |
| `<…>` | **the engine speaking to the model**; the model never writes these | `<say>` a character's line · `<event>` what happened · `<referee>…</referee>` an answer · `<refused>` why |

**The engine decides what waits, not the bracket.** Every op declares `wait` when registered; a wrong bracket is executed by the registry and logged in the trace. Both async forms tested (`<map>` and `[~map]`) had zero mistakes; `[~ ]` was chosen so the model only uses one bracket.

Output sections are always XML. Divider lines and code fences were tested and not adopted. Today: `<lines>` `<ops>` `<options>`; from 10-04 the narrator writes only `<lines>`, the state transition is `<vars>` `<files>`, and options are the `[options …]` tool.

<!-- section: retry -->
## When something is refused

- **Implemented**: refused ops go back with reasons and the narrator rewrites only that part (bounded retries); accepted ops still land, refused ones are dropped; text shown before a stop point is final and the continuation only appends.
- **Designed**: four retry levels (targeted rewrite → partial accept → restart from the stop point → whole turn); when retries run out, only accepted ops land and the prose gets one line of the world resisting — the turn never hangs.

<!-- section: next -->
## Related

[Propose → verify → apply](/docs/concepts/ops) · [Protagonists & NPCs](/docs/concepts/souls) · for creators: [How the engine thinks](/docs/creators/engine-logic)
