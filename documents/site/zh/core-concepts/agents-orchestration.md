---
title: "Agent 与编排"
description: "WorldLines 的 Agent 设计 —— 基于文件的 agent 格式 + harness 可定制性,带来高自由度的游戏创作能力。"
---

<!-- section: philosophy -->
## 为什么选择基于文件的 Agent

WorldLines 的 agent 系统是**彻底基于文件的**。每一个 agent —— 角色、领域、裁判 —— 都是一个由普通文件组成的目录:

- `agent.json` —— 触发器、标签、优先级、路由元数据
- `system.md` —— system 提示词模板(Markdown,人类可读)
- `skills/` —— 可选的可复用提示词片段 / 能力模块
- `tools.json` —— 可选的额外工具定义
- `policies.md` —— 可选的硬规则(v0.2+)

没有数据库。没有绑在 API 上的状态。你可以 `git diff` 一个 agent,fork 一个,复制/粘贴另一个。这和 Claude Code 对代码的洞察一致 —— **文件系统就是 UI**。

<!-- section: harness-editing -->
## 高自由度的 Harness 编辑

Harness —— 规划、拉取上下文、调用工具、应用 diff 的那个循环 —— 是**由 agent 文件定义**的,而不是由引擎代码定义的。

这意味着一个游戏作者可以:

- 通过改写一份 `system.md` 来改变**叙述声线**
- 通过编辑某个 agent 的 `tools.json` 来改变**检索范围**
- 通过添加一份 `policies.md` 来改变**决策风格**
- 通过调整触发器 / 标签 / 优先级来改变**dispatcher 行为**

一个全新的子类型(推理 / slipstream / 乙女 / TRPG)可以表达为在 stoneford 基底之上对 agent 目录的一组改动,不必动一行 Python。这正是 WorldLines 优化的设计空间。

<!-- section: anatomy -->
## Agent 结构解析

一个完整的 agent 目录看起来像:

```
agents/elena/
├── agent.json        # 触发器、标签、优先级、路由
├── system.md         # system 提示词模板
├── skills/
│   └── innkeeper.md  # 可复用的提示词片段
├── tools.json        # 额外工具定义(可选)
└── policies.md       # 硬规则(v0.2+)
```

stoneford 起步模板随附 **6 个 agent**:`orchestrator`、`town-agent`、`dungeon-agent`、`combat-referee`、`world-builder`、`rules-referee`。

<!-- section: dispatch -->
## Dispatcher

Dispatcher 通过以下方式为每个查询挑选 agent:

1. 显式 `--agent` 标志
2. 来自 `agent.json` 的正则触发模式
3. 与当前上下文的标签重叠
4. 优先级决胜

也可以通过 CLI 直接调用 agent:

```bash
neonrp agent run town-agent --query "describe the harbor"
neonrp agent list --json
neonrp agent show town-agent
```

<!-- section: harness-loop -->
## Harness —— 编排循环

WorldLines 的 agent harness 实现了一个**计划 → 差异 → 应用循环**,具备:

- 有界检索(最小上下文、模糊 + 向量混合)
- 确定性的工具调用顺序
- 每回合预算(tokens / tool 调用)
- thinking 通道与叙述分离

**orchestrator** agent 是顶层 harness 协调者 —— 它通过 `task()` 工具路由到领域 / 角色 agent,维持游戏状态的一致性,并掌管面向玩家的叙述。

Router 模式(`fast` / `orchestrator` / `multi-agent`)改变的是每回合*如何*进行编排 —— 参见 [Router 模式](/docs/core-concepts/engine-modes)。

<!-- section: skills -->
## 技能(Skills)

**Skills** 是可复用的提示词片段 / 能力模块,agent 可以 `use`。内置的 skill 随引擎打包;你也可以在 `skills/` 中定义项目级别的 skill。

列出可用:

```bash
/skills              # 在 TUI 内
```
