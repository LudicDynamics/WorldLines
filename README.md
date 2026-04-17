# WorldLines

**Language:** [English](./README.md) · [简体中文](./README.zh.md) · [日本語](./README.ja.md) · [한국어](./README.ko.md)

<p align="center">
  <img src="./assets/hero.png" alt="WorldLines — The Door to Living Worlds" width="640" />
</p>

<p align="center"><em>YouTube trailer — coming soon.</em></p>

> Status: Preview (v0.1.0 — 2026-04-17 Public Preview)

> *From AI chat to Agentic AIRP.*
> A file-backed, event-sourced engine for living worlds.

WorldLines is an Agentic AIRP engine (AI RolePlay engine) by
[Ludic Dynamics](https://ludic-dynamics.com). The engine binary is codenamed
`neonrp`; the release brand is **WorldLines**.

It treats the game world as a versioned, file-backed state machine, so
your playthroughs, your edits, and your Agents become reproducible
artifacts — not ephemeral chat logs.

---

## Why WorldLines

Traditional "chat with an AI" interfaces lose everything the moment the
context window fills. WorldLines gives you the guarantees of a real engine:

- **Event-sourced state.** Every turn is an append-only Event; Snapshots
  make rewind fast.
- **Branch / Undo / Redo.** Explore narrative forks like git branches.
- **Sandbox & Replay.** Run experiments in isolation; verify determinism.
- **Multi-Agent orchestration.** An Orchestrator routes to domain Agents
  (town / dungeon / combat-referee / world-builder / rules-referee) over
  one shared state.
- **Plan → Diff → Apply.** LLMs emit structured file operations you can
  review before they land.
- **File-backed world.** `game/` is just JSON and Markdown. Version it
  with git. Edit it with anything.
- **Rich TUI.** A Claude-Code-style conversational terminal for both
  play and build.
- **Local-first models.** GLM, OpenAI, LM Studio, or Ollama.

### Positioning — vs. Claude Code

|                  | Claude Code                       | WorldLines                              |
|------------------|-----------------------------------|-----------------------------------------|
| Domain           | Code editing / software agents    | Game worlds / AIRP agents               |
| State unit       | Files + git                       | Events + Snapshots + branches           |
| Primary loop     | Plan → Edit → Test                | Plan → Diff → Apply → Save              |
| Ships with       | You bring the repo                | `stoneford` starter template included   |
| Sandboxing       | Shell / container                 | First-class in-engine Sandbox + Replay  |

If Claude Code is your IDE for code, WorldLines is your IDE for living
worlds.

> Note: WorldLines's harness is currently stricter than Claude Code's — it depends on complete context to orchestrate reliably. This is a deliberate tradeoff for higher determinism and easier debugging, not a deficiency.

> **Why proprietary engine + open data?** The WorldLines engine is released as a proprietary preview to preserve orchestration fidelity during rapid iteration. Game data formats, starter worlds (like Stoneford), and integration protocols are open to seed an interoperable AIRP ecosystem.

---

## Quickstart

```bash
# 1. Install (see INSTALL.md for alternatives)
uv tool install -e /path/to/worldlines

# 2. Scaffold and run the stoneford starter
mkdir my-world && cd my-world
neonrp init
neonrp game new --template stoneford

# 3. Play in the TUI
neonrp tui
```

Type `look around` and press Enter. That is your first agentic turn.

A 30-minute walkthrough lives in [QUICKSTART.md](QUICKSTART.md).

---

## Module Map

- [INSTALL.md](INSTALL.md) — Install from wheel, source, or `uv tool`
- [QUICKSTART.md](QUICKSTART.md) — 30-minute first-play guide
- [CONCEPTS.md](CONCEPTS.md) — Events, Snapshots, branches, Agents, Sandboxes
- [CLI_REFERENCE.md](CLI_REFERENCE.md) — All `neonrp` commands
- [TUI_GUIDE.md](TUI_GUIDE.md) — Terminal UI reference
- [RELEASE_NOTES.md](RELEASE_NOTES.md) — v0.1.0 scope and roadmap
- [templates/stoneford-worldlines/](templates/stoneford-worldlines/README.md) — Sample world & Agents
- [CONTRIBUTING.md](CONTRIBUTING.md) — How to contribute
- [LICENSE](LICENSE) — Proprietary preview terms

## Community & Contact

- Issues & discussion: GitHub (link pending on 2026-04-17 D-Day)
- Founder / maintainer: Ludic Dynamics (Tokyo, Japan)
- Contact: `hello@ludic-dynamics.com` (placeholder)

---

## Copyright & Acknowledgements

Copyright © 2026 worldlines-nikoloside, redoctober. All rights reserved.

WorldLines is a proprietary engine released as preview for evaluation
only. No license is granted for reuse, redistribution, or derivative
works. See [LICENSE](LICENSE) for the full terms.

With gratitude to the Ludic Dynamics community, and to amber and other
friends whose support made this release possible.

*WorldLines and Ludic Dynamics are trademarks of Ludic Dynamics.*
