---
title: "协议"
description: "通用内核协议:所有世界都一样,任何语言都能接。"
---

<!-- section: verbs -->
## 动词

> **状态:设计中 · 接口为拟定** —— 3.0 定下的设计,名字和字段在实装前可能还会改。

| 动词 | 作用 | Python 里已有的对应 |
|---|---|---|
| `propose(ops)` | 提出;返回通过 / 拒绝(带理由)/ 待批准 | `sdk.verify` + `sdk.apply` |
| `get(var)` · `history(var)` | 读闭 schema | `load_registry` · `sdk.history` |
| `query(class, filter)` | 查开 schema 实例 | `load_registry(...).entries` |
| `register(table, id, spec)` | 注册 | `registry.register` |
| `subscribe(pattern)` | 变化事件流 | `sdk.on` · `neonrp schema watch` |
| `say(text)` · `tick()` | 按模板的接缝决定有没有 | —— |
| `log` · `branch` · `checkout` | 世界线 | `neonrp commit` |

<!-- section: transport -->
## 传输

HTTP 负责请求 / 响应,WebSocket 或 SSE 负责事件流,消息体是 JSON:

```text
POST /api/v1/worlds/stoneford-elena/propose
POST /api/v1/worlds/stoneford-elena/register/variables/price.T001.grain
GET  /api/v1/worlds/stoneford-elena/vars/price.T001.jade?history=1
GET  /api/v1/worlds/stoneford-elena/entities?class=faction
GET  /api/v1/worlds/stoneford-elena/events/stream?pattern=var.changed:*
```

> 今天:这些端点还不存在。web 端只有回合流的 SSE;`neonrp serve` 是 internal。
