---
title: "对比 Claude Code"
description: "Claude Code 是一个 agentic 编码环境。WorldLines 是一个 agentic 世界构造环境。相似的原语,不同的领域。"
---

<!-- section: shared-primitives -->
## 它们的共同之处

两个引擎坐落在相同的 agentic 基础之上:

- 结构化的 提案 / 差异 / 应用 循环
- 活在真实目录里、基于文件的状态
- 对话式的终端界面
- 对工作集而非全部语料的检索
- 可分支、可回放的 session 历史

如果 Claude Code 是你写 **代码** 的 IDE,那 WorldLines 是你构建 **活世界** 的 IDE。直觉可以迁移过来。

<!-- section: where-they-diverge -->
## 它们的分歧

|                  | Claude Code                       | WorldLines                              |
|------------------|-----------------------------------|-----------------------------------------|
| 领域             | 代码编辑 / 软件 Agent             | 游戏世界 / AIRP Agent                   |
| 状态单元         | 文件 + git                        | 事件 + Snapshot + 分支                  |
| 主循环           | 计划 → 编辑 → 测试                | 计划 → 差异 → 应用 → 存档               |
| 随附内容         | 需自备仓库                        | 内置 `stoneford` 起步模板              |
| 沙箱             | Shell / 容器                      | 一等公民的引擎内置 Sandbox + Replay     |
| 多 Agent         | 按任务派生子 agent                | World-agent + 一群灵魂构成的社会(村庄)+ 领域 agent |

同一身 agentic 肌肉,指向一个不同的领域:跨回合保持一个*世界*的连贯,而不是一个代码库。

<!-- section: fit-together -->
## 它们如何配合

它们不是对手 —— WorldLines 跑*在* Claude Code 推广的同一种 agentic 范式之上,而 Claude Code 是**创作**一个 WorldLines 世界最好的方式之一。

- **用 skill 创作。** WorldLines 自带 Claude Code(和 Codex)创作 skill —— clone 仓库,在 Claude Code 里打开,描述你想要的世界;它就替你搭建 `game/` + agent + 灵魂。见 [教程](https://github.com/LudicDynamics/WorldLines/tree/main/tutorials)。
- **agentic 地游玩。** 很多人已经直接在 Claude Code 里玩角色扮演。WorldLines 补上了缺失的部分:一个持久的世界、一群独立灵魂构成的社会(多智能体村庄),存档 / 分支 / 回放 —— 以及一个前端,让它不再全是原始终端。

如果 Claude Code 是你写代码的 IDE,WorldLines 把同一身 agentic 肌肉变成一个鲜活、可玩的世界。

<!-- section: what-we-push -->
## 我们更进一步推动的地方

很多人已经在 Claude Code 和 Codex 里玩角色扮演 —— 我们支持这件事。沿着这个方向,我们着手解决三件事:

1. **速度。** Claude Code / Codex 一回合可能要 **3 分钟以上** —— 写代码还行,游玩就难受。我们想要一个**为角色扮演调优的更快 agent**,让一回合像一段对话,而不是一次构建。

2. **不锁定 —— 任意模型,甚至本地与免费。** 角色扮演不该被绑在一家供应商上。把它跑在 **DeepSeek、OpenRouter、开源、本地与免费**模型上,并保持**可定制** —— 大脑由你选。

3. **多智能体,规模化。** 我们正把**多智能体村庄**推得更远 —— 更多独立灵魂、更大场景、更大世界 —— 并在让它们全部保持连贯的**编排**上持续创新。

与 Claude Code 同样的 agentic 精神;只是为活世界而非代码库调优。
