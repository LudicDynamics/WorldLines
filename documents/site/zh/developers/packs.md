---
title: "规则包开发"
description: "规则包(Pack)决定一局里有什么类、op、变量、触发器和接缝。Python 包或 JSON 包,可以叠片段。"
---

<!-- section: template -->
## 模板里怎么选

模板在 `template.json` 里写:

```json
"pack": {"name": "rpg", "mixins": ["economy"], "engine": {"turn": {"mode": "v3"}}}
```

- `name`:基础规则包;
- `mixins`:叠在上面的片段,见[写一个片段](/docs/developers/fragment);
- `engine`:这一局的引擎设置,搭局时合进 `game/meta/engine.json`。

搭出来的一局在 `manifest.json` 的 `template` 里记下组合名,如 `rpg+economy`。

<!-- section: pack -->
## Pack

```python
Pack(name, classes, actions, variables, triggers, mechanics, prompt, doc,
     flags=…, blocks=…, prompt_spec=…, modes={}, loop={}, ticks=[], mixins=(),
     base="", orchestration={}, ui={}, cast_class="")
```

| 字段 | 填进哪里 |
|---|---|
| `classes` | 开 schema 的类(ClassSpec) |
| `actions` | 允许的 op(ActionSpec:处理器 + 校验器) |
| `variables` | 闭 schema 变量 |
| `triggers` | WHEN / IF / THEN / ELSE |
| `mechanics` | 接缝 → 处理器名(见下) |
| `modes` | 模式层(如战斗):自己的提示词、可用 op、退出 op |
| `loop` | 这个包的回合设置(引擎配置片段) |
| `ticks` | 每次落地后跑的世界规则,`module:function` |
| `mixins` · `base` | 叠上的片段;建在哪个内置包上(pct → rpg) |
| `orchestration` | 这个包对编排图的补充节点和边 |
| `ui` | 素材槽、视图、面板、拍的显示方式 |
| `cast_class` | 卡司不是角色时,哪个类的实例算卡司(如狼人杀的座位) |
| `prompt` · `prompt_spec` | 包自己的世界侧说明文本和提示条目 |

内置四个:

- `rpg`(默认,开放世界 RPG);
- `pct`(沙盒跑团:建在 `rpg` 上,地图、人物、战斗层都沿用,换成百分骰 —— 检定是 d100 对技能或属性,另有理智检定);
- `werewolf`(狼人杀:没有地图,座位是登记类,`vote` / `kill` 是包自带的 op,世界侧是法官);
- `monopoly`(大富翁:环形棋盘,掷骰、租金、税都由程序结算,讲述者只叙事和决定买不买)。

狼人杀和大富翁的存在就是证明:**引擎不含任何玩法。** 每个包能用的 op、类、变量:`neonrp spec ops --pack <名字>`。

规则表、规则面板、检定与对抗、状态表、时钟怎么写,见[规格](/docs/developers/specs)里的「规则包 Pack」。

<!-- section: seams -->
## 接缝

引擎核心只知道这些接缝存在,具体由哪个函数填,由规则包登记(也可以在世界的 `manifest.json["mechanics"]` 或 `game/meta/mechanics.json` 里覆盖)。共 18 个:

`contract` · `soul_turn` · `observe` · `settle` · `participation` · `load` · `pack_hints` · `companions` · `speech_rule` · `gate` · `post_solve` · `understand` · `after_turn` · `roll_check` · `plan_event` · `run_outputs` · `sheet` · `skill_check`

签名和默认值见 `neonrp/core/mechanics.py` 的文件头。op 的 `validator` / `handler` 是另一类接缝,登记在 actions 里。

<!-- section: json -->
## JSON 包

一个放着 `pack.json` 的文件夹;处理器写成 `builtin:…` 或 `module:function`;`extends` 继承,`null` 表示从父包去掉;`mixins` 也可以写在这里:

```json
{
  "name": "stoneford-guilds", "extends": "rpg", "mixins": ["economy"],
  "classes": {"guild": {"required": ["name"], "folder": "game/guilds", "scope": "town"}},
  "actions": {"new_npc": null,
              "pay_dues": {"kind": "action", "handler": "myguilds:pay_dues", "validator": "myguilds:judge_dues",
                           "fields": ["guild", "amount"], "doc": "玩家向行会交会费"}},
  "variables": {"guild.T001.dues": {"type": "int", "min": 0, "path": "game/towns/T001/guild.json", "key": "dues"}}
}
```

<!-- section: resolve -->
## 名字怎么解析

一局用哪个包:`manifest.json["template"]` > `playthrough.json["template"]`(根目录或 `.neonrp/`)> 默认 `rpg`。

名字按这个顺序找:

1. 带 `+` 的(`rpg+economy`):拆开,基础包 + 片段;
2. `module:PACK`:导入那个对象;
3. 一个含 `pack.json` 的文件夹路径;
4. 内置包 `rpg` / `werewolf` / `monopoly` / `pct`;
5. 世界自带的 `<world>/template/`,然后 `NEONRP_TEMPLATE_PATH` 上的文件夹里同名的 `pack.json`。

<!-- section: config -->
## 设置的层级

一局的引擎设置分层合并,后者覆盖前者:

内置默认 < 规则包 `loop` < 玩法合约 < 编排(模板 `uses` 选的编排)< 世界 `game/meta/engine.json`(含模板 `pack.engine`)< 编排图步骤参数 < 这一局 `playthrough` < 环境变量

在世界文件夹里跑 `neonrp engine explain`,列出每个设置的生效值和它来自哪一层。
