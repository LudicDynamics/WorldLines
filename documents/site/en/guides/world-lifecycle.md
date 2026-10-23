---
title: "World — New · Import · Export"
description: "Create, import, and export game worlds."
---

<!-- section: new -->
## Creating a new world

**In the Launcher (recommended).** Open WorldLines and pick **New world** — choose a built-in template (Stoneford · Stoneford · Elena · Kagura Island · …), and it scaffolds and opens, ready to play and edit. Nothing to memorize.

**Author with an AI agent.** WorldLines ships **Claude Code** and **Codex** authoring skills. Open the repo in your AI coding agent and just describe what you want — *"a 国风 otome world with four princes"* — and the skill scaffolds the `game/` entities + agents for you. See the [authoring tutorials](https://github.com/LudicDynamics/WorldLines/tree/main/tutorials) (character card · world card · full world · soul).

**Advanced — CLI.** Scaffold from a template in the terminal:

```bash
neonrp game new --template stoneford-orch    # flagship siege TRPG (10-agent)
neonrp game new --template stoneford-elena   # Stoneford + Elena — multi-agent village
neonrp game new --template kagura-island     # mystery · 7 souls
neonrp game new --template default           # minimal starter
```

Or start from an empty project and hand-author `game/` directly (see [Creating Your First World](/docs/guides/creating-first-world)).

<!-- section: home-dir -->
## Where worlds live — `~/.worldlines/games/`

When you import or scaffold from the launcher, the resulting world lands under `~/.worldlines/games/<name>/`. That directory is the home for every world on your machine — each contains its own `game/` tree and `.neonrp/` state.

The current project you're playing is an instance of one of these folders (you can also work in an ad-hoc path via `cd` + `worldlines init`; that still works, but `~/.worldlines/games/` is the convention).

<!-- section: export -->
## Exporting a world

Use the built-in TUI command (or the shell alias):

```
/export-world                    # inside TUI → writes ~/Downloads/worldlines-<name>-<ts>.zip
/export-world my-world.zip       # specify output path
```

Shell equivalent:

```bash
neonrp export-world                        # default dest ~/Downloads/
neonrp export-world --output ~/my-world.zip
```

The archive contains the `game/` folder plus the `.neonrp/` state (events, snapshots, manifest) so the recipient can resume exactly where you left off.

📸 **Screenshots coming** — one-click export from the launcher UI is planned for v0.1.6.

<!-- section: import -->
## Importing a world

From inside the TUI or the shell:

```
/load-world ~/Downloads/worldlines-myworld-2026-04-23.zip
```

```bash
neonrp load-world ~/Downloads/worldlines-myworld-2026-04-23.zip
```

This extracts the archive under `~/.worldlines/games/<name>/` so it shows up alongside your other worlds. Then switch to it via `/worlds` (TUI) or `cd ~/.worldlines/games/<name>` before running the launcher.

📸 **Screenshots coming** — drag-and-drop import flow in the launcher.

<!-- section: browse -->
## Browsing local worlds

Inside the TUI:

```
/worlds                         # browse worlds in ~/.worldlines/games/ and scaffold from templates
/worldlines                     # guided world picker (model preset + world + launch)
```

Or manually:

```bash
ls ~/.worldlines/games/
```
