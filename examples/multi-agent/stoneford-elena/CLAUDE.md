# Stoneford-on-the-Shale — Claude Code RPG

这是一个用 Claude Code 运行的文件驱动 RPG。

## 怎么玩

直接在 Claude Code 里输入：`@world-agent 开始游戏`

## 架构

所有游戏数据在 `game/` 目录。所有 agent 在 `.claude/agents/`。

```
@world-agent  — 主控：状态管理 + 路由 + 叙事
  ├─ @town-agent       — 城镇交互
  ├─ @dungeon-agent    — 地下城探索
  ├─ @combat-referee   — d20 战斗
  ├─ @rules-referee    — 骰子判定 + 常识检查
  └─ @world-builder    — 世界地图更新
```

## 规则

- 所有不确定行为用 d20 判定
- HP 归零 = 死。没有自动复活。
- NPC 的好感是永久的。得罪了就是得罪了。
- 每个任务背后都有派系动机。没有"纯粹的好事"。

## 不要做

- 不要在叙事里暴露系统信息（HP 数值、骰子结果除外）
- 不要用感叹号
- 不要让玩家觉得自己是"天选之人"
