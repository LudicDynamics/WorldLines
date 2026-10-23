---
title: "简介"
description: "WorldLines 是一台 agentic 模拟引擎 —— 一座活着的 AI 村庄,和真人玩家,同场而生。"
---

<!-- section: what-is-worldlines -->
## 什么是 WorldLines?

WorldLines 是一台 **agentic 模拟引擎**。世界 agent 连着地点 agent;每个地点 agent 又连着住在那里的灵魂 agent。这里所有人都是 agent。你通过分身终端走进来。

这不是"一个 AI 角色陪你聊天"。这是一个 **多智能体社会**,实时运行,每个 agent 都有自己的目标、记忆和约束。

我们通过 harness 构建了「多智能体 × 世界智能体 × 灵魂智能体」系统。我们希望利用这个引擎进行：**互动体验创造 · 多智能体社会实验 · Agent 研究推进 · 人格模型与世界模型的 benchmark。**

当前状态：**v0.3.0**（2026-07-13）。[立即游玩 →](https://hub.worldlines.gg)

由 **nikoloside** 与 **redoctober** 共同开发，[Ludic Dynamics](https://ludicdynamics.com) 持续推进共创。

<!-- section: ways-to-play -->
## 三种游玩方式

> **👉 第一次来?从 Stoneford · Elena 这座多智能体村庄开始。** 两个角色,Elena 和 Rowan,各自*独立地思考、记忆、行动* —— 不是叙述者替他们写的台词。这是体会 WorldLines 与众不同之处最清晰的入口。在下面的 Launcher 里导入完整村庄,或一键 [在 WebHub 上见 Elena](https://hub.worldlines.gg/play/souls/elena)。

**1. WorldLines Launcher —— 桌面端,一次下载。** 从 [worldlines.gg](https://worldlines.gg) 获取 Launcher,双击,然后**导入一个世界** —— 官方世界开箱即玩,无需终端。它会替你配置好 Python 和 LLM provider。

**2. WebHub —— 浏览器,零安装。** 打开 [hub.worldlines.gg](https://hub.worldlines.gg),登录,即可游玩。浏览世界和灵魂的目录,用 AI 辅助的工坊创建你自己的内容,发布到公开注册表。云端 agent 替你跑。

**3. CLI & TUI —— 本地,开放工具(进阶)。** 安装 `worldlines` 二进制文件,在终端里用 Claude Code 风格的 TUI 游玩。示例、工具和协议是开源的(AGPL-3.0);可通过 Ollama / LM Studio / GLM 运行你自己的模型。

<!-- section: why-worldlines -->
## 为什么选择 WorldLines

传统的"与 AI 聊天"界面在上下文窗口被填满的那一刻就会丢失所有内容。WorldLines 给你一个真正引擎才有的保证:

- **⭐ 文件持久化的记忆与世界状态** —— 记忆、存档、NPC、Agent 全部以纯 JSON 和 Markdown 的形式落在磁盘上。没有云端,没有数据库,没有隐藏状态。只要你能打开这个文件夹,这个世界就是你的。
- **自动建索引、自动注入上下文** —— WorldLines 会自动构建文件索引和本地向量数据库,并在每一回合把相关的游戏数据自动注入到 Agent 的上下文里。不需要手动维护 lorebook。
- **事件溯源状态** —— 每一回合都是只追加的 Event;Snapshot 让回退变得高效。
- **分支 / 撤销 / 重做** —— 像 git 分支那样探索叙事的分叉。
- **沙箱 & 回放** —— 在隔离环境中跑实验;验证确定性。
- **Orchestrator 驱动的多 Agent** —— 一个 Orchestrator 在共享状态上路由到各领域 Agent(城镇 / 地下城 / 战斗裁判 / 世界构造者 / 规则裁判)。
- **计划 → 差异 → 应用** —— LLM 输出结构化的文件操作,你可以在落地前审阅。
- **丰富的 TUI** —— Claude Code 风格的对话式终端,游玩与构建皆可。
- **本地优先的模型** —— GLM、OpenAI、LM Studio 或 Ollama。

<!-- section: positioning -->
## WorldLines 与同类产品的对比

|                    | Character.AI     | SillyTavern               | Claude Code             | **WorldLines**                     |
|--------------------|-------------------|----------------------------|-------------------------|-------------------------------------|
| 主要领域            | 角色聊天          | Prompt 前端                | 代码编辑                 | 活的游戏世界                         |
| 世界存在于          | 他们的服务端      | Prompt 配置 + 聊天记录      | 磁盘上的代码库            | **纯文件 + git**                    |
| 记忆与检索          | 云端 / 不透明     | 手动 lorebook              | 代码库检索               | **自动文件索引 + 向量数据库**        |
| 多 agent           | —                 | —                          | 按任务启子 agent          | Orchestrator + 领域 agents           |
| 本地优先的 LLM      | ✗                | 自行接入                    | 仅 API                  | GLM / LM Studio / Ollama             |
| 确定性 / Replay    | —                 | —                          | —                       | **Sandbox + Replay**                 |

如果 Claude Code 是你写代码的 IDE,那 WorldLines 就是你构建活世界的 IDE —— 记忆、检索、orchestration 都已经内置好了。

对每个竞品的完整比较文章见 [Q&A](/docs/qa/what-is-airp) —— vs Character.AI · vs SillyTavern · vs Claude Code · vs LangGraph。

> 注:WorldLines 的 harness 目前比 Claude Code 更严格 —— 它依赖完整的上下文才能可靠地编排。这是为了更高的确定性与更易调试所做的刻意取舍,并非缺陷。

<!-- section: next-steps -->
## 下一步

- 跟随 [快速开始](/docs/getting-started/quickstart) —— 10 分钟内完成第一回合
- 了解 [核心概念](/docs/core-concepts/worlds) —— 事件、快照、分支、Agent
- 查看 [路线图](/docs/roadmap) —— 接下来的计划
- [Q&A](/docs/qa/what-is-airp) —— WorldLines 与现有工具的对比
