---
title: "主角与 NPC"
description: "只有主角是独立的;NPC 由世界驱动;把 NPC 升成主角是一次引擎操作。"
---

<!-- section: soul -->
## 主角(soul)

> **状态:随 1.0 发布**

主角带自己的 Agent:人格、目标、承诺、记忆,自己判断、自己说话。一个主角是一个文件夹 `souls/<sid>-<iid>/`:人格与规则是 markdown,情绪 / 信任 / 意图 / 位置在 `run_state` 里,立绘在 `assets/`。

在石津,艾琳娜跟着你;罗文在碧石镇,11:00 以后按自己的目标动身 —— 没有人给他写剧本。

<!-- section: npc -->
## NPC

公会的赫伦、旅店的米拉是 NPC:没有自己的 Agent,由 world agent 替他们说话、按规则动。NPC 是开 schema 里 `npc` 类的实例。

<!-- section: cast -->
## 升为主角

`neonrp cast` 把一个主角投进任意世界。把世界里的 NPC 升为主角也是 cast:新建主角文件夹、登记进主角团、从此自己判断 —— 它是一次引擎操作,不是改一个字段。
