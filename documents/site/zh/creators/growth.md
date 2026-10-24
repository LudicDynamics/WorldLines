---
title: "增长策略"
description: "游玩中叙事想新增一个类的实例时,谁说了算:自动 / 要批准 / 只在创作时 / 禁止。"
---

<!-- section: policy -->
## 四种策略

> **状态:随 1.0 发布**

每个类带一个 `policy`,管的是**叙事**用 `new` 新增这个类的实例:

| 策略 | 含义 |
|---|---|
| `auto` | 直接落地(默认;没设过策略的世界都是这样) |
| `approve` | 进「待批准」队列(`game/meta/pending.json`),你批了才落地,也可以拒 |
| `creator` | 只有创作者能加(`neonrp schema register` 或工作台);叙事提的会被拒 |
| `forbid` | 谁都不能再加 |

世界自己的规则(片段的每回合规则、op 处理器)不受策略限制:经济片段发商队不用你批。

<!-- section: set -->
## 怎么设

注册类时带上 `policy`,或者只改已有类的策略:

```bash
neonrp schema register classes npc --spec '{"policy": "approve"}'
```

创作者操作 `set_policy {cls, policy}` 把策略写进模板,之后开的每一局都按它走。游玩中也能改这一局的:

```
GET  /api/v1/play/engine/approvals          {pending: [...], policies: {类: 策略}}
POST /api/v1/play/engine/approvals/<id>     {approve: true|false}
POST /api/v1/play/engine/policy             {class, policy}
```

<!-- section: grow -->
## 走到没有的地方

玩家要去地图上还没有的地点时,引擎先在他所在的地方旁边长出这个地点(`new_location`),再走进去;不是直接拒绝。别的镇的 id,或者挂在一个没人知道的镇下面的地点,仍然会被拒。新长出的地点会出现在地图上,并发一条 `place.discovered` 事件。

游玩中新增实例的 op:`new`(登记类的新实例,类要有 `folder`)、`new_location`、`new_npc`。
