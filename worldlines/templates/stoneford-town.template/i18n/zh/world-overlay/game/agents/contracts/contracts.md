# 子代理契约（读写边界）

石津镇·艾琳娜在真实的石津镇契约之上，加入了显式的 souls。
`game/player/*` 仍是女主角的兼容投影，而不是唯一的角色真实来源。

每个子代理必须：
- 只读取允许的文件 glob
- 只写入允许的文件 glob
- 以“补丁计划（patch plan）”的形式输出变更，说明要创建/更新哪些文件以及原因

## Orchestrator（主控）
READ: game/**（全部），但只能通过补丁计划或 world-agent 的直接更新来写
WRITE: game/run_state.json, lore/notes.md（可选）, lore/story.md（可选）

Soul 运行时说明：
- 在场的 souls 声明在 `playthrough.json` 中
- world-agent 接收 soul 的输出，但不直接读取 `souls/**`
- `game/player/*` 是艾琳娜状态的本地投影，供旧版石津镇流程使用

## World Builder（世界构建）
READ: world/world_map.json, lore/story.md, lore/notes.md
WRITE: world/world_map.json, world/regions.json（可选）, world/factions.json（可选）

## Story / Narrative（故事叙述）
READ: lore/story.md, lore/notes.md, world/world_map.json, player/flags.json
WRITE: lore/story.md, lore/rumors.md（可选）

## Town Agent（城镇代理，每镇一个）
READ: towns/<town>/**, player/**, lore/notes.md
WRITE: towns/<town>/town.json, towns/<town>/town_map.json, towns/<town>/npcs.json, towns/<town>/quests.json

## Facility Agents（设施代理：公会/商店/旅店）
READ: towns/<town>/facilities/*.json, towns/<town>/quests.json, player/**
WRITE: towns/<town>/facilities/*.json, towns/<town>/quests.json, player/inventory.json, player/wallet.json, player/flags.json, player/stats.json（旅店休息）

## Dungeon Agent（地下城代理，每个地下城一个）
READ: dungeons/<dungeon>/**, player/**, rules/combat_rules.md
WRITE: dungeons/<dungeon>/**（状态）, world/world_map.json（发现/清除标记）, player/flags.json

## Combat Referee（战斗裁判）
READ: rules/combat_rules.md, player/stats.json, player/equipment.json, player/inventory.json
WRITE: player/stats.json, player/inventory.json, player/wallet.json（战利品）, lore/notes.md
