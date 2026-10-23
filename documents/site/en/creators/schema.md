---
title: "Register & subscribe (CLI)"
description: "Use neonrp schema to register variables, classes and instances, read values, and subscribe to changes. Follow along and it runs."
---

<!-- section: before -->
## Setup

> **Status: ships with 1.0**

Run every command inside a **world folder** (the one with `game/`), or pass `--world <path>`. `--json` prints one-line JSON. Registration writes to `game/meta/<table>.json` and **validates before writing** — if it fails, nothing is written.

```bash
neonrp schema list variables          # what exists now (template pack + world files + registrations)
neonrp schema list classes
neonrp schema list entries --class npc
```

<!-- section: var -->
## 1. Register a variable (closed schema)

Stoneford's grain price:

```bash
neonrp schema register variables price.T001.grain --spec '{
  "type": "int", "path": "game/towns/T001/market.json", "key": "price.grain",
  "value": 12, "min": 1, "max": 99,
  "doc": "Stoneford grain price (copper/measure). Fog season +1~3, caravan arrival −2~4"
}'
neonrp schema get price.T001.grain
```

| Field | Meaning |
|---|---|
| `type` | `int` · `float` · `str` · `bool`; anything else is rejected |
| `path` + `key` | **required**: which file and which (dotted) key holds the value |
| `min` · `max` · `max_key` | range; an `add` beyond it is clamped; `max_key` points at a dynamic max (e.g. `hp.max`) |
| `readonly` | only the engine may write it |
| `doc` | **the rule the model sees**, shown to the world agent next to the value |

Common errors: `variable type must be int|float|str|bool` · `variable needs path + key`.

<!-- section: class -->
## 2. Define a class, then add instances (open schema)

The class comes first, then its instances. Factions:

```bash
neonrp schema register classes faction --spec '{
  "required": ["name"], "folder": "game/factions", "scope": "world", "id_prefix": "F",
  "props": {"power": {"type": "int", "min": 0, "max": 100},
            "stance": {"type": "enum", "values": ["hostile", "neutral", "friendly"]}},
  "mutable": ["power", "stance"],
  "render": "- {id} {name} power {power}"
}'
neonrp schema register entries F_bandits --spec '{
  "class": "faction", "props": {"name": "One-Eyed Tiger bandits", "power": 46, "stance": "hostile"}
}'
neonrp schema list entries --class faction
```

| Class field | Meaning |
|---|---|
| `required` | props every instance must have |
| `folder` | where instances live (one JSON per instance); only classes with a folder can be `new`-ed during play |
| `scope` | which instances the model sees: `place` (here) · `town` · `world` |
| `props` | typed props: `int` `float` `str` `bool` `enum` (needs `values`) `list` |
| `mutable` | props `patch` may change during play (must be declared in props) |
| `rels` | references to other classes, e.g. `{"leader": "npc"}`; several allowed classes are joined with a vertical bar, e.g. npc or soul |
| `render` · `tier` | the one-line template shown to the model; context-trimming priority |

Common errors: `unknown class 'faction'; register it in classes first` · `class scope must be place|town|world` · `prop 'stance': enum needs values[]` · `mutable prop 'x' is not declared in props`.

<!-- section: rule -->
## 3. Rules, ops, and removal

```bash
neonrp schema register triggers bandits_strong --spec '{
  "when": {"entry": "F_bandits", "prop": "power"},
  "if": [{"entry": "F_bandits", "prop": "power", ">=": 60}],
  "then": [{"to": "narration", "text": "Caravans on the post road start travelling in convoys."}]
}'
neonrp schema unregister actions new_npc        # turn an op off (writes a tombstone)
neonrp schema unregister variables price.T001.grain
```

Full trigger syntax: [Triggers](/docs/creators/triggers).

<!-- section: read -->
## 4. Read (pull)

```bash
neonrp schema get player.gold                    # current value + definition
neonrp schema history player.gold                # every change of this variable
neonrp schema events --since 120 --type var.changed
```

<!-- section: watch -->
## 5. Subscribe (push)

Subscribe from another terminal; every matching event prints one JSON line (it reads `game/meta/events.jsonl`):

```bash
neonrp schema watch "var.changed:player.gold"
neonrp schema watch "entity.created:*" --timeout 60
```

```json
{"seq": 1043, "turn": 17, "ts": "…", "type": "var.changed", "payload": {"var": "player.gold", "from": 18, "to": 16, "by": "solve"}}
```

Patterns: `*` (everything) · `var.changed` (one type) · `var.changed:player.gold` (one key of a type) · `var.changed:*`. The full event-type table is in [Developers: register & subscribe](/docs/developers/schema-api).
