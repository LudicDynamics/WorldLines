---
title: "CLI 参考"
description: "核心 `neonrp` 命令。完整参数以 `worldlines <cmd> --help` 为准。"
---

<!-- section: overview -->
## 命令总览

| 命令        | 用途                                           |
|-------------|------------------------------------------------|
| `init`      | 在当前目录创建 `.neonrp/`                      |
| `game`      | 脚手架起步世界(模板)                          |
| `run`       | 把查询派发给 agent                              |
| `save`      | 为当前状态打快照                                |
| `load`      | 从快照恢复                                      |
| `branch`    | 创建或切换分支                                  |
| `undo`      | head 后退一个事件                               |
| `redo`      | 重新应用被撤销的事件                            |
| `validate`  | 对 `game/` 做 schema 校验                      |
| `index`     | 构建 / 更新实体索引                             |
| `find`      | 搜索实体                                        |
| `context`   | 对查询做相关度排序                              |
| `agent`     | Agent 生命周期(new / list / show / run / apply / logs / context / path) |
| `import`    | 导入 SillyTavern / 外部卡片                     |
| `sandbox`   | Sandbox 管理                                    |
| `replay`    | Replay 与确定性校验                             |
| `tui`       | 启动 Terminal UI                                |

<!-- section: project -->
## 项目生命周期

```bash
worldlines init                           # 创建 .neonrp/
neonrp game new --template stoneford-orch  # 模板:default / kagura-island / soul-talk / stoneford-elena / stoneford-orch
neonrp validate                       # 对 game/ 做 schema 校验
neonrp index build                    # 重建检索索引
```

<!-- section: play-loop -->
## Play 循环

```bash
neonrp run "look around"
neonrp save checkpoint-1
neonrp load checkpoint-1
neonrp undo
neonrp redo
neonrp branch try-stealing
```

<!-- section: agents -->
## Agent

```bash
neonrp agent list --json
neonrp agent new narrator
neonrp agent show town-agent
neonrp agent path town-agent                            # 打印 agent 目录
neonrp agent run town-agent --query "describe the harbor" --provider glm
neonrp agent run town-agent --query "add a merchant" --apply
neonrp agent apply town-agent --proposal proposal.json --dry-run
neonrp agent context town-agent --query "harbor" --limit 8
neonrp agent logs --tail 10
```

### `agent run` 选项

| 选项           | 用途                                              |
|----------------|---------------------------------------------------|
| `--query`, `-q` | 指令(必填)                                      |
| `--provider`   | 覆盖配置中的 provider(glm / openai / lmstudio / ollama / stub) |
| `--fixture`    | Stub provider 的提案 JSON 文件                    |
| `--apply`      | 预览后直接应用                                    |
| `--json`       | 机器可读输出                                      |

<!-- section: retrieval -->
## 检索

```bash
neonrp find "harbor" --kind location --json
neonrp context "stoneford guild" --limit 5
```

`find` 做实体搜索;`context` 返回某个查询的相关实体排序(当配置了 embedding 时为模糊 + 向量混合)。

<!-- section: import -->
## 导入

```bash
neonrp import sillytavern-card card.png --id mira-ashford
neonrp import sillytavern-card card.json
```

导入 SillyTavern(酒馆)角色卡(JSON 或带 tEXt 的 PNG)。参见 [SillyTavern 导入指南](/docs/guides/sillytavern-import)。

<!-- section: sandbox-replay -->
## Sandbox 与 Replay

```bash
neonrp save pre-experiment
neonrp sandbox new try-rebellion --from pre-experiment --switch
neonrp sandbox list
neonrp sandbox switch main
neonrp sandbox drop try-rebellion --force

neonrp replay verify --from pre-experiment
neonrp replay verify --from pre-experiment --to 12 --json
neonrp replay checkout --from pre-experiment --to 5 --to-branch rollback
```

<!-- section: tui -->
## TUI

```bash
neonrp tui                               # 默认
neonrp tui --branch experiment           # 指定分支
neonrp tui --provider lmstudio           # 覆盖 provider
neonrp tui --continue                    # 继续上次 session
neonrp tui --new                         # 强制新开 session
neonrp tui --import-card card.png --import-id world-card
neonrp tui --verbose                     # 流式输出原始 LLM 交互
```

<!-- section: slash-commands -->
## TUI —— 斜杠命令

在 TUI 中,`/<cmd>` 用于触发一个动作。完整列表:

### 会话与历史

