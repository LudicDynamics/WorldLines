---
title: "世界 —— 新建 · 导入 · 导出"
description: "创建、导入与导出游戏世界。"
---

<!-- section: new -->
## 新建世界

**在 Launcher 里(推荐)。** 打开 WorldLines,选 **New world** —— 挑一个内置模板(Stoneford · Stoneford · Elena · Kagura Island · …),它会搭建并打开,开箱即玩、即可编辑。没什么要记的。

**用 AI agent 创作。** WorldLines 自带 **Claude Code** 和 **Codex** 创作 skill。在你的 AI 编码 agent 里打开仓库,直接描述你想要什么 —— *"一个有四位皇子的国风乙女世界"* —— skill 就会替你搭建 `game/` 实体 + agent。见 [创作教程](https://github.com/LudicDynamics/WorldLines/tree/main/tutorials)(角色卡 · 世界卡 · 完整世界 · 灵魂)。

**进阶 —— CLI。** 在终端里从模板脚手架:

```bash
neonrp game new --template stoneford-orch    # flagship siege TRPG (10-agent)
neonrp game new --template stoneford-elena   # Stoneford + Elena — multi-agent village
neonrp game new --template kagura-island     # mystery · 7 souls
neonrp game new --template default           # minimal starter
```

或者从一个空项目起步,直接手工编写 `game/`(参见 [创建你的第一个世界](/docs/guides/creating-first-world))。

<!-- section: home-dir -->
## 世界存放位置 —— `~/.worldlines/games/`

当你从启动器导入或脚手架一个世界时,结果会落到 `~/.worldlines/games/<name>/` 之下。该目录是本机所有世界的总家 —— 每个世界都拥有自己的 `game/` 目录树和 `.neonrp/` 状态。

你正在游玩的"当前项目"就是这些文件夹中的某一个的实例(你也可以通过 `cd` + `worldlines init` 在一个临时路径里工作;这仍然行得通,但 `~/.worldlines/games/` 是约定用法)。

<!-- section: export -->
## 导出世界

使用内置的 TUI 命令(或 shell 别名):

```
/export-world                    # 在 TUI 中 → 写入 ~/Downloads/worldlines-<name>-<ts>.zip
/export-world my-world.zip       # 指定输出路径
```

Shell 等价命令:

```bash
neonrp export-world                        # 默认输出到 ~/Downloads/
neonrp export-world --output ~/my-world.zip
```

压缩包内含 `game/` 文件夹以及 `.neonrp/` 状态(事件、快照、manifest),接收者可以从你停下的位置精确续玩。

📸 **截图稍后补上** —— 从启动器 UI 一键导出计划在 v0.1.6 提供。

<!-- section: import -->
## 导入世界

在 TUI 或 shell 中:

```
/load-world ~/Downloads/worldlines-myworld-2026-04-23.zip
```

```bash
neonrp load-world ~/Downloads/worldlines-myworld-2026-04-23.zip
```

该命令会把压缩包解压到 `~/.worldlines/games/<name>/` 下,使它与你的其他世界并列显示。然后通过 `/worlds`(TUI)切换过去,或在运行启动器前 `cd ~/.worldlines/games/<name>`。

📸 **截图稍后补上** —— 启动器中的拖放导入流程。

<!-- section: browse -->
## 浏览本地世界

在 TUI 中:

```
/worlds                         # 浏览 ~/.worldlines/games/ 下的世界,并可从模板脚手架
/worldlines                     # 引导式世界选择器(模型预设 + 世界 + 启动)
```

或者手动:

```bash
ls ~/.worldlines/games/
```
