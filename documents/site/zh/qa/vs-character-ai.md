---
title: "对比 Character AI"
description: "WorldLines 与 Character AI 的重叠之处,以及决定性不同之处。"
---

<!-- section: what-caai-does-well -->
## Character AI 做得好的地方

- 零摩擦入门 —— 一键就能与角色聊天
- 庞大的角色卡社区库
- 移动端原生

<!-- section: where-worldlines-differs -->
## WorldLines 不同之处

最重要的有两点区别:

1. **以世界为中心,而非以角色为中心。** Character AI 给你一个角色去聊天。WorldLines 把每一个 AI 人格都构建**在一个活世界里** —— 角色存在于一个地方,被事件、其他 agent 和后果环绕,而不是真空中的一段聊天。

2. **持久人格 + 模拟,而非对话。** 一个角色的个性、记忆和关系是**持久化的** —— 它们跨 session 延续,甚至跨世界延续(同一个 Elena 能从 Stoneford 走到 Kagura Island)。而引擎运行的是一场**模拟**,不是一段对话:agent 自主行动,世界无论你在不在都会推进,发生的一切都被记录为可保存、可分支、可回放的状态。

具体来说:持久的世界 + 角色状态、多 agent 编排、基于文件 / git 版本化的世界、本地优先的模型(GLM / LM Studio / Ollama),以及可审阅的 计划 → 差异 → 应用 变更。

<!-- section: who-should-use-which -->
## 谁该选哪个

- 只想和喜欢的角色随便聊聊 → Character AI
- 想要一个能保留、分叉、演进的世界(构建或游玩) → WorldLines
