---
title: "世界线"
description: "每个回合都是一个 commit;可以回退、从任一处分出去、和另一条线对比。"
---

<!-- section: dag -->
## 提交图

> **状态:随 1.0 发布**

每局游戏有一张**提交图(DAG)**:每个回合落一个 commit,记父 commit 和快照。`neonrp commit` 提供 `log` · `checkout` · `branch` · `gc` · `verify`;默认存放在 `~/.worldlines/commits`。玩家在游戏里用 `/save` `/branch` `/undo`,见 [存档 · 分支 · 撤销](/docs/players/saves)。

<!-- section: why -->
## 为什么重要

世界会自己长东西(新地点、商队、传闻)。同一个开局可以在两条线上长成两个样子,然后逐项对比 —— 这是模拟和测试世界规则的基本工具。

> 设计中:工作台里的可视化提交图、从任意 commit 一键分出、两条线逐项 diff(见 3.0 mock)。
