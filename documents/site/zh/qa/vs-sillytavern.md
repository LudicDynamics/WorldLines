---
title: "对比 SillyTavern"
description: "与 SillyTavern 的格式兼容 —— 但是一种不同的范式:agentic 模拟,而非逐条提示词的聊天。"
---

<!-- section: two-paradigms -->
## 两种范式:提示词 vs agent

**SillyTavern** 是一个面向高阶用户的*前端*,把精心打磨的**提示词**发送给你选的 LLM。角色、世界书、提示词宏 —— 它是面向聊天、由提示词驱动的角色扮演里同类最佳的工具。

**WorldLines 是 agentic 的。** 不是一个 LLM 回答一条提示词,而是一套编排系统 —— 与驱动 **Claude Code** 和 **Codex** 的同一种 —— 运行一个世界:agent 规划、调用工具、读写状态,并自主行动。我们不是给一个角色发提示词;我们**模拟**一个角色,以及它周围的世界。

<!-- section: compatible -->
## 我们想保持兼容

SillyTavern 的角色卡和世界书是很棒的内容格式,我们想在用户所在之处与他们相遇。你现在已经可以导入 SillyTavern 的卡片:

```bash
neonrp import sillytavern-card card.png --id mira-ashford
```

方向是:保持 SillyTavern 格式可导入,同时在它之上提供一种**新的游玩方式** —— agentic 模拟,而非逐条提示词的聊天。

<!-- section: agent-roleplay -->
## 一种新的角色扮演

已经有很多人直接*在* **Claude Code** 或 **Codex** *里面*玩角色扮演,让一套 agentic 系统来驱动角色和场景。这已经超出了一个基于提示词的前端当初的设计 —— 一种我们称之为 **Agent Role Play** 的新范式。

WorldLines 正是为此而生:通过 agent 编排来模拟人格与世界。而且我们正在投入**前端打磨**,让 agentic 角色扮演用起来和它本身一样强大 —— 一场运行中的模拟的深度,而不必住在一个原始终端里。

当你想要一个能持久、能分支、真正被*模拟*的世界时,选 WorldLines。当你想要最大的提示词灵活性和它成熟的扩展生态时,选 SillyTavern —— 而无论哪种,你都能导入你的卡片。
