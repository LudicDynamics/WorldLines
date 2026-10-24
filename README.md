# WorldLines

**Language:** [English](./README.md) · [简体中文](./README.zh.md) · [日本語](./README.ja.md) · [한국어](./README.ko.md)

> **WorldLines — make you play with your AI character in an infinite world.**
> Open source: the **NeonRP** engine (Apache-2.0), the **WorldLines** product (AGPL-3.0), the documents and the benchmarks (CC BY 4.0).

<p align="center">
  <img alt="GitHub Stars" src="https://img.shields.io/github/stars/LudicDynamics/WorldLines?style=flat-square&color=8b5cf6" />
  <img alt="Forks" src="https://img.shields.io/github/forks/LudicDynamics/WorldLines?style=flat-square&color=8b5cf6" />
  <img alt="Issues" src="https://img.shields.io/github/issues/LudicDynamics/WorldLines?style=flat-square&color=8b5cf6" />
  <a href="https://doi.org/10.1145/3800965.3834285"><img alt="Paper" src="https://img.shields.io/badge/Paper-CHI%20PLAY%20Companion%20%2726-b31b1b?style=flat-square" /></a>
  <a href="https://arxiv.org/abs/2606.16014"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2606.16014-8b5cf6?style=flat-square" /></a>
  <img alt="Engine license" src="https://img.shields.io/badge/neonrp-Apache--2.0-blue?style=flat-square" />
  <img alt="Product license" src="https://img.shields.io/badge/worldlines-AGPL--3.0-blue?style=flat-square" />
</p>

<p align="center">
  <img src="./worldlines/assets/hero.png" alt="WorldLines — The Door to Living Worlds" width="640" />
</p>

## What it is

Most AI role-play gives you a character to chat with. WorldLines gives you **a world the character lives in** — with places,
prices, factions, other characters with their own minds, and rules that hold. You don't just talk; you go somewhere, strike a
deal, pick a fight, and the world answers with consequences that stay.

Under it is **NeonRP**, a world-simulation engine built on one idea: *let the model tell the story, let the world keep its rules.*

- **Talk first, then resolve.** Say what you want to do. In the planning beat the characters present answer and you
  agree on a plan; once a judge says the talk is settled (or you say 「定」 / `@dm`), the resolve beat rolls what needs
  rolling, writes the story and commits one validated change to the world.
- **Three parties.** The world, you and every character keep their own agency. What you say is an *attempt*, not a fact;
  characters decide for themselves.
- **The world is files.** Plain JSON / Markdown you can read, diff and version; every turn is a commit you can roll back
  or branch from.

## Vision

- **Stories from simulation.** NeonRP writes stories out of the friction between a simulated world and character agents
  with their own goals.
- **Orchestration anyone can write.** How a turn runs, from tabletop role-play to murder mystery, is designed in plain
  words and shared as content.
- **Characters, worlds and play kept apart.** A character's assets and settings, a world's, and the rules of play are
  separate pieces that combine freely.
- **A fast engine under any front end.** The AI engine stays fast, robust and open-ended; put a front end on top and it
  becomes a full game client.
