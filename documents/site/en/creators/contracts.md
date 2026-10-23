---
title: "Play contracts"
description: "Picking a contract is promising the player a kind of experience: how it starts, how it ends, how many endings, what it rewards."
---

<!-- section: what -->
## What a contract is

> **Status: ships with 1.0** (soul protocol: in design)

A contract states **what a kind of game must give the player**; it does not decide how beats run (that is the [orchestration graph](/docs/creators/workbench)). Your template declares one, lint checks against it, and when a run reaches its exit the engine settles by it.

| Contract | For | How it ends | Endings |
|---|---|---|---|
| `mystery-trpg` | Percentile-dice investigation and exploration (Greyoak House) | at an ending; the truth must be revealed | ≥ 3, a true ending among them |
| `open-adventure` | worlds without a finish line (Stoneford) | a segment settles each day; play goes on | not required |
| `murder-mystery` | a table where everyone has a script and a secret (werewolf-like) | an ending after the accusation; the truth revealed | ≥ 2, a true ending among them |
| `romance-companion` | a relationship with one character | a segment settles after each date | not required |

<!-- section: declare -->
## Declare one

- UI: the "Contract" tab on the Template page;
- CLI: `neonrp template set-contract <template> mystery-trpg`;
- file: top-level `"play_contract": "mystery-trpg@1"` in `template.json`.

Built-in templates are read-only — "copy to edit" first.

<!-- section: checks -->
## What lint checks against it

| The contract asks for | When it is missing |
|---|---|
| an opening | blocked: the world's `game-start.json` has no opening |
| a fixed cast | blocked: the template casts nobody |
| ending at an ending | blocked: no trigger reaches an ending |
| number / kinds of endings | blocked: fewer than `min`, or no true ending |
| revealing the truth | blocked: a plot with endings has no `reveal` |
| ending CGs as a reward | blocked: an ending has no image slot |
| deaths ending on a fail ending | warning: no fail ending — the engine gives a plain death exit |

<!-- section: death -->
## Deaths and the settlement

A contract also says how deaths count: a player's death usually exits on the template's fail ending (with its CG and epilogue); a companion's or an NPC's is recorded and play goes on — a plot may react. At the exit the engine writes a settlement (exit, CGs unlocked, epilogue, deaths, rewards, truth), and the play screen draws the ending card from it.

<!-- section: souls -->
## Soul protocol

> **Status: in design**

Contracts will say which sheet a character must bring, that what the world hands out (roles, secrets) lives in that run only, and what is written back to the library at the end. See [Characters and casting](/docs/creators/characters). Every field: `spec/contract.md` in the template folder.
