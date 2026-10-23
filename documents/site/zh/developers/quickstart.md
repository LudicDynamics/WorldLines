---
title: "开发者快速开始"
description: "只装引擎:neonrp。在一个世界文件夹上注册、读、订阅。"
---

<!-- section: install -->
## 1. 安装引擎

> **状态:随 1.0 发布**

```bash
pip install neonrp            # 引擎包,提供 neonrp 命令与 Python 接口
```

`worldlines`(产品)依赖 `neonrp` 并钉住一个确定的 `neonrp` 版本。只想接引擎的话,装 `neonrp` 就够了。需要 Python 3.11+。

> 下面用到的 `neonrp schema`、`sdk.on`、模板包等接口随 1.0 发布。

<!-- section: world -->
## 2. 拿一个世界文件夹

引擎只认一个世界文件夹(有 `game/`)。内置的石津模板就在包里:

```bash
cp -r "$(python -c 'import neonrp, os; print(os.path.dirname(neonrp.__file__))')/templates/stoneford-elena" ./stoneford
cd stoneford
```

<!-- section: cli -->
## 3. 命令行

```bash
neonrp schema list variables
neonrp schema register variables price.T001.grain \
  --spec '{"type":"int","path":"game/towns/T001/market.json","key":"price.grain","min":1}'
neonrp schema watch "var.changed:*" --timeout 30
```

<!-- section: py -->
## 4. Python

```python
from pathlib import Path
from neonrp.core import sdk
from neonrp.core.registry import register, load_registry

root = Path("stoneford")
register(root, "variables", "price.T001.grain",
         {"type": "int", "path": "game/towns/T001/market.json", "key": "price.grain", "min": 1})
reg = load_registry(root)
print(reg.variables["player.gold"].value)

off = sdk.on("var.changed:player.gold", lambda ev: print(ev["payload"]))
```

下一步:[注册与订阅(Python)](/docs/developers/schema-api) · [模板包](/docs/developers/packs) · [接入 Godot](/docs/developers/godot)
