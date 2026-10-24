---
title: "Developer quickstart"
description: "Install the engine, build a world folder from a bundled template, then read variables, register, subscribe and let the world run on its own."
---

<!-- section: install -->
## 1. Install

```bash
pip install worldlines        # the product shell + the neonrp engine version it pins + two bundled templates
```

Python 3.10 or later. You get two commands: `neonrp` (the engine CLI) and `worldlines` (the local web app).

`neonrp` installs on its own too (`pip install neonrp`), but the bundled templates (Greyoak House `pct-house`, Stoneford `stoneford-town`) ship in the `worldlines` package; with the engine alone, `neonrp template list` is empty.

**Two engines.** The package on PyPI includes the full two-beat orchestration (a planning beat, then a resolve beat). Building from the open-source GitHub repo gives you the open engine: the same interfaces, but a turn is a single beat (resolve only). Every command on this page works on both.

<!-- section: world -->
## 2. Build a world folder

The engine works on a world folder (one with `game/` in it). Build one from a bundled template:

```bash
neonrp template build stoneford-town ./stoneford
cd stoneford
```

`template build` lints first, then lays the template's world, characters, rules pack and plots into `./stoneford`. The folder is playable as it is (`neonrp tui --play`), and `neonrp serve` can host it (see [Protocol](/docs/developers/protocol)).

<!-- section: cli -->
## 3. Command line

```bash
neonrp schema list variables                 # every closed-schema variable and its value
neonrp schema get player.gold
neonrp schema register variables curfew.T001 \
  --spec '{"type":"int","path":"game/locations/T001/location.json","key":"curfew","min":0,"max":3,"doc":"0 no curfew · 3 the whole town shut"}'
neonrp schema watch "var.changed:*" --timeout 30
neonrp engine tick -n 3                      # the world runs three steps on its own (no model call)
neonrp engine explain                        # the engine settings in effect, and which layer each comes from
```

A registration goes into `game/meta/variables.json`; from then on the model sees the variable and its `doc` every turn. Don't reuse an existing name (such as `price.T001.grain`): registering replaces an entry of the same name by default, and would overwrite the economy mixin's own read-only variable.

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

for r in sdk.tick(root, turns=3):                  # no model: the pack's and mixins' ticks + triggers run three steps
    print(r.turn, [a["var"] for a in r.applied if "var" in a][:3])
```

`sdk.tick` moves the world with no player input (Stoneford's economy mixin changes stock and prices). Subscribe with `sdk.on`; see [Register & subscribe](/docs/developers/schema-api).

Next: [Register & subscribe (Python)](/docs/developers/schema-api) · [Rules packs](/docs/developers/packs) · [Protocol](/docs/developers/protocol) · [Godot](/docs/developers/godot)