| 命令         | 用途                                                    |
|--------------|---------------------------------------------------------|
| `/new`        | 开启一个全新的对话 session                              |
| `/continue`   | 恢复当前分支的上次对话                                  |
| `/sessions`   | 列出按分支保存的 session                                |
| `/clear`      | 清空对话历史                                            |
| `/copy`       | 把对话复制到剪贴板                                      |
| `/compact`    | 压缩对话历史                                            |
| `/stats`      | 显示对话统计                                            |
| `/files`      | 列出近期修改的文件                                      |

### 世界与状态

| 命令                                   | 用途                                            |
|----------------------------------------|-------------------------------------------------|
| `/init`                                | 在当前目录初始化项目                            |
| `/game new`                            | 从模板脚手架一个新世界                          |
| `/worlds`                              | 浏览 `~/.worldlines/games/` 下的世界           |
| `/worldlines`                          | 引导式世界选择器(模型 + 世界 + 启动)           |
| `/save [name]`                         | 为状态打快照                                    |
| `/load [name]`                         | 从快照恢复                                      |
| `/branch [name\|list]`                 | 创建 / 切换 / 列出分支                          |
| `/undo` · `/redo`                       | head 后退 / 前进                                |
| `/sandbox [new\|list\|switch\|drop]`     | 管理 sandbox                                    |
| `/validate`                            | 对 `game/` 做 schema 校验                      |
| `/index [build\|update]`                | 重建 / 更新检索索引                             |
| `/find <keyword>`                      | 搜索实体                                        |
| `/context <query>`                     | 对查询做相关度排序                              |
| `/export-world [output.zip]`           | 把 `game/` + `.neonrp/` 打包为 .zip           |
| `/load-world <zip>`                    | 把导出的 zip 还原到 `~/.worldlines/games/`     |
| `/import sillytavern-card <file>`      | 导入一张 SillyTavern 角色卡                     |
| `/replay [verify\|checkout]`            | Replay 校验                                     |

### 模式与路由

| 命令                                              | 用途                                           |
|---------------------------------------------------|------------------------------------------------|
| `/mode [build\|sandbox\|play]`                   | 切换 play 模式                                 |
| `/router-mode [fast\|orchestrator\|multi-agent]` | 切换 router 执行模式                           |
| `/autoapply [on\|off\|status]`                    | 切换 sandbox 自动应用                          |
| `/verbose [on\|off\|status]`                      | 切换 verbose 调试模式                          |
| `/debug`                                        | 切换 MCP 调试模式                              |

### Agent 与运行

| 命令                                                                          | 用途                                              |
|-------------------------------------------------------------------------------|---------------------------------------------------|
| `/run <query>`                                                                | 显式执行 agent 查询                                |
| `/agent [list\|show <name>\|run <name>\|new <name>]`                            | Agent 生命周期                                    |
| `/apply`                                                                      | 在 sandbox 模式下应用待定提案                     |
| `/skills`                                                                     | 列出可用 skills                                   |

### Provider 与设置

| 命令                                                                | 用途                                               |
|---------------------------------------------------------------------|----------------------------------------------------|
| `/models [name\|list\|set <name>\|show <name>]`                      | 快速切换模型                                       |
| `/auth [list\|add\|set\|rm\|show]`                                   | 管理命名的模型配置                                 |
| `/wl-model [preset]`                                               | 切换 WorldLines 模型预设(glm / opus)             |
| `/config [show\|set <key> <value>]`                                 | 查看 / 设置配置                                    |
| `/settings`                                                         | 打开统一的模型 / api key / discord 设置            |
| `/locale [auto\|en\|zh\|ja\|ko]`                                    | 切换 UI 语言                                       |
| `/mcp [status\|restart <server>]`                                   | MCP 服务器管理                                     |
| `/bridge [status\|start <name>\|stop <name>]`                        | 运行时管理 Discord / Telegram 桥接                 |
| `/update [check\|apply\|status\|channel <name>]`                     | 检查 / 应用 worldlines 更新                            |

### 其他

| 命令           | 用途                                      |
|----------------|-------------------------------------------|
| `/help`        | 显示帮助                                  |
| `/quit` · `/q`  | 退出 TUI                                  |

<!-- section: exit-codes -->
## 退出码

| 退出码 | 含义                                              |
|--------|---------------------------------------------------|
| 0      | 成功                                              |
| 1      | 一般错误(校验失败、未找到等)                    |
| 2      | 系统错误(未初始化、adapter 失败)                |

<!-- section: env -->
## 环境变量

| 变量                | 用途                        |
|---------------------|-----------------------------|
| `OPENAI_API_KEY`    | OpenAI                      |
| `GLM_API_KEY`       | 智谱 GLM                    |
| `ANTHROPIC_API_KEY` | Anthropic                   |
| `NEONRP_E2E_LLM`    | 启用真实端点测试            |

项目根目录下的 `.env` 会被自动加载。
