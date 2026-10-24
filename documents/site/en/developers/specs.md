---
title: "Specs"
description: "The full specs for worlds, characters (souls), templates, rules packs, play contracts and player data, plus what a template, a run and the character library look like on disk."
---

<!-- section: specs -->
## Specs

Read the matching spec before you write a world, a character, a template or a rules pack. Agents (Claude Code / Codex)
read the same files when they author.

| Spec | What it covers | English | 中文 |
|---|---|---|---|
| World | The world folder: the place tree, people, items, rule tables, opening | [world.en.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/world.en.md) | [world.zh.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/world.zh.md) |
| Soul (character) | The character bundle: identity, persona, memory, RPG body, portrait; the character library | [soul.en.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/soul.en.md) | [soul.zh.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/soul.zh.md) |
| Template | A world + characters + a rules pack + an orchestration bound into one playable, publishable package | [template.en.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/template.en.md) | [template.zh.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/template.zh.md) |
| Rules pack | Rule tables, rule panels, checks and contests, the status table, the clock (`rpg` / `pct`) | [pack.en.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/pack.en.md) | [pack.zh.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/pack.zh.md) |
| Contract | The play contract: turns, deaths, endings | [contract.en.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/contract.en.md) | [contract.zh.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/contract.zh.md) |
| Player | The player's own data: avatars, the record across runs, chats | [player.en.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/player.en.md) | [player.zh.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/player.zh.md) |

Four more are generated from the code every time, so they never go stale: `ops` (each rules pack's ops, classes, variables, triggers, seams and mode layers) · `authoring` (the template authoring ops) · `contracts` (the play contracts in force) · `http` (every HTTP path the engine answers).

With the engine installed you can read them in the terminal:

```bash
neonrp spec                 # list every spec
neonrp spec pack            # print one (--lang en for English)
neonrp spec ops --pack rpg  # the ops, classes and variables a rules pack offers
neonrp spec http            # every HTTP path
```

<!-- section: layout -->
## On disk

**A template** (`<id>.template/`, the unit you author and publish):

```
stoneford-town.template/
├── template.json           # card, mode, zone, orchestration `uses`, rules pack, cast, plots, lint, ui, rewards…
├── world-overlay/          # changes laid over a built-in world (or world/: a whole world of its own)
├── prompts/                # prompt layers (world / template / per soul prompts/souls/<sid>/)
├── plots/                  # plot packs
├── i18n/<lang>/            # layers for other languages
├── assets/                 # asset slots: assets/<class>/<slot>/
├── orchestration.json      # a patch to the orchestration graph (optional)
├── frontends/              # this world's own front ends (optional, not exported)
├── spec/ · AGENTS.md · CLAUDE.md   # generated, for agents
```

**A run** (the world folder `template build` or a new game produces; runs started in `worldlines` live under `~/.worldlines/plays/`):

```
<run>/
├── manifest.json           # template = the combined pack name (e.g. rpg+economy)
├── playthrough.json        # the cast and the soul instances
├── game/
│   ├── meta/               # engine state: run_state, engine.json, the variables / classes / actions / triggers / entries overlays,
│   │                       #   events.jsonl (the event ledger), template.json, play_contract.json, orchestration.json …
│   ├── locations/<T>/<spot>/location.json   # the place tree
│   ├── world/              # world data (world_map, mixin data such as economy.json)
│   ├── player/             # player state: wallet, items, stats
│   ├── rules/ · lore/ · plots/ · item/ …
├── souls/<sid>-<instance>/ # the soul instances in this run: soul.json, soul.md, persona/, character/, memory …
└── .neonrp/                # sessions, saves, branches, this run's settings
```

**`~/.worldlines/`** (shared by the local web app and the TUI):

```
~/.worldlines/
├── templates/              # your own templates (forked / imported / new)
├── official/               # Default Zone worlds fetched with your account
├── souls/<name>/           # the character library: a template links one with {"lib": "<name>"}; it is copied into a run only when the run starts
├── plays/                  # one folder per run
├── replays/<id>/           # exported replays
└── commits/                # world commits: worlds/, refs/<run>/{HEAD,branches/*}, blobs/
```

Every landed turn makes one world commit (content-addressed: the commit id is a hash of the content); a soul instance's commits sit in its own `.commits/`. Rolling back = branching off at a commit; the old line stays. Timestamps are never part of an identity, only labels.
