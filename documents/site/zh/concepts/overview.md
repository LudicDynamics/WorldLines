---
title: "三层:引擎 · 模板包 · 产品"
description: "WorldLines — Make you play with your AI character in an infinite world. 所有人先读这一页。"
---

<!-- section: what -->
## WorldLines 是什么

**WorldLines — Make you play with your AI character in an infinite world.**

你扮演主角,和 AI 角色一起活在一个会自己往前走的世界里:角色(soul)有自己的 agent,自己判断、自己说话;世界 NPC 由世界代说、按规则动;地图会长出新地点;经济和势力自己运转。你说的每一句话、角色做的每一个决定,都只是一次**提出** —— 世界(world agent)校验之后才会真正改变世界。

<!-- section: layers -->
## 三层,互相独立

| 层 | 是什么 | 谁用 |
|---|---|---|
| **NeonRP 引擎**(`neonrp` 包) | 只有开 schema / 闭 schema 两套状态逻辑、提出 → 校验 → 落地、事件与订阅、提交与分支。**不含任何玩法。** | SDK 开发者 |
| **模板包** | 把一种玩法登记进引擎:类、变量、ops、触发规则、机制接缝、提示词。内置 `rpg`(d20 + 属性修正,我们的自制规则;检定与倒地规则可选 SRD 5.2,CC BY 4.0)、`pct`(百分骰,BRP —— Chaosium《Basic Roleplaying》,ORC 授权:d100 技能 + 理智 + 濒死,以 rpg 为底;这一类玩法叫「沙盒跑团」)、`werewolf` 与 `monopoly` | 创作者 / 开发者 |
| **WorldLines 产品**(`worldlines` 包) | 游玩界面、创作工作台、组装、Lint、导出导入、发布到 Hub。它依赖 `neonrp` 引擎,只调公开接口 | 玩家 / 创作者 |

所以:**玩家装 `worldlines`**(它会带上引擎);**开发者可以只装 `neonrp`**,把引擎接进自己的程序或 Godot。

**两种装法,回合不一样。** PyPI 上的 `worldlines` / `neonrp` 包自带完整的两拍编排(先商量、后清算)。从开源仓库源码装,得到的是开源引擎,每回合只有清算一拍。同一个模板两种都能玩;模板写了两拍、引擎没有时,自动退回一拍。见 [一回合怎么走](/docs/concepts/turn-flow)。

<!-- section: readers -->
## 按你是谁来读

| 你是 | 从这里开始 |
|---|---|
| 玩家 | [玩家快速开始](/docs/players/quickstart) |
| 创作者 | [创作者快速开始](/docs/creators/quickstart) |
| SDK 开发者 / 重前端 | [开发者快速开始](/docs/developers/quickstart) · [实时事件流](/docs/developers/events) |
| 替人干活的 agent(Claude Code、Codex、WorldLines 创作 agent) | [给 agent](/docs/agents/overview) |

另外四页概念很短,建议都读:[开 / 闭 schema](/docs/concepts/schema) · [提出 → 校验 → 落地](/docs/concepts/ops) · [角色与 NPC](/docs/concepts/souls) · [世界线](/docs/concepts/worldlines)。

<!-- section: map -->
## 1.0 里有什么

| 东西 | 是什么 | 读 |
|---|---|---|
| 世界 | 一个文件夹:地点树、NPC、物品、开场 | 模板文件夹里的 `spec/world.md` |
| 角色 | 住在角色库,模板里只放 link,开局才实体化 | [角色库与选角](/docs/creators/characters) · [你的角色](/docs/players/your-character) |
| 模板 | 世界 + 角色 link + 规则包 + 合约 + 编排:玩、导出、发布的单位 | [模板文件](/docs/creators/template-card) · [工作台](/docs/creators/workbench) |
| 玩法合约 | 一种玩法要给玩家的体验;Lint 按它查,到出口按它结算 | [玩法合约](/docs/creators/contracts) |
| 编排 | 一回合怎么走:模板在 `uses` 里点名(两拍 `two_beat` / 一拍 `one_beat`),本机编排台可以改图 | [工作台](/docs/creators/workbench) · [商量与清算](/docs/concepts/planning-resolve) |
| 一回合 | 两拍:商量(世界不变)→ 清算(先叙事、再写状态);开源版只有清算一拍 | [一回合怎么走](/docs/concepts/turn-flow) · [实时事件流](/docs/developers/events) |

<!-- section: stoneford -->
## 贯穿全文档的例子:石津镇

例子统一用内置模板 **石津镇 · 雾退之夜**(`stoneford-town`):一年只有一夜,雾会从北路上退开;探路队没回来,驿路被**独眼虎**山贼截了,你有两个夜晚、一个白天,凑齐出北门的东西。治愈师**艾琳娜**和**罗文**是角色,有自己的 agent;守门人卡斯、公会的赫伦、旅店的米拉是世界 NPC。另一个内置模板是 **灰橡宅 · 关上的门**(`pct-house`),用百分骰的沙盒跑团。

<!-- section: license -->
## 关于许可

NeonRP 引擎从 1.0 起以 **Apache-2.0** 开源;WorldLines 产品(`worldlines`,含界面与内置样例模板)以 **AGPL-3.0** 发布。PyPI 包里的两拍编排不在开源仓库里,不开源。

模板与示例世界里的**内容**另有授权(见引擎包里的 `CONTENT-LICENSE.md`):设定文字(世界与角色设定、地点、规则表等)为 **CC BY 4.0**,可改编、可商用,署名即可;图片与音频(立绘、封面、背景、声音)为 **CC BY-NC 4.0**,可改编但不可商用。所用的开放规则保留各自的授权:SRD 5.2 为 CC BY 4.0,BRP 为 ORC License。
