---
title: "Developer quickstart"
description: "Install only the engine: neonrp. Register, read and subscribe on a world folder."
---

<!-- section: install -->
## 1. Install the engine

> **Status: ships with 1.0**

```bash
pip install neonrp            # the engine package: the neonrp command and the Python interfaces
```

`worldlines` (the product) depends on `neonrp` and pins a specific `neonrp` version. If you only want the engine, `neonrp` is enough. Requires Python 3.11+.

> `neonrp schema`, `sdk.on`, template packs and the other interfaces used below ship with 1.0.

<!-- section: world -->
## 2. Get a world folder

The engine works on a world folder (one with `game/`). The built-in Stoneford template ships inside the package:

```bash
cp -r "$(python -c 'import neonrp, os; print(os.path.dirname(neonrp.__file__))')/templates/stoneford-elena" ./stoneford
cd stoneford
```

<!-- section: cli -->
## 3. Command line

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

Next: [Register & subscribe (Python)](/docs/developers/schema-api) · [Template packs](/docs/developers/packs) · [Godot](/docs/developers/godot)
