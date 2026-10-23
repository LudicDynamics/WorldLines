---
title: "vs Claude Code"
description: "Claude Code is an agentic coding environment. WorldLines is an agentic worlding environment. Similar primitives, different domains."
---

<!-- section: shared-primitives -->
## What they share

Both engines sit on the same agentic foundation:

- A structured proposal / diff / apply loop
- File-backed state that lives in a real directory
- A conversational terminal interface
- Retrieval over the working set, not the whole corpus
- Session history you can branch and replay

If Claude Code is your IDE for **code**, WorldLines is your IDE for **living worlds**. The intuitions transfer.

<!-- section: where-they-diverge -->
## Where they diverge

|                  | Claude Code                       | WorldLines                              |
|------------------|-----------------------------------|-----------------------------------------|
| Domain           | Code editing / software agents    | Game worlds / AIRP agents               |
| State unit       | Files + git                       | Events + Snapshots + branches           |
| Primary loop     | Plan → Edit → Test                | Plan → Diff → Apply → Save              |
| Ships with       | You bring the repo                | `stoneford` starter template included   |
| Sandboxing       | Shell / container                 | First-class in-engine Sandbox + Replay  |
| Multi-agent      | Subagents per task                | World-agent + a society of souls (the village) + domain agents |

Same agentic muscle, pointed at a different domain: keeping a *world* coherent across turns rather than a codebase.

<!-- section: fit-together -->
## How they fit together

They're not rivals — WorldLines runs *on* the same agentic paradigm Claude Code popularized, and Claude Code is one of the best ways to **author** a WorldLines world.

- **Author with the skills.** WorldLines ships Claude Code (and Codex) authoring skills — clone the repo, open it in Claude Code, and describe the world you want; it scaffolds the `game/` + agents + souls for you. See the [tutorials](https://github.com/LudicDynamics/WorldLines/tree/main/tutorials).
- **Play it agentically.** Many people already role-play directly inside Claude Code. WorldLines gives that the missing pieces: a persistent world, a society of independent souls (the multi-agent village), save / branch / replay — and a front-end so it isn't all raw terminal.

If Claude Code is your IDE for code, WorldLines turns that same agentic muscle into a living, playable world.

<!-- section: what-we-push -->
## What we push further

Lots of people already role-play inside Claude Code and Codex — and we're for it. Building on that direction, we set out to solve three things:

1. **Speed.** Claude Code / Codex can take **3+ minutes** a turn — fine for coding, painful for play. We want a **faster agent tuned for role-play**, so a turn feels like a conversation, not a build.

2. **No lock-in — any model, even local & free.** Role-play shouldn't be chained to one vendor. Run it on **DeepSeek, OpenRouter, open-source, local, and free** models, and keep it **customizable** — you choose the brain.

3. **Multi-agent, at scale.** We're pushing the **multi-agent village** further — more independent souls, larger scenes, bigger worlds — and innovating on the **orchestration** that keeps them all coherent.

Same agentic spirit as Claude Code; tuned for living worlds instead of codebases.
