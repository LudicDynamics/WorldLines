---
title: "Introduction"
description: "WorldLines is an agentic simulation engine — a living village of AI agents, and you, playing together."
---

<!-- section: what-is-worldlines -->
## What is WorldLines?

WorldLines is an **agentic simulation engine**. A world-agent connects to place-agents; each place-agent hosts soul-agents. Everyone here is an agent. You join through an avatar terminal.

This is not "one AI character chatting with you." It is a **multi-agent society**, running in real time, where every agent has its own goals, memory, and constraints.

We built a harness that connects world-agents, place-agents, and soul-agents into one living simulation. We want this engine to power: **interactive-experience creation · multi-agent society experiments · agent-research advancement · personality-model and world-model benchmarks.**

Current status: **v0.3.0** (2026-07-13). [Play now →](https://hub.worldlines.gg)

Co-developed by **nikoloside** and **redoctober**, advanced together with [Ludic Dynamics](https://ludicdynamics.com).

<!-- section: ways-to-play -->
## Three ways to play

> **👉 New here? Start with Stoneford · Elena — the multi-agent village.** Two characters, Elena & Rowan, who each *think, remember, and act on their own* — not lines a narrator writes for them. It's the clearest taste of what makes WorldLines different. Import it in the Launcher below for the full village, or [meet Elena on WebHub](https://hub.worldlines.gg/play/souls/elena) in one click.

**1. WorldLines Launcher — desktop, one download.** Get the launcher from [worldlines.gg](https://worldlines.gg), double-click, and **import a world** — the official worlds are ready to play, no terminal needed. It sets up Python and your LLM provider for you.

**2. WebHub — browser, zero install.** Go to [hub.worldlines.gg](https://hub.worldlines.gg), sign in, and play. Browse the catalog of worlds and souls, create your own with the AI-assisted studio, and publish to the public registry. The cloud agents run for you.

**3. CLI & TUI — local, open tools (advanced).** Install the `worldlines` binary and play in the terminal with a Claude-Code-style TUI. The examples, tools, and protocol are open-source (AGPL-3.0); run your own models via Ollama / LM Studio / GLM.

<!-- section: why-worldlines -->
## Why WorldLines

Traditional "chat with an AI" interfaces lose everything the moment the context window fills. WorldLines gives you the guarantees of a real engine:

- **⭐ File-persisted memory & world state** — Everything (memory, saves, NPCs, Agents) lives on disk as plain JSON and Markdown. No cloud, no database, no hidden state. If you can open the folder, you own the world.
- **Auto-indexed context, auto-injected** — WorldLines builds a file index and a local vector database automatically, and injects only the relevant game data into each Agent's context per turn. No manual lorebook juggling.
- **Event-sourced state** — Every turn is an append-only Event; Snapshots make rewind fast.
- **Branch / Undo / Redo** — Explore narrative forks like git branches.
- **Sandbox & Replay** — Run experiments in isolation; verify determinism.
- **Orchestrator-driven multi-agent** — An Orchestrator routes to domain Agents (town / dungeon / combat-referee / world-builder / rules-referee) over one shared state.
- **Plan → Diff → Apply** — LLMs emit structured file operations you can review before they land.
- **Rich TUI** — A Claude-Code-style conversational terminal for both play and build.
- **Local-first models** — GLM, OpenAI, LM Studio, or Ollama.

<!-- section: positioning -->
## How WorldLines compares

|                         | Character.AI        | SillyTavern              | Claude Code            | **WorldLines**                     |
|-------------------------|---------------------|---------------------------|-------------------------|-------------------------------------|
| Primary domain          | Character chat      | Prompt frontend           | Code editing            | Living game worlds                  |
| Your world lives in     | Their service       | Prompt config + chat logs | Codebase on disk        | **Plain files + git**               |
| Memory & retrieval      | Cloud / opaque      | Manual lorebook           | Codebase retrieval      | **Auto file index + vector DB**     |
| Multi-agent             | —                   | —                         | Subagents per task      | Orchestrator + domain agents        |
| Local-first LLM         | No                  | Bring your own            | API-only                | GLM / LM Studio / Ollama            |
| Determinism / replay    | —                   | —                         | —                       | **Sandbox + Replay**                |

If Claude Code is your IDE for code, WorldLines is your IDE for living worlds — with the memory, retrieval, and orchestration baked in.

Full per-tool write-ups live at [Q&A](/docs/qa/what-is-airp) — vs Character.AI · vs SillyTavern · vs Claude Code · vs LangGraph.

> Note: WorldLines's harness is currently stricter than Claude Code's — it depends on complete context to orchestrate reliably. This is a deliberate tradeoff for higher determinism and easier debugging, not a deficiency.

<!-- section: next-steps -->
## Next Steps

- Follow the [Quickstart](/docs/getting-started/quickstart) — first turn in under 10 minutes
- Explore [Core Concepts](/docs/core-concepts/worlds) — events, snapshots, branches, agents
- See the [Roadmap](/docs/roadmap) — what's next
- [Q&A](/docs/qa/what-is-airp) — how WorldLines compares to existing tools
