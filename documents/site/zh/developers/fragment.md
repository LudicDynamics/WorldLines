---
title: "写一个片段(mixin)"
description: "以内置的 economy 片段为例:类、op(校验 + 落地)、每拍跑的 tick、视图;规则在片段里,数据在世界里。"
---

<!-- section: shape -->
## 一个片段的形状

片段(mixin)叠在一个基础规则包上:模板写 `"pack": {"name": "rpg", "mixins": ["economy"]}`,这一局的规则包就是 `rpg+economy`。内置两个:`economy`(集市、价格、商队、买卖)和 `factions`(势力、关系、传闻、委托)。源码在 `neonrp/packs/mixins/`。

片段是一个字典 `MIXIN`,键和规则包一样:

| 键 | 作用 |
|---|---|
| `classes` | 开 schema 的类,如 `caravan` |
| `actions` | op:`handler`(落地)+ 可选的 `validator`(校验)+ `fields` + `doc`(模型每回合读到的说明) |
| `variables` · `triggers` | 闭 schema 变量和触发器 |
| `ticks` | 每次落地后跑的世界规则(不调模型) |
| `ui` | 素材槽、视图、面板 |
| `prompt` | 给模型的提示条目 |
| `mechanics` · `loop` · `orchestration` | 接缝(只填基础包空着的)、回合设置、编排图的补充 |

合并规则:类 / op / 变量 / 触发器同名时后来的覆盖前面的,不报错;tick 追加;接缝只填基础包没填的。

**规则在片段里,数据在世界里。** economy 读 `game/world/economy.json`(货物、各镇市场、路线);世界没有这个文件时片段不起作用,lint 报 `pack.mixin.data` 警告。石津镇的这份数据在它的 `world-overlay/game/world/economy.json`。

<!-- section: install -->
## 安装:登记变量

搭一局时(`template build` / 开新局),引擎对每个内置片段调 `install(root)`。economy 在这里按世界数据登记闭 schema 变量并写入初始值:

```python
def install(root):
    d = data(root)                                   # game/world/economy.json
    specs = {}
    for t, m in d["markets"].items():
        for g in d["goods"]:
            specs[f"price.{t}.{g}"] = {"type": "int", "path": f"game/towns/{t}/market.json", "key": f"price.{g}",
                                       "min": 1, "max": 9999, "readonly": True, "seed": …, "doc": …}
            ...                                      # stock.<T>.<g> · inv.<g> · econ.index 同理
    return register_vars(root, specs)                # 写 game/meta/variables.json,只补缺的
```

`readonly` 的变量模型不能直接改,只能由片段自己的 op 和 tick 改。

<!-- section: op -->
## op:校验 + 落地

```python
from neonrp.core.handlers import Verdict

def judge_trade(root, reg, op) -> Verdict:
    t = town_of(reg, reg.player_location)
    g, qty = str(op.get("good") or ""), int(op.get("qty") or 0)
    if t not in data(root)["markets"]:
        return Verdict(False, reason="这里没有集市")
    if qty > 0 and coins(reg) < price(reg, t, g) * qty:
        return Verdict(False, reason=f"钱不够:要 {price(reg, t, g) * qty} 铜", scope="field", field="qty")
    return Verdict(True, data={"good": g, "qty": qty, "town": t})   # data 合进被接受的 op

def trade(root, reg, op, res):
    ...                    # 改钱包、stock、inv(set_var)
    return {"town": t, "unit": unit, "total": total, "side": "buy" if qty > 0 else "sell"}
```

- 校验器 `validator(root, reg, op) -> Verdict`,落地 `handler(root, reg, op, res) -> dict`;
- `Verdict(ok, to=None, clamped=False, reason="", allowed=[], data={}, scope="world", field="op", fixable=True)` 是一个 dataclass,用构造函数建;
- 被拒时 `reason` 会交给模型(可修的拒绝让它重写状态),所以写成人话;`fixable=False` 表示别再提;
- 登记:`"trade": {"kind": "action", "handler": "neonrp.packs.mixins.economy:trade", "validator": "neonrp.packs.mixins.economy:judge_trade", "fields": ["good", "qty"], "doc": …}`。

<!-- section: rule -->
## tick:只提出

```python
def tick(root, reg, *, turn, res) -> list[dict]:
    ops = []
    for t, g in markets(reg):
        p = price_from_stock(...)
        if p != vint(reg, f"price.{t}.{g}"):
            ops.append({"op": "set", "var": f"price.{t}.{g}", "value": p})
    return ops

tick.unit = {"on": "apply", "llm": False,
             "writes": ["var:stock.*", "var:price.*", "var:econ.index", "op:new_caravan", "op:haul", "op:deliver", "op:rob"]}
```

在 `MIXIN["ticks"]` 里登记:`["neonrp.packs.mixins.economy:tick"]`。每次落地,在这一回合自己的 op 之后、触发器之前跑。tick 返回的 op 不走模型那一套校验,但引擎会拒掉两种:没登记的 op,以及超出 `tick.unit["writes"]` 声明范围的写。拒绝记在这一拍的 `refused` 里,不会打断回合。随机数用按 `(turn, 事件)` 播种的 `rng(...)`,回放同一回合结果相同。

economy 的 tick 依次做:产出减消耗 → 价格跟着库存走 → 路上的商队移动、被劫或到达 → 差价够大的路线发新商队。

<!-- section: own -->
## 写自己的片段

片段名按两种方式找:内置名字从 `neonrp.packs.mixins.<名字>` 导入;否则当作路径,读那个文件夹里的 `mixin.json`(或那个 JSON 文件),形状同上,处理器写成 `module:function`(模块要能被导入)。

- `install` 只对 `neonrp.packs.mixins` 下的片段调用;JSON 片段要在 `variables` 里直接写出变量。
- 路径按引擎进程的当前目录解析,所以目前请用绝对路径,适合本机试验。
- 改完跑 `neonrp template lint <模板>`:片段找不到是 block,世界缺数据文件是 warn。
