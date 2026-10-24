---
title: "创作者快速开始"
description: "在 WorldLines 里做一个世界:复制模板 → schema → 规则与剧情 → 片段 → 素材 → Lint → 发布。"
---

<!-- section: path -->
## 一条完整路径

> **状态:随 1.0 发布**

| 步 | 做什么 | 页面 |
|---|---|---|
| 1 | 复制一个内置模板,改 `template.json`:卡面、模式、规则包与片段 | [模板](/docs/creators/template-card) |
| 2 | 注册变量、定义类、加实例 | [注册与订阅](/docs/creators/schema) |
| 3 | 决定游玩中能长出什么 | [增长策略](/docs/creators/growth) |
| 4 | 写规则 | [触发规则](/docs/creators/triggers) |
| 5 | 剧情包与结局 | [剧情包](/docs/creators/plot-packs) · [结局](/docs/creators/endings) |
| 6 | 经济、势力等系统 | [片段](/docs/creators/fragments) |
| 7 | 素材 | [素材:槽位 · 配方 · 视图](/docs/creators/assets) |
| 8 | 检查、发布 | [Lint](/docs/creators/lint) · [发布到 Hub](/docs/creators/publish) |

世界、角色、模板、规则包、玩法合约各有一份规格,写什么、放哪、引擎怎么读都在里面:见 [规格](/docs/developers/specs)。

<!-- section: copy -->
## 第一步:复制一个模板

内置的灰橡宅(`pct-house`)和石津镇(`stoneford-town`)只读,但允许复制:

```bash
neonrp template fork stoneford-town my-town --store ~/.worldlines/templates
```

复制出来的是你自己的作品(自由区),可以随便改、导出、发布。本机创作台 Template 页的「复制一份来改」做的是同一件事。

<!-- section: try -->
## 五分钟试一下 schema

在一局的文件夹里试(用本地首页开一局石津镇,每局的文件夹在 `~/.worldlines/plays/` 下):

```bash
neonrp schema list variables
neonrp schema register variables town.T001.lanterns \
  --spec '{"type":"int","path":"game/towns/T001/town.json","key":"lanterns","min":0,"max":20,"doc":"石津北门还亮着的灯笼数。雾越浓灭得越多"}'
neonrp schema get town.T001.lanterns
```

别拿 `price.T001.grain` 这类名字试:石津装了经济片段,集市价格变量已经被片段占用,同名注册会把它覆盖掉。

<!-- section: studio -->
## 创作者操作

工作台和让 coding agent 改模板,用的是同一组**创作者操作**,全部先校验、再一次写入(有一条被拒就什么都不写),写完重新跑 Lint:

| 管什么 | 操作 |
|---|---|
| 卡面与模式 | `edit_card` · `set_mode` · `set_play_contract` |
| 规则包 | `set_mixins` · `set_world_data`(片段的世界数据) |
| 类与增长 | `register_class` · `set_policy` |
| 素材与视图 | `add_slot` · `remove_slot` · `edit_recipe` · `edit_prompt` · `set_view` · `remove_view` · `set_budget` |
| 选角 | `set_cast` |
| 编排 | `set_orchestration` · `set_soul_orchestration` · `set_soul_ambient` · `set_engine_setting` |

HTTP:`POST /api/v1/local/templates/<id>/ops {ops: [...]}`。只能改你自己模板库里的模板;内置模板先复制。
