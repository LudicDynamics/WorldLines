---
title: "How a turn works"
description: "What you say is an attempt. Every turn talks first, then resolves; state is written at once and checked again in the background."
---

<!-- section: talk -->
## What you say is an attempt

Say what you want to do in plain words: "go to the adventurers' guild", "I try to pick that lock", "Elena, what do you think?".

What you say is an **attempt**, not a fact. The world decides whether it can work and whether it needs a roll; the characters have minds of their own and may not do what you ask. If something can't happen, you are told why.

<!-- section: beats -->
## Two beats: talk, then resolve

Every turn has two beats:

| Beat | What happens | Has the world changed? |
|---|---|---|
| **Planning** | the host sets the scene and the characters present answer; you agree on what to do, how, and whether to roll | not yet |
| **Resolve** | the host writes what happens in this beat, the dice that matter are rolled, and the result lands on the world: moves, wounds, items, clues … | yes |

Planning can go back and forth for a few lines. When the talk is settled and resolve begins is decided by the **judge**:

- signed in with a Worldlines account (`/login`): Jev decides, in under a second;
- not signed in: your run's own model decides, which adds a few seconds per planning beat.

Don't want to wait for the judge? Say 「定」 or `@dm` and resolve starts right away.

<!-- section: settle -->
## State is written first, then checked

When the resolve beat's prose is done, the engine first writes the state the fast way so you can keep playing at once; at the same time it works it out again, more carefully, in the background. That usually comes back within one to three seconds:

- same result: nothing changes;
- different result: the state is corrected and you are told what changed (money, place, items gained or lost …).

If you say your next line before the check comes back, the check is dropped and your new action counts. The check waits at most 90 seconds; past that, the state stays as it was.

<!-- section: souls -->
## Talking to characters

Call them by name, or use `@name`: "Elena, wait for me here", "@Rowan come with us". Only characters who are **present** can answer. They answer by their own judgement: they agree, refuse, or suggest something else.

To see where a character is, what they remember and what they have been doing, use `/who` in the terminal.

<!-- section: move -->
## Moving, travelling, waiting

- **Within a place**: "go to the inn", "go upstairs" — you walk straight there.
- **To another town**: first reach the gate, then take the road. The trip takes time, and you arrive by the world's calendar. Things can happen on the way.
- **Waiting**: say "wait a while" or "sleep until morning", and the world's clock moves on.

Characters who aren't with you keep pursuing their own goals, and they have to walk to other towns too; nobody teleports.

<!-- section: next -->
## Next

- Where to look on the web and in the terminal: [The play screen](/docs/players/play-screen)
- Going back and trying another way: [Save · branch · undo](/docs/players/saves)
