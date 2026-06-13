# WorldLines

**Language:** [English](./README.md) · [简体中文](./README.zh.md) · [日本語](./README.ja.md) · [한국어](./README.ko.md)

> **What's open:** example worlds, tools, and protocol in this repo — AGPL-3.0. Fork, modify, and ship your own worlds.
> **What's not:** the engine core (`neonrp`). Free to play, not free to fork or redistribute. See [LICENSE](LICENSE).

<p align="center">
  <img alt="GitHub Stars" src="https://img.shields.io/github/stars/LudicDynamics/WorldLines?style=flat-square&color=8b5cf6" />
  <img alt="Watchers" src="https://img.shields.io/github/watchers/LudicDynamics/WorldLines?style=flat-square&color=8b5cf6" />
  <img alt="Forks" src="https://img.shields.io/github/forks/LudicDynamics/WorldLines?style=flat-square&color=8b5cf6" />
  <img alt="Issues" src="https://img.shields.io/github/issues/LudicDynamics/WorldLines?style=flat-square&color=8b5cf6" />
  <a href="https://hub.worldlines.gg"><img src="https://img.shields.io/badge/Live%20Demo-hub.worldlines.gg-8b5cf6?style=flat-square" /></a>
  <img alt="License" src="https://img.shields.io/badge/License-AGPL--3.0%20(examples)-blue?style=flat-square" />
  <img alt="LINUX DO" src="https://img.shields.io/badge/LINUX%20DO-WorldLines-8b5cf6?style=flat-square" />
</p>

<p align="center">
  <img src="./assets/hero.png" alt="WorldLines — The Door to Living Worlds" width="640" />
</p>

## Overview

**What can you do with it?**

Step into a world that remembers everything you do. Give siege orders in a grey-fog northern port. Explore every carriage of a train that never reaches the station. Sit across from an amnesiac healer who really remembers every word you say. Create a world in minutes — set its rules, its pace, its NPCs — or browse a public catalog and jump straight in. This is a multi-agent society running in real time: many AI souls and you, in one world, shaping it together.

It is an agentic simulation engine. A world-agent connects to place-agents; each place-agent hosts soul-agents. Everyone here is an agent. You join through an avatar terminal. This is not a chatbot, not a scripted game.

