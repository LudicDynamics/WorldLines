---
title: "计划 → 差异 → 应用"
description: "Agent 不直接修改文件。它们产出提案。你审阅,然后应用。"
---

<!-- section: proposal -->
## 提案(Proposal)

当 agent 要写入世界时,它不会直接编辑文件。它会产出一个**提案**:

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

引擎展示 diff,按 schema 校验,然后作为一个新事件应用。你(或者自动应用规则)批准这次状态转移。

<!-- section: ops-schema -->
## 操作种类

操作是一个小而封闭的词表:

- `upsert_text` —— 创建或替换一个文本文件
- `upsert_json` —— 创建或替换一个 JSON 实体
- `patch_json` —— 精确字段更新(按 JSONPath)
- `delete` —— 删除文件
- `move` —— 重命名 / 移动

每个 op 在应用前都会过 schema 校验。

<!-- section: retrieval -->
## 检索 —— 最小上下文

Harness 使用**有界检索**把相关实体喂给每个 agent 回合:

- 模糊 + 向量混合搜索
- 每次查询的实体预算
- 按实体种类过滤(`--kind location`、`--kind npc`)

在 CLI 中:

```bash
neonrp find "harbor" --kind location --json
neonrp context "stoneford guild" --limit 5
```

这就是即使世界膨胀到 10,000+ 实体也能保持回合延迟有上限的原因。

<!-- section: determinism -->
## 为什么这很重要

计划 → 差异 → 应用 让 WorldLines **可审阅**且**可复现**:

- 你可以把每次状态变更作为结构化 diff 审计
- Agent 无法悄悄破坏世界状态
- `replay verify` 可以从事件再次推导出相同状态
- 聊天 UI 无法提供这些保证
