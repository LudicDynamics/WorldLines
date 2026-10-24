---
title: "Propose → verify → apply"
description: "Everyone can only propose; only the world (the world agent) changes the world. Which ops are tools in the prose and which are part of the state."
---

<!-- section: loop -->
## One turn

```text
propose (a player line / a character's intent / a rule / a hook)
   → the world writes the prose (anything whose result it needs is a tool in the prose; the engine answers on the spot)
   → the state: <vars> new values of registered variables · <files> file-system changes
   → verify (the tools' and the engine's rulings win; schema, ranges, who is present, the class's growth policy)
   → apply (written into the world folder)
   → events recorded in the ledger → subscribers, triggers, the UI
```

Each step inside a beat: [How a turn runs](/docs/concepts/turn-flow).

<!-- section: routing -->
## Where each op goes

Ops are registered by each rules pack; the engine does not hard-code them. The table below is the `rpg` pack's (Stoneford). The `pct` pack (Greyoak House) builds on `rpg` and adds `san` (a sanity check); `werewolf` and `monopoly` have their own ops (vote, kill, phase; roll, buy, end turn).

The same op can land on either side. What decides it is not the op but **whether this beat's prose has to wait for its result to go on** — if it must wait, it is a tool in the prose; if not, it goes into the state written after the prose.

| Where | Op | Why |
|---|---|---|
| **Tool in the prose** (stop here, continue with the result) | `dice` · `roll` · `referee` | Success is decided by the dice or the referee |
| | `need` (written `[ask name]`) | What she says and does is hers to decide |
| | `combat` | Enters the combat layer: the layer resolves this turn and the prose follows its answer |
| | `new_town` | The engine sets the distance and the town the road starts from; the prose follows it |
| | `new_location` (walked into this beat) | The engine decides whether it fits on the map and where it hangs |
| | `move_to` for a far trip by the player (written `[move player …]`) | The engine decides whether you arrive or are stopped on the way |
| | `link` / `unlink` (a new road taken this beat / a road cut in your way) | Refused when cutting it would leave part of town unreachable |
| | a variable change (written `[player.gold -12]`, when money may not be enough) | Not enough → it does not happen |
| | `[~map]` · `[~sheet]` | Only shown to the player, not waited for; drawn after landing |
| **State · `<vars>`** (closed schema: new values) | `set` · `add` · `flag` | Time, position (in town), money, hp, alert, flags |
| **State · `<files>`** (open schema: the file system) | `new` · `patch` · `remove` | Instances of registered classes: items, quests, status effects, carried things |
| | `new_npc` · `move_to` for anyone but the player | People who just appeared, where others went |
| | `write` · `rm` · `edit` · `mkdir` · `rmdir` | Text and files written, changed or deleted |
| | `new_location` / `new_town` / `link` / `unlink` (only heard of or mentioned) | Not walked into this beat; the prose does not wait for it |
| | `define` | The world needs a kind of thing it does not have yet (rare, verified on its own) |
| **The world does not write** | `mood` | For characters themselves only; the world does not write characters |
| | `end_combat` | Used by the combat layer to end a fight |
| | `engage` | Retired, off by default |

`[options a | b | c]` is not an op: it hands the next move to the player, is picked up by the engine directly, and changes nothing in the world.

<!-- section: refusal -->
## Refusal

When verify fails it returns a **readable reason** instead of failing silently:

```json
[{"op": "move_to", "who": "player", "to": "T004/tavern"},   // ✓
 {"op": "need", "who": "rowan"}]                            // ✗ Rowan is not here — only those present can be asked
```

A fixable refusal sends only the state back for a rewrite; the prose does not change. What still fails after the rewrite is dropped; what passed lands as usual. `add` beyond a range is clamped; read-only variables can be written only by the engine; switching an op off means removing it from the `actions` table.

<!-- section: hooks -->
## Subscribers can only propose too

A subscriber (hook) is called after events land, but it **cannot write files directly** — it can only queue an op (`sdk.enqueue`), which goes through verify on the next turn. So logic outside the engine cannot get around "only the world changes the world" either.

<!-- section: tiers -->
## Who spends tokens

- Characters at your place: one LLM call each, in parallel.
- Characters elsewhere: take a beat where they are, through the same verify.
- Background units such as the economy, factions and effect countdowns: plain code, no tokens, and they may write only the variables they declared.

All three propose through the same verify.
