# ⛩ Stoneford — WorldLines Flagship World

**Language:** [English](./README.md) · [简体中文](./README.zh.md) · [日本語](./README.ja.md) · [한국어](./README.ko.md)

![Stoneford](./assets/s1bg.png)

> A grey-fog northern river port. Classic-fantasy TRPG · d20 dice · **10-agent multi-agent village**.

Stoneford is the flagship example that ships with [WorldLines](https://github.com/LudicDynamics/WorldLines) — a complete, playable town with NPCs, quests, a dungeon, and siege mechanics, orchestrated by a multi-agent society.

**[▶ Play online (no install) →](https://hub.worldlines.gg/play/worlds/stoneford)**

## How to play

```bash
# Local TUI
neonrp tui --from examples/orch/stoneford

# Claude Code / MCP — open Claude Code inside this directory
@world-agent 开始游戏
```

## The village — a multi-agent society

Stoneford is a **living village**: a `world-agent` at the centre orchestrates a society of domain agents, each owning part of the world. Only the world-agent has a trigger; every other agent is dispatched by it via `task()`, each with its own isolated context.

```
world-agent (Orchestrator)        — reads state · routes · merges patches · narrates · archives
├── rpg-world-builder             — world map, regions, factions
├── rpg-story-narrative           — main story + rumours
├── rpg-town-agent                — town navigation, NPCs, shops, guild, inn
├── rpg-dungeon-agent             — dungeon exploration
├── rpg-combat-referee            — d20 combat resolution
├── rpg-rules-referee             — rule lookups & checks
├── rpg-clock-keeper              — time, schedules, world clock
├── rpg-world-evolution           — long-term world change
└── rpg-character-agent           — NPC minds: intent, memory, dialogue
```

This is the **village structure** in practice: the world remembers, NPCs have their own minds, and every turn is an orchestrated society of agents rather than a single prompt.

## What's inside

- **T001 Stoneford** — the starting town: guild, general store, inn, docks
- **T004** — a second settlement: chapel, appraiser, herb shop, tavern
- **D001 Moss Tomb** — a 4-room dungeon
- **Quests** — the missing in the mist · the howl before the moss tomb · caravan escort
- **Combat** — d20 + ability modifiers + status effects

<p align="center">
  <img src="./assets/gameplay.jpg" alt="Stoneford gameplay — arriving in the mist" width="640" />
</p>

## Key files

| File | Role |
|------|------|
| `game/agents/manifest.json` | the 10-agent manifest (ids, roles, read/write scopes) |
| `game/meta/run_state.json` | world state (location, time, last action) |
| `game/meta/game-start.json` | opening narration + initial read list |
| `game/towns/*/` | town data: NPCs, quests, facilities, maps |
| `game/dungeons/D001/` | dungeon layout, rooms, encounter & loot tables |
| `game/rules/combat_rules.md` | d20 combat rules |
| `agents/*/` · `.claude/agents/*` | agent definitions (TUI + Claude Code mirrors) |

## License

Stoneford is **AGPL-3.0**. Fork it, mod it, ship your own world. The WorldLines engine (`neonrp`) that runs it is a proprietary preview.

> *Stoneford is an original scenario co-authored by **nikoloside**, **redoctober**, and Claude, blending Eastern worldbuilding with Western medieval magic.*
