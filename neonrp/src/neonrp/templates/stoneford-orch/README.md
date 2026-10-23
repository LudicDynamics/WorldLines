# Stone Ford Town — 石津镇

> 灰雾北境的河港贸易小镇。经典奇幻 TRPG · d20 骰子判定 · 5 Agent 编排

## Quick Start

```bash
cd NeonRP/examples/stone-ford-town
neonrp play .
```

## 来源

从 `llm-rpg-starter` 迁移。原版 10 个 CC agent 精简为 5 个 NeonRP agent。

## Agent 编排（3 层）

```
Layer 1: world-agent        — 状态管理 + 路由 + 叙事 + 故事 + 归档
Layer 2: town-agent          — 城镇全能（导航/NPC/商店/公会/旅店）
         dungeon-agent       — 地下城探索
         combat-referee      — 战斗裁判（d20 骰子）
         world-builder       — 世界地图更新
Layer 3: (未来: dice/rules tool-agent)
```

**路由规则：** 只有 world-agent 有 trigger。所有 domain agent 只能被 world-agent 通过 `task()` 调用。

## 世界内容

- **T001 石津镇** — 起点：公会/杂货/旅店/码头
- **D001 苔墓地穴** — 4 房间 地下城
- **3+ 任务** — 雾中失踪者 / 苔墓前的狼嚎 / 商队护卫
- **战斗规则** — d20 + 属性修正 + 状态效果

## 关键文件

| 文件 | 作用 |
|------|------|
| `game/meta/run_state.json` | 世界状态（位置/时间/上次行动） |
| `game/meta/game-start.json` | 启动引导（开场叙事 + 初始读取列表） |
| `game/player/*.json` | 玩家 7 文件（profile/stats/inventory/equipment/wallet/flags/journal） |
| `game/rules/combat_rules.md` | d20 战斗规则 |
