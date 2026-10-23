---
title: "注册与订阅(Python)"
description: "registry.register / load_registry,ledger 事件与 sdk.on / events / history / enqueue。"
---

<!-- section: register -->
## register(root, table, id, spec)

> **状态:随 1.0 发布**

闭 schema 与开 schema 的**唯一写入口**:写一条到 `game/meta/<table>.json`,写之前校验,失败抛 `RegisterError`。`spec=None` 表示删除(对 `actions` 是写墓碑 = 关掉这个 op);`replace=False` 时已存在就报错。调用方自己重新 `load_registry(root)`。

```python
from neonrp.core.registry import register, load_registry, RegisterError

register(root, "classes", "faction", {
    "required": ["name"], "folder": "game/factions", "scope": "world",
    "props": {"power": {"type": "int", "min": 0, "max": 100}}, "mutable": ["power"]})
register(root, "entries", "F_bandits", {"class": "faction", "props": {"name": "独眼虎山贼", "power": 46}})
reg = load_registry(root)   # 模板包 + 世界文件 + 注册的覆盖层
```

<!-- section: rules -->
## 各表的校验规则

| 表 | 规则 |
|---|---|
| `variables` | `type` ∈ int / float / str / bool;必须有 `path` + `key` |
| `entries` | `class` 必须先注册;按类检查必填与类型化属性(`check_envelope`) |
| `classes` | `required` / `invariants` / `mutable` 是列表;`scope` ∈ place / town / world;属性类型 ∈ int float str bool enum list,enum 要 `values`;`rels` 的值是允许的类名(多个用竖线连接,或 `*`)且类必须存在;`mutable` 必须在 props 里;模板自带的类不能加 folder |
| `actions` | `kind` ∈ action / update;`fields` 是列表 |
| `triggers` | 按 WHEN / IF / THEN / ELSE 校验 |

<!-- section: specs -->
## VarSpec 与 ClassSpec

```python
VarSpec(name, type, path, key, value=None, min=None, max=None, max_key=None,
        readonly=False, doc="")          # doc = 模型看到的规则
ClassSpec(name, parent_class=None, required=[], invariants=[], render="",
          folder="", scope="place", tier=2, id_prefix="",
          props={}, mutable=[], rels={})
```

<!-- section: events -->
## 事件类型

每次落地都写一行到 `game/meta/events.jsonl`:`{"seq", "turn", "ts", "type", "payload"}`。类型是封闭的:

| 类型 | payload |
|---|---|
| `turn.started` · `turn.done` | 回合开始 / 结束(done 带 applied / refused / created / triggered 计数) |
| `var.changed` | `var` · `from` · `to` · `by` |
| `flag.set` | `key` · `from` |
| `entry.entered` | `who` · `entry` |
| `entity.created` · `entity.patched` · `entity.promoted` | 新实例 / 改属性 / 升为主角 |
| `trigger.fired` | `id` · `why` · `emitted` |
| `tool.requested` · `tool.ran` | 规则请求工具 / 工具跑完 |
| `soul.settled` · `narration.landed` · `turn.ended` | 主角结算 / 叙事落地 / 结局 |

<!-- section: sub -->
## 订阅:push 与 pull

```python
from neonrp.core import sdk

def on_gold(ev):
    if ev["payload"]["to"] < 3:
        sdk.enqueue(root, {"op": "flag", "key": "broke"}, by="my-hook")   # 只能排队,不能写文件

off = sdk.on("var.changed:player.gold", on_gold)     # push:落地后按 seq 顺序回调
sdk.events(root, since=120, type="var.changed")      # pull:事件
sdk.history(root, "player.gold")                     # pull:[{turn, seq, var, from, to, by}]
off()
```

- 模式:`*` · `<type>` · `<type>:<key>` · `<type>:*`(key = 变量名 / 触发器 id / 实例 id / who);
- 回调在账本写完之后被调用;回调出错不会打断回合;
- `enqueue` 写 `game/meta/op_queue.json`,**下一回合**被取出送进 verify —— 外部逻辑仍然只能「提出」;
- 进程外订阅用 `neonrp schema watch <pattern>`(它在读同一个 events.jsonl)。

> HTTP 上的注册与订阅端点还没有(web 端目前只有回合流的 SSE),见 [协议](/docs/developers/protocol)。
