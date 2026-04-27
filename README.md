# WorldLines

**Language:** [English](./README.md) · [简体中文](./README.zh.md) · [日本語](./README.ja.md) · [한국어](./README.ko.md)

<p align="center">
  <img src="./assets/hero.png" alt="WorldLines — The Door to Living Worlds" width="640" />
</p>

<p align="center">
  <img src="./assets/helloworld.jpg" alt="WorldLines TUI launch screen" width="720" />
</p>

<p align="center"><em>YouTube trailer — coming soon.</em></p>

<table align="center">
  <tr>
    <td width="50%" align="center"><img src="./assets/cards/D0%20Hero%20%28deck%20%C2%B7%20EN%29.png" alt="WorldLines — Hero" /></td>
    <td width="50%" align="center"><img src="./assets/cards/D1%20Mira%27s%20Tab%20%28deck%20%C2%B7%20EN%29.png" alt="Mira's Tab — story card" /></td>
  </tr>
  <tr>
    <td align="center"><img src="./assets/cards/D2%20Lao%20Wei%20Invite%20%28deck%20%C2%B7%20EN%29.png" alt="Lao Wei's Invite — story card" /></td>
    <td align="center"><img src="./assets/cards/D3%20Gameplay%20%28deck%20%C2%B7%20EN%29.png" alt="Gameplay loop" /></td>
    <td align="center"><img src="./assets/cards/D4%204%20Worlds%20%28deck%20%C2%B7%20EN%29.png" alt="Four playable worlds" /></td>
  </tr>
</table>

> Status: **v0.1.7 stable** (2026-04-27) · next: **v0.2.0** (planned)

> *Agents for Role Play. Agents for Game. Agents as a Game.*
> A file-backed, event-sourced engine for living worlds.

> **Still early — we're building in the open.** WorldLines is in active
> development. Expect a steady drumbeat of new gameplay, new
> orchestration modes, and new modules. We'd rather ship early and
> iterate with you than polish in silence.

