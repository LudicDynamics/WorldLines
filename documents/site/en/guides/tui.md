---
title: "TUI terminal guide"
description: "Play and manage from the terminal: the worldlines launcher, slash commands, settings and data locations."
---

<!-- section: entries -->
## Two entry points

After installing (`pip install worldlines`, or `uv tool install worldlines`, or the one-line `curl -LsSf https://worldlines.gg/install.sh | sh`) you get two commands; both check for a newer release at launch and update themselves:

- **`worldlines`** — the local web UI at http://127.0.0.1:8787/local: worlds, saves, the creation desk, settings.
- **`neonrp`** — the terminal: the 「Welcome to WorldLines」 launcher picks a world or a save and drops you into the game; slash commands inside (`/status` · `/plan` · `/update` …). First run asks for your UI language.

> Prefer a browser? `neonrp web` serves the LocalShell at http://127.0.0.1:8787/local — same data as the TUI, switch anytime.

<!-- section: first-run -->
## Your first run

The `worldlines` main menu is a 2×2 grid: **Play** (continue/new), **World library** (new/import/Hub download/upload/manage), **Character library** (Soul Talk/new/import/Hub/manage), plus a bottom bar (settings/quit). Hotkeys: `c` continue, `n` new, `s` settings.

A new run chains: **pick world → pick avatar + cast companions → pick model preset (guided key setup on first use) → pick surface (🌟 browser / terminal)**. Choose terminal and the world opens itself — just start playing.

<!-- section: slash -->
## Slash commands in play

Type `/` for completion and suggestions. The usual suspects:

- `/save [name]` · `/load` · `/undo` · `/redo` — named saves and checkpoint-level undo/redo
- `/cast <soul> [npc|player]` — project a library character into this run
- `/mode [build|play]` — switch creation/play (build lets the agent edit world files freely)
- `/models` · `/auth` · `/config` · `/locale` — models, keys, language
- `/export-world` · `/load-world <zip>` — pack/restore a world
- `/settings` — full settings; `/help` — everything

Global keys: `Ctrl+K` command palette, `Ctrl+L` info layers, `F6` copy transcript.

Bare REPL: `neonrp play` (input = action; `/trace` shows last turn's routing, `/debug` recent agent calls).

<!-- section: settings-data -->
## Settings & where data lives

Settings (launcher → Settings, or `/settings`): model entries (test/replace key/delete), creation LLM (a separate model for authoring), image generation (ComfyUI URL/ckpt/custom workflow nodes, or OpenAI), language, Discord bridge.

Data lives in:

- `~/.worldlines/worlds/` world sources · `plays/` one dir per run · `souls/` character library
- `~/.neonrp/config.json` model keys / image backend / language (shared by TUI and Web)

Backup = archive `~/.worldlines`; delete a save = remove its dir under `plays/`.
