---
title: "Quickstart"
description: "From download to your first living world — Launcher, browser, or CLI."
---

<!-- section: launcher -->
## 1. Run locally — Web UI (recommended)

The fastest way in. Download WorldLines and run it — it **opens a local Web UI in your browser by default**, no terminal setup needed.

From [worldlines.gg](https://worldlines.gg) → **Download**, grab the installer for your OS:

- **macOS**: `WorldLines.command`
- **Windows**: `WorldLines.bat`
- **Linux**: `WorldLines.sh` (`chmod +x` then run)

It's self-contained — it bootstraps Python if needed and opens the local Web UI. Three official worlds are right there to **import and play**:

- **Spice & Witch** — a spice caravan × an ageless witch × a witch-hunt
- **Kagura Island** (7 souls) — Japanese-style mystery · time loop
- **Stoneford · Elena** — amnesiac heroine + companion (Elena & Rowan)

All three are **multi-agent villages** — a world-agent wrapping a society of independent souls. Continue a saved session, or create your own. The first run walks you through picking an LLM provider (step 5) — you never edit `config.json` by hand.

<!-- section: tui -->
## 2. WorldLines TUI (terminal)

Prefer the terminal? The same engine ships the **WorldLines TUI** — a Claude Code-style conversational terminal, for both playing and building.

```bash
pip install worldlines        # or: uv tool install worldlines
neonrp           # the terminal launcher: pick a world, then play
```

Also runs locally, and plays the full multi-agent villages. Scriptable/advanced usage is in step 6.

<!-- section: webhub -->
## 3. Hub — browser, zero install

Don't want to install anything? Go to [hub.worldlines.gg](https://hub.worldlines.gg), sign in, and play. The cloud agents run for you — no setup needed.

- Browse the catalog of **worlds** and **souls**
- Talk to a soul like [Elena](https://hub.worldlines.gg/play/souls/elena), or try a lighter orchestrator world
- Create your own with the AI-assisted studio and publish to the public registry

Hub currently runs **fast** and **orchestrator** worlds. The full **multi-agent villages** (the three official worlds above) run locally — via the Web UI or TUI.

<!-- section: worlds -->
## 4. The official worlds

The three official worlds are all **multi-agent villages** — a world-agent wrapping a society of independent souls. Play each one by importing in the **Web UI**, running it in the **TUI**, or from the **CLI** (step 6).

| World | What it is | Mode |
|---|---|---|
| **Spice & Witch** | A spice caravan × an ageless witch × a witch-hunt | multi-agent |
| **Kagura Island** | Japanese-style mystery · time loop · **7 independent souls** | multi-agent |
| **Stoneford · Elena** | Amnesiac heroine + companion · **Elena & Rowan** | multi-agent |

The multi-agent villages run **locally** (Web UI or TUI). For a zero-install taste in the browser, play a lighter orchestrator world or talk to a soul on [Hub](https://hub.worldlines.gg).

<!-- section: configure-provider -->
## 5. Pick an LLM provider

WorldLines runs on top of an LLM, and there are **three ways** to wire one up. The launcher walks you through whichever you pick — you don't have to edit `config.json` by hand.

### Option 1: Claude Code (MCP) — zero API key

If you already have [Claude Code](https://claude.com/claude-code) installed, WorldLines can drive it over MCP. No separate API key, no separate billing. Pick **"Claude Code"** when the launcher asks for a provider — done.

### Option 2: a third-party provider with an API key

On first run, the launcher prompts you to pick one and paste the key. It lands in `~/.neonrp/config.json` automatically and is reused on every subsequent run.

| Provider         | Where to get a key                                                                     | Notes                    |
|------------------|----------------------------------------------------------------------------------------|--------------------------|
| **GLM-4-Flash**  | [zhipuai.cn](https://zhipuai.cn)                                                        | **free tier available**  |
| Anthropic        | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys)     | pay-as-you-go            |
| OpenAI           | [platform.openai.com/api-keys](https://platform.openai.com/api-keys)                   | pay-as-you-go            |
| DeepSeek         | [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys)               | pay-as-you-go            |
| OpenRouter       | [openrouter.ai/keys](https://openrouter.ai/keys)                                        | aggregator — one key, many models |

### Option 3: OpenAI-compatible custom endpoint

If you run a local model server (**Ollama**, **LM Studio**, **vLLM**, etc.) or have your own OpenAI-compatible backend, point WorldLines at its URL. No cloud API key needed. Pick **"Custom"** in the settings flow and fill in `base_url` + optional auth.

---

**Where keys live:** `~/.neonrp/config.json`, plus environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GLM_API_KEY`, …) if you set them. The launcher reads env first, then the config file.

**Change your mind later:** pick `[3] settings / api` on the launcher menu to add models, switch defaults, or test connections.

<!-- section: advanced-cli -->
## 6. Advanced — CLI (developers / researchers)

Prefer the terminal, or want a scriptable harness for experiments? The same engine ships the `worldlines` CLI.

```bash
pip install worldlines        # or: uv tool install worldlines
# or the one-line installer (macOS / Linux / WSL):
curl -fsSL https://worldlines.gg/install.sh | sh
```

Open the TUI, or run an example world straight from the repo:

```bash
neonrp           # the terminal launcher: pick a world, then play

git clone https://github.com/LudicDynamics/WorldLines.git && cd WorldLines

# the two built-in worlds (sign in on the local Hub for the other official worlds):
neonrp template build worldlines/templates/pct-house.template /tmp/pct-house && neonrp play --project /tmp/pct-house   # Greyoak House
neonrp template build worldlines/templates/stoneford-town.template /tmp/stoneford-town && neonrp play --project /tmp/stoneford-town   # Stoneford

# orchestrator worlds too (these also play on Hub):
neonrp tui --from examples/orch/stoneford
```

**Take a turn:** type `look around`. The world-agent narrates and routes to the right sub-agent — or, in a multi-agent world, wakes the souls in the scene. You'll see a thinking stream, tool-use as it reads files, the narrative, and a new **event** appended to the log.

**Save · branch · rewind:** `/save opening-scene` checkpoints; `/branch try-stealing` explores a risky path on a new branch; `/undo` rewinds; `neonrp load opening-scene` restores. The main branch stays untouched.

Needs Python 3.11+ (3.12 recommended) and a 256-color UTF-8 terminal.

<!-- section: what-next -->
## What next?

- [Core Concepts](/docs/core-concepts/worlds) — how a world remembers: events, snapshots, branches
- **Import & play** the official worlds in the Web UI, then tweak them in the Create studio
- **[Play on WebHub](https://hub.worldlines.gg)** — including a multi-agent soul like [Elena](https://hub.worldlines.gg/play/souls/elena)
- Advanced (CLI): [CLI Reference](/docs/guides/world-editor) — `/mode build`, edit JSON directly, all subcommands
