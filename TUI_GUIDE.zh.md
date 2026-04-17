# TUI 指南

**Language:** [English](./TUI_GUIDE.md) · [简体中文](./TUI_GUIDE.zh.md) · [日本語](./TUI_GUIDE.ja.md) · [한국어](./TUI_GUIDE.ko.md)

> 状态：Beta — 布局已稳定；键位配置将在 v0.2 开放

WorldLines 的 TUI 是一个 Claude-Code 风格的对话式终端，用于游玩与构建世界。

## 启动

```bash
neonrp tui                               # 默认
neonrp tui --branch experiment           # 指定 branch
neonrp tui --provider lmstudio           # 覆盖 provider
neonrp tui --continue                    # 接续上次会话
neonrp tui --new                         # 强制新会话（默认）
neonrp tui --import-card card.png        # 首回合前先导入
neonrp tui --verbose                     # 流式输出原始 LLM 流量
```

只完成 `init` 的空目录可以直接进入 build 模式。`game new` 是可选的——它只是额外添加默认世界和 play-agent 脚手架。

## 布局

顶部是单窗格对话式 transcript，底部是输入行，右上角是状态栏。

```
┌─────────────────────────────────────────────────────────────────┐
│ project │ branch │ head │ turn │ [AUTO]/[manual] │ provider     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Transcript                                                     │
│   user     > look around                                        │
│   tool     read_context("harbor") -> 3 entities                 │
│   thinking …                                                    │
│   agent    The Shale rolls grey under dawn fog. …               │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ > _                                                             │
├─────────────────────────────────────────────────────────────────┤
│ q Quit │ Ctrl+K Commands │ Esc Interrupt │ F6 Copy              │
└─────────────────────────────────────────────────────────────────┘
```

## 模式

通过 `/mode <name>` 切换：

| 模式      | 行为                                                          |
|-----------|---------------------------------------------------------------|
| `build`   | 直接文件编辑 + 自然叙事。用于创作世界。                       |
| `sandbox` | Proposal 流水线。每次修改都需批准。                           |
| `play`    | GM 模式。auto-apply 开启，完全沉浸。                          |

## 斜杠命令

| 命令                            | 用途                                        |
|---------------------------------|---------------------------------------------|
| `/init`                         | 在当前目录初始化项目                        |
| `/game new [--template T]`      | 脚手架生成起步世界                          |
| `/mode <build\|sandbox\|play>`  | 切换交互模式                                |
| `/save [name]`                  | 快照                                        |
| `/load <name>`                  | 从快照恢复                                  |
| `/branch <name>`                | 创建或切换 branch                           |
| `/undo` / `/redo`               | head 前后移动                               |
| `/run <query>`                  | 显式 dispatcher 调用                        |
| `/files`                        | 显示文件导航器                              |
| `/skills`                       | 列出 builtin + 本地 skill                   |
| `/agents`                       | 列出 agent 及其 trigger                     |
| `/import sillytavern-card`      | 导入角色卡                                  |
| `/sessions`                     | 会话选择器                                  |
| `/continue` / `/new`            | 会话选择                                    |
| `/verbose on\|off\|status`      | 切换 verbose 诊断                           |
| `/clear`                        | 清屏（状态不动）                            |
| `/help`                         | 应用内帮助                                  |

Tab 自动补全命令；Enter 提交。

## 键位

| 键           | 行为                                             |
|--------------|--------------------------------------------------|
| `q`          | 退出                                             |
| `Ctrl+Q`     | 安全退出（立即返回终端）                         |
| `Esc`        | 打断进行中的 LLM 回合                            |
| `Ctrl+K`     | 命令面板                                         |
| `Ctrl+P`     | 命令面板（备用）                                 |
| `Enter`      | 提交                                             |
| `F6`         | 复制完整 transcript                              |

## 流式输出

三路流交织显示：

- **user** —— 你的输入
- **tool** —— 工具调用（`read_context`、`find`、文件读取……）
- **thinking** —— 默认折叠，展开查看推理过程
- **agent** —— 最终叙事

右上角状态栏有一个实时 token 计数器。

## 会话持久化

Session 按 branch 持久化。`--continue` 恢复当前 branch 的上次会话；`/sessions` 打开选择器以跨 branch 跳转。

## 故障排查

| 症状                            | 处理                                             |
|---------------------------------|--------------------------------------------------|
| 字符乱码                        | 使用 iTerm2 / Ghostty / Alacritty，UTF-8         |
| 颜色异常                        | 确认 `TERM` 支持 256 色                          |
| TUI 卡住                        | 按 `Esc` 打断当前回合                            |
| Agent 输出为空                  | 用 `--verbose` 启动检查流量                      |
| "not initialized"               | 执行 `/init` 或 `neonrp init`                    |

## 另见

- [CLI_REFERENCE.zh.md](CLI_REFERENCE.zh.md)
- [CONCEPTS.zh.md](CONCEPTS.zh.md)
- [QUICKSTART.zh.md](QUICKSTART.zh.md)
