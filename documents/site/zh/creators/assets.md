---
title: "素材:槽位 · 配方 · 视图"
description: "槽位说要什么图,配方说图怎么来,视图说状态怎么显示。都写在 template.json 的 ui 里。"
---

<!-- section: slots -->
## ① 槽位:要什么

> **状态:随 1.0 发布** —— `neonrp template slots <模板>` 列出每个槽位填了没有;Template 页「素材」一栏可以上传或生成。

槽位是一个列表,按**类**声明:这个类的每个实例都要一张。规则包自带一组,模板在 `ui.slots` 里按 `cls` + `slot` 覆盖或追加。`rpg` 包自带的:

```json
[
  {"cls": "level", "slot": "map",      "kind": "image", "ratio": "3:2",  "hotspots": true, "required": "publish", "recipe": "map"},
  {"cls": "soul",  "slot": "portrait", "kind": "image", "ratio": "3:4",  "required": "publish", "recipe": "portrait"},
  {"cls": "soul",  "slot": "sprite",   "kind": "image", "required": "optional", "recipe": "sprite"},
  {"cls": "place", "slot": "scene",    "kind": "image", "ratio": "16:9", "required": "optional", "fallback": "map_crop", "recipe": "scene"},
  {"cls": "item",  "slot": "icon",     "kind": "icon",  "required": "optional", "recipe": "item_icon"}
]
```

| 字段 | 意思 |
|---|---|
| `cls` · `slot` | 哪个类、哪个槽 |
| `kind` | `image` · `icon` 等 |
| `required` | `publish` = 发布必需;`optional` = 可以空着 |
| `recipe` | 怎么生成(见下) |
| `ratio` · `fallback` | 比例;没有图时用什么顶上 |
| `scope` | 写 `class` = 整个类共用一张,不按实例分 |

`required: publish` 的槽位没填或过期,[Lint](/docs/creators/lint) 在 `lint.level: publish` 下拦下发布,`draft` 下只提醒。

除了这些类槽位,封面、剧情包里的物品 / 地点 / 结局图、开场 CG、奖励卡图也都是槽位,在同一栏里填。

**角色的站姿直接用立绘**:立绘本身就是全身像时,在角色的 `soul.json` 里写

```json
"assets": {"sprite": "portrait"}
```

站姿槽就指向立绘,不复制文件。

<!-- section: recipe -->
## ② 配方:怎么来

`recipe` 是内置配方(`map` · `scene` · `portrait` · `sprite`)或模板 `ui.prompts` 里的一条具名提示。生成交给配置好的图像后端:`openai` · `codex` · `comfyui`。

- **地图**(`map`)按世界文件里的坐标先画构图引导,再交给图像模型;地图上的点用同一套坐标,所以对得上。地点变了,地图标「过期」。
- **立绘 / 站姿**按角色的人设写提示。
- **具名提示**里可以用 `{inst.name}`、`{style}` 这类占位符;灰橡宅的玩家立绘就是一条具名提示 `player_portrait`。

<!-- section: view -->
## ③ 视图:怎么显示

视图只写**绑定哪些变量、什么控件、布局提示**,不写 HTML。经济片段自带的「集市」:

```json
{"id": "market", "title": {"zh": "集市", "en": "Market"}, "bind": ["price.{town}.*", "stock.{town}.*", "inv.*"],
 "widget": "table", "actions": ["trade"], "layout": {"area": "right", "order": 3}}
```

`{town}` = 玩家所在的镇,`*` = 一段。也可以绑一个类:`"class:quest"`。控件有 `table` · `gauge` · `bars` · `meter` · `sparkline` · `list` · `number`。

游玩时 `GET /api/v1/play/engine/views` 返回每个视图绑定的当前值,前端按自己的方式画。
