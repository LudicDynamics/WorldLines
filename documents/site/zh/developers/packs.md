---
title: "模板包开发"
description: "Pack = classes / actions / variables / triggers / mechanics / prompt。Python 包或 JSON 包。"
---

<!-- section: pack -->
## Pack

> **状态:随 1.0 发布**

```python
Pack(name, classes, actions, variables, triggers, mechanics, prompt, doc)
```

| 字段 | 填进哪里 |
|---|---|
| `classes` | 开 schema 的类(ClassSpec) |
| `actions` | 允许的 ops(ActionSpec:处理器 + 校验器) |
| `variables` | 闭 schema 变量 |
| `triggers` | WHEN / IF / THEN / ELSE |
| `mechanics` | 接缝:`contract` · `soul_turn` · `observe` · `settle` · `participation` |
| `prompt` | 模板自己的世界侧契约文本 |

内置四个:

- `rpg`(默认,开放世界 RPG);
- `pct`(沙盒跑团:建在 `rpg` 上,地图、人物、战斗层都沿用,换成 BRP 百分骰 —— 检定是 d100 对技能或属性 ×5,另有理智与濒死检定);
- `werewolf`(狼人杀:没有地图,座位是登记类,`vote` / `kill` 是模板自带 op,世界侧是法官);
- `monopoly`(大富翁:环形棋盘,掷骰、租金、税都由程序结算,讲述者只叙事和决定买不买)。

狼人杀和大富翁的存在就是证明:**引擎不含任何玩法。**

规则表、规则面板、检定与对抗、状态表、时钟怎么写,见 [规格](/docs/developers/specs) 里的「规则包 RPG Pack」。

<!-- section: json -->
## JSON 包

一个放着 `pack.json` 的文件夹;处理器写成 `builtin:…` 或 `module:function`;`extends` 继承,`null` 表示从父包去掉:

```json
{
  "name": "stoneford-trade", "extends": "rpg",
  "classes": {"caravan": {"required": ["from", "to", "cargo"], "folder": "game/caravans"}},
  "actions": {"new_npc": null,
              "trade": {"kind": "action", "handler": "mytrade:apply_trade", "validator": "mytrade:judge_trade",
                        "fields": ["town", "good", "qty"], "doc": "玩家在集市买卖"}},
  "variables": {"price.T001.grain": {"type": "int", "min": 1, "path": "game/towns/T001/market.json", "key": "price.grain"}}
}
```

<!-- section: resolve -->
## 世界用哪个包

`manifest.json["template"]` > `playthrough.json["template"]`(根目录或 `.neonrp/`)> 默认 `rpg`。名字的解析顺序:内置包 → 路径或 `module:PACK` → 世界自带的 `<world>/template/` → `NEONRP_TEMPLATE_PATH` 上的文件夹(WorldLines 的模板仓库)。

<!-- section: mixins -->
## mixins(设计中)

今天只支持单个 `extends`。计划加 `mixins: [...]`:一个基础模板 + 多个片段合并,冲突时报错。见 [写一个片段](/docs/developers/fragment)。
