---
title: "Talk it over, then resolve: the two halves of a turn"
description: "The world hosts a conversation and hands the floor to each participant; once it is settled, one resolve writes it all down. Two agent loops: planning only looks, resolving writes the prose first and then one state transition."
---

<!-- section: what -->
## In short

> **Status: planning implemented · resolve's "prose first, then the state transition" designed and being implemented · neither released** — on the NeonRP development branch with tests and benchmarks; **off by default**, turn on `turn.plan_loop` in `engine.json`. For what the engine does inside a single beat, see [How a turn runs](/docs/concepts/turn-flow); this page covers the layer around it.

A turn has two kinds of beat, **each its own agent loop**:

- **The planning beat only looks.** The world hosts as the GM: it puts the player's intent into the scene, decides whom to ask, lays out costs, checks and time, and keeps a **plan board**. Read-only — not one word of the world changes.
- **The resolve beat does.** The same world (the GM and the world agent are one) writes the beat from the agreed plan: first the prose — anything whose result decides what comes next is a tool call inside the prose; then, from one clean context, a single **state transition**, reconciled and written down.

What was talked over is the resolve's input — that is what the talk is for. The resolve beat has no turns for the player or the characters, and no options round.

<!-- section: diagram -->
## The picture

```text
 start the game ──→ [Opening] the world's own authored opening (game-start.json), no model call
                │
 player line ──→ [Planning beat · agent loop] the world hosts, round by round: think → call a tool → read the result → think
                │   tools: [read name] real records · <mic> hand the floor to a character present · <board> edit the plan, set checks
                │   how the beat ends (the loop decides):
                │     · hand the talk back to the player (1–3 sentences, options only for a real choice) → wait
                │     · next: advance → switch to the resolve
                │   interrupts: the player @GM · a character @GM · Jev (or a small model) judges it settled
                │   before switching: something uncertain or opposed without a check → one more round to set it
                ▼ the planning beat is recorded on its own
 [Resolve beat · agent loop] (runs straight on, no waiting for the player)
   ① prose: only prose; where the result decides what follows, call a tool on that line, stop, take the result, go on
          [dice] [roll] [referee] · [ask name] (a character carries out what she agreed) · [move far] · [new_location] · [new_town]
          · [link] [unlink] · [pay] · [combat] (the beat continues under the combat layer) · [options] · [~map] [~sheet]
   ② state transition: one clean context (all of this beat's prose + every tool result + the registers and starting values)
          <vars>  closed schema: new values of registered variables → run_state and the other state files
          <files> open schema: file-system changes (instances, text, new people and places)
   ③ reconcile: ② against the world-changing tools in ①; on conflict use Jev if there is one, else the tool result wins
          · verify · drop what the prose never showed; to fix, only ② is re-run — the prose does not change
   ④ write down → draw the map → after the reply (everyone's experience, placing grown places)
                ▼ the resolve beat is recorded on its own
               back to planning
```

<!-- section: planning -->
## The planning beat

1. **An agent loop, not a fixed pipeline.** Each round the host decides: look something up (`[read the shop]` — only it learns what it read), hand the floor to someone (`<mic>`), change the plan board (`<board>`). The results come back and it thinks again; a round with no tool call is the last. At most 4 rounds per beat (`turn.plan_loop_max_rounds`).
2. **One to three sentences to the player.** Facts, costs, risks, whom to ask; no scenery or action description — the picture is the resolve's. The host may speak an NPC's line itself. The opening is the exception: it is the world's own.
3. **Handing the floor.** The host retells the player's words to her in its own voice and asks what she thinks — it never speaks for her; she answers herself (what she says aloud + what she means to do this beat), and the result goes back to the host. `@Elena`, her name, or "have her …" in the player's line gives her the floor in the first round.
4. **Checks are agreed, not rolled.** Written `check: who ATTR difficulty why` or `contest: A vs B ATTR why`, kept on the board; the engine rolls them by the character sheets at the resolve.
5. **The world stands still while you talk.** No clock, no file changes; the talk, the board and the agreed checks live only in the scene buffer `.neonrp/scene.json`. The talk itself takes time, counted at the resolve.
6. **The player's words are attempts.** The gate marks what the player states as a world fact ("it's already night", "he agreed") as their account, not a fact; names with a source land, names out of nothing are not made.

<!-- section: advance -->
## From planning to resolve

| Who | How | What happens |
|---|---|---|
| The planning loop | everyone's part is clear, nobody objects → `next: advance` | one sentence restating what was agreed (no options, no "shall we?"), then the resolve |
| Jev / a small model | after the host hands the talk back, judges it already settled | the options are dropped, then the resolve |
| The player | `@GM` (`@world` `@dm` work the same) | **not a guaranteed advance**: the host takes this round decisively, asks no one else and decides — go, or name the one thing still open. Only the player's own part moves; someone else not agreeing does not hold them back |
| A character | `@GM` in her reply | the next round is the host's decisive one, as above (only her own part) |
| The player | says "settled" (定) | switch on the board as it is |
| An outside event | a fight under way, a road stop not settled | no waiting for the talk |

**A long talk is not cut off.** From the third beat (`turn.plan_loop_nudge_at`) the host urges — restating what is agreed, suggesting action — but never forces; the switch is still one of the above.

<!-- section: resolve -->
## The resolve beat

- **A tool in the prose = something whose result decides what follows.** A roll, a character carrying out her part, travelling far (maybe stopped at a gate), walking into a place the map lacks, heading for a new town, taking a new path or finding one cut, money that may not suffice, a fight — the prose stops there, the engine answers, the prose goes on. Everything else already in the prose (money spent, things handed over, words written, where others went, new faces) is not booked as you write — ② does it. Where each op goes: [Propose → verify → apply](/docs/concepts/ops).
- **A character in the resolve carries out, she does not talk it over again.** When the prose needs her, `[ask her]` tells her what she agreed, the dice that concern her, and the scene so far — she does and says it, may react to a surprise, but does not change the plan or open a new topic. At most twice per character per resolve.
- **Dice first, before the prose.** The agreed checks are rolled by the sheets as the resolve starts and shown as its first line: `[Elena CHA (haggle): 13+2=15 >= 12] → success`; the prose must agree with them.
- **The state transition has two parts, one per schema.** `<vars>` new values of the registered variables (time, place, money, hp, flags); `<files>` file-system changes (instances of registered classes, text, new places, new people). A character's own state and diary are not the world's to write — she settles them herself.
- **Options are a tool.** To hand the player a choice, call `[options …]`; no call, no options. The engine and the front end can call it too.

<!-- section: next -->
## Read on

- [Four scenes](/docs/concepts/planning-scenes): the shop, inviting Heron, the docks, setting out for Fog Harbour — beat by beat
- [How a turn runs](/docs/concepts/turn-flow): the stages inside the resolve beat
- [Propose → verify → apply](/docs/concepts/ops): which ops are tools in the prose and which belong to the state transition
