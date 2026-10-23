# Example Worlds

The playable worlds that ship with WorldLines. Each is a complete,
self-contained game world, open-source (AGPL-3.0) — fork, mod, and ship
your own. They run with the local **CLI / TUI**
(`neonrp tui --from worldlines/examples/worlds/<world>`), with **Claude Code / MCP**, and
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

> Runs **locally** (TUI / CLI). `neonrp template build templates/<id>.template /tmp/<id> && neonrp web --project /tmp/<id>` plays best in the browser, where you watch every soul live.

| World | Souls | Run |
|---|---|---|
| [Greyoak House · The Closed Door](../templates/pct-house.template) | **2** — Winnie, Oswin Hale (the butler) | [Source →](../templates/pct-house.template) |
| [Stoneford · The Night the Fog Withdraws](../templates/stoneford-town.template) | **2** — Elena, Rowan | [Source →](../templates/stoneford-town.template) |

The local edition ships these two; the other official worlds come down after you sign in on the local Hub.

### 🌐 Also: lighter `orch` / `fast` worlds

A world-agent voicing data-driven NPCs — no per-soul agents. Good for tighter, single-thread scenes.

| World | Play style | Mode | Online |
|---|---|---|---|
| [Stoneford](./worlds/stoneford) | Siege TRPG — a world-agent routing to town / dungeon / combat / story | **orch** | [Play →](https://hub.worldlines.gg/play/worlds/stoneford) |
| [Goblin Ambush](./worlds/goblin-ambush) | 3-layer dungeon — fight 3 boss goblins | fast / orch | — |
| [Worldline](./worlds/worldline) | Time-drift — text the past, watch timelines rewrite | orch | — |
| [Sakura Hallway](./worlds/sakura-hallway) | A school love story · emotional narrative | orch | — |
| [Lamp of Souls](./worlds/otome-lamp) | 国风乙女 court romance · 4 princes, a soul-lamp, 8 endings | orch | — |

Each world has four language READMEs: **en** · **zh** (中文) · **ja** (日本語) · **ko** (한국어).

## How to play

### Local (CLI)

```bash
# Install WorldLines
curl -LsSf https://worldlines.gg/install.sh | sh

# orchestrator world
neonrp tui --from worldlines/examples/worlds/stoneford

# multi-agent world (souls/ engages the soul wrapper): the two built-in templates
neonrp template build templates/pct-house.template /tmp/pct-house && neonrp tui --from /tmp/pct-house
neonrp template build templates/stoneford-town.template /tmp/stoneford-town && neonrp tui --from /tmp/stoneford-town
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
