---
title: "注册与订阅(Python)"
description: "registry.register / load_registry,事件账本与 sdk.on / events / history / enqueue,以及对应的 HTTP 接口。"
---

<!-- section: register -->
## register(root, table, id, spec, *, replace=True)

闭 schema 与开 schema 的**唯一写入口**:写一条到 `game/meta/<table>.json`,写之前校验,失败抛 `RegisterError`。`spec=None` 表示删除(对 `actions` 是写墓碑 = 关掉这个 op);`replace=False` 时已存在就报错。写完由调用方自己重新 `load_registry(root)`。

```python
from neonrp.core.registry import register, load_registry, RegisterError

register(root, "classes", "faction", {
    "required": ["name"], "folder": "game/factions", "scope": "world", "policy": "approve",
    "props": {"power": {"type": "int", "min": 0, "max": 100}}, "mutable": ["power"]})
register(root, "entries", "F_bandits", {"class": "faction", "props": {"name": "独眼虎山贼", "power": 46}})
reg = load_registry(root)   # 规则包(含片段)+ 世界文件 + 注册的覆盖层
```

<!-- section: rules -->
## 各表的校验规则

| 表 | 规则 |
|---|---|
| `variables` | `type` ∈ int / float / str / bool;必须有 `path` + `key` |
| `entries` | `class` 必须先注册;按类检查必填与类型化属性 |
| `classes` | `required` / `invariants` / `mutable` 是列表;`scope` ∈ place / town / world;`policy` ∈ auto / approve / creator / forbid;属性类型 ∈ int float str bool enum list,enum 要 `values`;`rels` 的值是允许的类名(多个用竖线连接,或 `*`)且类必须存在;`mutable` 必须在 props 里;规则包自带的类不能加 folder |
| `actions` | `kind` ∈ action / update / tool / request / mode;`fields` 是列表 |
| `triggers` | 按 WHEN / IF / THEN / ELSE 校验 |

<!-- section: specs -->
## VarSpec 与 ClassSpec

```python
VarSpec(name, type, path, key, value=None, min=None, max=None, max_key=None,
        readonly=False, doc="",          # doc = 模型在变量旁看到的规则
        max_step=None,                   # 一回合最多能动多少
        monotonic=False, carry=None,     # 只增不减;HH:MM 时钟跨日时让 carry 指向的变量 +1
        about=None, rest=None)           # 关于某个实体:只在它在场或值离开 rest 时给模型看
ClassSpec(name, parent_class=None, required=[], invariants=[], render="",
          folder="", scope="place", tier=2, id_prefix="",
          props={}, mutable=[], rels={}, title="", packed=False,
          policy="auto",                 # 叙述里冒出新实例时:auto / approve / creator / forbid
          effect=False, person=False, clue=False)
```

`effect` 类是挂在某人身上、每回合自己倒数和生效的状态;`person` 类的实例能持有东西;`clue` 类的实例算线索。

`actions` 的 `kind`:`action`(落地的动作)· `update`(改变量 / 属性)· `tool`(请求,引擎执行后回答)· `request`(要某人回话)· `mode`(切到一个模式层再续写)。

<!-- section: events -->
## 事件类型

回合落地时写一行到 `game/meta/events.jsonl`:`{"seq", "turn", "ts", "type", "payload"}`。类型是封闭的:

| 类型 | payload |
|---|---|
| `turn.started` · `turn.done` | 回合开始 / 结束(done 带 applied / refused / created / triggered 计数) |
| `var.changed` | `var` · `from` · `to` · `by` |
| `flag.set` | `key` · `from` |
| `entry.entered` | `who` · `entry` |
| `entity.created` · `entity.patched` | 新实例 / 改属性 |
| `trigger.fired` | `id` · `why` · `emitted` |
| `tool.requested` · `tool.ran` | 规则请求工具 / 工具跑完 |
| `soul.settled` · `narration.landed` · `turn.ended` | 角色结算 / 叙事落地 / 到达结局 |

`entity.promoted` 在类型表里,目前不产生。`sdk.tick` 和 `POST /api/v1/play/engine/tick` 让世界自己走的那几拍不写账本。

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
- 回调在账本写完之后、在跑回合的那个进程里被调用;回调出错不会打断回合;
- `enqueue` 写 `game/meta/op_queue.json`,**下一回合**被取出送进校验 —— 外部逻辑只能「提出」;
- 进程外订阅用 `neonrp schema watch <pattern>`(读同一个 events.jsonl)。

<!-- section: http -->
## HTTP

同样的读和订阅在本机引擎(`worldlines` 或 `neonrp serve`)上:

```text
GET  /api/v1/play/schema                          规则包名 + 五张表(变量带当前值)
GET  /api/v1/play/schema/history?var=player.gold  一个变量的变化
GET  /api/v1/play/schema/events?since=0&type=…    已落地的事件
GET  /api/v1/play/schema/stream?pattern=…&since=  SSE:每条匹配的新事件
```

游玩这一侧只读不写:玩家只能提出,不能注册。注册在创作台打开的编辑会话上:`POST /api/v1/create/session/edit-local/schema/register {table, id, spec}` 和 `…/unregister {table, id}`,读接口同形(`/api/v1/create/session/edit-local/schema[/history|/events|/stream]`)。
