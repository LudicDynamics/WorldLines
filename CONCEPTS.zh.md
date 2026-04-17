# 核心概念

**Language:** [English](./CONCEPTS.md) · [简体中文](./CONCEPTS.zh.md) · [日本語](./CONCEPTS.ja.md) · [한국어](./CONCEPTS.ko.md)

> 状态：Beta — 概念模型已稳定；内部实现可能调整

WorldLines 围绕一小组基本单元设计，理解它们就能把握引擎的其余部分。

## Events

世界中的每一次变更都是一条 **append-only event**，写入 `.neonrp/events.jsonl`。一条 event 的样貌：

```json
{
  "id": 42,
  "ts": "2026-04-17T10:03:11Z",
  "branch": "main",
  "agent_id": "town-agent",
  "kind": "proposal_applied",
  "ops": [
    {"op": "upsert_text", "path": "player/journal.json", "content": "..."}
  ]
}
```

Events 是唯一的真相来源；`game/` 只是 event 流的 *物化*。你总能通过从 event 0 重放来重建 `game/`。

## Snapshots

一个 **snapshot**（即 save）是某个 event 时刻的 `game/` 完整副本，再加上元数据。Snapshots 存在 `.neonrp/saves/<name>/` 里。它们的作用是让回溯变快——重放一万条 event 很慢，加载 snapshot 只是一次文件拷贝。

```bash
neonrp save opening-scene
neonrp load opening-scene
```

## Branches

一个 **branch** 是 event log 上一个带名字的 head 指针。和 git 类似，分支很廉价：从当前状态 fork 出去后写分叉的 events。

```bash
neonrp branch try-stealing
```

Branches 通过 `.neonrp/branches/` 下的 copy-on-write 共享未变更的实体。

## Undo / Redo

`undo` / `redo` 把 head 指针沿 event 日志前后移动：先从最近的 snapshot 恢复，再向前重放。你的 event log 永不被销毁。

## Sandboxes

**Sandbox** 是一个从 snapshot 创建、且被标记为临时的 branch。Sandbox 让你做"如果当时……"的 what-if 实验而不污染命名 branch，可以干净地丢弃。

```bash
neonrp sandbox new experiment --from opening-scene --switch
# ... 游玩 ...
neonrp sandbox drop experiment --force
```

## Replay 与确定性

给定相同的 events、以及一个 seeded LLM（或缓存的 fixture），重放应产出相同的 `game/` 状态。`replay verify` 用于校验这一点：

```bash
neonrp replay verify --from opening-scene
```

这正是 WorldLines 让 AI 驱动的状态保持可复现的方式——这是聊天 UI 给不了你的。

## Agents

一个 **agent** 是 `agents/<agent-id>/` 目录，其中包含：

- `agent.json` —— triggers、tags、priority、路由元数据
- `system.md` —— system prompt 模板
- （可选）`skills/`、`tools.json`、`policies.md`

**dispatcher** 按以下顺序为每个查询选择 agent：

1. 显式的 `--agent` flag
2. 正则 trigger 匹配
3. Tag 重合度
4. Priority 打破平局

stoneford 起步模板自带 6 个 agent（见 [templates/stoneford](templates/stoneford/README.zh.md)）。

## Skills

**Skills** 是可复用的 prompt 片段 / 能力模块，agent 可以 `use`。Builtin skill（随引擎打包）会自动出现；你也可以在 `skills/` 里定义项目级 skill。

## Plan → Diff → Apply

当 agent 要改动世界时，它不会直接编辑文件，而是发出一份 **proposal**：

```json
{
  "run_id": "20260417-100311",
  "agent_id": "town-agent",
  "rationale": "Player examined the harbor; adding observed detail.",
  "ops": [
    {"op": "upsert_text", "path": "towns/stoneford.json", "content": "..."}
  ]
}
```

引擎会展示 diff、对照 schema 做校验，然后作为一个新 event 应用。你（或 auto-apply 规则）批准这次转移。

## Harness —— 编排循环

WorldLines 的 agent harness 实现了 Plan–Diff–Apply 循环，具备：

- Bounded retrieval（minimal-context、fuzzy+vector 混合）
- 确定性的工具调用顺序
- 每轮预算（tokens / tool 调用次数）
- Thinking 通道与叙事分离

**orchestrator** agent 是顶层 harness 协调者——它通过 `task()` 工具路由到领域 agent，保持游戏状态一致，并掌管面向玩家的叙事。

## Build / Sandbox / Play 模式

TUI 暴露三种模式：

- **build** —— 直接文件编辑 + 叙事回应。适合写世界时使用。
- **sandbox** —— proposal 流水线 + 手动审批。最安全。
- **play** —— GM 模式，auto-apply 开启，完全沉浸。

在 TUI 里通过 `/mode <name>` 切换。

## 延伸阅读

- [CLI_REFERENCE.zh.md](CLI_REFERENCE.zh.md) —— 表层命令
- [TUI_GUIDE.zh.md](TUI_GUIDE.zh.md) —— 交互式工作流
- [templates/stoneford/](templates/stoneford/README.zh.md) —— 示例世界
