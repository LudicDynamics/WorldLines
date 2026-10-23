---
title: "创作者快速开始"
description: "在 WorldLines 里建一个世界:模板卡 → 模板与片段 → schema → 规则 → 素材 → Lint → 发布。"
---

<!-- section: path -->
## 一条完整路径

> **状态:混合** —— 每一节标了哪些随 1.0 发布、哪些还在设计中。

| 步 | 做什么 | 页面 | 状态 |
|---|---|---|---|
| 1 | 填模板卡 `card.yaml`,选模板与片段 | [模板卡](/docs/creators/template-card) | 设计中 |
| 2 | 注册变量、定义类、加实例 | [注册与订阅](/docs/creators/schema) | 随 1.0 发布 |
| 3 | 决定游玩中能长出什么 | [增长策略](/docs/creators/growth) | 设计中 |
| 4 | 写规则 | [触发规则](/docs/creators/triggers) | 随 1.0 发布 |
| 5 | 剧情包与结局 | [剧情包](/docs/creators/plot-packs) · [结局](/docs/creators/endings) | 随 1.0 发布 |
| 6 | 经济、势力等系统 | [片段](/docs/creators/fragments) | 设计中 |
| 7 | 素材 | [素材:槽位 · 配方 · 视图](/docs/creators/assets) | 设计中 |
| 8 | 检查、发布 | [Lint](/docs/creators/lint) · [发布到 Hub](/docs/creators/publish) | 设计中 |

世界、角色、模板、规则包、玩法合约各有一份规格,写什么、放哪、引擎怎么读都在里面:见 [规格](/docs/developers/specs)。

<!-- section: try -->
## 五分钟试一下

先装好 [WorldLines](/docs/players/quickstart),在石津的世界文件夹里(用本地首页开一局,每局的文件夹在 `~/.worldlines/plays/` 下)试:

```bash
neonrp schema list variables
neonrp schema register variables price.T001.grain \
  --spec '{"type":"int","path":"game/towns/T001/market.json","key":"price.grain","min":1,"max":99,"doc":"石津粮价,每斗铜币"}'
neonrp schema get price.T001.grain
```

> `neonrp schema` 随 1.0 发布。

<!-- section: studio -->
## 工作台

3.0 的工作台和创作 Agent 共用同一套**创作者 op**(`register_class` · `register_var` · `set_policy` · `add_slot` · `edit_recipe` · `fill_asset` · `edit_prompt` · `set_rule` · `cast`)。创作也走 提出 → 校验 → 落地,改动会进提交图,所以对模板的修改也能分支、对比、回退。(设计中)
