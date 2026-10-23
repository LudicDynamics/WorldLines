---
title: "三层:引擎 · 模板包 · 产品"
description: "WorldLines — Make you play with your AI character in an infinite world. 所有人先读这一页。"
---

<!-- section: what -->
## WorldLines 是什么

> **状态:混合** —— 每一节标了哪些随 1.0 发布、哪些还在设计中。

**WorldLines — Make you play with your AI character in an infinite world.**

你和 AI 角色一起活在一个会自己往前走的世界里:主角自己判断、自己说话;NPC 由世界驱动;地图会长出新地点;经济和势力自己运转。你说的每一句话、主角做的每一个决定,都只是一次**提出** —— world agent 校验之后才会真正改变世界。

<!-- section: layers -->
## 三层,互相独立

| 层 | 是什么 | 谁用 |
|---|---|---|
| **NeonRP 引擎**(`neonrp` 包) | 只有开 schema / 闭 schema 两套状态逻辑、提出 → 校验 → 落地、事件与订阅、提交与分支。**不含任何玩法。** | SDK 开发者 |
| **模板包** | 把一种玩法登记进引擎:类、变量、ops、触发规则、机制接缝、提示词。内置 `rpg`(d20 + 属性修正,我们的自制规则;检定与倒地规则可选 SRD 5.2,CC BY 4.0)、`pct`(百分骰,BRP —— Chaosium《Basic Roleplaying》,ORC 授权:d100 技能 + 理智 + 濒死,以 rpg 为底;这一类玩法叫「沙盒跑团」)、`werewolf` 与 `monopoly` | 创作者 / 开发者 |
| **WorldLines 产品**(`worldlines` 包) | 游玩界面、创作工作台、组装、Lint、导出导入、发布到 Hub。它依赖 `neonrp` 引擎,只调公开接口 | 玩家 / 创作者 |

所以:**玩家装 `worldlines`**(它会带上引擎);**开发者可以只装 `neonrp`**,把引擎接进自己的程序或 Godot。

<!-- section: readers -->
## 按你是谁来读

| 你是 | 从这里开始 |
|---|---|
| 玩家 | [玩家快速开始](/docs/players/quickstart) |
| 创作者 | [创作者快速开始](/docs/creators/quickstart) |
| SDK 开发者 / 重前端 | [开发者快速开始](/docs/developers/quickstart) · [实时事件流](/docs/developers/events) |
| 替人干活的 agent(Claude Code、Codex、WorldLines 创作 agent) | [给 agent](/docs/agents/overview) |

另外四页概念很短,建议都读:[开 / 闭 schema](/docs/concepts/schema) · [提出 → 校验 → 落地](/docs/concepts/ops) · [主角与 NPC](/docs/concepts/souls) · [世界线](/docs/concepts/worldlines)。

<!-- section: map -->
## 1.0 里有什么

> **状态:随 1.0 发布**

| 东西 | 是什么 | 读 |
|---|---|---|
| 世界 | 一个文件夹:地图层级、地点、NPC、物品、开场 | 模板文件夹 `spec/world.md` |
| 角色 | 住在角色库,模板里只放 link,开局才实体化 | [角色库与选角](/docs/creators/characters) · [你的角色](/docs/players/your-character) |
| 模板 | 世界 + 演员表 + 玩法包 + 合约 + 编排:玩、导出、发布的单位 | [工作台](/docs/creators/workbench) · [导出与导入](/docs/creators/export-import) |
| 玩法合约 | 一种玩法要给玩家的体验;Lint 按它查,到出口按它结算 | [玩法合约](/docs/creators/contracts) |
| 编排图 | 一局怎么推进:商量 → 清算 → 各种层 | [工作台](/docs/creators/workbench) · [商量与清算](/docs/concepts/planning-resolve) |
| 一回合 | 两拍:商量(世界不变)→ 清算(先叙事、再落状态) | [游玩界面](/docs/players/play-screen) · [实时事件流](/docs/developers/events) |

<!-- section: stoneford -->
## 贯穿全文档的例子:石津

例子统一用内置世界 **石津 · 艾琳娜与罗文**(`stoneford-elena`):你是雾里醒来的失忆旅人;治愈师**艾琳娜**在北门遇见你;**罗文**在碧石镇,11:00 以后按自己的目标动身去石津;驿路上**独眼虎**山贼盯着来往的**商队**。

<!-- section: license -->
## 关于许可

NeonRP 引擎从 1.0 起以 **Apache-2.0** 开源;WorldLines 产品(`worldlines`,含界面与内置样例模板)以 **AGPL-3.0** 发布。

模板与示例世界里的**内容**另有授权(见引擎包里的 `CONTENT-LICENSE.md`):设定文字(世界与角色设定、地点、规则表等)为 **CC BY 4.0**,可改编、可商用,署名即可;图片与音频(立绘、封面、背景、声音)为 **CC BY-NC 4.0**,可改编但不可商用。所用的开放规则保留各自的授权:SRD 5.2 为 CC BY 4.0,BRP 为 ORC License。
