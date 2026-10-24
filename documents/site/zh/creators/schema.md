---
title: "注册与订阅(命令行)"
description: "用 neonrp schema 注册变量、类、实例,读值,订阅变化。照着做就能跑。"
---

<!-- section: before -->
## 准备

> **状态:随 1.0 发布**

所有命令都在**一局的文件夹**里跑(有 `game/` 的那个,在 `~/.worldlines/plays/` 下;下面的例子用石津镇的一局),或者加 `--world <路径>`。加 `--json` 输出单行 JSON。注册写进 `game/meta/<表>.json`,**写之前先校验**,过不了就报错、不写。

```bash
neonrp schema list variables          # 看现在有哪些变量(模板包 + 世界文件 + 注册)
neonrp schema list classes
neonrp schema list entries --class npc
```

<!-- section: var -->
## 1. 注册一个变量(闭 schema)

石津北门的灯笼:

```bash
neonrp schema register variables town.T001.lanterns --spec '{
  "type": "int", "path": "game/towns/T001/town.json", "key": "lanterns",
  "min": 0, "max": 20,
  "doc": "石津北门还亮着的灯笼数。雾越浓灭得越多"
}'
neonrp schema get town.T001.lanterns
```

名字别和片段的变量撞:石津装了经济片段,`price.T001.grain` 这类集市变量已经被它占用(只读),同名注册会把它覆盖掉。

| 字段 | 说明 |
|---|---|
| `type` | `int` · `float` · `str` · `bool`,别的会被拒 |
| `path` + `key` | **必填**:值存在哪个文件的哪个键(点号路径) |
| `min` · `max` · `max_key` | 范围;`add` 超出会被钳位;`max_key` 指向动态上限(如 `hp.max`) |
| `readonly` | 只有引擎能写 |
| `doc` | **模型看到的规则**,和值放在一起给讲述者看 |

常见报错:`variable type must be int|float|str|bool` · `variable needs path + key`。

<!-- section: class -->
## 2. 定义一个类,再加实例(开 schema)

先有类,才能有实例。势力:

```bash
neonrp schema register classes faction --spec '{
  "required": ["name"], "folder": "game/factions", "scope": "world", "id_prefix": "F",
  "props": {"power": {"type": "int", "min": 0, "max": 100},
            "stance": {"type": "enum", "values": ["hostile", "neutral", "friendly"]}},
  "mutable": ["power", "stance"],
  "render": "- {id} {name} 势力{power}"
}'
neonrp schema register entries F_bandits --spec '{
  "class": "faction", "props": {"name": "独眼虎山贼", "power": 46, "stance": "hostile"}
}'
neonrp schema list entries --class faction
```

| 类字段 | 说明 |
|---|---|
| `required` | 实例必须有的属性 |
| `folder` | 实例存放的文件夹(一个实例一个 JSON);有 folder 的类才能在游玩中 `new` |
| `scope` | 给模型看哪些实例:`place`(此地)· `town` · `world` |
| `props` | 类型化属性:`int` `float` `str` `bool` `enum`(要 `values`)`list` |
| `mutable` | 游玩中 `patch` 能改的属性(必须在 props 里声明过) |
| `rels` | 指向其他类的引用,如 `{"leader": "npc"}`;允许多个类时用竖线连接,例如 npc 或 soul |
| `render` · `tier` | 给模型看的一行模板、上下文裁剪优先级 |

常见报错:`unknown class 'faction'; register it in classes first` · `class scope must be place|town|world` · `prop 'stance': enum needs values[]` · `mutable prop 'x' is not declared in props`。

<!-- section: rule -->
## 3. 规则、op 与撤销

```bash
neonrp schema register triggers bandits_strong --spec '{
  "when": {"entry": "F_bandits", "prop": "power"},
  "if": [{"entry": "F_bandits", "prop": "power", ">=": 60}],
  "then": [{"to": "narration", "text": "驿路上的商队开始结伴而行。"}]
}'
neonrp schema unregister actions new_npc        # 关掉一个 op(写入墓碑)
neonrp schema unregister variables town.T001.lanterns
```

触发规则的完整写法见 [触发规则](/docs/creators/triggers)。

<!-- section: read -->
## 4. 读(pull)

```bash
neonrp schema get player.gold                    # 这个变量的定义
neonrp schema history player.gold                # 这个变量的每次变化
neonrp schema events --since 120 --type var.changed
```

<!-- section: watch -->
## 5. 订阅(push)

在另一个终端里订阅,每条匹配的事件打印一行 JSON(它在读 `game/meta/events.jsonl`):

```bash
neonrp schema watch "var.changed:player.gold"
neonrp schema watch "entity.created:*" --timeout 60
```

```json
{"seq": 1043, "turn": 17, "ts": "…", "type": "var.changed", "payload": {"var": "player.gold", "from": 18, "to": 16, "by": "solve"}}
```

写法:`*`(全部)· `var.changed`(一种)· `var.changed:player.gold`(一种里的一个键)· `var.changed:*`。事件类型全表见 [开发者:注册与订阅](/docs/developers/schema-api)。
