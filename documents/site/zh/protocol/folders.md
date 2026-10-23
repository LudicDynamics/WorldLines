---
title: "文件夹与版本管理"
description: "一个 world(game/)、一个 soul(soul/)在磁盘上的形状,以及三条版本轴 —— 创作者、实例、commit —— 之间的关系。一套文件夹布局,两个消费者:引擎写它,网页渲染器走它。"
---

<!-- section: shared-contract -->
## 共享契约

这是 **world**(`game/`)、**soul**(`soul/`)在磁盘上形状的权威参考,以及三条版本轴如何关联。

它综合了已设计锁定的 SoulHub(M16)与 commit 版本化(M17);world 的 `game/` 这一半记录的是今天磁盘上已经存在的东西。一套文件夹布局,两个消费者:引擎写这些文件夹,网页渲染器走它们。

<!-- section: world-folder -->
## world 文件夹 —— game/

一个 world bundle 就是一个 `game/` 目录。创作者编写,由 world 作者版本化,通过 WorldHub 分发。当前实际布局:

```
game/
├── agents/                 # world 的 agent 阵容(创作者版本化模板)
│   ├── manifest.json       # 这个 world 带哪些 sub-agent(world-agent + domain agent)
│   └── contracts/          # 每个 agent 的 IO 契约
├── meta/
│   ├── run_state.json      # 实时位置 / 时间 / turn_count(每个 playthrough)
│   ├── active-agent.json   # 当前持写锁的 sub-agent
│   ├── game-start.json     # 开场 / handoff
│   ├── flag_aliases.json   # story flag 的可读名
│   └── schedule.json       # 定时 / 计划世界事件
├── lore/
│   ├── story.md            # 主线(append-only 叙事)
│   └── notes.md            # 传闻 / 世界观察
├── world/
│   ├── world_map.json      # 节点图
│   ├── regions.json
│   └── factions.json
├── towns/<Txxx>/           # 城镇位置节点
├── dungeons/<Dxxx>/        # 地下城位置节点
├── rules/                  # 规则 schema(骰子、检定、战斗)
└── player/                 # 旧的玩家状态 —— 迁移进 soul
```

- `game/agents/manifest.json` 是 world sub-agent 团队的**创作者版本化模板**。playthrough 创建时被 *seed* 进 `playthrough.json`;运行中的引擎读 `playthrough.json`,从不直接读 bundle manifest。
- `game/player/` 是**旧**的单玩家状态模型。M16 下被 soul 文件夹取代;现有 game 自动迁移。

<!-- section: soul-folder -->
## soul 文件夹 —— soul/

一个 soul bundle 是自包含的角色。可以是玩家化身或 NPC。通过 SoulHub 分发。设计锁定形状(M16,方案 B —— NeonRP 原生,不兼容旧版):

```
souls/<sid>-<instance_id>/
├── soul.json               # 机器身份信封(NeonRP 专用)
├── soul.md                 # 面向运行时的灵魂宪章(语气 / 价值观 / 禁忌)
├── run_state.json          # 实时位置/状态(soul-orchestrator/action 写)
├── agents/
│   ├── manifest.json       # soul 的 6-agent 阵容 + 每 agent 写 glob
│   └── contracts.md        # 每个 agent 的输入/输出 schema
├── persona/                # 不可变心理内核
│   └── core_traits.json  motivations.json  values.json  relationships.json
├── background/             # 不可变 lore: origin.md  history.md  secrets.md
├── character/              # RPG 机制(仅 soul-action)
│   └── stats.json  inventory.json  equipment.json  wallet.json  status.json  profile.json
├── rules/                  # 决策/行为护栏(只读)
├── short-term-memo/        # 会话工作记忆
├── long-term-memo/         # 持久记忆(soul-memory 写)
├── trajectory/             # append-only 自主行动日志
└── .commits/               # 这个 soul 实例自己的 commit 链(M17)
```

**`soul.json` —— 身份信封:**

```json
{
  "schema_version": 1,
  "sid": "elena",
  "name": "Elena Voss",
  "name_local": "艾莲娜",
  "version": "1.0",
  "source": {"kind": "soulhub|builtin|local-create", "hash": "...", "version": "1.0"},
  "agent_template": "heroine-classic|minimal",
  "tags": ["companion", "mage"]
}
```

**`soul.md` —— 面向运行时的灵魂宪章。** 与 `soul.json` 并列的一等根文件。一个文件的自然语言总览，讲*这个灵魂在角色扮演里该有什么感觉、该怎么行动*：第一人称身份与自我形象、语气与情绪基调、价值观 / 禁忌 / 不可逾越的底线、这个灵魂倾向于注意、隐藏、追求或回避什么。它补充而非替代结构化文件：`soul.json` = 机器身份 / 版本锚点 · `soul.md` = 面向运行时的自然语言宪章 · `persona/*.json` = 结构化心理内核 · `background/*.md` = 事实 lore。这是 NeonRP 对更广义「soul document」模式的角色扮演化改编 —— 明确面向角色扮演，不是通用助手宪法。

