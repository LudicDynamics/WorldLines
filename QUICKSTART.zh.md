# Quickstart —— 30 分钟开启你的第一个回合

**Language:** [English](./QUICKSTART.md) · [简体中文](./QUICKSTART.zh.md) · [日本語](./QUICKSTART.ja.md) · [한국어](./QUICKSTART.ko.md)

> 状态：Beta — 覆盖默认的 stoneford 起步路径

本指南假设你已经完成 [INSTALL.zh.md](INSTALL.zh.md) 的步骤，并且 `neonrp --help` 能输出命令列表。

## 1. 创建项目（2 分钟）

```bash
mkdir my-world && cd my-world
neonrp init
```

这会在当前目录生成 `.neonrp/`，其中包含 `manifest.json` 和一个 `config.json` 模板。此时还没有世界——只是一个空项目。

## 2. 搭建 stoneford 起步模板（3 分钟）

```bash
neonrp game new --template stoneford
```

现在你有：

```
my-world/
├── .neonrp/
│   ├── manifest.json
│   └── config.json
├── agents/
│   ├── orchestrator/
│   ├── town-agent/
│   ├── dungeon-agent/
│   ├── combat-referee/
│   ├── world-builder/
│   └── rules-referee/
└── game/
    ├── meta/
    ├── player/
    ├── towns/
    ├── dungeons/
    ├── rules/
    ├── lore/
    └── world/
```

示例世界的内容见 [templates/stoneford/](templates/stoneford/README.zh.md)。

## 3. 配置 provider（5 分钟）

编辑 `./.neonrp/config.json`，从 [INSTALL.zh.md](INSTALL.zh.md#llm-provider-配置) 中挑一段配置块。导出 API key：

```bash
export GLM_API_KEY=sk-...
# 或
export OPENAI_API_KEY=sk-...
```

校验世界：

```bash
neonrp validate
neonrp index build
```

## 4. 启动 TUI（1 分钟）

```bash
neonrp tui
```

右上角状态栏显示项目名、分支（`main`）、head event（`0`）以及 provider。

## 5. 你的第一个回合（5 分钟）

在输入行里键入：

```
look around
```

Orchestrator 会路由到 `town-agent`，后者读取 Stoneford 的小镇数据并叙事。你会看到：

1. 一段 **thinking** 流（默认折叠）。
2. 一个 **tool use** 指示——agent 正在读取文件。
3. 最终的 **narrative** 响应。
4. 一条新的 **event** 追加到日志，head 从 `0` 前进到 `1`。

## 6. 存一个检查点

在 TUI 中：

```
/save opening-scene
```

或者从另一个 shell：

```bash
neonrp save opening-scene
```

## 7. 分支一个实验（5 分钟）

尝试一个冒险选择——比如偷 Old Reed 的钱：

```
/branch try-stealing
steal the coin pouch while Old Reed is turned away
```

WorldLines 会把这些写到新分支。main 分支保持不变。

## 8. Undo / 回退

```
/undo
```

head event 往回走一步。输入 `/redo` 可重做。

## 9. 加载存档

```bash
neonrp load opening-scene
```

或者用 `--continue` 重启 TUI 来接续上次会话。

## 10. 下一步？

- 速读 [CONCEPTS.zh.md](CONCEPTS.zh.md) 了解 events、snapshots、sandboxes。
- 试试 `/mode build`，让 agent 向 Stoneford 添加一个新 NPC，观察 **plan → diff → apply** 流水线。
- 阅读 `templates/stoneford/README.zh.md` 并直接编辑某个小镇的 JSON。
- 查阅 [CLI_REFERENCE.zh.md](CLI_REFERENCE.zh.md) 了解所有子命令。

## 故障排查

| 症状                                 | 处理                                                 |
|--------------------------------------|------------------------------------------------------|
| `neonrp: command not found`          | 重新执行 `uv tool install -e .`                      |
| TUI 渲染乱码                         | 换用 iTerm2 / Ghostty / Alacritty；设置 UTF-8        |
| `provider not configured`            | 检查 `.neonrp/config.json` 和环境变量                |
| `validate` 报告 schema 错误          | 执行 `neonrp validate --json` 查看详情               |
| Agent 挂起 / 输出为空                | 用 `neonrp tui --verbose` 查看原始 LLM 流量          |
