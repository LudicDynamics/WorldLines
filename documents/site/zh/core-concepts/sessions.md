---
title: "模式 —— Build · TUI · Web UI"
description: "运行一个世界的三种方式:创作它(Build)、在终端里游玩(TUI),或在浏览器里游玩(Web UI)。"
---

<!-- section: modes -->
## 三种模式:Build · TUI · Web UI

一个世界以以下三种模式之一运行:

| 模式 | 是什么 | 在哪里 |
|---|---|---|
| **Build** | 创作世界 —— 直接编辑 `game/` 文件,或让 AI agent 来做(计划 → 差异 → 应用) | Launcher · CLI · 任意编辑器 |
| **TUI** | 在终端里游玩,Claude Code 风格 —— 看着思考、工具调用与叙述 | `neonrp tui` |
| **Web UI** | 在浏览器里游玩,实时观看每个 agent | [WebHub](https://hub.worldlines.gg),或本地 `neonrp web` |

**可插拔的媒体生成。** 一个世界不局限于文本。你可以接入生成 API,让引擎在场景展开时调用它们:

- 一个**图像生成 API** —— 场景画面、角色立绘、关键时刻
- 一个**BGM 生成 API** —— 跟随情绪自适应的背景音乐

于是同一个 agentic 世界可以呈现为一段完整的视听体验,而不只是一份文字记录。

> 在 **Build** 与游玩内部,引擎还会追踪 agent 提案*如何*被应用 —— **直接**、**受控(sandbox)**,或**自动** —— 并与 [router 模式](/docs/core-concepts/engine-modes)(fast / orchestrator / multi-agent)组合。详见下面各节。

<!-- section: build-mode -->
## Build 模式

创作模式。你直接(在任意编辑器里)编辑 `game/` 下的文件 —— 不会有 agent 回合被路由。适合:

- 搭建新的城镇 / NPC / 任务
- 修复一次游玩 session 暴露出的数据问题
- 快速测试 agent 对给定状态的叙述方式

既然 *你* 就是真相源,就没有审批门,也不涉及 router 模式。

<!-- section: sandbox-mode -->
## Sandbox 模式

Agent 运行产生**提案**,由你审阅并**逐回合批准**。在任何内容写入 `.neonrp/events.jsonl` 之前,diff 会先展示给你看。

在 TUI 中用 `/autoapply on|off` 即时切换审批门 —— `autoapply on` 实际上让 sandbox 在本 session 中变成 play;`autoapply off` 则恢复审批门。

**适合**:
- 试用你尚未完全信任其提案的新 agent
- 在保留否决权的前提下借助 AI 创作
- 调试 dispatcher / harness 行为 —— 每个提案都可见

<!-- section: play-mode -->
## Play 模式

GM 模式。Agent 生成提案,引擎**自动应用**。剧本式地读下来 —— 只有 schema 校验失败时你才会看到 diff。

这是玩家花费最多时间的模式。世界随故事推进而变化。想在冒险举动前后能回退,就先分支或打快照。

Router 模式在这里生效:`/router-mode fast` 用于最少路由,`/router-mode orchestrator` 用于跨领域一致性,`/router-mode multi-agent` 用于粘性的子 agent 委托。

<!-- section: tui-layout -->
## TUI 布局

顶部是单窗格的对话式 transcript,底部是输入行,右上角是状态栏。状态栏里的 `[AUTO]`/`[manual]` 标签反映当前的 play 模式。

```
┌─────────────────────────────────────────────────────────────────┐
│ project │ branch │ head │ turn │ [AUTO]/[manual] │ provider     │
├─────────────────────────────────────────────────────────────────┤
│   user     > look around                                        │
│   tool     read_context("harbor") -> 3 entities                 │
│   thinking …                                                    │
│   agent    The Shale rolls grey under dawn fog. …               │
├─────────────────────────────────────────────────────────────────┤
│ > _                                                             │
└─────────────────────────────────────────────────────────────────┘
```
