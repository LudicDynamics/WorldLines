# CLI 参考

**Language:** [English](./CLI_REFERENCE.md) · [简体中文](./CLI_REFERENCE.zh.md) · [日本語](./CLI_REFERENCE.ja.md) · [한국어](./CLI_REFERENCE.ko.md)

> 状态：Beta — v0.1.0 的命令已稳定；flag 可能新增选项

`neonrp` 命令行工具的完整参考。运行 `neonrp <cmd> --help` 可获取权威、最新的 flag 列表。

## 命令一览

| 命令        | 用途                                           |
|-------------|------------------------------------------------|
| `init`      | 在当前目录创建 `.neonrp/`                      |
| `game`      | 脚手架生成起步世界（templates）                |
| `run`       | 把一个 query 派发给某个 agent                  |
| `save`      | 快照当前状态                                   |
| `load`      | 从快照恢复                                     |
| `branch`    | 创建或切换 branch                              |
| `undo`      | head 后退一个 event                            |
| `redo`      | 重做被 undo 的 event                           |
| `validate`  | 用 schema 校验 `game/`                         |
| `index`     | 构建 / 更新实体索引                            |
| `find`      | 搜索实体                                       |
| `context`   | 对某个 query 做相关性排序                      |
| `agent`     | agent 生命周期                                 |
| `import`    | 导入 SillyTavern / 外部角色卡                  |
| `sandbox`   | sandbox 管理                                   |
| `replay`    | Replay 与确定性校验                            |
| `tui`       | 启动终端 UI                                    |

## 项目生命周期

```bash
neonrp init
neonrp game new --template stoneford    # 或：default / isekai / kagura-island
neonrp validate
neonrp index build
```

## 游玩循环

```bash
neonrp run "look around"
neonrp save checkpoint-1
neonrp undo
neonrp redo
neonrp branch try-stealing
```

## Agents

```bash
neonrp agent list --json
neonrp agent new narrator
neonrp agent show town-agent
neonrp agent run town-agent --query "describe the harbor" --provider glm
neonrp agent run town-agent --query "add a merchant" --apply
neonrp agent logs --tail 10
```

### Agent run 选项

| 选项            | 用途                                                       |
|-----------------|------------------------------------------------------------|
| `--query, -q`   | 指令（必填）                                               |
| `--provider`    | 覆盖配置里的 provider（glm/openai/lmstudio/ollama/stub）   |
| `--fixture`     | Stub provider 使用的 proposal JSON 文件                    |
| `--apply`       | 预览后直接 apply                                           |
| `--agentic`     | 多轮 agentic 循环                                          |
| `--json`        | 机器可读输出                                               |

## 检索

```bash
neonrp find "harbor" --kind location --json
neonrp context "stoneford guild" --limit 5
```

## 导入

```bash
neonrp import sillytavern-card card.png --id mira-ashford
neonrp import sillytavern-card card.json
```

## Sandbox

```bash
neonrp save pre-experiment
neonrp sandbox new try-rebellion --from pre-experiment --switch
neonrp sandbox list
neonrp sandbox switch main
neonrp sandbox drop try-rebellion --force
```

## Replay

```bash
neonrp replay verify --from pre-experiment
neonrp replay verify --from pre-experiment --to 12 --json
neonrp replay checkout --from pre-experiment --to 5 --to-branch rollback
```

## TUI

```bash
neonrp tui
neonrp tui --branch experiment
neonrp tui --provider lmstudio
neonrp tui --continue
neonrp tui --import-card card.png --import-id world-card
neonrp tui --verbose
```

## 退出码

| 码   | 含义                                                       |
|------|------------------------------------------------------------|
| 0    | 成功                                                       |
| 1    | 通用错误（校验失败、未找到等）                             |
| 2    | 系统错误（未初始化、adapter 失败）                         |

## 环境变量

| 变量                | 用途                          |
|---------------------|-------------------------------|
| `OPENAI_API_KEY`    | OpenAI                        |
| `GLM_API_KEY`       | 智谱 GLM                      |
| `ANTHROPIC_API_KEY` | Anthropic                     |
| `NEONRP_E2E_LLM`    | 启用真实 endpoint 测试        |

项目根目录的 `.env` 会自动加载。

## 另见

- [TUI_GUIDE.zh.md](TUI_GUIDE.zh.md)
- [CONCEPTS.zh.md](CONCEPTS.zh.md)
