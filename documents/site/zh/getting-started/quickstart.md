---
title: "快速开始"
description: "从下载到你的第一个活世界 —— Launcher、浏览器,或 CLI。"
---

<!-- section: launcher -->
## 1. 本地运行 —— Web UI(推荐)

最快的入口。下载 WorldLines,运行后**默认在浏览器里打开本地 Web UI** —— 无需配置终端。

在 [worldlines.gg](https://worldlines.gg) → **Download**,获取适合你系统的安装文件:

- **macOS**:`WorldLines.command`
- **Windows**:`WorldLines.bat`
- **Linux**:`WorldLines.sh`(先 `chmod +x` 再运行)

它是自包含的 —— 必要时会自动引导 Python 环境,并打开本地 Web UI。三个官方世界开箱即玩,可直接**导入并游玩**:

- **Spice & Witch** —— 香料商队 × 不老魔女 × 女巫追猎
- **Kagura Island**(7 个灵魂)—— 和风悬疑 · 时间循环
- **Stoneford · Elena** —— 失忆女主 + 同伴(Elena & Rowan)

三个都是**多智能体村庄** —— 一个世界 agent 包裹起一群独立灵魂。继续一个已存档的 session,或创建你自己的。首次运行会引导你选择 LLM provider(第 5 步)—— 你永远不必手动编辑 `config.json`。

<!-- section: tui -->
## 2. WorldLines TUI(终端)

更喜欢终端?同一台引擎也提供 **WorldLines TUI** —— Claude Code 风格的对话式终端,游玩与构建皆可。

```bash
pip install worldlines        # 或:uv tool install worldlines
neonrp           # 终端启动器:选世界,开局
```

同样在本地运行,能玩完整的多智能体村庄。进阶的可脚本化用法见第 6 步。

<!-- section: webhub -->
## 3. Hub —— 浏览器,零安装

不想装任何东西?打开 [hub.worldlines.gg](https://hub.worldlines.gg),登录即玩。云端 agent 替你跑 —— 无需任何设置。

- 浏览 **世界** 和 **灵魂** 的目录
- 与 [Elena](https://hub.worldlines.gg/play/souls/elena) 这样的灵魂对话,或试玩较轻量的编排世界
- 用 AI 辅助工坊创建你自己的内容并发布到公开注册表

Hub 目前运行 **fast** 与 **orchestrator** 世界。完整的**多智能体村庄**(上面三个官方世界)在本地运行 —— 用 Web UI 或 TUI。

<!-- section: worlds -->
## 4. 官方世界

三个官方世界都是**多智能体村庄** —— 一个世界 agent 包裹起一群独立灵魂构成的社会。每个都可以在 **Web UI** 里导入、用 **TUI** 游玩,或从 **CLI** 运行(第 6 步)。

| 世界 | 是什么 | 模式 |
|---|---|---|
| **Spice & Witch** | 香料商队 × 不老魔女 × 女巫追猎 | multi-agent |
| **Kagura Island** | 和风悬疑 · 时间循环 · **7 个独立灵魂** | multi-agent |
| **Stoneford · Elena** | 失忆女主 + 同伴 · **Elena & Rowan** | multi-agent |

多智能体村庄在**本地**运行(Web UI 或 TUI)。想在浏览器里零安装试玩,去 [Hub](https://hub.worldlines.gg) 玩较轻量的编排世界或与灵魂对话。

<!-- section: configure-provider -->
## 5. 选择 LLM provider

WorldLines 运行在 LLM 之上,接入方式有**三种**。launcher 会根据你的选择一步步引导,不需要手动编辑 `config.json`。

### 方式一:Worldlines 账号 —— 零 API key

进游戏后 `/login`(或在启动器的设置里登录):回合走 Worldlines 的模型中转,商量谈没谈妥由 Jev 判官判断,不用自己的 key。0.4.x 的 Claude Code(MCP)预设自 1.0.3 起去掉了。

### 方式二:第三方 provider + API key

首次运行时,launcher 会提示你选择 provider 并粘贴 key。key 会自动写入 `~/.neonrp/config.json`,之后每次运行都会复用。

| Provider         | 获取 key 的地址                                                                         | 说明                          |
|------------------|----------------------------------------------------------------------------------------|-------------------------------|
| **GLM-4-Flash**  | [zhipuai.cn](https://zhipuai.cn)                                                        | **自带免费额度**              |
| Anthropic        | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys)     | 按量计费                      |
| OpenAI           | [platform.openai.com/api-keys](https://platform.openai.com/api-keys)                   | 按量计费                      |
| DeepSeek         | [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys)               | 按量计费                      |
| OpenRouter       | [openrouter.ai/keys](https://openrouter.ai/keys)                                        | 聚合平台 —— 一把 key,多种模型 |

### 方式三:OpenAI 兼容的自定义端点

如果你在本地跑模型服务(**Ollama**、**LM Studio**、**vLLM** 等),或者有自己的 OpenAI 兼容后端,把 WorldLines 指向它的 URL 即可,不需要云端 API key。在设置流程中选择 **"Custom"**,填入 `base_url` 和可选的鉴权信息。

---

**key 存放位置:**`~/.neonrp/config.json`,以及你设置的环境变量(`ANTHROPIC_API_KEY`、`OPENAI_API_KEY`、`GLM_API_KEY` 等)。launcher 会优先读环境变量,然后再读配置文件。

**事后想改:**在 launcher 菜单里选 `[3] settings / api`,可以添加模型、切换默认 provider 或测试连接。

<!-- section: advanced-cli -->
## 6. 进阶 —— CLI(开发者 / 研究者)

更喜欢终端,或者想要一个可脚本化的 harness 来做实验?同一台引擎也提供 `worldlines` CLI。

```bash
pip install worldlines        # 或:uv tool install worldlines
# 或一行命令安装器(macOS / Linux / WSL):
curl -fsSL https://worldlines.gg/install.sh | sh
```

打开 TUI,或直接从仓库运行一个示例世界:

```bash
neonrp           # 终端启动器:选世界,开局

git clone https://github.com/LudicDynamics/WorldLines.git && cd WorldLines

# 两个内置世界(其他官方世界:在本地 Hub 用 Worldlines 账号登录获取):
neonrp template build worldlines/templates/pct-house.template /tmp/pct-house && neonrp play --project /tmp/pct-house   # 灰橡宅
neonrp template build worldlines/templates/stoneford-town.template /tmp/stoneford-town && neonrp play --project /tmp/stoneford-town   # 石津镇

# 也有编排式世界(同样能在 Hub 上玩):
neonrp tui --from examples/orch/stoneford
```

**走一回合:**输入 `look around`。世界 agent 叙述场景并路由到正确的子 agent —— 或者,在多智能体世界里,唤醒场景中的灵魂。你会看到一条思考流、agent 读文件时的工具调用、叙述,以及一条被追加到日志里的新 **event**。

**存档 · 分支 · 回退:**`/save opening-scene` 打检查点;`/branch try-stealing` 在新分支上探索一条冒险路线;`/undo` 回退;`neonrp load opening-scene` 还原。主分支保持不变。

需要 Python 3.11+(推荐 3.12)和一个 256 色 UTF-8 终端。

<!-- section: what-next -->
## 接下来做什么?

- [核心概念](/docs/core-concepts/worlds) —— 世界如何记住:事件、快照、分支
- 在 **Web UI** 里**导入并游玩**官方世界,再到创作工坊里调整它们
- **[在 WebHub 上游玩](https://hub.worldlines.gg)** —— 包括像 [Elena](https://hub.worldlines.gg/play/souls/elena) 这样的多智能体灵魂
- 进阶(CLI):[CLI 参考](/docs/guides/world-editor) —— `/mode build`、直接编辑 JSON、所有子命令
