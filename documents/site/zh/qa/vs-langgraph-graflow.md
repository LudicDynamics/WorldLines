---
title: "对比 LangGraph、Graflow 及其他多智能体框架"
description: "WorldLines 是一个专为角色扮演而生的多智能体框架。"
---

<!-- section: vs-orchestration -->
## 对比编排框架(LangGraph · Graflow)

**LangGraph** 和 **Graflow** 是构建有状态、多智能体工作流的*通用*工具箱 —— 节点、边、状态通道、检查点 —— 你把它们组装成你领域所需的任何东西。

**WorldLines 专为一件事而生:角色扮演。** 它的原语 —— world-agent、灵魂 agent、事件、快照、分支、计划 → 差异 → 应用 —— 是一套面向*鲜活、可玩世界*的词汇,而不是一张你自己设计的通用图。

<!-- section: vs-simulators -->
## 对比多智能体模拟器(Oasis · 灵台 · Mirror Fish)

一波多智能体*模拟*框架在为不同类型的世界建模:

- **Oasis** —— 模拟**社交网络**:大量 agent 发帖、关注、相互影响。
- **灵台(Lingtai)** · **Mirror Fish** —— 其他多智能体模拟环境。

WorldLines 刻意瞄准一个不同的领域:由**多个灵魂 Agent**驱动的**桌面式角色扮演(跑团)**。我们**不**适配 SNS / 社交网络模拟。我们适配更接近**现实生活**或**奇幻世界**的设定 —— 一个你走进去游玩的地方,每个角色都是它自己的灵魂,有记忆和能动性。

<!-- section: when-to-pick-which -->
## 何时选哪个

- **LangGraph / Graflow** —— 构建一个自定义的 agentic 工作流(研究助手、客服机器人、代码流水线);你想要最大的灵活性。
- **Oasis / 社交模拟器** —— 研究网络规模的社会动态。
- **WorldLines** —— 构建或游玩一个**角色扮演世界**:TRPG、叙事、同伴 —— 一个由灵魂 agent 构成、可保存、可分支、可回放的活世界。