**Soul agent 阵容。** `soul/agents/manifest.json` 列出 6 个专家:`soul-orchestrator`(分派)+ `soul-mind`(认知)+ `soul-memory`(留存)+ `soul-action`(执行)+ `soul-dialogue`(言语)+ `soul-narrative`(故事接口)。每个带 `write_globs` 白名单;apply 管线拒绝白名单外的写。

**写权限契约:**

| 路径 | 写者 |
|---|---|
| `persona/` `background/` `rules/` | 无(创建后不可变) |
| `soul.md` | 无(创建后不可变) |
| `soul.json` | `soul-orchestrator` —— 仅 rename 时 |
| `character/` | `soul-action` |
| `short-term-memo/` | `soul-memory`、`soul-dialogue` |
| `long-term-memo/` | `soul-memory` |
| `trajectory/` | `soul-action`、`soul-orchestrator`(append-only) |
| `run_state.json` | `soul-orchestrator`、`soul-action` |
| `agents/manifest.json` | 从不(随 soul bundle 版本化) |

**迁移。** 现有 `~/.worldlines/players/` profile 在 M16 后首次启动自动导入 `~/.worldlines/souls/`:合成一个最小 `soul.json` + persona stub;`game/player/*` 内容映射进 `soul/character/*`。

<!-- section: version-axes -->
## 版本管理 —— 三条身份轴

world 和 soul 共享同一个模型。三条正交的轴(M17):

- **创作者轴 —— `slug + version_hash`。** 已发布、已编写的版本。不可变。`wid`/`sid` + `version_hash`。WorldHub/SoulHub 注册表里每个 slug+version 一份。*(M17 之前唯一存在的版本化。)*
- **实例轴 —— `instance_id`。** 一次 playthrough 的 fork。soul 进入 world 时被 fork → 一个新的 soul **实例**,有自己的 `instance_id`(fork 时的 UUID)和自己独立的每回合 commit 链。被玩的 world 同样是一个实例。两条链从不嵌入对方的哈希。`(wid|sid, instance_id)` 全局唯一 —— **身份里没有时间戳**。
- **commit 轴 —— `commit_hash`。** 一个实例的每回合状态快照。内容哈希 → 哈希就是身份,不是元数据。world 实例和 soul 实例各有自己的 commit DAG(可分叉,v1 不 merge)。一个 commit 打包文件夹 blob + 每个 agent 的对话快照 + 一个 `determinism` 块(rng seed、rolls、llm-calls 哈希)—— 一个完整、可移植、确定性的执行上下文。

**完整地址 + 绑定:**

| 资产 | 地址 |
|---|---|
| World | `(wid, instance_id, version_hash, commit_hash)` |
| Soul  | `(sid, instance_id, version_hash, commit_hash)` |

world↔soul 关系与活动 agent 团队**只**在 session 层 playthrough manifest 里是权威的:`~/.worldlines/games/<wid>-<world_instance_id>/.neonrp/playthrough.json`。它带 world 实例 ref + `world_agent_team`(从 `game/agents/manifest.json@<version_hash>` seed)+ soul 实例列表。world commit 额外带一个*只读*的 `soul_scene_index`;soul 从不反指 world。

**时间戳规则。** 时间戳永远不是身份的一部分。`instance_id` 唯一;`commit_hash` 钉死状态。`archived_at` 只在 commit 被打包上传/导出时出现 —— 给人看的排序标签,绝不是 key。**哈希定位;时间戳只贴标签。**

<!-- section: on-disk-map -->
## 磁盘布局图

```
~/.worldlines/
├── games/<wid>-<world_instance_id>/
│   ├── .neonrp/
│   │   ├── playthrough.json     # 绑定
│   │   ├── HEAD                 # 当前 world commit_id
│   │   └── sessions/<branch>.jsonl
│   ├── game/                    # world 工作树
│   └── souls/<sid>-<soul_instance_id>/   # soul 工作树
├── souls/<sid>-<ts>/            # 下载/创建的 soul 库(fork 前)
│   └── .commits/<soul_commit_id>.json + blobs/
└── commits/
    ├── worlds/<world_commit_id>.json
    ├── refs/<wid>/{HEAD,branches/*,tags/*}
    └── blobs/<hash>.{tar,jsonl}.zst
```

<!-- section: sandbox-replay -->
## 与 sandbox / replay 的关系

这个模型是 M4 sandbox/replay 设计的**超集**:`sandbox` = 把一个 commit fork 到一条分支;`save` = 退化的单 agent commit;`replay verify` = 跨机器 commit 哈希比对。引擎稳定的 tree-hash 原样复用于文件夹哈希。M4 预留的 seed/rolls 接口由 commit `determinism` 块填充。

另见:[World 协议](/docs/protocol/world) · [Soul 协议](/docs/protocol/soul) · [Agent 协议](/docs/protocol/agent)。
