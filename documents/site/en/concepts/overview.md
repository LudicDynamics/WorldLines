---
title: "Three layers: engine · template packs · product"
description: "WorldLines — Make you play with your AI character in an infinite world. Everyone reads this page first."
---

<!-- section: what -->
## What WorldLines is

**WorldLines — Make you play with your AI character in an infinite world.**

You play the protagonist and live alongside AI characters in a world that keeps moving on its own: characters (souls) have their own agents and decide and speak for themselves; world NPCs are voiced by the world and move by its rules; the map grows new places; the economy and factions run by themselves. Everything you say and every decision a character makes is only a **proposal** — it changes the world only after the world (the world agent) verifies it.

<!-- section: layers -->
## Three independent layers

| Layer | What it is | Who uses it |
|---|---|---|
| **NeonRP engine** (the `neonrp` package) | Only the open-schema / closed-schema state logic, propose → verify → apply, events and subscriptions, commits and branches. **No gameplay at all.** | SDK developers |
| **Template packs** | Register a kind of play into the engine: classes, variables, ops, triggers, mechanics seams, prompt. Built in: `rpg` (d20 + attribute modifier, our own rules; checks and the downed rule can use SRD 5.2, CC BY 4.0), `pct` (percentile dice, BRP — Chaosium's *Basic Roleplaying*, ORC License: d100 skills, sanity, dying checks — built on rpg; this kind of play is called "sandbox tabletop"), `werewolf` and `monopoly` | Creators / developers |
| **WorldLines product** (the `worldlines` package) | The play UI, the creation workbenches, assembly, Lint, export / import, publishing to the Hub. It depends on the `neonrp` engine and only calls public interfaces | Players / creators |

So: **players install `worldlines`** (it brings the engine along); **developers can install `neonrp` alone** and embed the engine in their own program or in Godot.

**Two ways to install, two kinds of turn.** The `worldlines` / `neonrp` packages on PyPI include the full two-beat orchestration (talk first, then resolve). Building from the open-source repository gives you the open engine, which runs single-beat turns (resolve only). The same template plays on both; when a template asks for two beats and the engine does not have them, it falls back to one. See [How a turn runs](/docs/concepts/turn-flow).

<!-- section: readers -->
## Read by who you are

| You are | Start here |
|---|---|
| a player | [Player quickstart](/docs/players/quickstart) |
| a creator | [Creator quickstart](/docs/creators/quickstart) |
| an SDK / heavy-front-end developer | [Developer quickstart](/docs/developers/quickstart) · [Live event stream](/docs/developers/events) |
| an agent working for someone (Claude Code, Codex, WorldLines' authoring agent) | [For agents](/docs/agents/overview) |

Four more short concept pages worth reading: [Open & closed schema](/docs/concepts/schema) · [Propose → verify → apply](/docs/concepts/ops) · [Characters & NPCs](/docs/concepts/souls) · [World lines](/docs/concepts/worldlines).

<!-- section: map -->
## What is in 1.0

| Thing | What it is | Read |
|---|---|---|
| World | a folder: a tree of places, NPCs, items, the opening | `spec/world.md` in a template folder |
| Character | lives in the library; templates hold links, made real when a run starts | [Characters and casting](/docs/creators/characters) · [Your character](/docs/players/your-character) |
| Template | world + character links + rules pack + contract + orchestration: the unit you play, export and publish | [The template file](/docs/creators/template-card) · [Workbenches](/docs/creators/workbench) |
| Play contract | the experience a kind of game promises; lint checks it, the run settles by it | [Play contracts](/docs/creators/contracts) |
| Orchestration | how a turn runs: the template names it in `uses` (two beats `two_beat` / one beat `one_beat`); the local orchestration bench can edit the graph | [Workbenches](/docs/creators/workbench) · [Talk it over, then resolve](/docs/concepts/planning-resolve) |
| A turn | two beats: planning (the world unchanged) → resolve (prose first, then the state); the open-source edition has the resolve beat only | [How a turn runs](/docs/concepts/turn-flow) · [Live event stream](/docs/developers/events) |

<!-- section: stoneford -->
## The running example: Stoneford

Every example uses the built-in template **Stoneford · The Night the Fog Withdraws** (`stoneford-town`): one night a year the fog draws back from the north road; the scouts never came back, the **One-Eyed Tiger** bandits hold the post road, and you have two nights and a day to gather what you need to leave by the north gate. The healer **Elena** and **Rowan** are characters with their own agents; Kas at the gate, Heron at the guild and Mira at the inn are world NPCs. The other built-in template is **Greyoak House · The Closed Door** (`pct-house`), sandbox tabletop with percentile dice.

<!-- section: license -->
## Licensing

From 1.0 the NeonRP engine is open source under **Apache-2.0**; the WorldLines product (`worldlines`, the UI and the built-in sample templates) is released under **AGPL-3.0**. The two-beat orchestration in the PyPI packages is not in the open-source repository and is not open source.

The **content** of templates and example worlds has its own license (see `CONTENT-LICENSE.md` in the engine package): setting text (world and character settings, places, rules tables) is **CC BY 4.0** — remix it, use it commercially, just credit it; images and audio (portraits, covers, backgrounds, sounds) are **CC BY-NC 4.0** — remix with credit, not for commercial use. The open rules keep their own licenses: SRD 5.2 is CC BY 4.0, BRP is under the ORC License.
