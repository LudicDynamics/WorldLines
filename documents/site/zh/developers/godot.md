---
title: "接入 Godot"
description: "连一个本地引擎进程 + 生成的 GDScript 客户端 + 素材映射到 res://。"
---

<!-- section: arch -->
## 架构

> **状态:设计中 · 接口为拟定** —— 3.0 定下的设计,名字和字段在实装前可能还会改。

```text
Godot 游戏  ── WebSocket / HTTP ──>  本地引擎进程
    ^                                   |
    └── 生成的 GDScript 客户端 <── world.contract.json
```

Godot 连本地进程(像语言服务器那样),而不是把引擎塞进游戏:NeonRP 内核是专有的,不随游戏分发;分发出去的只有契约和生成的客户端。

<!-- section: gd -->
## 生成的 GDScript

```gdscript
# generated from world.contract.json · stoneford-elena · do not edit
class_name StonefordWorld
extends Node

const CONTRACT_HASH := "ae5debb"

signal changed(var_name: String, from, to)
signal refused(op: String, why: String)
signal hook_h1(payload: Dictionary)   # town.alert >= 3 → 镇署贴出宵禁告示

var player_gold: int                   # 0…
var price_T001_grain: int              # 1…999

func trade(town: String, good: String, qty: int) -> Dictionary:
    return await propose([{"op": "trade", "town": town, "good": good, "qty": qty}])
```

<!-- section: assets -->
## 素材

槽位目录 `assets/{类}/{槽位}/` 原样拷进 `res://worldlines/stoneford-elena/`,地图热点生成 `.tres`。配方节点图在 WorldLines 这边跑,Godot 只消费产物;视图描述可以生成默认控件场景,也可以自己做 UI。
