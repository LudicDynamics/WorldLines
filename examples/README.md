# Example Worlds

The playable worlds that ship with WorldLines. Each is a complete,
self-contained game world, open-source (AGPL-3.0) — fork, mod, and ship
your own. They run with the local **CLI / TUI**
(`neonrp tui --from examples/<world>`), with **Claude Code / MCP**, and
most have online demos on the [WebHub](https://hub.worldlines.gg).

## Engine modes — these are distinct, not interchangeable

WorldLines runs a world in one of **three engine modes**. A world is
authored for a specific mode; `fast`, `orch`, and `multi-agent` do **not**
share the same structure.

| Mode | What it is | Structure |
|---|---|---|
| **fast** | one quick agent — minimal latency, single voice | world-agent only |
| **orch** | a world-agent **orchestrating domain agents** (town / dungeon / combat / story…). NPCs are data the orchestrator voices. | `agents/` + `game/` |
| **multi-agent** | a world-agent **wrapping independent souls** — each a character-agent with its own mind, memory, and agenda. The society. | `agents/` + `game/` + **`souls/`** + `playthrough.json` |

The tell-tale sign of a multi-agent world is a **`souls/` folder**: each
soul thinks for itself. `multi-agent` runs locally (TUI / CLI); hosted
play offers `fast` + `orch`.

## Worlds

### 🌐 orch & single-world

| World | Play style | Mode | Online |
|---|---|---|---|
| [Stoneford](./orch/stoneford) | Flagship siege TRPG — 10-agent orchestrated village | **orch** | [Play →](https://hub.worldlines.gg/play/worlds/stoneford) |
| [Dark Train](./orch/dark-train) | Open world — do anything, the world remembers | orch | [Play →](https://hub.worldlines.gg/play/worlds/dark-train) |
| [Goblin Ambush](./orch/goblin-ambush) | 3-layer dungeon — fight 3 boss goblins | fast / orch | — |
| [Worldline](./orch/worldline) | Time-drift — text the past, watch timelines rewrite | orch | — |
| [Sakura Hallway](./orch/sakura-hallway) | A school love story · emotional narrative | orch | — |
| [Lamp of Souls](./orch/otome-lamp) | 国风乙女 court romance · 4 princes, a soul-lamp, 8 endings | orch | — |

### 👥 multi-agent — independent souls in one world

> Multi-agent runs **locally** (TUI / CLI) — not on hosted play yet. `neonrp tui --from examples/<world>`.

| World | Souls | Mode | Run |
|---|---|---|---|
| [Kagura Island](./multi-agent/kagura-island) | **7** — Kagami, Hane, Makoto, Miyaji, Shiro, Tsubasa, Yuto | **multi-agent** | [Source →](./multi-agent/kagura-island) |
| [Stoneford · Elena](./multi-agent/stoneford-elena) | **2** — Elena, Rowan | **multi-agent** | [Source →](./multi-agent/stoneford-elena) · [Elena soul (hosted)](https://hub.worldlines.gg/play/souls/elena) |

Each world has four language READMEs: **en** · **zh** (中文) · **ja** (日本語) · **ko** (한국어).

## How to play

### Local (CLI)

```bash
# Install WorldLines
curl -LsSf https://worldlines.gg/install.sh | sh

# orch world
neonrp tui --from examples/orch/stoneford

# multi-agent world (souls/ engages the soul wrapper)
neonrp tui --from examples/multi-agent/kagura-island
neonrp tui --from examples/multi-agent/stoneford-elena
```

### Local (Claude Code / MCP)

Open Claude Code inside the world directory and start playing:

```
@world-agent 开始游戏
```

### Online (WebHub)

No install. Go to [hub.worldlines.gg](https://hub.worldlines.gg), sign in,
and play in the browser. (Hosted play offers `fast` + `orch`; run
`multi-agent` locally.)

## Want more worlds?

Browse the [WorldHub catalog](https://hub.worldlines.gg/worlds) — download
and play worlds the community has published.

## License

All example worlds are **AGPL-3.0**. Fork, modify, and publish your own.
The WorldLines engine (`neonrp`) that runs them is a proprietary preview.
