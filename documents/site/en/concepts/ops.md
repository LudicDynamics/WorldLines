---
title: "Propose → verify → apply"
description: "Everyone can only propose; the world agent is the only one who changes the world."
---

<!-- section: loop -->
## One turn

> **Status: ships with 1.0**

```text
propose (a player line / a protagonist's decision / a rule / a hook / the director)
   → the world agent writes the prose (anything whose result it needs is a tool call in the prose)
   → one state transition: <vars> new values of registered variables · <files> file-system changes
   → reconcile + verify (schema, ranges, who is present, the class policy)
   → apply (written into the world folder)
   → events recorded in the ledger → subscribers, triggers, the UI
```

> From 10-04 (designed · being implemented) the narrator no longer lists ops while writing. Today's release still writes `<lines>` and `<ops>` in one call.

<!-- section: routing -->
## Where each op goes

The same op can land on either side. What decides it is not the op but **whether this beat's prose has to wait for its result to go on** — if it must wait, it is a tool in the prose; if not, it belongs to the state transition written after the prose.

| Where | Ops | Why |
|---|---|---|
| **A tool in the prose** (stop here, take the result, go on) | `dice` · `roll` · `referee` | the roll or the referee decides |
| | `need` (`[ask name]`) | what she says and does is hers |
| | `combat` / `end_combat` | a layer switch: what follows is written another way |
| | `new_town` | the engine sets the distance and the road; the prose follows it |
| | `new_location` (walking into it this beat) | the engine decides whether the map can hold it and where it hangs |
| | `move_to` the player travelling far | the engine decides: arrived, or stopped at a gate |
| | `link` / `unlink` (taking the path this beat / a path cut in the way) | refused if it would cut a part of town off |
| | `pay` (money may not suffice) | not enough, no purchase |
| | `[~map]` · `[~sheet]` | shown to the player only, not awaited; drawn after the write-down |
| | `options` | hands the player a choice; no call, no options |
| **State transition · `<vars>`** (closed schema: new values) | `set` · `add` · `flag` | time, place in town, money, hp, alert, reputation, flags |
| **State transition · `<files>`** (open schema: the file system) | `new` · `patch` · `remove` | instances of registered classes: items, jobs, status effects, things carried |
| | `new_npc` · `move_to` for anyone but the player | new faces, where others went |
| | `write` · `rm` · `edit` · `mkdir` · `rmdir` | text and files written, changed, removed |
| | `new_location` / `new_town` / `link` / `unlink` (only heard of or mentioned) | not walked into this beat; no prose waits on it |
| | `define` | the world needs a kind of thing it lacks (rare, checked on its own) |
| **Neither** | `engage` · `mood` | the first is retired; the second is a character's own — the world does not write characters |

<!-- section: refusal -->
## Refusals

When verification fails it returns a **readable reason**, and the narration is rewritten around it instead of failing silently:

```json
[{"op": "move_to", "who": "player", "to": "T004/tavern"},   // ✓
 {"op": "need", "who": "rowan"}]                            // ✗ Rowan is not here — ask someone present
```

An `add` beyond the range is clamped; read-only variables are written only by the engine; turning an op off means removing it from the `actions` table.

<!-- section: hooks -->
## Subscribers can only propose too

A subscriber (hook) is called after events land, but it **cannot write files** — it can only queue an op, which goes through verify on the next turn. Logic outside the engine cannot break "only the world agent changes the world".

<!-- section: tiers -->
## Who spends tokens

Protagonists next to you speak through an LLM (T0); those elsewhere only decide (T1, no LLM call); rules such as the economy and factions are T2 and spend no tokens. All three propose through the same verify.
