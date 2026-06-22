# Example Worlds

The playable worlds that ship with WorldLines. Each is a complete,
self-contained game world, open-source (AGPL-3.0) — fork, mod, and ship
your own. They run with the local **CLI / TUI**
(`neonrp tui --from examples/<world>`), with **Claude Code / MCP**, and
most have online demos on the [WebHub](https://hub.worldlines.gg).

## A multi-agent simulation

WorldLines is a **multi-agent simulation**: a world-agent wrapping a cast of
**independent souls** — each a character-agent with its own mind, memory,
secrets, and agenda. The tell-tale sign is a **`souls/` folder**: each soul
thinks for itself. This is the engine, and where every world is heading.

Lighter modes exist for simpler, single-thread scenes — `orch` orchestrates
domain agents over data-driven NPCs (`agents/` + `game/`), `fast` is a single
world-agent — but the heart of WorldLines is the multi-agent society.
`multi-agent` runs locally (TUI / CLI); hosted play currently offers `fast` + `orch`.

## Worlds

### 👥 The multi-agent society — independent souls in one world

> Runs **locally** (TUI / CLI). `neonrp web --project examples/multi-agent/<world>` plays best in the browser, where you watch every soul live.

| World | Souls | Run |
|---|---|---|
| [Kagura Island](./multi-agent/kagura-island) | **7** — Kagami, Hane, Makoto, Miyaji, Shiro, Tsubasa, Yuto | [Source →](./multi-agent/kagura-island) |
| [Stoneford · Elena](./multi-agent/stoneford-elena) | **2** — Elena, Rowan | [Source →](./multi-agent/stoneford-elena) · [Elena soul (hosted)](https://hub.worldlines.gg/play/souls/elena) |

### 🌐 Also: lighter `orch` / `fast` worlds

A world-agent voicing data-driven NPCs — no per-soul agents. Good for tighter, single-thread scenes.

| World | Play style | Mode | Online |
|---|---|---|---|
| [Stoneford](./orch/stoneford) | Siege TRPG — a world-agent routing to town / dungeon / combat / story | **orch** | [Play →](https://hub.worldlines.gg/play/worlds/stoneford) |
| [Goblin Ambush](./orch/goblin-ambush) | 3-layer dungeon — fight 3 boss goblins | fast / orch | — |
| [Worldline](./orch/worldline) | Time-drift — text the past, watch timelines rewrite | orch | — |
| [Sakura Hallway](./orch/sakura-hallway) | A school love story · emotional narrative | orch | — |
| [Lamp of Souls](./orch/otome-lamp) | 国风乙女 court romance · 4 princes, a soul-lamp, 8 endings | orch | — |

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
