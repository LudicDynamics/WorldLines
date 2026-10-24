---
title: "A run, end to end"
description: "From install to publishing a world, what the system does at each step: models, templates, run start, the two-beat turn, write-down, saves, creating, publishing."
---

<!-- section: why -->
## What this page covers

This page walks the real order of things: you install, connect a model, pick a world, say your first line, play to a save, then make a world of your own and publish it. Each step says **what happens and what you see**; details link to their own pages.

Three ideas hold up everything below:

1. **World, characters and player are three parties.** The world (the host) decides consequences, characters have their own memory and intent, and what the player says is **an attempt**, not a fact.
2. **A template is the unit you make worlds in.** A template = a world + links to characters + a rules pack + a play contract + an orchestration. Every run you play is opened from a template.
3. **Every turn lands one world commit.** State lives in files, one commit per turn; going back means starting a new line from an earlier commit.

<!-- section: editions -->
## Two engines: full and open-source

| | How you get it | A turn |
|---|---|---|
| **Full** | `pip install worldlines` / `pip install neonrp` (PyPI) | Two beats: **talk** first, then **resolve** |
| **Open-source** | Install from source from the [GitHub repository](https://github.com/LudicDynamics/WorldLines) | The resolve beat only |

Both read the same templates, saves and rules. If a template asks for two beats and you run the open-source engine, it falls back to a single beat and characters still act. The rest of this page describes the full engine.

<!-- section: install -->
## 1. Install and launch

- `worldlines` opens the local web UI at `http://127.0.0.1:8787/local` (local Hub, play screen, workbench).
- `neonrp` opens the launcher in your terminal: pick a world, start, play, all in the terminal.
- Both share `~/.worldlines` (templates, character library, saves); a run started in the browser continues in the terminal.
- Both check for a new version at launch and, by default, update and restart; to be asked first: `/update mode prompt`.
- Nothing to install: play at [worldlines.gg](https://worldlines.gg) or in the iOS app.

Two worlds ship locally: **Greyoak House · The Closed Door** (one night of deduction, good for a first run) and **Stoneford · The Night the Fog Withdraws** (an open town). The other official worlds show up in the local Hub without signing in, and can be downloaded after you sign in.

<!-- section: model -->
## 2. Connect a model

- **Worldlines account**: `/login` in the terminal, or sign in on the web page. You get our relayed models and the **Jev** judge.
- **Your own key**: OpenCode, DeepSeek, OpenRouter, Anthropic, OpenAI, GLM, or any OpenAI-compatible endpoint.
- A new run uses the model you picked before; if you never picked one and you are signed in, Worldlines; otherwise the first preset that has a key.

The **judge** only answers small yes/no questions, like "is this talk settled?" or "who does this name refer to?". Without Jev, **the run's own model** answers them (a few seconds more per beat); without that, fixed rules decide. The judge never writes the story.

See [Connect a model](/docs/players/providers).

<!-- section: start -->
## 3. Start a run

You pick a template, optionally make your own character, and start. The engine then:

1. Creates a new folder under `~/.worldlines/plays/`; everything about this run lives there.
2. Copies in the template's world, the language layer you chose, and the rules pack.
3. **Instantiates the characters now.** Most characters in a template are links into the character library; only at run start are they copied into this run, carrying their own memory. One character can live in several worlds at once without them affecting each other.
4. Merges settings: rules pack < play contract < orchestration < world < this run. Later layers win.
5. Plays the opening (the opening image first, if there is one), and the host writes the author's first scene.

<!-- section: turn -->
## 4. A turn: talk, then resolve

You say something; the turn begins.

**The talk beat.** The host places your line in the scene and passes the mic to the characters present; they answer, set conditions, bargain. The host lists what this will cost in money, which checks it needs, and how long it takes. **The world does not move during this beat**: the clock stands still, nothing changes, and you can keep talking or change your mind.

When talk turns into resolve:

- the judge says the talk is settled (the run's own model, without Jev);
- you say so outright ("deal", "let's do it");
- a line with nothing to discuss (a few steps across town) resolves directly;
- outside events don't wait for the talk to finish.

`@dm` asks the host to take a decisive turn; `@name` passes the mic to that character.

**The resolve beat.** What was agreed actually happens:

1. **Who acts.** The judge reads what you mean to do and which characters move with you; each character present decides what it does, and characters elsewhere take a step where they are.
2. **Rules first.** Dice are rolled where needed; rule layers such as combat are entered when needed.
3. **The narration.** The host writes this beat's prose. Whenever an outcome matters for what follows, the prose calls a tool, the engine rules on it on the spot, and the host writes on from that ruling. Money agreed in the talk is settled by the engine directly against the wallet.
4. **The write-down.** A separate, clean call reads the prose and writes down what changed: registered values (money, stamina, time…) and files in the world (who went where, who got what).
5. **Checks.** The engine checks layer by layer: is it well-formed, do the names and variables exist, do the world's rules allow it. If not, only the write-down is redone; the prose stays.
6. **Landing.** Changes are written to files, the turn count goes up by one, and the turn's world commit is made.

**State lands fast, then gets corrected.** Step 4 first lands with a fast pass so you can keep playing; at the same time a slower, thinking pass re-reads the beat in the background and corrects wrong values a few seconds later (it waits at most 90 seconds). You see "checking", then "corrected …" or "no change". If you send your next line first, the check is cancelled.

<!-- section: save -->
## 5. Saves, going back, replays

- A run is a folder with one commit per turn. The web UI shows the commit graph.
- **Going back deletes nothing**: returning to a turn starts a new line from there, and the old line stays. In the terminal: `/undo list` to look, `/undo <turn>` to go back.
- `/save`, `/load` to save and load; `/open` to continue or start a run.
- At an ending (or by hand) you can export a **replay**: story, timeline and cover, to share with others.

See [Save · branch · undo](/docs/players/saves).

<!-- section: create -->
## 6. Make your own world

Three ways in; all of them edit the same template folder:

- **Web / iOS creation desk**: start from an official template, add characters, plots, endings and clues, write the title and blurb in four languages, change the cover. The orchestration is chosen from 2–3 presets and its graph is read-only.
- **Local workbench**: "+ New Template / World / Character"; edit the orchestration graph, the map and triggers, and save back into the template.
- **A coding agent**: open the template folder in Claude Code or Codex. Every template carries `AGENTS.md`, `CLAUDE.md` and `spec/`; follow the spec to write folders and JSON / Markdown, no engine changes needed.

Characters live in the character library (`~/.worldlines/souls/`); a template only holds links.

See [Creator quickstart](/docs/creators/quickstart).

<!-- section: lint -->
## 7. Checks (lint)

`neonrp template lint <template>`, or the check in the workbench, first opens the template as a run in a temporary folder, then checks references, characters, plots, assets, the contract and all four languages. Findings come in two levels: **block** stops publishing, **warn** is only a heads-up.

<!-- section: publish -->
## 8. Publish to the Hub

| | How it goes up | Who sees it |
|---|---|---|
| **Free zone** | Uploaded straight from the local creation desk; public once automatic checks pass | Everyone; moderated afterwards |
| **Default zone** | Submitted from the web / iOS creation desk, goes to review | Listed after review |

Three gates before upload: no keys or credential files in the package; no lint blocks; title and blurb in all four languages and a cover. Submitting the same work again makes a new version: resubmitting while in review replaces the queued version; a revision of a listed work stays on the old version online until the new one passes review.

<!-- section: next -->
## Read next

- [Turn flow](/docs/concepts/turn-flow): what each step of the resolve beat takes in and puts out
- [Talk and resolve](/docs/concepts/planning-resolve): the rules of the two beats
- [How to play](/docs/players/how-to-play) · [Creator quickstart](/docs/creators/quickstart) · [Publishing](/docs/creators/publish)