- **Open engine, hosted platform.** The engine is open source and runs with your own API key. [worldlines.gg](https://worldlines.gg)
  is the platform for everyone else. The community builds on both.

## What's in this repository

| Folder | What | License |
|---|---|---|
| [`neonrp/`](./neonrp) | The engine: turn loop, schema, packs (`rpg`, `pct`, `werewolf`, `monopoly`, `economy`, `factions` …), templates, CLI, terminal UI, SDK | Apache-2.0 |
| [`worldlines/`](./worldlines) | The product: web UI (3.0), launcher package, templates, example worlds, tutorials; the NeonRP desktop app (macOS) | AGPL-3.0 |
| [`documents/`](./documents) | Specs (world · soul · template · contract · pack) and the source of [docs.worldlines.gg](https://docs.worldlines.gg) | CC BY 4.0 |
| [`benchmarks/`](./benchmarks) | The test suites behind the engine's design decisions | code Apache-2.0 · data CC BY 4.0 |
| `CLAUDE.md` · `AGENTS.md` · `.claude/` · `.agents/` | A card-crafting workbench for Claude Code / Codex (see below) | AGPL-3.0 |

## This repository and the PyPI packages

The PyPI packages are built from the same code and add components that are not open source
([`neonrp/LICENSE-PROPRIETARY.md`](./neonrp/LICENSE-PROPRIETARY.md)):

| | This repository | PyPI `neonrp` / `worldlines` |
|---|---|---|
| Turn | Resolve beat | Planning beat + resolve beat, and the bundled orchestrations |
| Web UI | Workbench, test bench, play page | Also the Hub, the standard player and the phone chat page |
| Bundled worlds | Greyoak House, Stoneford | The same; other official worlds come from worldlines.gg after sign-in |

Everything in this repository runs on its own with your own API key.

## Quick start

```bash
pip install worldlines          # or: uv tool install worldlines — the product, with the neonrp engine
worldlines                      # local web UI → http://127.0.0.1:8787/local
neonrp                          # terminal: the "Welcome to WorldLines" launcher
```

**Desktop app (macOS, Apple silicon):** [download NeonRP](https://worldlines.gg/downloads/NeonRP_aarch64.dmg). Not notarized: on first launch, open System Settings › Privacy & Security and click "Open Anyway". The app installs the engine on first launch.

The local edition installs from here (PyPI packages; this repository is the source). [worldlines.gg](https://worldlines.gg)
is online play, nothing to install. Both commands check for a newer release at launch and update themselves
(`/update mode prompt` inside the game to be asked first). Release notes: [`neonrp/CHANGELOG.md`](./neonrp/CHANGELOG.md) ·
[GitHub Releases](https://github.com/LudicDynamics/WorldLines/releases). The one-line installer still works:
`curl -LsSf https://worldlines.gg/install.sh | sh` (macOS / Linux) · `irm https://worldlines.gg/install.ps1 | iex` (Windows).
Python 3.10 or newer. The first run walks you through choosing a model: sign in with a Worldlines account (`/login`: model
relay and the Jev judge, no key of your own), or bring your own key (OpenCode Zen, DeepSeek, OpenRouter, Anthropic, OpenAI,
GLM, or any OpenAI-compatible server). Keys stay on your machine.

## Play

Pick a world, and the world opens with its own opening scene. Then just say what you want to do:

```text
你:   艾琳娜，陪我去杂货铺买一瓶小治疗药水，价你来砍。
主持: 杂货铺在主街，你们走了十来分钟。艾琳娜在柜台前和老苇讲价，说好谈下来的差价一半归她……
      金 18 → 8 · 两人到杂货铺 · +小治疗药水
```

Each turn has two beats. In the **planning** beat the host sets the scene and the characters present answer; you agree on
what to do. When the talk is settled — a judge decides (Jev with a Worldlines account, otherwise your run's own model), or you
say 「定」 / `@dm` — the **resolve** beat narrates what happens and writes the change into the world. The state is written at
once and checked again in the background; if the check finds a mistake, it is corrected and you are told what changed.

| Template | What it is |
|---|---|
| Greyoak House · The Closed Door | an old house at the end of Fog Lane whose master walked through a door three days ago and never came out; one night, a tight-lipped butler, percentile-dice mystery |
| Stoneford · The Night the Fog Withdraws | the fog draws back one night a year: two nights and a day to gather what you need to leave by the north gate |

The local edition ships these two worlds. The other official worlds are on the Hub: browse them without signing in and play
them online at [worldlines.gg](https://worldlines.gg) (or from "Hub ↗" in the local web UI); sign in with a Worldlines account
to download one and play it locally.

<p align="center">
  <img src="./worldlines/assets/web-multi-agent.png" alt="WorldLines — a living world" width="860" />
</p>

## Create

Clone this repository and open it in **Claude Code** or **Codex**: the workbench (`CLAUDE.md` / `AGENTS.md` and the skills in
`.claude/skills/` · `.agents/skills/`) helps you craft a character, a world, or a full template — and checks it with the engine.

```bash
neonrp template lint  my/<id>.template          # every problem; blocks stop publishing
neonrp template build my/<id>.template /tmp/try
cd /tmp/try && neonrp tui --play
```

Specs: [world](./documents/spec/world.en.md) · [soul](./documents/spec/soul.en.md) · [template](./documents/spec/template.en.md)
· [contract](./documents/spec/contract.en.md) · [pack](./documents/spec/pack.en.md)
· tutorials (zh): [`worldlines/tutorials/`](./worldlines/tutorials).

## Research & citation

The claims behind WorldLines are written up as three papers — define the world, scale it to many agents, and show that a world
holding together is a property of the architecture. Summary: [worldlines.gg/research](https://worldlines.gg/research/).

> **[From Character Role-Play to Orchestrated Reality: LLM-Driven Game World Simulation as a Parameterized-Action POMDP](https://doi.org/10.1145/3800965.3834285)**
> Yuhang Huang, Chenmiao Li, Chaowei Fang. *CHI PLAY Companion '26*, ACM. DOI: 10.1145/3800965.3834285 · [arXiv:2606.16014](https://arxiv.org/abs/2606.16014)

> **Multi-Agent LLM Simulation for Living Game Worlds: Coordinating World, Soul, and Player Agents over a Pub/Sub Message Bus**
> *IPSJ Entertainment Computing 2026* (Kyoto, Sep 2026).

A third, working paper is in preparation.

```bibtex
@inproceedings{huang2026orchestrated,
  title     = {From Character Role-Play to Orchestrated Reality: LLM-Driven
               Game World Simulation as a Parameterized-Action POMDP},
  author    = {Huang, Yuhang and Li, Chenmiao and Fang, Chaowei},
  booktitle = {Companion Proceedings of the Annual Symposium on
               Computer-Human Interaction in Play (CHI PLAY Companion '26)},
  publisher = {Association for Computing Machinery},
  year      = {2026},
  doi       = {10.1145/3800965.3834285},
  url       = {https://doi.org/10.1145/3800965.3834285}
}
```

## Contributing

This repository is the public release of WorldLines; development happens upstream and each release lands here as one commit.
Issues and pull requests are welcome — accepted PRs are merged here first (your authorship stays in this history) and carried
into the next release. See [CONTRIBUTING.md](./CONTRIBUTING.md).

## License

- `neonrp/` — Apache License 2.0 ([`neonrp/LICENSE`](./neonrp/LICENSE), [`neonrp/NOTICE`](./neonrp/NOTICE))
- `worldlines/` and the workbench — GNU AGPL v3.0 ([`worldlines/LICENSE`](./worldlines/LICENSE))
- `documents/`, benchmark data — CC BY 4.0 ([`documents/LICENSE`](./documents/LICENSE))
- setting content in `worldlines/templates/` and `worldlines/examples/` — text CC BY 4.0, images and audio CC BY-NC 4.0
  ([`worldlines/CONTENT-LICENSE.md`](./worldlines/CONTENT-LICENSE.md))

"NeonRP" and "WorldLines" are names of Ludic Dynamics; the licenses do not grant rights to use them.

## Community

- [worldlines.gg](https://worldlines.gg) · [docs.worldlines.gg](https://docs.worldlines.gg) · [Discord](https://discord.gg/HJYWbdqWrE) · `info@worldlines.gg`

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./worldlines/assets/star-history-dark.svg" />
    <img alt="Star History Chart" src="./worldlines/assets/star-history-light.svg" />
  </picture>
</p>

Developed by **nikoloside** & **redoctober**, advanced by [Ludic Dynamics](https://ludicdynamics.com).
