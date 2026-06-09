# Example Worlds

Four playable worlds that ship with WorldLines. Each is a complete,
self-contained game world showing a different kind of play. All four are
open-source (AGPL-3.0) — fork, mod, and ship your own.

They work with the local **CLI / TUI** (`neonrp play examples/<world>/zh`)
or with **Claude Code / MCP**. Most also have online demos on the
[WebHub](https://hub.worldlines.gg).

| World | Play style | Agents | Online |
|---|---|---|---|
| [Dark Train](./dark-train) | Open world — do anything, the world remembers | World-agent + sub-agents | [Play →](https://hub.worldlines.gg/play/worlds/dark-train) |
| [Stoneford](./stoneford) | Siege — give orders, pay the cost | World-agent + NPC agents | [Play →](https://hub.worldlines.gg/play/worlds/stoneford) |
| [Goblin Ambush](./goblin-ambush) | D&D 5e combat — one encounter, three adventurers | World-agent (DM) + Referee (dice) | — |
| [Worldline](./worldline) | Time-drift — text the past, watch timelines rewrite | World-agent + Worldline-agent + Drift-agent | — |

Each world has four language variants: **zh** (中文) · **en** (English) ·
**ja** (日本語) · **ko** (한국어).

## How to play

### Local (CLI)

```bash
# Install WorldLines
pip install worldlines

# Play any world
neonrp play examples/dark-train/zh
neonrp play examples/stoneford/zh
neonrp play examples/goblin-ambush/zh
neonrp play examples/worldline/zh
```

### Local (Claude Code / MCP)

Open Claude Code inside the world directory and start playing:

```
@world-agent 开始游戏
```

### Online (WebHub)

No install. Go to [hub.worldlines.gg](https://hub.worldlines.gg), sign in,
and play directly in the browser.

## Want more worlds?

Check the [WorldHub catalog](https://hub.worldlines.gg/worlds) — browse,
download, and play worlds the community has published.

## License

All example worlds are **AGPL-3.0**. Fork, modify, and publish your own.
The WorldLines engine (`neonrp`) that runs them is a proprietary preview.
