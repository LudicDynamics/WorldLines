# Kagura Island — Multi-Agent RPG

A lonely island of Japanese-flavored suspense: time loop × amnesia × three factions. A file-driven multi-agent RPG.

## How to Play

> ⚠️ **This world requires the NeonRP engine to run** (the `worldlines` launcher / `neonrp web`).
> The concurrent orchestration of the 7 souls, the on-stage determination (scene-understanding),
> and failure isolation are all handled by the engine runtime — plain Claude Code has no such
> runtime and cannot run the 7-soul orchestration.
> To play multi-agent directly inside Claude Code, use **stoneford-elena** (2 souls,
> with an @-dispatchable character-agent inside).

Once launched inside the engine, play directly; `@world-agent start game` applies only to engine-hosted sessions.

## Architecture

All game data lives in `game/`. All agents live in `.claude/agents/`. The named characters (Kakaru / Hane / Yuto / Tsubasa / Shiro / Kagami / Makoto / Miyaji) are autonomous soul-agents, each under `souls/`.

```
@world-agent  — world sovereign: state + turn-close + final narrative
  ├─ @town-agent       — town/venue navigation and interaction
  ├─ @combat-agent     — crisis/conflict/blood-loss time-limit adjudication (not dungeon combat)
  ├─ @rules-referee    — BRP-style skill/sanity/taboo checks
  ├─ @world-builder    — island map geographic state
  ├─ @npc-builder      — temporary unnamed passerby NPCs
  └─ @story-narrative  — fallback thin description when drifting into unauthored content
```

## Rules

- Uncertain actions go through BRP-style checks (Spot / Listen / Psych / Persuade / Sneak / Knowledge / Sanity), not d20 combat.
- The player is a **human**, not any character. Identity/body/items are in `game/player/`. Never let the player play a named character.
- Once a taboo is violated it is **irreversible** — trust drops, attitude changes the next day, no do-over roll.
- Tsubasa bleeds out within a few hours of Day 1 unless found and given first aid; Yuto attacks the nearest person reflexively when he wakes.
- The GM truth is in `game/lore/gm-truth.md` — readable only by world-agent.

## Don't

- Don't expose system information in the narrative (agent calls, JSON, flag names, the mechanics themselves).
- Don't spoil the loop / blood loss / Yith / Waen — the atmosphere can be "off," but don't spell it out.
- Don't narrate for the player, don't decide for the player; when the player hasn't acted, settle on "awaiting the player's choice."
- Don't pile on adjectives, don't overuse exclamation marks. The spareness of Japanese-flavored suspense rests on restraint.
