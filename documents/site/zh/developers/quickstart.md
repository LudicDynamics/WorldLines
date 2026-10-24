---
title: "开发者快速开始"
description: "装引擎,把内置模板搭成一个世界文件夹,在上面读变量、注册、订阅、让世界自己跑几拍。"
---

<!-- section: install -->
## 1. 安装

```bash
pip install worldlines        # 产品壳 + 它钉住版本的 neonrp 引擎 + 两个内置模板
```

需要 Python 3.10 或更高。装好后有两个命令:`neonrp`(引擎命令行)和 `worldlines`(本机网页)。

`neonrp` 也能单独装(`pip install neonrp`),但内置模板(灰橡宅 `pct-house`、石津镇 `stoneford-town`)在 `worldlines` 包里,单装引擎时 `neonrp template list` 是空的。

**两种引擎。** PyPI 上的包带完整的两拍编排(商量拍 + 清算拍)。从 GitHub 开源仓的源码安装,得到的是开源引擎:同样的接口,回合只有一拍(清算拍)。本页的命令两种都能跑。

<!-- section: world -->
## 2. 搭一个世界文件夹

引擎操作的单位是一个世界文件夹(里面有 `game/`)。从内置模板搭一个:

```bash
neonrp template build stoneford-town ./stoneford
cd stoneford
```

`template build` 先跑 lint,通过后把模板的世界、角色、规则包、剧情都铺进 `./stoneford`。这个文件夹可以直接玩(`neonrp tui --play`),也可以交给 `neonrp serve`(见[协议](/docs/developers/protocol))。

<!-- section: cli -->
## 3. 命令行

```bash
neonrp schema list variables                 # 所有闭 schema 变量和当前值
neonrp schema get player.gold
neonrp schema register variables curfew.T001 \
  --spec '{"type":"int","path":"game/locations/T001/location.json","key":"curfew","min":0,"max":3,"doc":"0 无宵禁 · 3 全城封门"}'
neonrp schema watch "var.changed:*" --timeout 30
neonrp engine tick -n 3                      # 世界自己走三拍(不调模型)
neonrp engine explain                        # 生效的引擎设置,以及各自来自哪一层
```

注册写进 `game/meta/variables.json`,之后模型每回合都能看到这个变量和它的 `doc`。不要用已有的名字(比如 `price.T001.grain`):注册默认覆盖同名项,会盖掉 economy 片段自己的只读变量。

<!-- section: py -->
## 4. Python

```python
from pathlib import Path
from neonrp.core import sdk
from neonrp.core.registry import register, load_registry

root = Path("stoneford")
register(root, "variables", "curfew.T001",
         {"type": "int", "path": "game/locations/T001/location.json", "key": "curfew", "min": 0, "max": 3})
reg = load_registry(root)
print(reg.variables["player.gold"].value)          # 18

for r in sdk.tick(root, turns=3):                  # 不调模型:规则包和片段的 tick + 触发器跑三拍
    print(r.turn, [a["var"] for a in r.applied if "var" in a][:3])
```

`sdk.tick` 让世界在没有玩家输入时自己走(石津镇的 economy 片段会改库存和价格)。订阅用 `sdk.on`,见[注册与订阅](/docs/developers/schema-api)。

下一步:[注册与订阅(Python)](/docs/developers/schema-api) · [规则包](/docs/developers/packs) · [协议](/docs/developers/protocol) · [接入 Godot](/docs/developers/godot)
