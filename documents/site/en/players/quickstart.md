---
title: "Player quickstart"
description: "Install WorldLines and enter your first world in the browser."
---

<!-- section: install -->
## 1. Install

> **Status: ships with 1.0**

**Desktop app (recommended)** — the first launch installs the engine, then opens the local web product.

| Platform | File |
|---|---|
| macOS (Apple Silicon) | [WorldLines-Installer.dmg](https://github.com/LudicDynamics/WorldLines/releases/latest/download/WorldLines-Installer.dmg) |
| Windows | [WorldLines-Desktop-windows-x64-setup.exe](https://github.com/LudicDynamics/WorldLines/releases/latest/download/WorldLines-Desktop-windows-x64-setup.exe) |

macOS: right-click the installer → Open → Open. Windows: SmartScreen → More info → Run anyway.

**Or from a terminal** (use this on Linux):

```bash
pip install worldlines        # or: uv tool install worldlines (any OS)
# one-line installer — macOS / Linux
curl -LsSf https://worldlines.gg/install.sh | sh
# Windows (PowerShell)
irm https://worldlines.gg/install.ps1 | iex
```

<!-- section: open -->
## 2. Open it

```bash
worldlines        # opens http://127.0.0.1:8787/local in your browser
```

The first run walks you through choosing a model provider — see [Model providers](/docs/players/providers). Your worlds and saves live in `~/.worldlines`.

<!-- section: hub -->
## Don't want to install?

Open [hub.worldlines.gg](https://hub.worldlines.gg), sign in, and play in the browser.

<!-- section: next -->
## Next

[Your first world: Stoneford](/docs/players/first-world) → [How to play](/docs/players/how-to-play)
