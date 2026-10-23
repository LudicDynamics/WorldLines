---
title: "素材:槽位 · 配方 · 视图"
description: "素材是 schema 的一种视图。三段都用同一个 schema 地址对上。"
---

<!-- section: slots -->
## ① 槽位:要什么

> **状态:设计中 · 接口为拟定** —— 3.0 定下的设计,名字和字段在实装前可能还会改。

类上声明需要哪些素材:

```yaml
level:   { map:      {kind: image, ratio: "3:2", hotspots: true, required: publish} }
soul:    { portrait: {kind: image, ratio: "3:4", required: publish},
           sprite:   {kind: image, from: portrait} }
place:   { scene:    {kind: image, ratio: "16:9", fallback: 地图裁切} }
faction: { emblem:   {kind: icon} }
```

`required: publish` 的槽位没填,[Lint](/docs/creators/lint) 就拦下发布。

<!-- section: recipe -->
## ② 配方:怎么来

配方是一张小节点图,模板给默认配方,实例可以覆盖:

```text
读数据(坐标 / 属性 / 画风参考) → 构图引导 → 提示词 → 生图(openai / codex / comfy)
      → 后处理(裁切 / 抠 sprite) → 绑定(热点坐标写回)
```

石津的地图就是这样来的:文件里的坐标先画成构图引导,再交给图像模型;地图上的点用同一套坐标,所以一定对得上。每个节点的输入算哈希,地点一变,地图就标「过期」。

<!-- section: view -->
## ③ 视图:怎么显示

视图只写**绑定哪些变量、什么控件、布局提示**,不写 HTML:

```json
{"id": "market", "title": "集市", "bind": ["price.{town}.*", "stock.{town}.*", "inv.*"],
 "widget": "table", "actions": ["trade"], "layout": {"area": "right", "order": 3}}
```

WorldLines 把它画成 `*.panel.html`;Godot 由代码生成器画成控件场景。**HTML 只是渲染器之一。**
