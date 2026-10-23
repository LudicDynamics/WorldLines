# Stoneford-on-the-Shale — Claude Code RPG

This is a file-driven RPG run with Claude Code.

## How to Play

Just type into Claude Code: `@world-agent start the game`

## Architecture

All game data is in the `game/` directory. All agents are in `.claude/agents/`.

```
@world-agent  — master controller: state management + routing + narration
  ├─ @town-agent       — town interaction
  ├─ @dungeon-agent    — dungeon exploration
  ├─ @combat-referee   — d20 combat
  ├─ @rules-referee    — dice checks + common-sense checks
  └─ @world-builder    — world map updates
```

## Rules

- All uncertain actions use a d20 check
- HP to zero = death. No automatic revival.
- NPC goodwill is permanent. Wrong someone and you've wronged them.
- Every quest has a faction motive behind it. There is no "purely good deed."

## Don't

- Don't expose system information in the narration (except HP values, dice results)
- Don't use exclamation marks
- Don't let the player feel like a "chosen one"

> 上下文语言(词条包 · 输出格式 · <> [] 标签 · 条目):见 `CONTEXT.md`(引擎生成)。
