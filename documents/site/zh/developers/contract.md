---
title: "接口契约:world.contract.json"
description: "Lint 通过后为每个世界导出一份类型化契约。所有客户端都从它生成。"
---

<!-- section: what -->
## 契约是什么

> **状态:设计中 · 接口为拟定** —— 3.0 定下的设计,名字和字段在实装前可能还会改。

协议是「怎么说话」,契约是「这个世界有什么可说」。组装与 Lint 已经把模板包、片段、内容、槽位都解析完了,于是能导出这个世界具体的契约:

```json
{
  "world": "stoneford-elena", "version": "1.2", "hash": "sha256:…",
  "template": "rpg", "mixins": ["space", "tick", "economy", "factions"],
  "variables": {"price.T001.jade": {"type": "int", "min": 1, "max": 999, "on": "T001"}},
  "classes":   {"caravan": {"required": ["from", "to", "cargo"], "policy": "auto"}},
  "ops":       {"trade": {"fields": {"town": "str", "good": "enum", "qty": "int"}, "from": "economy"}},
  "events":    ["var.changed", "entity.created", "trigger.fired", "turn.ended"],
  "slots":     {"place.scene": {"kind": "image", "ratio": "16:9"}},
  "views":     {"market": {"bind": ["price.{town}.*", "inv.*"], "widget": "table", "actions": ["trade"]}}
}
```

<!-- section: hash -->
## 哈希与兼容

契约内容一变,哈希就变。客户端用新契约重新生成代码时,被删掉的变量会直接**编译报错**;Godot 端的 `CONTRACT_HASH` 对不上就拒绝连接 —— 而不是运行时悄悄坏掉。
