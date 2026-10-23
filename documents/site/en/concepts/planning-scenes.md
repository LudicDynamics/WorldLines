---
title: "Four scenes: talk it over, then resolve"
description: "The general store, a drink with Herron, trouble at the dock, the road to Mistport — beat by beat: who gets the floor, how the plan board changes, what is committed."
---

<!-- section: legend -->
## Legend

> **Status: implemented · not yet released** — these four scenes are the design examples for [Talk it over, then resolve](/docs/concepts/planning-resolve) and also the engine benchmark cases of the same names (each checks: the world state is unchanged during the talk beats, the floor went to the right people, nothing was rolled early; after resolve the committed state is right). The dialogue below is from the design, not a transcript of one run.

**P** player · **W** world (host during planning) · **E** Elena (a character agent) · NPCs are voiced by W. The right-hand column is the **plan board** after each beat.

<!-- section: shop -->
## Scene 1 · The general store (buy a potion, sell the lantern; Elena is there)

| Beat | Who | What happens | Plan board |
|---|---|---|---|
| 1 | P | I go to the general store, buy a small healing potion, and sell my hooded lantern while I'm at it. | — |
| 2 | W | The store is at the east end of Main Street, a quarter hour's walk. Old Reed is dozing behind the counter; the potion is 8 silver, he'd give about 3 silver for the lantern. [dry run: you can afford it] Selling the lantern affects your companion — ask Elena first. | P: buy potion, sell lantern (draft) |
| 3 | E | "Sell the lantern, and what lights our way into the crypt tonight?" I'm against selling it; the potion is fine. | E: against selling the lantern |
| 4 | W | Elena objects to selling the lantern. Your call: ① the original plan ② just the potion ③ let Elena haggle with Old Reed (Persuasion DC 10; on success the potion drops to 6 silver) | choosing |
| 5 | P | Just the potion, and let her haggle. | P: buy potion; keep the lantern |
| 6 | E | "Fine, I'll do the talking." | E: haggle (Persuasion DC 10, she rolls) |
| 7 | W | Plan board: you buy the potion; Elena haggles (Persuasion DC 10); the lantern stays; about 20 minutes. Go? | to confirm |
| 8 | P | Go. | → resolve |

**Resolve** (one world beat):

- Roll: Elena's Persuasion 1d20+1 = 14, success;
- One paragraph of narration: Old Reed grumbles and comes down to 6 silver;
- Commit: time +20 minutes, both of you at the store, money −6 silver, inventory + small healing potion;
- Elena writes her own: mood satisfied, one line in her diary.

<!-- section: herron -->
## Scene 2 · A drink with Herron (inviting an NPC; Elena listens)

| Beat | Who | What happens | Plan board |
|---|---|---|---|
| 1 | P | Herron, let me buy you a drink at the River Lantern Inn tonight. | — |
| 2 | W | You're talking to Herron, so the world answers for him. Herron: "I keep the books after closing; no time before the gates are locked." Elena is listening and has no reason to cut in, so she isn't asked this beat. | Herron: not before lock-up |
| 3 | P | After lock-up, then? I'll wait for you at the inn. | — |
| 4 | W | Herron pauses his pen: "...After lock-up. Half an hour." | appointment (draft): Herron, tonight after lock-up, River Lantern Inn |
| 5 | W | Plan board: meet Herron at the River Lantern Inn tonight after lock-up. Go? | to confirm |
| 6 | P | Go. | → resolve |

**Resolve**:

- The appointment, with time and place, is written into Herron's own record;
- time +5 minutes;
- Elena's recent experience notes "he made a date with Herron".

When the evening beat comes and the appointment is due, Herron goes to the inn as agreed. Without a planning half, the appointment was never formally agreed — which is exactly why the "date with an NPC" benchmark case kept failing.

<!-- section: dock -->
## Scene 3 · Trouble at the dock (conflict, initiative, dice)

| Beat | Who | What happens | Plan board |
|---|---|---|---|
| 1 | P | I walk over and kick the dockworker's fish basket over. | — |
| 2 | W | Borg is unloading three steps away; kick his basket and he will swing — this goes into conflict. Fastest reaction goes first: by Dexterity, Elena 14 > you 12 > Borg 10. Elena first. | P: kick the basket (draft) |
| 3 | E | "Are you mad? One shout and the whole dock is on us." I try to hold you back. | E: hold the player back |
| 4 | W | Elena is grabbing you. You: ① shake her off and kick anyway (contest: your Dexterity vs hers) ② listen to her ③ try something else | choosing |
| 5 | P | Shake her off, kick it. | P: kick the basket; contest |
| 6 | E | "...Fine. I'll be right behind you." | E: stops holding you; stands behind you, joins in if it comes to blows |
| 7 | W | Plan board: you shake off Elena (contest) and kick the basket over; if Borg strikes back, we enter the combat layer, initiative by Dexterity; Elena is behind you. Once you kick, there's no taking it back. Go? | to confirm |
| 8 | P | Go. | → resolve |

**Resolve**:

- Roll the contest first;
- Narrate the basket going over and Borg charging in;
- Switch into the combat layer, order initiative by Dexterity; the fight itself follows the existing combat layer.

The dice were agreed while talking: who rolls, what, the difficulty, the consequences. The actual roll happens at resolve, so there's no "rolled first, regretted after".

<!-- section: mistport -->
## Scene 4 · The road to Mistport (nobody else around — just the player and the world)

| Beat | Who | What happens |
|---|---|---|
| 1 | P | I leave by the north gate and head east, somewhere I haven't been. |
| 2 | W | East lies a stretch of scrub woods; beyond it, faintly, an old post road. You won't reach the next shelter before dark, and you're carrying only two loaves of rye bread. Go back to town for supplies first? |
| 3 | P | No, straight on. |
| 4 | W | Plan board: out the north gate, east along the old post road, camp at the edge of the woods tonight. Go? |
| 5 | P | Go. → resolve: travel referee, days, events on the road, new places grow on the map |

With nobody else around, planning is the world building the scene on the spot so the player can see it clearly and ask questions before setting out.
