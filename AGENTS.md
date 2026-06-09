# WorldLines — 角色卡 / 世界卡创作工作台

用 Codex 创作 WorldLines 角色卡（Character Card）和世界卡（World Card / Lorebook）。

## 项目结构

```
WorldLines/
  templates/stoneford-worldlines/   ← 入门世界模板（游戏数据 + agent 定义）
  cards/                            ← 角色卡 / 世界卡输出目录
  示例/                             ← 参考示例卡片
  .Codex/skills/                   ← 创作 skill
  .Codex/agents/                   ← 游戏运行时 agent（在 stoneford-worldlines 里）
```

## 可用 Skill

创作卡片时，Codex 会自动加载对应 skill：

| Skill | 用途 |
|---|---|
| `character-card-authoring` | 创建 SillyTavern 兼容角色卡 (V2/V3) |
| `world-card-authoring` | 创建世界卡 / lorebook |
| `entity-authoring` | 创建 NeonRP 原生 game/ 实体 |
| `soul-authoring` | 创建 soul 文件夹（角色灵魂包，多 soul → 一世界） |
| `world-game-authoring` | 创建完整 game 世界 |

## 怎么用

直接在 Codex 里说：
- "帮我创建一个角色卡，名字叫 xxx，背景是…"
- "帮我把这个 NeonRP 角色导出成 tavern 角色卡"
- "帮我创建一个世界卡，世界观是…"
- "校验一下 cards/ 下面的卡片格式对不对"

## 架构背景

WorldLines 是多 agent 框架：一个 Orchestrator 调度多个子 agent（town-agent、dungeon-agent、combat-referee、npc-mind 等），多个 soul 对应一个 world。

- game-time agent 在 `templates/stoneford-worldlines/.Codex/agents/`
- 创作 skill 在 `.Codex/skills/`

## 语言

角色卡和世界卡的内容用目标语言写（中文 / 日文 / 英文等），不要翻译。ID、字段名保持 ASCII。
