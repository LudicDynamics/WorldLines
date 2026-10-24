---
title: "Talk it over, then resolve: the two beats of a turn"
description: "The world hosts a talk and hands the floor to the characters present; once it is settled, one resolve writes it all down. The planning beat only looks; the resolve beat writes the prose first, then the state."
---

<!-- section: what -->
## In short

How many beats a turn has is decided by the orchestration the template picks (`uses` in `template.json`). Both built-in templates (Greyoak House, Stoneford) use two:

- **Planning beat**: the world is the host. It places your intent in the scene, decides whom to ask, lays out costs, checks and time, and keeps a **plan board**. The world does not change by a word during this beat.
- **Resolve beat**: the same world writes the beat as agreed — prose first, with tools on the lines whose results matter; then one clean-context call writes the state, which is verified and committed. Details in [How a turn runs](/docs/concepts/turn-flow).

What was agreed in the talk is the input of the resolve. The resolve beat has no turns for the player or the characters.

**Which edition has the planning beat:** the `worldlines` / `neonrp` packages on PyPI include the full two-beat orchestration. An engine built from the open-source repository has one beat only (`one_beat`): each line you say is resolved straight away, with no planning beat.

<!-- section: diagram -->
## The whole picture

```text
 a new run ──→ the world's own written opening (no model call); an unplayed run starts by itself when opened
            │
 your line ──→ [planning beat] the world as host, possibly over several rounds:
            │   · look up real records (only the host sees them)
            │   · hand the floor to a character present: what she says, what she means to do
            │   · update the plan board: who does what, what it costs, which checks, how long
            │   the beat ends by handing the floor back to you, or by judging the talk settled → resolve
            ▼
 [resolve beat] (runs on without waiting for you)
   ① prose: lines whose result decides what follows call a tool, and continue with the result
   ② state: <vars> new values of registered variables · <files> file-system changes
   ③ verify: the tools' and the engine's rulings win; a fix rewrites ② only, never the prose
   ④ commit → one world commit
            ▼
           back to the talk
```

<!-- section: planning -->
## The planning beat

1. **The host decides what the beat does.** Whether to look something up, whom to ask, how to change the plan board; each round it sees the results and decides the next. The number of rounds is capped.
2. **The picture is left to the resolve.** While talking, the host gives information, costs, risks and whom to ask — not long descriptions of surroundings or action. The host may voice NPCs directly.
3. **Handing the floor.** The host relays your words to a character present and asks what she thinks; she answers herself (what she says aloud + what she means to do this beat). The host never speaks for her. Write `@Elena`, call her by name, or say "have her go …" and she gets the floor first.
4. **Checks are agreed, not rolled.** Who, which attribute, what difficulty, for what — written on the plan board; the engine rolls from the character sheet during the resolve.
5. **The world stands still while you talk.** The clock does not move, files do not change; the talk and the plan board live only in a scene buffer. Time spent talking is counted in the resolve.
6. **Your words are an attempt.** When you state something for the world ("it's already dark", "he agreed"), it counts as your claim only; a name you mention must have a source to count, nothing is made up from it.

<!-- section: advance -->
## When the resolve starts

| Who | How | What happens |
|---|---|---|
| The judge | Judges once per beat whether the talk is settled | Settled → straight to the resolve; you are not asked "shall we?" |
| You | Say a commit word: "deal", "do it", 「定」, 「決まり」 … | Resolve by the plan board |
| You | `@dm` (`@GM` `@world` `@主持` `@世界` work too) | The host takes this round decisively and stops asking others; resolves if it can, otherwise names the one thing still open |
| A character | She calls the host in her reply | Same, for her own part only |
| The world | The host proposes, you accept | Resolve |
| An outside event | A fight in progress, an unfinished stop on the road | No waiting for the talk: resolve now |
| Nothing to discuss | One step in town, no cost | Resolve now |

**Who the judge is:** with a Worldlines account signed in, or Jev / a judging model configured, that one. With none of them, the run's own model answers that single yes/no question (`turn.plan_loop_own_judge`, on by default).

**A long talk is not cut off.** After a few rounds the host nudges — recaps what was agreed, suggests acting — but does not force it.

**Quick talk:** the orchestration "Talk first, then act" has a pace parameter. With "Quick talk" (`two_beat?pace=quick`) the host answers at most twice per line, starts wrapping up at round 2, and moves on after 6 lines of talk. For worlds that want characters to talk back without slowing the pace.

<!-- section: resolve -->
## The resolve beat

- **A tool in the prose = something whose result decides what follows.** Dice, asking a character to carry out her part, travelling far (you may be stopped at the gate), walking into a place not on the map, heading for a new town, taking a new road or finding one cut, money that may not be enough, a fight breaking out — the prose stops there, the engine answers, the prose continues. Every other consequence already written in the prose goes to ②. Which op goes where: [Propose → verify → apply](/docs/concepts/ops).
- **In the resolve, characters carry out — they do not talk again.** When the prose needs her, she is asked: what you agreed to do, what your dice rolled, how the scene stands now — she acts on the plan and may improvise around surprises, but opens no new topic. At most two characters are asked per continuation, and nobody is asked twice.
- **Dice are rolled at the start of the resolve.** Agreed checks are rolled from the character sheet and shown at the top of the beat; the prose must match their outcome.
- **Agreed payments are settled by the engine** on the wallet, not by the narrator's bookkeeping.
- **The state is written fast first, corrected later.** The fast answer lands; a thinking answer corrects it from the background (up to 90 s). See [How a turn runs](/docs/concepts/turn-flow).
- **The world does not write a character's own state or diary**; she settles those herself.

<!-- section: examples -->
## Two examples

Illustrations, not the transcript of a real run. **P** player · **W** world (host while talking) · **E** Elena. The right column is the plan board after the beat.

**The general store (Stoneford, buy a potion + sell the lantern, Elena with you)**

| # | Who | What | Plan board |
|---|---|---|---|
| 1 | P | I go to the general store, buy a small healing potion, and sell the hooded lantern while I'm at it. | — |
| 2 | W | Old Reed is dozing behind the counter. The potion is 8 silver; he'd give maybe 3 for the lantern. Selling the lantern concerns your companion — asking Elena first. | P: buy potion, sell lantern (draft) |
| 3 | E | "Sell the lantern and what do we light the crypt with tonight?" Buy the potion, keep the lantern. | E: against selling |
| 4 | P | Then just the potion — and let her haggle. | P: buy potion; keep lantern |
| 5 | E | "Fine, I'll talk to him." | E: haggle (persuasion check, DC 10) |
| — | judge | settled | → resolve |

Resolve: Elena's persuasion is rolled first (success); the prose has Old Reed grumbling down to 6 silver; committed: time moves on, −6 silver, one small healing potion in the pack; Elena records it herself.

**Meeting Heron (no disagreement, settled in one beat)**

| # | Who | What | Plan board |
|---|---|---|---|
| 1 | P | Heron, let me buy you a drink at the Riverlamp Inn tonight after the gates close. | — |
| 2 | W | The words are for Heron, so the world answers for him: "…After closing. Half an hour." Elena has no reason to cut in and is not asked this beat. | Appointment: Heron, tonight after closing, Riverlamp Inn |
| — | judge | settled | → resolve |

Resolve: the appointment is written into Heron's own record (time and place); that night, Heron walks into the inn as agreed.

<!-- section: next -->
## Read next

- [How a turn runs](/docs/concepts/turn-flow): every step of the resolve beat
- [Propose → verify → apply](/docs/concepts/ops): which ops are tools in the prose and which are part of the state
- [The play screen](/docs/players/play-screen): what the two beats look like on screen