WorldLines is an Agentic AIRP engine (AI RolePlay engine) co-developed
by **nikoloside** and **redoctober**, continuously advanced together
with [Ludic Dynamics](https://ludicdynamics.com). The engine binary is
codenamed `neonrp`; the release brand is **WorldLines**.

It treats the game world as a versioned, file-backed state machine, so
your playthroughs, your edits, and your Agents become reproducible
artifacts — not ephemeral chat logs.

---

## Why WorldLines

Traditional "chat with an AI" interfaces lose everything the moment the
context window fills. WorldLines gives you the guarantees of a real engine:

- **⭐ File-persisted memory & world state.** Everything — memory, saves,
  NPCs, Agents — lives on disk as plain JSON and Markdown. No cloud,
  no database, no hidden state. If you can open the folder, you own
  the world.
- **Auto-indexed context, auto-injected.** WorldLines builds a file
  index and a local vector database automatically, and injects only
  the relevant game data into each Agent's context per turn. No manual
  lorebook juggling.
- **Event-sourced state.** Every turn is an append-only Event; Snapshots
  make rewind fast.
- **Branch / Undo / Redo.** Explore narrative forks like git branches.
- **Sandbox & Replay.** Run experiments in isolation; verify determinism.
- **Orchestrator-driven multi-agent.** An Orchestrator routes to domain
  Agents (town / dungeon / combat-referee / world-builder / rules-referee)
  over one shared state.
- **Plan → Diff → Apply.** LLMs emit structured file operations you can
  review before they land.
- **Rich TUI.** A Claude-Code-style conversational terminal for both
  play and build.
- **Local-first models.** GLM, OpenAI, LM Studio, or Ollama.

### How WorldLines compares

|                         | Character.AI        | SillyTavern              | Claude Code             | **WorldLines**                     |
|-------------------------|---------------------|---------------------------|-------------------------|-------------------------------------|
| Primary domain          | Character chat      | Prompt frontend           | Code editing            | Living game worlds                  |
| Your world lives in     | Their service       | Prompt config + chat logs | Codebase on disk        | **Plain files + git**               |
| Memory & retrieval      | Cloud / opaque      | Manual lorebook           | Codebase retrieval      | **Auto file index + vector DB**     |
| Multi-agent             | —                   | —                         | Subagents per task      | Orchestrator + domain agents        |
| Local-first LLM         | No                  | Bring your own            | API-only                | GLM / LM Studio / Ollama            |
| Determinism / replay    | —                   | —                         | —                       | **Sandbox + Replay**                |

If Claude Code is your IDE for code, WorldLines is your IDE for living
worlds — with the memory, retrieval, and orchestration baked in.

> Full per-tool write-ups live at
> [docs.worldlines.gg/docs/qa](https://docs.worldlines.gg/docs/qa)
> (vs Character.AI · vs SillyTavern · vs Claude Code · vs LangGraph · vs OpenClaw).

> Note: WorldLines's harness is currently stricter than Claude Code's — it depends on complete context to orchestrate reliably. This is a deliberate tradeoff for higher determinism and easier debugging, not a deficiency.

---

## Install

### One-liner

```bash
# macOS / Linux
curl -LsSf https://worldlines.gg/install.sh | sh

# Windows (PowerShell)
irm https://worldlines.gg/install.ps1 | iex
```

Installs `uv` (if missing) then `uv tool install worldlines`. Verify
with `neonrp --help` or just `worldlines`.

### Double-click launcher

Prefer not to touch a terminal? Download a platform launcher and
double-click it. Each opens a terminal window, runs the first-time
install (or self-updates on subsequent launches), then hands off to the
TUI:

| Platform | File                 | Download |
|----------|----------------------|----------|
| macOS    | `WorldLines.command` | [latest](https://worldlines.gg/WorldLines.command) |
| Windows  | `WorldLines.bat`     | [latest](https://worldlines.gg/WorldLines.bat)     |
| Linux    | `WorldLines.sh`      | [latest](https://worldlines.gg/WorldLines.sh)      |

After download (macOS / Linux), `chmod +x` once:

```bash
chmod +x ~/Downloads/WorldLines.command   # or WorldLines.sh
```

Then drag to Desktop / Dock and treat it like any other shortcut.

### Users in China

Some mainland networks throttle GitHub Releases and Cloudflare-fronted
domains. If `curl https://worldlines.gg/install.sh` times out:

```bash
# Direct GitHub fetch (sometimes faster than the Cloudflare redirect):
curl -LsSf \
  https://github.com/LudicDynamics/WorldLines/releases/latest/download/install.sh \
  | sh

# Or force uv to use a Tsinghua PyPI mirror:
export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
uv tool install worldlines

# Or both at once:
CHINA_MIRROR=1 curl -LsSf https://worldlines.gg/install.sh | sh
```

Auto-update (`neonrp self-update`) honors `UV_DEFAULT_INDEX`, so
exporting it in your shell profile keeps future upgrades on the mirror.

### Developers — editable install

```bash
uv tool install -e /path/to/worldlines
neonrp --help
```

Full install options (wheel, source, alternate mirrors) live at
[docs.worldlines.gg/docs/guides/launcher](https://docs.worldlines.gg/docs/guides/launcher).

---

## Quickstart

```bash
# Fresh directory — /init is enough to start in build mode
mkdir my-world && cd my-world
neonrp init

# Or scaffold the stoneford starter for a headline sample
neonrp game new --template stoneford

# Launch the TUI
neonrp tui
```

Fresh projects expose packaged builtin skills automatically; `/game new`
is optional unless you want the starter world + play-agent scaffold
immediately.

> **First run walks you through API setup.** Pick **Claude Code (MCP)** if
> you already have it, paste a key for **Anthropic / OpenAI / DeepSeek /
> OpenRouter / [GLM free tier](https://zhipuai.cn)**, or point to a local
> server via **Ollama / LM Studio**. Keys save to `~/.neonrp/config.json`;
> change later via `[3] settings / api`.
> [Full provider guide →](https://docs.worldlines.gg/docs/getting-started/quickstart)

Type `look around` and press Enter. That is your first agentic turn.

<p align="center">
  <img src="./assets/gameplay.jpg" alt="WorldLines gameplay — arriving at Stoneford in the mist" width="720" />
</p>

A 10-minute walkthrough lives at
[docs.worldlines.gg/docs/getting-started/quickstart](https://docs.worldlines.gg/docs/getting-started/quickstart).

---

## Documentation

Full docs are on the website — this repo keeps only the entry points.

| Topic                | URL                                                                              |
|----------------------|----------------------------------------------------------------------------------|
| Getting started      | [docs.worldlines.gg/docs/getting-started](https://docs.worldlines.gg/docs/getting-started) |
| Core concepts        | [docs.worldlines.gg/docs/core-concepts](https://docs.worldlines.gg/docs/core-concepts) (worlds · characters & multi-agent · agents & orchestration · engine modes · sessions · memory) |
| Guides               | [docs.worldlines.gg/docs/guides](https://docs.worldlines.gg/docs/guides) (launcher · world lifecycle · SillyTavern import · Discord tutorial) |
| Q&A / comparisons    | [docs.worldlines.gg/docs/qa](https://docs.worldlines.gg/docs/qa) (vs Character.AI · vs SillyTavern · vs Claude Code · vs LangGraph · vs OpenClaw) |
| Changelog & roadmap  | [docs.worldlines.gg/docs/changelog](https://docs.worldlines.gg/docs/changelog) |

**In this repo:**

- [templates/stoneford-worldlines/](templates/stoneford-worldlines) — Sample world & Agents (submodule)
- [CONTRIBUTING.md](CONTRIBUTING.md) — How to contribute
- [SECURITY.md](SECURITY.md) — How to report vulnerabilities
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — Community expectations
- [LICENSE](LICENSE) — Proprietary preview terms

## Why AGPL · Contributor policy

Our OSS surface (`templates/stoneford-worldlines/` etc.) is **AGPL-3.0**. Anything you create on top of stoneford — new worlds, templates, modules — enters the same open commons, and no one can quietly fork it into a closed-source product. For contributors:

- 🪪 **You keep your copyright** — no copyright assignment required.
- 🟢 **Default in-bound license = AGPL-3.0** — same as the rest of the OSS surface.
- 🛡 **No silent re-licensing** — maintainers won't merge your code into a closed-source build without asking.

Engine core (`neonrp`) is a proprietary preview — see [CONTRIBUTING.md → License Asymmetry](CONTRIBUTING.md#license-asymmetry).

## Community & Contact

- Web: [worldlines.gg](https://worldlines.gg) · Docs: [docs.worldlines.gg](https://docs.worldlines.gg)
- Discord: [discord.gg/HJYWbdqWrE](https://discord.gg/HJYWbdqWrE) · Patreon: [patreon.com/cw/WorldLines](https://www.patreon.com/cw/WorldLines)
- GitHub: [LudicDynamics/WorldLines](https://github.com/LudicDynamics/WorldLines)
- Contact: `info@worldlines.gg`

---

## Copyright & Acknowledgements

Copyright © 2026 **nikoloside**, **redoctober**. All rights reserved.

WorldLines is a proprietary engine released as preview for evaluation
only. No license is granted for reuse, redistribution, or derivative
works. See [LICENSE](LICENSE) for the full terms.

Developed and maintained by **nikoloside** and **redoctober**,
continuously operated, experimented with, and advanced by the Ludic
Dynamics community. Special thanks to the early participants of the
`llm-rpg-starter` predecessor (the Ludic Dynamics community) for their
generous, heated discussions, exchanges, collaboration, and support:
**Amber**, **琛琛**, **Claire**.

*WorldLines and Ludic Dynamics are trademarks of Ludic Dynamics.*
