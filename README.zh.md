# WorldLines

**Language:** [English](./README.md) · [简体中文](./README.zh.md) · [日本語](./README.ja.md) · [한국어](./README.ko.md)

> **开源部分:** 本仓库中的示例世界、工具和协议 —— AGPL-3.0。可自由 fork、修改并发布你自己的世界。
> **不开源部分:** 引擎核心(`neonrp`)。免费游玩,不可 fork 或再分发。见 [LICENSE](LICENSE)。

<p align="center">
  <img alt="GitHub Stars" src="https://img.shields.io/github/stars/LudicDynamics/WorldLines?style=flat-square&color=8b5cf6" />
  <img alt="Watchers" src="https://img.shields.io/github/watchers/LudicDynamics/WorldLines?style=flat-square&color=8b5cf6" />
  <img alt="Forks" src="https://img.shields.io/github/forks/LudicDynamics/WorldLines?style=flat-square&color=8b5cf6" />
  <img alt="Issues" src="https://img.shields.io/github/issues/LudicDynamics/WorldLines?style=flat-square&color=8b5cf6" />
  <a href="https://hub.worldlines.gg"><img src="https://img.shields.io/badge/Live%20Demo-hub.worldlines.gg-8b5cf6?style=flat-square" /></a>
  <img alt="License" src="https://img.shields.io/badge/License-AGPL--3.0%20(examples)-blue?style=flat-square" />
  <img alt="LINUX DO" src="https://img.shields.io/badge/LINUX%20DO-WorldLines-8b5cf6?style=flat-square" />
</p>

<p align="center">
  <img src="./assets/hero.png" alt="WorldLines — 通往活世界的门" width="640" />
</p>

## 概述

**你能用它做什么？**

进入一个会记住你一切行为的世界 —— 在灰雾弥漫的北境港口下达攻防指令，在一列永不停站的黑暗列车上探索每个车厢的秘密，与一位失忆却温柔的治愈师对坐长谈而她真的会记得你说过的每一句话。你可以在几分钟内创建一个世界，设定它的规则、节奏与 NPC，也可以从公开目录中挑选他人创作的世界直接进入。这是实时运行的多智能体社会 —— 不是一对一聊天，是许多 AI 灵魂与你同在一个世界里彼此影响、彼此记住。

它是一台 agentic 模拟引擎。世界 agent 连着地点 agent；每个地点 agent 又连着住在那里的灵魂 agent。这里所有人都是 agent。你通过分身终端走进来。这不是聊天机器人，不是脚本游戏。

