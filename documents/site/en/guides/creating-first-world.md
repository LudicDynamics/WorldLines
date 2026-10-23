---
title: "Creating Your First World"
description: "Three ways to make a world — the Launcher, the WebHub studio, or an AI coding agent."
---

<!-- section: launcher -->
## In the WorldLines Launcher

Open WorldLines → **New world**, start from a template close to what you want (Stoneford · Kagura Island · …), then play it and tweak it in **Build** mode. The fastest way to a world you can actually play.

<!-- section: webhub -->
## In the browser — WebHub Create studio

At [hub.worldlines.gg](https://hub.worldlines.gg), the **Create** studio guides you through a world with AI assistance — set the premise, characters, and tone, then publish to the public registry when you're happy. Zero install.

<!-- section: ai-skill -->
## With Claude Code or Codex — the authoring skills

WorldLines ships **Claude Code** and **Codex** authoring skills. Clone the repo, open it in your AI coding agent, and just describe what you want:

```bash
git clone https://github.com/LudicDynamics/WorldLines.git
cd WorldLines        # then open in Claude Code or Codex
```

> *"Make a 国风 otome world: a palace, four princes, and a lamp that chooses the heroine."*

The matching skill loads automatically and scaffolds the `game/` entities, agents, and (for a village) souls for you. Step-by-step: [authoring tutorials](https://github.com/LudicDynamics/WorldLines/tree/main/tutorials) — character card · world card · full world · soul.

<!-- section: advanced-cli -->
## Advanced — hand-author from the CLI

Want full control? Scaffold the engine metadata and write `game/` by hand:

```bash
worldlines init        # creates .neonrp/ engine metadata
# author game/meta/world.json, game/player/, locations, agents…
neonrp validate        # check the schema
neonrp index build     # rebuild the retrieval index
```

A minimal world needs `game/meta/world.json`, a starting player state, at least one location, and one agent (the orchestrator).
