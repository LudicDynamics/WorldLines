---
title: "写一个片段"
description: "以经济片段为例:注册变量、注册类、登记 ops 与 T2 规则。"
---

<!-- section: shape -->
## 一个片段的形状

> **状态:设计中 · 接口为拟定** —— 3.0 定下的设计,名字和字段在实装前可能还会改。

一个片段只做三件事,而且全部走公开入口:

1. **注册变量** —— `stock.{镇}.{货}`、`price.{镇}.{货}`、`inv.{货}`、`econ.index`;
2. **注册类** —— `caravan`(带增长策略);
3. **登记 ops 与规则** —— 每个 op 一对 verify / apply;每拍跑的 T2 规则只能**提出** ops。

<!-- section: op -->
## op:verify + apply

```python
def judge_trade(root, op, reg):
    town, good, qty = op["town"], op["good"], op["qty"]
    if player_town(reg) != town:
        return Verdict.refuse(f"你不在{town_name(reg, town)}")
    if qty > 0 and gold(reg) < price(reg, town, good) * qty:
        return Verdict.refuse(f"钱不够:要 {price(reg, town, good) * qty} 铜")
    return Verdict.ok()

def apply_trade(root, op, reg, res):
    ...  # 改 stock / inv / 钱包,记进 res(引擎据此写账本 var.changed)
```

签名以引擎 `core/handlers.py` 为准;这里是示意。

<!-- section: rule -->
## T2 规则:只提出

```python
def economy_tick(root, reg):
    ops = []
    for town, good in markets(reg):
        p = round(base(good) * (target(town, good) / max(1, stock(reg, town, good))) ** 0.55)
        if p != price(reg, town, good):
            ops.append({"op": "set", "var": f"price.{town}.{good}", "value": p})
    return ops            # 交给 verify,和玩家的提出一样
```

势力片段同理:`faction.*.power`、`rel.a.b`、类 `quest` / `rumor`,规则每 4 拍出一次手(巡路、劫道、挂委托、罢工),传闻用 `spread` op 沿边扩散。完整可运行的版本在 3.0 mock 里。