> 状态：**v0.2.0 — Hub 上线**（2026-06）· [立即游玩 →](https://hub.worldlines.gg)

---

## 团队与愿景

我们是一支由来自**东京大学、名古屋大学**的 PhD 和研究员，以及游戏从业者组成的跨专业（社会学、经济学、图形学、AI Agent、虚拟世界）团队 —— **Ludic Dynamics**。

我们热爱 TRPG（跑团）、galgame 与乙女游戏。当 AI 还没有普及之前，我们长期从事日文文化翻译的志愿者工作，在各种桌面游戏以及游戏图形引擎行业深耕，并曾经协助日本视觉小说作品在 Steam 发行。疫情开始后，我们一头扎进了 AI 角色扮演与叙事类游戏 —— 每个周末、每一个深夜，跑团、搭建世界、追逐那种"故事真的在呼吸"的感觉。

穿越时空在十多个国家之间辗转冒险，在异世界的世界里面探寻它过去的历史，一次一次死去重回某一天只为救回重视的人，辗转在平行时空中找到那唯一的世界线，召唤历史完成一次奔赴理想的战争。

WorldLines 就是这种执念的产物。

> Orchestrated Reality · 编排的真实。通过 Harness 模拟世界与 AI 灵魂 —— 世界具有物理一致性，NPC 具有心智一致性。不要为 agent 写代码。用 agent 来编排世界。

我们通过 harness 构建了「多智能体 × 世界智能体 × 灵魂智能体」系统。我们希望利用这个引擎进行：互动体验创造 · 多智能体社会实验 · Agent 研究推进 · 人格模型与世界模型的 benchmark。

---

## 演示视频

<p align="center">
  <a href="https://youtu.be/oofuC8BSehE">
    <img src="https://img.youtube.com/vi/oofuC8BSehE/maxresdefault.jpg" alt="WorldLines · 演示" width="640"/>
  </a>
</p>
<p align="center"><em>▶ 在 YouTube 观看演示</em></p>

---

## 快速上手

### 🖥️ 下载启动器

下载对应平台的启动器，双击即可安装。无需打开终端。

| 平台    | 文件                  | 下载 |
|---------|-----------------------|------|
| macOS   | `WorldLines.command`  | [最新版](https://worldlines.gg/WorldLines.command) |
| Windows | `WorldLines.bat`      | [最新版](https://worldlines.gg/WorldLines.bat)     |
| Linux   | `WorldLines.sh`       | [最新版](https://worldlines.gg/WorldLines.sh)      |

macOS / Linux 上下载后 `chmod +x` 一次，然后拖到桌面即可。

### ⌨️ 或通过终端安装

```bash
# macOS / Linux
curl -LsSf https://worldlines.gg/install.sh | sh

# Windows（PowerShell）
irm https://worldlines.gg/install.ps1 | iex
```

安装完成后：

```bash
./worldlines
```

启动 TUI 界面。从那里你可以创建新世界、浏览目录、或继续之前的存档。

> **首次运行会引导你设置 API。** 密钥保存在 `~/.neonrp/config.json`。[完整提供商指南 →](https://docs.worldlines.gg/docs/getting-started/quickstart)

### 🌐 或者直接在浏览器玩

无需安装。打开 **[hub.worldlines.gg](https://hub.worldlines.gg)**，登录，在浏览器中游玩。

---

## 截图

<p align="center">
  <img src="./assets/gameplay.jpg" alt="游戏画面 — 抵达石津镇" width="720" />
</p>
<p align="center"><em>游戏画面 — 在雾中抵达石津镇</em></p>

---

## 示例世界

### ⛩ Stoneford — 起始世界

灰雾北境的河港小镇。经典奇幻 TRPG · d20 骰子 · 10-agent 编排。旗舰示例：完整的小镇，含 NPC、任务、地下城、攻防机制。**[在线游玩 →](https://hub.worldlines.gg/play/worlds/stoneford)** · **[源码与文档 →](./examples/stoneford)**

### 更多世界

| 世界 | 玩法 | 在线 |
|---|---|---|
| **暗夜列车** | 开放世界 —— 想做什么都行，世界都记着 | [游玩 →](https://hub.worldlines.gg/play/worlds/dark-train) |
| **哥布林遭遇战** | 3 层地下城 —— 逐一击败 3 个哥布林 boss | [源码 →](./examples/goblin-ambush) |
| **世界线收束** | 时间漂移叙事 —— 发短信到过去 | [源码 →](./examples/worldline) |
| **樱坂走廊** | Clannad 式校园 · 情感叙事 | [源码 →](./examples/sakura-hallway) |

所有世界都在 [examples/](./examples/) —— 开源（AGPL-3.0），fork 并发布你自己的。

---

## 使用此引擎的其他项目

- **[Soul Talk](https://hub.worldlines.gg/play/souls/elena)** — 角色对话场景。Elena 会记住你。
- **[Worldline](./examples/worldline)** — 时间漂移叙事引擎。发短信到过去，看时间线重写。
- **即将推出：RP-Abyss** — TRPG 远征。DM + 骰子检定。

---

## 适合谁

### 🎮 AI 角色扮演玩家

你来自 **Character.AI、SillyTavern 或 AI 酒馆**。你喜欢深度的角色对话 —— 但世界总是忘掉你说过的话。

WorldLines 给你有**真实记忆**的角色。她们记得你三天前说过的话。她们有内心独白、意图、目标。而且她们不孤单 —— 她们和其他角色一起活在一个世界里，彼此记住。

→ [和 Elena 对话](https://hub.worldlines.gg/play/souls/elena) · [浏览角色目录](https://hub.worldlines.gg/souls)

### 📖 Galgame · 视觉小说爱好者

你喜欢 **Ren'Py、TyranoBuilder 和分支叙事** —— 但你厌倦了手写每一条路线。你想要故事*回应你*，而不是按预设路线走。

WorldLines 让你设定角色、世界规则和基调 —— agent 会实时生成故事。每一个选择都会激起涟漪。没有两次游玩是一样的。

→ [创建你的第一个世界](https://docs.worldlines.gg/docs/guides/creating-first-world) · [SillyTavern 导入 →](https://docs.worldlines.gg/docs/guides/sillytavern-import)

### ✍️ TRPG 主持人 · 世界创作者

你在 **Foundry VTT、Discord 或线下** 带团。你花在准备上的时间比实际游玩还多。

WorldLines 是一个 GM 引擎：你设定约束 —— 规则、NPC、基调 —— agent 替你跑世界。自动索引的 lore、每个 NPC 独立的记忆、掷骰裁判 agent。

→ [快速上手](https://docs.worldlines.gg/docs/getting-started/quickstart) · [Stoneford 起始世界](./examples/stoneford)

### 🔬 研究者 —— AI 人格 · 世界模型 · Multi-Agent

你研究人格模型、世界模型 benchmark 或多智能体社会。你需要一个**可复现的沙箱** —— 不是黑盒 API。

WorldLines 是**文件支撑、事件溯源、git-diffable** 的。每个 agent 决策、每次世界状态变化，都是一条纯文本事件，可以追踪、回放、度量。用不同模型跑同一个场景，对比输出，发布结果。

→ [核心概念](https://docs.worldlines.gg/docs/core-concepts/agents-orchestration) · [架构说明](#how-it-works)

### 🛠️ 开发者

你用 **Claude Code、LangGraph 或自定义 agent 管线**。你需要一个可以检查、fork、质疑的协议。

WorldLines 的示例、工具和协议是**开源的（AGPL-3.0）**。fork 一个世界，修改一个 agent，发布你自己的。引擎二进制文件免费游玩 —— 本地使用不需要 API key。

→ [examples/](./examples/) · [协议文档](https://docs.worldlines.gg/docs/protocol/overview)

---

## 工作原理

WorldLines 把游戏世界当作文件支撑、事件溯源的状态机。每一回合都是只追加的事件；快照让回溯变得高效。

**Agent 架构（3 层）:**

```
Layer 1: world-agent        — 状态 · 路由 · 叙事 · 归档
Layer 2: town-agent          — NPC、商店、导航
         dungeon-agent       — 探索
         combat-referee      — d20 骰子
         world-builder       — 地图更新
Layer 3:（未来）骰子/规则工具 agent
```

- **文件持久化的记忆与世界状态** — 一切都以纯 JSON 和 Markdown 存在磁盘上。
- **自动索引、自动注入上下文** — 无需手动维护 lorebook。
- **分支 / 撤销 / 重做** — 像 git 分支一样探索叙事分叉。
- **沙箱与回放** — 验证确定性。
- **本地优先模型** — GLM、OpenAI、LM Studio、Ollama。

---

## 教程

完整文档在 **[docs.worldlines.gg](https://docs.worldlines.gg)**：

| 主题 | 链接 |
|---|---|
| 快速开始 | [docs.worldlines.gg/docs/getting-started](https://docs.worldlines.gg/docs/getting-started) |
| 核心概念 | [docs.worldlines.gg/docs/core-concepts](https://docs.worldlines.gg/docs/core-concepts) |
| 指南 | [docs.worldlines.gg/docs/guides](https://docs.worldlines.gg/docs/guides) |
| Q&A / 对比 | [docs.worldlines.gg/docs/qa](https://docs.worldlines.gg/docs/qa) |

---

## 路线图

| 版本 | 状态 |
|---|---|
| **v0.1.9** — 引擎 (2026-04) | ✓ 10-agent 编排器 · Stoneford 起始世界 · Claude Code 运行时 |
| **v0.2.0** — Hub 上线 (2026-06) | ✓ WebHub · 在线游玩 · Soul Talk · 创作工坊 · Stripe · 封面 · 存档 |
| **v0.3.0** — 桌面版 (2026-06) | ◑ Tauri 桌面应用 · 多智能体社会 · 常驻世界 · 支付宝/微信 |
| **v1.0** — 协议 | ○ 稳定 WORLD/SOUL 协议 · 自托管 Web 版 |

完整路线图：[docs.worldlines.gg/docs/roadmap](https://docs.worldlines.gg/docs/roadmap)

---

## 许可证

**开源（AGPL-3.0）：** `examples/` 和 `tools/` 中的示例世界、角色包、工具和协议。

**不开源：** 引擎核心（`neonrp`）。专有预览版 —— 免费游玩，不可 fork。

## Star 历史

<p align="center">
  <a href="https://star-history.com/#LudicDynamics/WorldLines&Date">
    <img src="https://api.star-history.com/svg?repos=LudicDynamics/WorldLines&type=Date" alt="Star History Chart" width="640" />
  </a>
</p>

---

## 社区

- 官网：[worldlines.gg](https://worldlines.gg) · 文档：[docs.worldlines.gg](https://docs.worldlines.gg)
- Discord：[discord.gg/HJYWbdqWrE](https://discord.gg/HJYWbdqWrE)
- GitHub：[LudicDynamics/WorldLines](https://github.com/LudicDynamics/WorldLines)
- 联系：`info@worldlines.gg`

<p align="left">
  <img src="./assets/qrqq.png" alt="WorldLines QQ 群二维码" width="160" />
</p>

---

由 **nikoloside** 与 **redoctober** 开发，[Ludic Dynamics](https://ludicdynamics.com) 持续推进。

特别感谢 `llm-rpg-starter` 前身的早期参与者们：**Amber**、**琛琛**、**Claire**。
