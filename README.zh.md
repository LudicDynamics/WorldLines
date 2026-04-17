# WorldLines

**Language:** [English](./README.md) · [简体中文](./README.zh.md) · [日本語](./README.ja.md) · [한국어](./README.ko.md)

<p align="center">
  <img src="./assets/hero.png" alt="WorldLines — 通往活世界的门" width="640" />
</p>

<p align="center"><em>YouTube 预告片 — 即将上线。</em></p>

> 状态：Preview（v0.1.0 — 2026-04-17 公开预览版）

> *从 AI 聊天到 Agentic AIRP。*
> 一个文件托底、事件溯源的活世界引擎。

WorldLines 是由 [Ludic Dynamics](https://ludic-dynamics.com) 打造的
Agentic AIRP engine（AI RolePlay engine）。引擎可执行文件代号 `neonrp`，
发行品牌名为 **WorldLines**。

它把游戏世界当作一台带版本、以文件为后端的状态机——让你的每次游玩、
每次编辑、每个 Agent 都变成可复现的产物，而不是转瞬即逝的聊天记录。

---

## 为什么是 WorldLines

传统的"和 AI 聊天"界面会在 context window 填满的那一刻丢失一切。
WorldLines 提供真正的引擎级保证：

- **Event-sourced state。** 每一回合都是 append-only 的 Events，
  Snapshots 让回溯变快。
- **Branch / Undo / Redo。** 像 git 分支那样探索叙事分叉。
- **Sandbox & Replay。** 隔离环境中做实验；校验确定性。
- **Multi-Agent 编排。** Orchestrator 把路由分发给领域 Agents
  （town / dungeon / combat-referee / world-builder / rules-referee），
  它们共享同一份状态。
- **Plan → Diff → Apply。** LLM 输出结构化文件操作，落地前可审阅。
- **File-backed world。** `game/` 只是 JSON 和 Markdown；用 git
  版本化，用任何编辑器改。
- **Rich TUI。** Claude-Code 风格的对话式终端，游玩与构建共用。
- **Local-first 模型。** GLM、OpenAI、LM Studio、Ollama 都支持。

### 定位——对比 Claude Code

|              | Claude Code                     | WorldLines                              |
|--------------|---------------------------------|-----------------------------------------|
| 领域         | 代码编辑 / 软件 agent           | 游戏世界 / AIRP agent                   |
| 状态单元     | 文件 + git                      | Events + Snapshots + branches           |
| 主循环       | Plan → Edit → Test              | Plan → Diff → Apply → Save              |
| 附带内容     | 你自备仓库                      | 随附 `stoneford` 起步模板               |
| Sandbox      | Shell / 容器                    | 引擎原生 Sandbox + Replay               |

Claude Code 是你写代码的 IDE，WorldLines 就是你孕育活世界的 IDE。

> 说明：目前 WorldLines 的 harness 比 Claude Code 更严格——它依赖完整的上下文才能可靠地进行 orchestration。这是为了换取更高的确定性与更易调试的刻意取舍，而不是缺陷。

> **为什么是闭源引擎 + 开放数据？** WorldLines 引擎以闭源预览形式发布，是为了在高速迭代中保持 orchestration 的一致性与保真度。而游戏数据格式、起步世界（如 Stoneford）以及集成协议则保持开放，用以孕育一个可互通的 AIRP 生态。

---

## 快速上手

```bash
# 1. 安装（其他方式见 INSTALL.zh.md）
uv tool install -e /path/to/worldlines

# 2. 脚手架生成并运行 stoneford 起步模板
mkdir my-world && cd my-world
neonrp init
neonrp game new --template stoneford

# 3. 在 TUI 中游玩
neonrp tui
```

输入 `look around` 并回车。这就是你的第一个 agentic 回合。

30 分钟完整流程见 [QUICKSTART.zh.md](QUICKSTART.zh.md)。

---

## 模块地图

- [INSTALL.zh.md](INSTALL.zh.md) — 通过 wheel、源码或 `uv tool` 安装
- [QUICKSTART.zh.md](QUICKSTART.zh.md) — 30 分钟首次游玩指南
- [CONCEPTS.zh.md](CONCEPTS.zh.md) — Events、Snapshots、branches、Agents、Sandboxes
- [CLI_REFERENCE.zh.md](CLI_REFERENCE.zh.md) — 全部 `neonrp` 命令
- [TUI_GUIDE.zh.md](TUI_GUIDE.zh.md) — 终端 UI 参考
- [RELEASE_NOTES.zh.md](RELEASE_NOTES.zh.md) — v0.1.0 范围与路线图
- [templates/stoneford-worldlines/](templates/stoneford-worldlines/README.zh.md) — 示例世界与 Agents
- [CONTRIBUTING.zh.md](CONTRIBUTING.zh.md) — 如何贡献
- [LICENSE](LICENSE) — 闭源预览条款

## 社区与联系方式

- Issue 与讨论：GitHub（链接将于 2026-04-17 D-Day 公布）
- 创始人 / 维护者：Ludic Dynamics（日本东京）
- 联系邮箱：`hello@ludic-dynamics.com`（占位）

---

## 版权与鸣谢

Copyright © 2026 worldlines-nikoloside, redoctober. 保留所有权利。

WorldLines 是一款闭源引擎，仅以预览形式发布供评估使用。未授予任何用于
再利用、再分发或衍生作品的许可。完整条款见 [LICENSE](LICENSE)。

感谢 Ludic Dynamics 社区的同行者，感谢 amber 以及其他让本次发布成为
可能的朋友。

*WorldLines 与 Ludic Dynamics 是 Ludic Dynamics 的商标。*
