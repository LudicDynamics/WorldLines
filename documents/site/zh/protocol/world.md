---
title: "World 协议"
description: "可分发的 WorldLines world 的形状。上传到 WorldHub 的 zip 里装什么,下载方又是怎么把它还原成可玩的 game 目录。"
---

<!-- section: what-is-a-world -->
## world 是什么

*world* 是场景:区域、城镇、NPC、势力、任务、空间地图、传说、规则。它**不**包括玩家或操控它的 agent —— 那是另两套协议([Soul](/docs/protocol/soul) 和 [Agent](/docs/protocol/agent))。一个 world + 一个 soul + 一套 agent 才是*可运行的 session*。

每个 world 都有一个稳定标识符 —— `wid` —— 这就是 WorldHub 上的 slug,也是用户用来 pin 存档和 hash 的 key。

<!-- section: bundle-layout -->
## 包结构 —— game/

一个 world bundle 就是一个 `game/` 目录。创作者编写,由 world 作者版本化,通过 WorldHub 分发。这是磁盘上的权威形状(完整契约见 [文件夹与版本管理](/docs/protocol/folders)):

```
game/
├── agents/                 ← world 的 agent 阵容(创作者版本化模板)
│   ├── manifest.json       ← 这个 world 带哪些 sub-agent
│   └── contracts/          ← 每个 agent 的 IO 契约
├── meta/
│   ├── run_state.json      ← 实时位置 / 时间 / turn_count
│   ├── active-agent.json   ← 当前持写锁的 sub-agent
│   ├── game-start.json     ← 开场 / handoff
│   ├── flag_aliases.json   ← story flag 的可读名
│   └── schedule.json       ← 定时 / 计划世界事件
├── lore/
│   ├── story.md            ← 主线(append-only 叙事)
│   └── notes.md            ← 传闻 / 世界观察
├── world/
│   ├── world_map.json      ← 节点图(必需)
│   ├── regions.json
│   └── factions.json
├── towns/<Txxx>/           ← 城镇位置节点
├── dungeons/<Dxxx>/        ← 地下城位置节点
├── rules/                  ← 规则 schema(骰子、检定、战斗)
└── player/                 ← 旧的玩家状态 —— 被 soul 取代
```

上传到 `s3://worldlines-hub/worlds/<hash>.zip` 的 zip **就是**这个 `game/` 目录,gzip 后的形态。`game/agents/manifest.json` 是 world sub-agent 团队的创作者版本化模板;playthrough 创建时 seed 进 `playthrough.json`(运行中的引擎读那个,从不直接读 bundle manifest)。`game/player/` 是 M16 之前的单玩家模型,只作为分阶段兼容面保留 —— 长期 ontology 是玩家化身就是一个 soul 实例。

<!-- section: schemas -->
## 什么放在哪

| 区域 | 路径 | 形态 |
|---|---|---|
| Agent 阵容 | `game/agents/manifest.json` | JSON —— 创作者版本化模板 |
| 实时运行状态 | `game/meta/run_state.json` | JSON —— 每个 playthrough |
| 开场 | `game/meta/game-start.json` | JSON |
| 主线 | `game/lore/story.md` | **Markdown** —— append-only 叙事 |
| 传闻 | `game/lore/notes.md` | **Markdown** |
| 导航 | `game/world/world_map.json` | JSON —— 节点图 |
| 区域 / 阵营 | `game/world/{regions,factions}.json` | JSON |
| 位置 | `game/towns/<Txxx>/` · `game/dungeons/<Dxxx>/` | 每节点 JSON |
| 规则 | `game/rules/` | JSON —— 骰子 / 检定 / 战斗 |

world↔soul 绑定与活动 agent 团队只在 session 层的 `playthrough.json` 里是权威的(见 [文件夹与版本管理](/docs/protocol/folders))。

<!-- section: authoring-rules -->
## 作者经验法则

- **`wid` 是永久的。** 改名会断链。
- **叙事 lore 是 Markdown。** `lore/story.md` 和 `lore/notes.md` 是 append-only Markdown —— 故事在游玩中生长。结构化 world 数据(`world_map.json`、`regions.json`、`factions.json`、位置节点)保持 JSON,这样 agent 能引用、变异、检索。
- **位置是节点文件夹。** `towns/<Txxx>/` 和 `dungeons/<Dxxx>/` —— 一节点一文件夹,不是一 entity 一扁平文件。
- **模板别带 playthrough。** 模板 world 没有实时的 `meta/run_state.json` 历史 —— 只有 saved-game 导出才有。
- **agent 阵容是创作者版本化的。** 它作为模板随 bundle 发布,fork 时 seed 进 `playthrough.json`;运行时从不直接读 bundle manifest。

<!-- section: distribution -->
## 分发

```
neonrp world upload examples/orch/dark-train --slug dark-train --version 2.0
# → s3://worldlines-hub/worlds/<hash>.zip + worlds/index.json 添加一条
neonrp world download dark-train
# → ~/.worldlines/games/dark-train-<world_instance_id>/  → 可玩
```

在 [hub.worldlines.gg/worlds](https://hub.worldlines.gg/worlds) 浏览已发布内容。完整地址模型见 [GitHub 上的 WorldHub spec](https://github.com/LudicDynamics)。

<!-- section: see-also -->
## 另见

- [Soul 协议](/docs/protocol/soul) —— 谁在 world 里面玩
- [Agent 协议](/docs/protocol/agent) —— world 自带的 agent 集合怎么驱动游玩
- GitHub 上的规范文档:[WORLD-PROTOCOL.md](https://github.com/LudicDynamics)
