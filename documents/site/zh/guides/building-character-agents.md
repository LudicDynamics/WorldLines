---
title: "构建角色 Agent"
description: "面向角色的一等 AI agent 构建流程正在路线图中。本页预览预期形态。"
---

<!-- section: shipping -->
## ✓ v0.2.0 已提供

多 Agent 角色 NPC 和灵魂 agent 在 v0.2.0 中**已上线**。角色以灵魂包（persona, character, agents, memo）的形式创作,可在 WebHub 的 [Soul Talk](https://hub.worldlines.gg/play/souls/elena) 中游玩,或通过 CLI 本地加载。

对于世界中的 NPC,引擎支持在 `agents/` 下为每个 NPC 配置 agent 目录（参见 [CLI `agent new`](/docs/guides/world-editor#agents) 命令）。Orchestrator 根据上下文将任务分派给对应的 agent。

<!-- section: agent-structure -->
## Agent 目录结构

创建 `agents/my-agent/`,包含:

```
agents/my-agent/
├── agent.json        # 触发器、标签、优先级
├── system.md         # system 提示词模板
├── skills/           # 可选:skill 片段
└── tools.json        # 可选:额外的工具定义
```

用 CLI 脚手架:

```bash
neonrp agent new my-agent
```

<!-- section: agent-json -->
## 计划中:agent.json

```json
{
  "id": "harbormaster",
  "triggers": ["harbor", "dock", "ship"],
  "tags": ["location:harbor", "npc:official"],
  "priority": 50,
  "routing": {
    "invoke": "on_match",
    "fallback_to": "town-agent"
  }
}
```

当查询命中 triggers 或 tags 时,dispatcher 会按优先级挑选此 agent。

<!-- section: test-agent -->
## 计划中:测试 agent

```bash
neonrp agent run harbormaster --query "who is in charge of the harbor?"
neonrp agent run harbormaster --query "register a ship" --apply
```

加 `--json` 得到机器可读输出。加 `--fixture file.json` 在测试时 stub LLM 响应。
