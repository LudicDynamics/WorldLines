# 世界线收束 · Worldline

一个**单场景** WorldLines 示例:时间线漂移。深夜,你拥有一台能发短信到过去的
旧手机,你的朋友三天前出事昏迷。你改一条短信,过去重写,世界线漂移——但有些
事会**收束**回来,而每跨一条线,代价都更重。

## 看点(它在展示什么)
- **三 agent 编排**:`world-agent`(叙述 + 把短信解析成对过去的改动)+
  `worldline-agent`(从时间线算出**分歧率**与所属域)+ `drift-agent`(判定一次
  改动让世界线**漂移**多远、是否被**收束**弹回)。
- **可计算的世界状态**:分歧率是个真实数字,存在 `game/meta/worldline_state.json`,
  由 agent 每回合重算——不是文案,是状态机。
- **三条吸引域 α / β / γ**:跨过 1.0 进 β,跨过 2.0 进 γ,每道墙一个代价。
- **收束补偿**:擦边的改动会被时间线拉回原样,逼玩家找真正的杠杆点。
- **一回合一停**:每发一条短信看一次世界线怎么变,绝不自己跑到结局。

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
neonrp tui --from examples/orch/worldline/zh
```
Claude Code / MCP:在该目录里 `@world-agent 开始游戏`。

## 文件
```
zh/
  runtime_contract.json          orchestrator
  game/meta/game-start.json
  game/meta/run_state.json
  game/meta/timeline.json        过去事件数据库(带因果链 + locked 吸引子)
  game/meta/worldline_state.json 当前分歧率 + 所属域 α/β/γ
  game/item/old-phone.json       能发往过去的旧手机(规则)
  game/location/your-room.json   深夜的房间
  agents/world-agent/            叙述 + 短信解析 + 调度
  agents/worldline-agent/        算分歧率 + 定域
  agents/drift-agent/            算漂移 + 收束判定
  .claude/agents/                Claude Code / MCP 镜像
```
