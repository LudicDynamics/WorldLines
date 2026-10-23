---
title: "存档 · 分支 · 撤销"
description: "每一步都能退回去,也能分出去试另一条路。"
---

<!-- section: cmds -->
## 在游戏里

> **状态:随 1.0 发布**

| 命令 | 作用 |
|---|---|
| `/save <名字>` | 打一个检查点 |
| `/branch <名字>` | 从这里分出一条新的世界线,在上面试另一条路 |
| `/undo` | 回退上一步 |

主线不会被分支影响。

<!-- section: under -->
## 背后是提交图

每个回合都是一个 commit,见 [世界线](/docs/concepts/worldlines)。想从命令行看:`neonrp commit log`。
