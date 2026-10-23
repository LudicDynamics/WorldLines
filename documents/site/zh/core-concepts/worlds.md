---
title: "事件、快照与分支"
description: "WorldLines 把每次变更都存为只追加的事件。快照和分支让回退变得廉价。"
---

<!-- section: events -->
## 事件

世界中的每次变更都是一条**只追加的事件**,写入 `.neonrp/events.jsonl`:

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

事件是**唯一真相源**。`game/` 是事件流的物化结果。你随时可以从 event 0 开始重放事件来重建 `game/`。

<!-- section: snapshots -->
## 快照

**快照**(或称存档)是在某个事件处对 `game/` 的完整拷贝,加上元数据。快照位于 `.neonrp/saves/<name>/`。快照的存在是为了让回退变快 —— 重放一万条事件很慢;加载一个快照只是复制文件。

```bash
neonrp save opening-scene
neonrp load opening-scene
```

<!-- section: branches -->
## 分支

**分支**是事件日志上一个命名的 head 指针。和 git 一样,分支很便宜:从当前状态分叉,然后写入不同的事件即可。

```bash
neonrp branch try-stealing
```

未修改的实体通过 `.neonrp/branches/` 下的写时复制(copy-on-write)在分支间共享。

<!-- section: sandboxes -->
## 沙箱

**沙箱**是从*某个快照*创建、被标记为临时的分支。沙箱让你运行"如果……会怎样"的实验,而不会污染命名分支。

```bash
neonrp sandbox new experiment --from opening-scene --switch
# ... 游玩 ...
neonrp sandbox drop experiment --force
```

<!-- section: replay -->
## 回放与确定性

在相同事件和设定种子的 LLM(或缓存 fixture)下,重放应得到相同的 `game/` 状态。`replay verify` 会检查这一点:

```bash
neonrp replay verify --from opening-scene
```

这就是 WorldLines 保持 AI 驱动状态可复现的方式 —— 一个聊天 UI 给不了的属性。
