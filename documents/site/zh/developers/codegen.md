---
title: "代码生成"
description: "从接口契约生成 TypeScript 和 GDScript 的类型与小客户端。"
---

<!-- section: targets -->
## 目标

```bash
neonrp template contract stoneford-town --ts > stoneford-town.world.ts
neonrp template contract stoneford-town --gd > stoneford_town_world.gd
```

也可以 `GET /api/v1/local/templates/<id>/contract?fmt=ts|gd`。输出到 stdout,文件名自己定。类名由模板 id 得来:`stoneford-town` → `StonefordTownWorld`,`pct-house` → `PctHouseWorld`。

| 目标 | 生成物 |
|---|---|
| TypeScript | 变量、op、类、拍事件的类型,加一个很小的 HTTP 客户端类 |
| GDScript | 每个变量一个带类型的属性、变量名表、op 名表、三个 signal |

只有这两种。要完整的连接(握手、逐字流、断线重连),用示例客户端:`worldlines/examples/clients/ts/src/client.ts` 和 `worldlines/examples/clients/godot/addons/worldlines/client.gd`(见[协议](/docs/developers/protocol))。生成的类型可以和它们一起用。

<!-- section: ts -->
## TypeScript

生成的内容:`CONTRACT_HASH`;`StonefordTownWorldVars`(变量名 → 类型);`StonefordTownWorldOps`(op → 字段);`StonefordTownWorldClass`;`ProposeResult`;`BeatEvent`;以及:

```ts
export class StonefordTownWorld {
  constructor(private base = '') {}
  schema()                 // GET  /api/v1/play/schema
  say(text: string)        // POST /cmd
  tick(turns = 1)          // POST /api/v1/play/engine/tick
  on(pattern, fn)          // SSE  /api/v1/play/schema/stream?pattern=…  → 返回取消函数
}
```

```ts
const w = new StonefordTownWorld("http://127.0.0.1:8788");
const off = w.on("var.changed:price.T001.*", (e) => hud.update(e));
await w.tick(3);
```

<!-- section: gd -->
## GDScript

```gdscript
# generated from worldlines.contract/0.1 · stoneford-town 0.1 · hash 1a8b17c389cd — do not edit
class_name StonefordTownWorld
extends Node

const CONTRACT_HASH := "1a8b17c389cd"

signal changed(var_name: String, from, to)
signal ended(ending: Dictionary)
signal beat(event: String, data: Dictionary)

var player_gold: int  # 0…
var price_T001_grain: int  # 1…9999
const VAR_NAMES := { "player.gold": "player_gold", … }
const OPS := ["move_to", …, "trade", "haul"]

func apply_change(var_name: String, value) -> void   # 写属性并发 changed
```

GD 版不联网:它是一份带类型的状态镜像。把收到的 `var.changed`(或 `state.changed` 里的变量)交给 `apply_change`,UI 连 `changed` 信号。
