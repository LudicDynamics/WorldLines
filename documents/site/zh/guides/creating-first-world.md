---
title: "创建你的第一个世界"
description: "创建世界的三种方式 —— Launcher、WebHub 工坊,或一个 AI 编码 agent。"
---

<!-- section: launcher -->
## 在 WorldLines Launcher 里

打开 WorldLines → **New world**,从一个最接近你想法的模板起步(Stoneford · Kagura Island · …),然后游玩它,并在 **Build** 模式里调整。这是通向一个你真能玩起来的世界的最快路径。

<!-- section: webhub -->
## 在浏览器里 —— WebHub Create 工坊

在 [hub.worldlines.gg](https://hub.worldlines.gg),**Create** 工坊以 AI 辅助引导你创建一个世界 —— 设定前提、角色和基调,满意后发布到公开注册表。零安装。

<!-- section: ai-skill -->
## 用 Claude Code 或 Codex —— 创作 skill

WorldLines 自带 **Claude Code** 和 **Codex** 创作 skill。clone 仓库,在你的 AI 编码 agent 里打开它,然后直接描述你想要什么:

```bash
git clone https://github.com/LudicDynamics/WorldLines.git
cd WorldLines        # then open in Claude Code or Codex
```

> *"做一个国风乙女世界:一座宫殿、四位皇子,以及一盏会选定女主的灯。"*

对应的 skill 会自动加载,替你搭建 `game/` 实体、agent,以及(对村庄而言)灵魂。逐步教程见:[创作教程](https://github.com/LudicDynamics/WorldLines/tree/main/tutorials) —— 角色卡 · 世界卡 · 完整世界 · 灵魂。

<!-- section: advanced-cli -->
## 进阶 —— 在 CLI 里手工创作

想要完全掌控?搭建引擎元数据,然后手工编写 `game/`:

```bash
worldlines init        # creates .neonrp/ engine metadata
# author game/meta/world.json, game/player/, locations, agents…
neonrp validate        # check the schema
neonrp index build     # rebuild the retrieval index
```

一个最简世界需要 `game/meta/world.json`、一个初始玩家状态、至少一个地点,以及一个 agent(orchestrator)。
