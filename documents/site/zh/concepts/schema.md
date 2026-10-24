---
title: "开 schema 与闭 schema"
description: "世界的全部状态只有两种:可以一直加实例的「类」,和先注册再改值的「变量」。"
---

<!-- section: two -->
## 两种状态

| | 开 schema | 闭 schema |
|---|---|---|
| 是什么 | **类 + 实例**:地点、NPC、物品、委托、势力、传闻、商队…… | **注册过的变量**:金币、警戒、价格、势力值、两方关系…… |
| 游玩中 | 可以一直加新实例(受类的增长策略约束) | 只改值;没注册的变量不能写 |
| 例子 | 类 `faction`,实例「独眼虎山贼」 | `player.gold` = 18、`price.T001.grain` = 12(经济片段登记的只读变量,只有引擎能改) |

引擎的登记表一共五张:`variables` · `classes` · `entries` · `actions` · `triggers`。前两种状态用的是前三张;`actions` 决定允许哪些改法,`triggers` 是创作者写的规则。

<!-- section: relations -->
## 关系也是变量

社会关系不需要特殊系统:它是挂在实体上的闭 schema 数值 —— `town.alert`(挂在镇上)、`rel.guard.bandits`(挂在两个势力之间)。

角色自己的那一面(情绪、信任、意图、目标、记忆)不在这里:那由角色自己的回话结算,世界不写。

<!-- section: howto -->
## 怎么注册、怎么订阅

- 创作者:[注册与订阅(命令行)](/docs/creators/schema)
- 开发者:[注册与订阅(Python)](/docs/developers/schema-api)
