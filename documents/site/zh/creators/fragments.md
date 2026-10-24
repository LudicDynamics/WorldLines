---
title: "片段:经济 · 势力"
description: "把常见系统做成可以叠加的片段。每个片段登记变量、类、op,再带一条每回合自己跑的规则。"
---

<!-- section: what -->
## 怎么叠加

> **状态:随 1.0 发布**

在 `template.json` 的 `pack` 里写:

```json
"pack": {"name": "rpg", "mixins": ["economy"]}
```

石津镇就是这样写的。片段要有自己的世界数据才会动:`economy` 读 `game/world/economy.json`,`factions` 读 `game/world/factions.json`(通常放在 `world-overlay/` 里);没有就什么都不做,Lint 报 warn。

每个片段做四件事:注册变量(闭 schema)、注册类(开 schema)、登记 op(带校验器)、加一条**每回合规则**(tick)。tick 在回合落地之后跑,不调模型,它提出的改动和别的改动一样落库、进账本、能唤醒触发器;引擎只查两件事:op 已经登记、改的东西在这个片段声明的范围里。

<!-- section: economy -->
## 经济片段 `economy`

| 部分 | 内容 |
|---|---|
| 变量 | `stock.<镇>.<货>` · `price.<镇>.<货>` · `inv.<货>`(玩家背包)· `econ.index`,都是只读,只有片段自己写 |
| 类 | `caravan`(商队,游玩中不断新增) |
| op | `trade`(玩家买卖)· `new_caravan` · `haul` · `deliver` · `rob` |
| 每回合 | 产出 − 消耗;定价 `基价 × (目标库存 / 现库存)^0.55`,夹在 0.45–3.2 倍之间,再乘传闻溢价;两地差价超过 35% 就发商队;商队按路程走,到了就交货;同时装了势力片段时,路上可能被山贼劫 |

石津镇的数据有三个集市(石津、碧石镇、风栈堡),货有粮、盐鱼、药草、碧石、铁器。玩家说「买 3 斗粮」「卖碧石」会变成 `trade`,校验器查你在不在有集市的镇上、货名对不对、数量是否大于 0。右栏「集市」视图显示当地价格、库存和你的货。

<!-- section: factions -->
## 势力片段 `factions`

| 部分 | 内容 |
|---|---|
| 变量 | `faction.<id>.power` · `faction.<id>.wealth` · `rep.<id>`(玩家声望)· `rel.<a>.<b>`(两方关系) |
| 类 | `faction` · `quest`(委托)· `rumor`(传闻) |
| op | `take_quest`(玩家接委托)· `new_quest` · `quest` · `rumor` · `spread` · `strike` |
| 每回合 | 传闻按热度沿路线扩散,每 4 回合降温一次;警戒高或山贼强时守卫巡路;山贼用赃物招人,压过守卫时出去劫掠;山贼坐大时公会挂悬赏,削弱后发赏金;某种货一直太便宜,对应的劳工罢工 |

势力的角色由数据里的 `role` 决定:`bandits`、`guard`、`labor`。传闻带标签时可以给某几种货加溢价(`premiums`),和经济片段连起来:镇上听说「北路有山贼」,北路来的货就涨价。

`take_quest` 要你人在委托人所在的地方;「委托」视图列出当前的委托。

<!-- section: write -->
## 自己写一个片段

见开发者文档 [写一个片段](/docs/developers/fragment)。
