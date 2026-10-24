---
title: "Start playing"
description: "Three ways in: online, the local web UI, or the terminal. Pick one and be in your first world in a few minutes."
---

<!-- section: paths -->
## Three ways in

| How | What to install | Where |
|---|---|---|
| **Online** | nothing | [worldlines.gg](https://worldlines.gg), or the iOS app |
| **Local web UI** | `worldlines` | http://127.0.0.1:8787/local in your browser |
| **Terminal** | `worldlines` or `neonrp` | type `neonrp` in a terminal |

The local web UI and the terminal read and write the same worlds, saves and settings, so you can switch between them at any time.

<!-- section: online -->
## Play online

Open [worldlines.gg](https://worldlines.gg), pick a world on the Hub and play it in your browser; on a phone, use the iOS app. Nothing to install, and no model of your own needed.

<!-- section: install -->
## Install locally

You need Python 3.10 or newer.

```bash
pip install worldlines        # or: uv tool install worldlines / pipx install worldlines
```

Installing `worldlines` also installs the `neonrp` engine, so you get both commands. Terminal only: `pip install neonrp`.

The source and release notes are in the GitHub repository [LudicDynamics/WorldLines](https://github.com/LudicDynamics/WorldLines). The one-line installer still works (it installs uv if you don't have it):

```bash
curl -LsSf https://worldlines.gg/install.sh | sh      # macOS / Linux
irm https://worldlines.gg/install.ps1 | iex           # Windows PowerShell
```

<!-- section: open -->
## Open it

```bash
worldlines        # local web UI: opens http://127.0.0.1:8787/local in your browser
neonrp            # terminal: the "Welcome to WorldLines" launcher
```

- **Web**: on the overview, click a world and start a new run. Your saved runs of that world are listed in the same panel, ready to continue.
- **Terminal**: in the launcher choose "start new run" (`n`) and pick a world; "⚡ Resume" (`r`) jumps straight into your latest run. The very first run asks for your interface language.

The first run also asks you to choose a model — see [Connect a model](/docs/players/providers). A new run opens its own scene; you don't need to type anything first.

<!-- section: update -->
## Automatic updates

If you installed with pip, uv tool or pipx, both `worldlines` and `neonrp` check for a new version at launch; when there is one, they update themselves and restart into it. To change that, type inside the terminal game:

| Command | Effect |
|---|---|
| `/update mode prompt` | ask you first |
| `/update mode notify` | only tell you, don't update |
| `/update mode auto` | update by themselves (default) |
| `/update status` | show the current version and update settings |

A source install (`pip install -e`) only tells you; it never updates itself.

<!-- section: data -->
## Where your data lives

| Location | What |
|---|---|
| `~/.worldlines/plays/` | every run you have played |
| `~/.worldlines/templates/` | your own templates (copied to edit, or new) |
| `~/.worldlines/souls/` | your character library |
| `~/.worldlines/official/` | official worlds downloaded after signing in |
| `~/.neonrp/config.json` | models, keys, language, update mode |

To back up, copy `~/.worldlines` together with `~/.neonrp/config.json`.

<!-- section: next -->
## Next

[Connect a model](/docs/players/providers) → [Your first run](/docs/players/first-world) → [How a turn works](/docs/players/how-to-play)