> Status: **v0.2.0 — Hub Launch** (2026-06) · [Play now →](https://hub.worldlines.gg)

---

## Team & Vision

We are **Ludic Dynamics** — a cross-disciplinary team of PhDs and researchers from the **University of Tokyo**, together with game industry practitioners. Our backgrounds span sociology, economics, computer graphics, AI agents, and virtual worlds.

We grew up on TRPGs, galgames, and otome games. Long before AI became what it is today, we spent years volunteering in Japanese cultural translation, working deep in the tabletop and game-graphics-engine industry, and helping Japanese visual novels launch on Steam. When the pandemic hit, we fell into AI role-play and narrative games — every weekend, every late night, running sessions, building worlds, chasing the feeling of a story that *really breathes*.

We have crossed time and space, adventuring across a dozen countries. We have explored the lost histories of other worlds, died and returned to a single day again and again to save someone precious, threaded through parallel timelines to find the one true world-line, and summoned the past to fight one last idealistic war.

WorldLines is what came out of that obsession.

> **Orchestrated Reality.** Through the Harness, we simulate worlds and AI souls — with physical consistency in the world, and cognitive consistency in every NPC. Don't code the agent. Use the agent to orchestrate the world.

We built a harness that connects world-agents, place-agents, and soul-agents into one living simulation. We want this engine to power: **interactive-experience creation · multi-agent society experiments · agent-research advancement · personality-model and world-model benchmarks.**

---

## Demo & Video

<p align="center">
  <a href="https://youtu.be/M_0xX8OZMa0">
    <img src="https://img.youtube.com/vi/M_0xX8OZMa0/maxresdefault.jpg" alt="WorldLines · Demo" width="640"/>
  </a>
</p>
<p align="center"><em>▶ Watch the demo on YouTube</em></p>

---

## Quick Start

### 🖥️ Download the launcher

Pick your platform. Double-click to install. No terminal needed.

| Platform | File | Download |
|----------|------|----------|
| macOS | `WorldLines.command` | [latest](https://worldlines.gg/WorldLines.command) |
| Windows | `WorldLines.bat` | [latest](https://worldlines.gg/WorldLines.bat) |
| Linux | `WorldLines.sh` | [latest](https://worldlines.gg/WorldLines.sh) |

macOS / Linux: `chmod +x` once, then drag to Desktop.

### ⌨️ Or install via terminal

```bash
# macOS / Linux
curl -LsSf https://worldlines.gg/install.sh | sh

# Windows (PowerShell)
irm https://worldlines.gg/install.ps1 | iex
```

Then:

```bash
worldlines
```

This launches the TUI. From there you can start a new world, browse the catalog, or jump into a saved session.

> **First run walks you through API setup.** Keys save to `~/.neonrp/config.json`. [Full provider guide →](https://docs.worldlines.gg/docs/getting-started/quickstart)

### 🌐 Or just play online

No install. Go to **[hub.worldlines.gg](https://hub.worldlines.gg)**, sign in, and play in the browser.

---

## Screenshots

<p align="center">
  <img src="./assets/gameplay.jpg" alt="Gameplay — arriving at Stoneford" width="720" />
</p>
<p align="center"><em>Gameplay — arriving at Stoneford in the mist</em></p>

---

## Example Worlds

WorldLines runs a world in one of **three engine modes** — and they are *not* interchangeable:

- **fast** — one quick agent, single voice.
- **orch** — a world-agent orchestrating domain agents (town / dungeon / combat / story); NPCs are data.
- **multi-agent** — a world-agent wrapping **independent souls**, each a character-agent with its own mind, memory, and agenda. The tell-tale sign is a `souls/` folder. *This is the new release.*

### 👥 multi-agent — independent souls in one world

| World | Souls | Live Demo |
|---|---|---|
| **[Kagura Island](./examples/kagura-island)** | **7** — Kagami · Hane · Makoto · Miyaji · Shiro · Tsubasa · Yuto. Japanese-folk mystery, time loop, CoC checks. The richest multi-agent society. | [Play →](https://hub.worldlines.gg/play/worlds/kagura-island) |
| **[Stoneford · Elena](./examples/stoneford-elena)** | **2** — Elena (the healer who remembers) + Rowan. The Stoneford world, now inhabited by living souls. | [Play →](https://hub.worldlines.gg/play/worlds/stoneford-elena) |

### ⛩ Stoneford — Flagship orch world

A grey-fog northern river port. Classic-fantasy TRPG · d20 dice · **10-agent orchestrated village** — a world-agent at the centre routing to town, dungeon, combat, story, and NPC agents. **[Play online →](https://hub.worldlines.gg/play/worlds/stoneford)** · **[Source & docs →](./examples/stoneford)**

### More worlds

| World | Play style | Live Demo |
|---|---|---|
| **Dark Train** | Open world — do anything, the world remembers | [Play →](https://hub.worldlines.gg/play/worlds/dark-train) |
| **Goblin Ambush** | 3-layer dungeon — fight through 3 boss goblins | [Source →](./examples/goblin-ambush) |
| **Worldline** | Time-drift narrative — text the past | [Source →](./examples/worldline) |
| **Sakura Hallway** | Clannad-style school-life · emotional narrative | [Source →](./examples/sakura-hallway) |

All worlds live in [examples/](./examples/) — open-source (AGPL-3.0), fork and ship your own.

### Quick run

```bash
# multi-agent (souls/ engages the soul wrapper)
neonrp tui --from examples/kagura-island       # 7 souls — Japanese-folk mystery
neonrp tui --from examples/stoneford-elena     # 2 souls — Elena & Rowan

# orch
neonrp tui --from examples/stoneford           # flagship siege TRPG
neonrp tui --from examples/dark-train          # open world
neonrp tui --from examples/goblin-ambush/zh    # 3-layer dungeon
neonrp tui --from examples/sakura-hallway/zh   # school-life narrative
```

Or play online: [Kagura Island](https://hub.worldlines.gg/play/worlds/kagura-island) · [Stoneford · Elena](https://hub.worldlines.gg/play/worlds/stoneford-elena) · [Stoneford](https://hub.worldlines.gg/play/worlds/stoneford) · [Dark Train](https://hub.worldlines.gg/play/worlds/dark-train)

### Claude Code / MCP

Open Claude Code inside any world directory and the agents are there:

```
cd examples/dark-train
claude
@world-agent 开始游戏
```

WorldLines exposes its agents as MCP tools. Claude Code discovers them
automatically — no extra setup. Each example ships with `.claude/agents/`
pre-configured.

---

## Other Projects Using This Engine

- **[Soul Talk](https://hub.worldlines.gg/play/souls/elena)** — character-agent dialogue scene. Elena remembers.
- **[Worldline](./examples/worldline)** — time-drift narrative engine. Text the past, watch timelines rewrite.
- **Coming: RP-Abyss** — TRPG expedition. DM + dice checks.

---

## Who Is This For

### 🎮 AI Role-Play Players

You come from **Character.AI, SillyTavern, or AI Tavern**. You love deep character conversations — but the world always forgets.

WorldLines gives you characters with **real memory**. They remember what you said three sessions ago. They have inner voices, intentions, goals. And they're not alone — they live in a world with other characters who also remember.

→ [Play Elena (Soul Talk)](https://hub.worldlines.gg/play/souls/elena) · [Browse catalog](https://hub.worldlines.gg/souls)

### 📖 Galgame & Visual Novel Fans

You love **Ren'Py, TyranoBuilder, and branching narratives** — but you're tired of writing every route by hand. You want stories that *respond*, not just branch.

WorldLines lets you set the characters, the world rules, and the tone — and the agents generate the story in real time. Every choice ripples. No two playthroughs are the same.

→ [Create your first world](https://docs.worldlines.gg/docs/guides/creating-first-world) · [SillyTavern import →](https://docs.worldlines.gg/docs/guides/sillytavern-import)

### ✍️ TRPG GMs & World Creators

You run tabletop campaigns in **Foundry VTT, Discord, or pen-and-paper**. You spend more time prepping than playing.

WorldLines is a GM's engine: you set the constraints — the rules, the NPCs, the tone — and the agents run the world for you. Auto-indexed lore, per-NPC memory, dice-referee agents.

→ [Quickstart](https://docs.worldlines.gg/docs/getting-started/quickstart) · [Stoneford starter world](./examples/stoneford)

### 🔬 Researchers — AI Personality · World Models · Multi-Agent

You study personality models, world-model benchmarks, or multi-agent societies. You need a **reproducible sandbox** — not a black-box API.

WorldLines is **file-backed, event-sourced, and git-diffable**. Every agent decision, every world-state change, is a plain-text event you can trace, replay, and measure. Run the same scenario with different models, compare outputs, publish the results.

→ [Core concepts](https://docs.worldlines.gg/docs/core-concepts/agents-orchestration) · [How It Works](#how-it-works)

### 🛠️ Developers

You build with **Claude Code, LangGraph, or custom agent pipelines**. You want a protocol you can inspect, fork, and disagree with.

WorldLines examples, tools, and protocol are **open-source (AGPL-3.0)**. Fork a world, mod an agent, ship your own. The engine binary is free to play — no API key for local use.

→ [examples/](./examples/) · [Protocol docs](https://docs.worldlines.gg/docs/protocol/overview)

---

## How It Works

WorldLines treats the game world as a file-backed, event-sourced state machine. Every turn is an append-only Event; Snapshots make rewind fast.

**Agent architecture (3 layers):**

```
Layer 1: world-agent        — state · routing · narrative · archive
Layer 2: town-agent          — NPCs, shops, navigation
         dungeon-agent       — exploration
         combat-referee      — d20 dice
         world-builder       — map updates
Layer 3: (future) dice/rules tool-agents
```

- **File-persisted memory & world state** — Everything lives on disk as plain JSON and Markdown.
- **Auto-indexed context, auto-injected** — No manual lorebook juggling.
- **Branch / Undo / Redo** — Explore narrative forks like git branches.
- **Sandbox & Replay** — Verify determinism.
- **Local-first models** — GLM, OpenAI, LM Studio, or Ollama.

---

## Tutorial

Full documentation at **[docs.worldlines.gg](https://docs.worldlines.gg)**:

| Topic | Link |
|---|---|
| Getting started | [docs.worldlines.gg/docs/getting-started](https://docs.worldlines.gg/docs/getting-started) |
| Core concepts | [docs.worldlines.gg/docs/core-concepts](https://docs.worldlines.gg/docs/core-concepts) |
| Guides | [docs.worldlines.gg/docs/guides](https://docs.worldlines.gg/docs/guides) |
| Q&A / comparisons | [docs.worldlines.gg/docs/qa](https://docs.worldlines.gg/docs/qa) |

---

## Roadmap

| Version | Status |
|---|---|
| **v0.1.9** — Engine (2026-04) | ✓ 10-agent orchestrator · Stoneford starter · Claude Code runtime |
| **v0.2.0** — Hub Launch (2026-06) | ✓ WebHub · Hosted Play · Soul Talk · Create Studio · Stripe · Covers · Saves |
| **v0.3.0** — Desktop (2026-06) | ◑ Tauri desktop app · Multi-agent society · Persistent worlds · Alipay/WeChat |
| **v1.0** — Protocol | ○ Stable WORLD/SOUL protocol · Self-hostable web edition |

Full roadmap: [docs.worldlines.gg/docs/roadmap](https://docs.worldlines.gg/docs/roadmap)

---

## License

**Open-source (AGPL-3.0):** example worlds, character bundles, tools, and protocol in `examples/` and `tools/`.

**Not open-source:** the engine core (`neonrp`). Proprietary preview — free to play, not free to fork.

## Star History

<p align="center">
  <a href="https://www.star-history.com/?type=date&repos=LudicDynamics%2FWorldLines">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=LudicDynamics/WorldLines&type=date&theme=dark&legend=top-left" />
      <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=LudicDynamics/WorldLines&type=date&legend=top-left" />
      <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=LudicDynamics/WorldLines&type=date&legend=top-left" />
    </picture>
  </a>
</p>

---

## Community

- Web: [worldlines.gg](https://worldlines.gg) · Docs: [docs.worldlines.gg](https://docs.worldlines.gg)
- Discord: [discord.gg/HJYWbdqWrE](https://discord.gg/HJYWbdqWrE)
- GitHub: [LudicDynamics/WorldLines](https://github.com/LudicDynamics/WorldLines)
- Contact: `info@worldlines.gg`

---

Developed by **nikoloside** & **redoctober**, advanced by [Ludic Dynamics](https://ludicdynamics.com).
