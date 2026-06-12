# 哥布林遭遇战 · Goblin Ambush

一个**最小单场景** WorldLines 示例:D&D 5e 战斗。你指挥三名冒险者
(战士 / 游荡者 / 法师)对一只哥布林,掷先攻、d20 命中、骰伤害,把它放倒。

一进场就有一段简短规则说明,然后直接开打。

## 看点(它在展示什么)
- **两 agent 编排**:`world-agent`(DM,叙述+管回合+替哥布林行动)+ `referee`
  (只做 d20 数学,温度 0.2,返回结构化判定)。
- **完整 5e 回合**:先攻顺序 → 逐人行动 → 攻击检定 vs AC → 伤害 → HP 归零。
- **一回合一停**:每次只推进到需要玩家决定的点,绝不自己把整场打完。

## 多语言
本世界提供四个完整语言版,各自可独立游玩 / 上传 hub:

| 语言 | 目录 |
|---|---|
| 中文 | `zh/` |
| English | `en/` |
| 日本語 | `ja/` |
| 한국어 | `ko/` |

## 怎么玩
NeonRP TUI:
```
neonrp tui --from examples/goblin-ambush/zh
```
Claude Code / MCP:在该目录里 `@world-agent 掷先攻,开始战斗`。

## 文件
```
zh/
  runtime_contract.json          orchestrator
  game/meta/{game-start,run_state}.json
  game/agents/manifest.json      2 agent
  game/party/{aldric,bree,merrin}.json   3 名冒险者(5e 极简数据)
  game/npc/goblin.json           哥布林(5e MM)
  game/location/forest-path.json 黄昏林道
  game/rules/combat-5e.md        5e 战斗速查
  agents/world-agent/            DM
  agents/referee/                掷骰裁判
  .claude/agents/                Claude Code / MCP 镜像
```
