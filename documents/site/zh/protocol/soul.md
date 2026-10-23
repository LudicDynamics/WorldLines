---
title: "Soul 协议"
description: "可分发的 soul 的形状:一个自包含的 agent bundle,带人格、记忆、目标,以及驱动行为的 agent 集合。上传到 SoulHub。"
---

<!-- section: what-is-a-soul -->
## soul 是什么

*soul* 是玩家或 NPC 的内在世界:他们是谁(人格)、记得什么(记忆)、想要什么(动机)、怎么行动(agent)。它**默认是 world-agnostic 的** —— 同一个 Elena 应该能 drop 进多个 world。当行为依赖特定 world 的 lore 时,作者可以用 manifest 的 `compatible_worlds` 字段 pin 死。

**命名。** 正式术语是 `soul`。`character` 作为旧别名保留在 schema 里;两者校验完全一致。`sid` 是 soul id(对应 world 的 `wid`)。

<!-- section: bundle-layout -->
## 包结构

```
<sid>/
├── soul.json                          ← 机器身份信封(必需)
├── soul.md                            ← 面向运行时的灵魂宪章(必需)
├── run_state.json                     ← 单次运行的可变状态(必需)
│
├── persona/                           ← 他们是谁(必需)
│   ├── core_traits.json
│   ├── values.json
│   ├── motivations.json
│   └── relationships.json
│
├── character/                         ← 机制层(必需)
│   ├── profile.json
│   ├── stats.json
│   ├── status.json
│   ├── equipment.json
│   ├── inventory.json
│   └── wallet.json
│
├── background/                        ← 散文 lore(可选)
│   ├── origin.md
│   ├── history.md
│   └── secrets.md
│
├── rules/                             ← 单 soul 约束(可选)
│   ├── action_rules.md
│   ├── decision_rules.md
│   └── interaction_rules.md
│
├── long-term-memo/                    ← 持久记忆
│   ├── emotional_memories.json
│   ├── important_events.md
│   └── learned_facts.json
│
├── short-term-memo/                   ← session 内记忆
│   ├── current_context.json
│   ├── recent_events.json
│   └── conversation_cache.json
│
├── trajectory/                        ← 第一人称行动日志
│   └── action_log.md
│
└── agents/                            ← agent 集合(必需)
    ├── manifest.json
    └── contracts/<agent_id>.json
```

soul 实例还带自己的 `.commits/` 版本仓库(它每回合的 commit 链 —— 见 [文件夹与版本管理](/docs/protocol/folders))。

<!-- section: soul-md -->
## soul.json 与 soul.md

两个根文件,两份职责。`soul.json` 是**机器身份信封** —— `sid`、名字、版本、来源/hash、agent 模板。它把 soul 锚在 SoulHub 注册表里,让 `list_souls()` 能快速发现这个 bundle。

`soul.md` 是**面向运行时的灵魂宪章** —— 一个文件的自然语言总览,讲*这个 soul 在角色扮演里该有什么感觉、该怎么行动*:

- 第一人称身份与自我形象
- 语气、说话风格、情绪基调
- 价值观、禁忌、不可逾越的底线
- 这个 soul 倾向于注意、隐藏、追求或回避什么

它补充而非替代结构化文件:

| 文件 | 职责 |
|---|---|
| `soul.json` | 机器身份 / 来源 / 版本锚点 |
| `soul.md` | 面向运行时的自然语言宪章 |
| `persona/*.json` | 结构化心理内核(工具 / 校验) |
| `background/*.md` | 事实 lore 与秘密 |

把 `soul.md` 看作 NeonRP 对更广义「soul document」模式的角色扮演化改编:一个文件告诉模型这个存在该如何*成为*,周围的文件告诉引擎它*包含*什么。`soul.json` 和 `soul.md` 创建后都不可变(只有 `soul-orchestrator` 能动 `soul.json`,且仅限 rename)。

<!-- section: six-agents -->
## 参考 soul:6 个 agent

第一个 sample soul([Elena](https://hub.worldlines.gg/souls/elena),`elena@1.0`,hash `827ac36a11c1`)用的是 6-agent 基线:

| Agent | 职责 |
|---|---|
| **orchestrator** | 玩家每回合后触发。串联其他 agent。 |
| **mind** | 情境分析 + 人格对齐的决策。 |
| **action** | 执行移动、用物品、NPC 交互、调查、休息。 |
| **memory** | 存新感知;短期记忆 → 长期记忆的整合。 |
| **dialogue** | 生成发言;声音 / 心情 / 信息披露层级过滤。 |
| **narrative** | 与 world 的 narrative agent 对话 —— 发请求、观察、剧情建议。 |

自定义 soul 可以通过另一份 `agents/manifest.json` 替换其中任何子集。6-agent 是推荐基线,不是强制。

<!-- section: authoring-rules -->
## 作者经验法则

- **`sid` 是永久的。** 这是公共把手。
- **样例文本要短。** bundle 装的是 soul 的*形状*;玩家描述想要的 soul 时,LLM 在 onboarding 阶段重写散文。`persona/values.json` 写几条就好,不要写论文。
- **发布时别在 `learned_facts.json` 里塞剧透。** 那些 entry 是游玩中才积累出来的。带剧透发布,会毁掉「拿到新 world 重玩」的乐趣。
- **Markdown 写散文,JSON 写结构。** Markdown 只在 `background/`、`rules/`、`*-memo/important_events.md`、`trajectory/action_log.md` 里出现。其他地方一律 JSON,这样 editor 能校验。

<!-- section: distribution -->
## 分发

```
neonrp world upload my-soul --kind souls --slug elena --version 1.0
# → s3://worldlines-hub/souls/<hash>.zip + souls/index.json 添加一条
neonrp world download elena --kind souls
```

在 [hub.worldlines.gg/souls](https://hub.worldlines.gg/souls) 浏览已发布的 soul。launcher 的消费侧流程还在设计 —— 关注 [GitHub 上的 SOULHUB.md](https://github.com/LudicDynamics)。

<!-- section: see-also -->
## 另见

- [World 协议](/docs/protocol/world) —— soul 在哪里玩
- [Agent 协议](/docs/protocol/agent) —— soul 怎么真正决策与行动
- GitHub 上的规范文档:[SOUL-PROTOCOL.md](https://github.com/LudicDynamics)
