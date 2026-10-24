# Pack 规范(规则包 / 玩法包)

> 适用于 NeonRP 引擎当前实现。最小可运行单元 = **pack**(引擎规则)+ **world**(数据)+ **souls**(数据);**template** 可选地把三者绑在一起。本文只讲 pack,重点是 RPG 一系的两个包 `rpg` 和 `pct`。world 见 [world.zh.md](world.zh.md),soul 见 [soul.zh.md](soul.zh.md),template 见 [template.zh.md](template.zh.md)。
>
> 状态标记:**已实装** = 代码里有、今天就生效;**设计中** = 字段 / 键已预留或已声明,但引擎尚未完整使用。
>
> 一个包有哪些操作(op)、类、变量、触发器、接缝,引擎能现读给你:`neonrp spec ops --pack rpg`(或 `pct` / `werewolf` / `monopoly`)。本文讲的是那份清单之外的东西:规则表、面板、检定、状态、时钟,以及怎么写 / 改一个包。

---

## 1. 是什么

**pack 决定"这个世界按什么规则跑"**:有哪些类(地点、人、物、状态……)、模型能写哪些 op、每回合后台跑哪些确定性规则(tick)、检定怎么掷、子层(战斗、裁判)用什么提示词。世界只是数据;同一个世界换一个包,就是另一种玩法。

### 1.1 内置包

| 包 | 是什么 | 基于 | 状态 |
|---|---|---|---|
| `rpg` | 开放世界 RPG:镇 / 地点连通图、同地才同场、d20 检定、战斗层、远行、倒地、状态表、规则面板。**默认包** | — | 已实装 |
| `pct` | 百分骰调查(BRP 一系):d100 技能检定、理智、濒死体质检定、百分骰战斗 | `rpg` | 已实装 |
| `werewolf` | 狼人杀:无地图,一张桌,座位是类,`vote` / `kill`,结局是触发器 | — | 已实装 |
| `monopoly` | 大富翁:环形棋盘,掷骰前进、租金 / 税按程序结算 | — | 已实装 |

内置 mixin(叠在包上的插件):`economy`(市场、价格、商队)、`factions`(势力、关系、谣言)。写法 `rpg+economy+factions`;它们的数据在世界里(见 [template.zh.md](template.zh.md) §3.5)。

`pct` 保留 `rpg` 的全部(地图、地点、人物、物品、剧情包、状态表、角色状态、战斗层机制),只换骰子:检定改成 d100 ≤ 技能值,加 `[san]` 工具,倒地规则换成体质检定,战斗层换百分骰提示词。

### 1.2 Pack 字段

代码定义:`src/neonrp/packs/__init__.py:Pack`。JSON 包(`pack.json`)里键名相同。

| 字段 | 类型 | 默认 | 说明 | 状态 |
|---|---|---|---|---|
| `name` | str | 文件夹名 | 包名;组合 mixin 后变成 `base+m1+m2` | 已实装 |
| `classes` | {类名: 类定义} | `{}` | 开放 schema 的类(`parent_class` / `required` / `props` / `mutable` / `folder` / `effect` …,同 `game/meta/classes.json`) | 已实装 |
| `actions` | {op: 定义} | `{}` | 模型能写的 op(`kind` / `handler` / `fields` / `validator` / `doc` / `alias` / `wait` …,同 `game/meta/actions.json`) | 已实装 |
| `variables` | {名字: {type, path, key, min, max, max_step, monotonic, carry, …}} | `{}` | 封闭 schema 的变量(写在哪个文件的哪个键) | 已实装 |
| `triggers` | {id: {when, if, then, else}} | `{}` | 当 / 若 / 则 规则 | 已实装 |
| `mechanics` | {接缝: 处理器} | `{}` | 接缝 → `module:function` 或 `builtin:…`(接缝清单见 §2.3) | 已实装 |
| `prompt` | str 或 object | `""` | 字符串 = 世界侧合约文本;对象 = 提示词条目(rules / voice / entries / ops_docs),与世界的 `prompt.json` 同形 | 已实装 |
| `doc` | str | `""` | 一句话说明 | 已实装 |
| `flags` | {path, key} | `game/meta/flags.json` · `flags` | story flag 存在哪(`rpg` 用 `game/player/flags.json` · `story_flags`) | 已实装 |
| `blocks` | [str] | `["lines","ops","options"]` | 每回合要模型输出的块 | 已实装 |
| `modes` | {层名: 定义} | `{}` | 子层(战斗、地城、裁判):`prompt` / `reads` / `ops` / `exit` / `state` / `one_shot` / `output` / `tail` … | 已实装 |
| `loop` | object | `{}` | 回合循环配置片段;叠加顺序见 §2.3「回合循环」 | 已实装 |
| `ticks` | ["module:function"] | `[]` | 每次结算(apply)里、本回合 op 之后跑的确定性规则 | 已实装 |
| `mixins` | [str] | `[]` | 叠加的 mixin | 已实装 |
| `base` | str | `""` | 这个包基于哪个内置包(`pct` → `rpg`):层提示词找不到时回落到它的 | 已实装(仅 Python 包会设,见 §2.4) |
| `ui` | object | `{}` | 呈现声明:`slots` / `views` / `panels` / `prompts` / `budget` / `beats`(见 [template.zh.md](template.zh.md) §6) | 已实装 |
| `orchestration` | {nodes, edges} | `{}` | 这个包自己的编排图片段(如 `rpg` 的「进房间遇敌 → 战斗层」边) | 已实装 |
| `cast_class` | str | `""` | 演员不是 souls 时,哪个类的实例算演员(`werewolf` = `seat`) | 已实装 |

### 1.3 两种形态

- **Python 包**:`neonrp.packs.<name>.pack` 里的 `PACK`(四个内置包都是),或任意可导入的 `module:PACK`。
- **JSON 包**:一个含 `pack.json` 的文件夹,创作者 / agent 写的就是这种。处理器写成 `builtin:…` 或 `module:function`。

`pack.json` 可以 **`extends`** 一个已有包,只写差异:

```json
{
  "name": "grim-rpg",
  "extends": "rpg",
  "doc": "低魔、伤得重的 rpg 变体",
  "actions": { "new_town": null, "sheet": { "enabled": false } },
  "classes": { "curse": { "title": "诅咒", "effect": true, "props": { "turns": { "type": "int", "min": 0 } } } },
  "ui": { "prompts": { "modes.combat": { "zh": "你是战斗裁判……", "en": "You run the fight…" } } },
  "mixins": ["economy"]
}
```

合并规则(`Pack.from_dict`):

| 键 | 怎么叠 |
|---|---|
| `classes` / `actions` / `modes` | 按键覆盖、同键字段级合并;**写 `null` = 删掉**这一项 |
| `variables` / `triggers` / `mechanics` | 按键覆盖 |
| `flags` | 按键覆盖 |
| `blocks` | 整个替换 |
| `prompt`(对象) | 按条目合并 |
| `loop` | 深合并 |
| `ticks` | 追加在 base 之后 |
| `ui` | `slots` 按 (cls, slot)、`views` / `panels` 按 id 合并,写 `"remove": true` 删一项;`prompts` 按键,写 `null` 删;`budget` 替换 |
| `orchestration` | `nodes` 按键,`edges` 追加(同 id 替换) |
| `mixins` | 最后按顺序组合进来 |

---

## 2. 解析与叠加顺序

### 2.1 一个世界用哪个包 · 已实装

`src/neonrp/packs/__init__.py:template_of`,先找到的为准:

1. 世界根目录 `manifest.json` 的 `"template"`;
2. `game/playthrough.json` 的 `"template"`;
3. 根目录 `playthrough.json` 的 `"template"`;
4. 都没有 → `"rpg"`。

键名是 `template`(历史原因),值是包名。模板 build 时会把它写进 `manifest.json` 和 playthrough(见 [template.zh.md](template.zh.md) §8)。

### 2.2 名字怎么解析 · 已实装

`packs.load(name, root)`:

| 写法 | 解析到 |
|---|---|
| `rpg+economy+factions` | 先解析 `rpg`,再按顺序组合 mixin |
| `pkg.module:PACK` | 导入这个对象(`Pack` 或 dict) |
| 一个含 `pack.json` 的文件夹路径 | 这个 JSON 包 |
| `rpg` / `pct` / `werewolf` / `monopoly` | 内置包 |
| 其他名字 | 依次找 `<world>/template/<name>/pack.json`、`NEONRP_TEMPLATE_PATH` 上各目录的 `<name>/pack.json`,最后 `<world>/template/pack.json` |

都找不到 → `PackError`,模板 lint 报 `ref.pack`(block)。

### 2.3 每样东西的叠加顺序 · 已实装

后面的盖前面的。

| 东西 | 顺序 | 读取位置 |
|---|---|---|
| 规则表(`rules` / `foes` / `hazards`) | `packs/rpg/data/<表>.json` < 内置包自己的 `packs/<包>/data/<表>.json`(如 `pct`) < 旧世界 `world_map.json` 的 `travel` / `foes` < 世界 `game/rules/<表>.json` | `packs/rpg/data.py:table` |
| 状态表 | 内置包的 `packs/<包>/data/status.<lang>.md`(无则 `.en` → `.zh`) < 世界 `game/rules/status.md`(同名以世界为准) | `core/effect_rules.py:table` |
| 层提示词(战斗 / 地城 / 裁判) | 模板 / 世界覆盖(`ui.prompts["modes.<层>"]` 或 `game/meta/prompt.json` 的 `modes.<层>`)→ 世界自带 `agents/<id>/system.md` → 包的 `prompts/<层>.<lang>.md` → base 包的同名文件 | `core/modes.py:prompt_source` |
| 机制接缝 | 引擎通用默认 < `pack.mechanics` < `manifest.json` 的 `mechanics` < `game/meta/mechanics.json` | `core/mechanics.py` |
| 提示词条目 | `pack.prompt` < `manifest.json` 的 `prompt` < `game/meta/prompt.json` | `core/adv.py:prompt_spec` |
| 回合循环 | 内置默认 < `pack.loop` < 玩法合约的 `engine` < 编排模板(模板 `uses` 点名的那个,运行时叠上)< 世界的 `game/meta/engine.json` < 编排图的步骤参数 < playthrough 的 `engine` < 环境变量 | `core/engine_config.py:_layers` |
| 呈现 ui | 包(+ mixin)< 模板 `ui` | `packs:merge_ui` |

接缝(`core/mechanics.py:SEAMS`):`contract` · `soul_turn` · `observe` · `settle` · `participation` · `load` · `pack_hints` · `companions` · `speech_rule` · `gate` · `post_solve` · `understand` · `after_turn` · `roll_check` · `plan_event` · `run_outputs` · `sheet` · `skill_check`,共 18 个。`rpg` 填了其中 16 个(没填 `run_outputs`、`skill_check`);`pct` 换掉 `roll_check`、`load`、`sheet`、`skill_check`。

### 2.4 自己写的 JSON 包 extends rpg 时要知道的 · 已实装(行为如此)

- **规则表**总是从 `rpg` 的默认值起步;JSON 包文件夹里的 `data/` **不会被读**(只有内置包目录 `packs/<包>/data/` 会)。数值改在世界的 `game/rules/rules.json` 里(模板用 `world-overlay/game/rules/rules.json`)。
- **状态表**按包名找 `packs/<包名>/data/`,JSON 包没有这个目录 → 包这一层是空的,`rpg` 的默认状态行**不会继承**。要用就把行写进世界的 `game/rules/status.md`。
- **层提示词**:`extends` 不设置 `base`,所以 `rpg` 的 `prompts/combat.md` 等**不会回落**。给每个要用的层写一份覆盖:`pack.json` 的 `ui.prompts["modes.combat"]`(字符串或 `{zh,en,ja,ko}`),或世界里的 `agents/combat-referee/system.md`。
- 类、op、接缝、tick、模式定义、loop、ui 都正常继承。

---

## 3. 规则表(rulebook)

规则表就是 `data/rules.json`。引擎代码不认识任何具体属性、技能、身份——它们都是表里的行。

### 3.1 `rpg` 的 `data/rules.json` · 已实装

| 键 | 默认 | 含义 | 谁读 |
|---|---|---|---|
| `attr_mod_base` | `5` | 属性修正 = 属性值 − 它(属性 5 = +0,8 = +3) | 检定、裁判、战斗、倒地(simple) |
| `referee_difficulty` | `{easy: 8, normal: 12, hard: 15, very_hard: 18, extreme: 21}` | 难度档位 → DC | 检定、规则裁判 |
| `actions` | 11 行(见下) | 检定名目 → 用哪个属性 | 检定 |
| `fallback_attr` | `"int"` | 什么都没对上时用的属性 | 检定 |
| `dc_numbers` | `"tier"` | 主持(GM)写了数字 DC 时:`tier` = 读成最近的档位;`keep` = 数字照用 | 检定 |
| `baseline` | `{attributes: {str:5, dex:5, int:5, vit:5, cha:5}}` | 普通人的规则面板(回退链的底) | 面板 |
| `role_panels` | `{}` | 身份 → 面板;由世界 / 模板作者写 | 面板 |
| `generate_panels` | `false` | 预留:缺面板时是否让引擎生成 | 设计中(引擎尚未读取) |
| `down_rule` | `"srd"` | 倒地规则:`srd` / `simple` / `pct`(旧 id `dnd`→`srd`、`coc_simple`→`simple` 仍认) | 倒地 tick |
| `down_names` | —(`pct` 有) | 倒地 / 稳住 / 死亡三个状态名(四语) | 倒地 tick |
| `npc_hp_default` | `8` | 有 hp 的类、记录里没写 hp 时的初值 | 角色状态 |
| `def_base` | `10` | 防御 = 它 + 护甲 def + VIT 修正 | 战斗状态块 |
| `hit_die` / `damage_die` | `"1d20"` / `"1d6"` | 命中骰 / 默认伤害骰(写进战斗状态块) | 战斗层 |
| `unit_labels` | `{zh:"甲乙丙丁戊己", en:"ABCDEF", ja:…}` | 同种敌人的编号 | 战斗层 |
| `travel_per_day` | `20` | 一天走多少路程单位 | 远行 |

以 `_` 开头的键是注释,引擎不读。

**`actions` 行**(检定名目 → 属性):

```json
"persuade": {
  "zh": "说服", "en": "Persuade", "ja": "説得", "ko": "설득",
  "attr": "cha",
  "aliases": ["交涉", "砍价", "讲价", "negotiate", "haggle", "値切り", "흥정"]
}
```

内置 11 行:`persuade` `deceive` `intimidate`(cha)· `insight` `search` `recall`(int)· `stealth` `sleight` `dodge`(dex)· `athletics`(str)· `endure`(vit)。

匹配规则(`packs/rpg/panel.py:find`):在检定**自己的字眼**里找(理由那一段去掉,「为了侦查书房」不会把说服检定认成侦查);行键、四语名、aliases 都算名字,**最长的名字赢**;纯 ASCII 名字按词边界匹配,其他按子串。

**`dc_numbers`**:`tier` 时,数字读成最近的档位;正好落在两档中间,**取更难的那档**——读主持(GM)写的数字,永远不会让事情比它要的更容易。

### 3.2 `pct` 的 `data/rules.json` · 已实装

叠在 `rpg` 的表上(所以 `referee_difficulty`、`actions`、`attr_mod_base` 等仍在,只是百分骰检定不读它们)。

| 键 | 值 | 含义 |
|---|---|---|
| `attr_x` | `5` | 属性检定目标 = 属性 × 它 |
| `attrs` | `str con siz int pow dex cha edu` | 属性表:四语名 + `aliases`。`con` 的别名含 `vit`;`cha` 的别名含 `app` / `appearance` |
| `skills` | 33 行 | 技能表(见下) |
| `difficulty` | `{easy: 2, normal: 1, hard: 0.5}` | 档位 = 目标值倍率(容易 ×2、困难 ×½);不在表里的档位按 ×1 |
| `crit_div` / `special_div` | `20` / `5` | 大成功 ≤ ⌈目标/20⌉、特殊成功 ≤ ⌈目标/5⌉(向上取整,至少 1) |
| `fumble_min` | `99` | 掷出 99 / 00 大失败;目标 ≥ 99 时只有 00 大失败 |
| `fallback_attr` | `"int"` | 没对上任何技能时用的属性(× `attr_x`) |
| `baseline` | 8 项属性全为 `10` | 普通人面板 |
| `down_rule` | `"pct"` | 濒死:每次结算 d100 ≤ CON × 5,失败即死,三次成功稳住 |
| `down_names` | 濒死 / 稳住了 / 死亡(四语) | 倒地三状态的名字 |
| `npc_hp_default` | `11` | |
| `major_wound_ratio` | `0.5` | 一击掉最大 hp 的一半以上 → 挂「重伤」 |
| `san_max` | `99` | 理智上限 |
| `san_insane_ratio` | `0.5` | 一次结算内失去本场开始时 SAN 的一半 → 临时疯狂 |
| `damage_bonus` | `[{max:12, db:"-1d6"}, {max:16, db:"-1d4"}, {max:24, db:"0"}, {max:32, db:"+1d4"}, {max:40, db:"+1d6"}, {max:99, db:"+2d6"}]` | 按 STR + SIZ 查伤害加值 |
| `effect_names` | 重伤 / 临时疯狂 / 永久疯狂(四语) | pct tick 挂的状态名 |
| `weapons_default` | `{brawl:"1d3", melee:"1d6", firearms:"1d10", throw:"1d4"}` | 默认武器伤害骰(设计中:引擎尚未读取) |
| `system` | `"pct"` | 标记(引擎不读;检定结果里另写 `system: "pct"`) |

其他派生值(`packs/pct/rules.py`):hp = ⌈(CON + SIZ) / 2⌉(人物卡没写 hp 时);理智初值按人物卡 `san`。旧人物卡里的 `app` 读作 `cha`。

**`skills` 行**:

```json
"persuade": { "zh": "说服", "en": "Persuade", "ja": "…", "ko": "…",
              "base": 15, "attr": "cha", "opposed": "insight" },
"dodge":    { "zh": "闪避", "en": "Dodge", "base": "dex*2", "attr": "dex" },
"spot":     { "zh": "察觉", "en": "Spot", "base": 25, "attr": "int",
              "aliases": ["侦查", "搜查", "search", "탐색"] }
```

| 字段 | 含义 |
|---|---|
| `zh` / `en` / `ja` / `ko` | 显示名(按本局语言),也都是能被匹配的名字 |
| `base` | 没有自己的值时的底值:数字,或 `<属性>*n`(如 `dex*2`,属性值走面板回退链) |
| `attr` | 这项技能归哪个属性(给人和模型看;引擎算底值只读 `base`) |
| `opposed` | 对抗时对方用哪项技能(说服 ↔ 洞察、潜行 ↔ 聆听);没有就用同一项 |
| `aliases` | 旧名、俗名、别的语言;旧人物卡写旧名照样认,显示用今天的名字 |

### 3.3 其他表 · 已实装

| 表 | 每行 | 用途 |
|---|---|---|
| `foes.json` | 稳定 id → `hp` / `def` / `atk` / `dmg` / `names{lang}` / `aliases` / `traits{lang}`(`pct` 另有 `skill` 攻击 % / `dodge` 闪避 %) | 战斗层花名册;`foe` 行是兜底 |
| `hazards.json`(仅 `rpg`) | 路况标签 → `p` 每趟触发概率 / `dc`(1d6 目标)/ `fail_days` / `foes {敌人: [最少, 最多]}` / `also` / `text` `pass` `fail`{lang} | 远行路上的事 |

### 3.4 世界怎么改表 · 已实装

在世界里放 `game/rules/<表>.json`,**按键覆盖**:

- 对象逐层深合并:只写要改的键;
- 列表、数字、字符串整个替换(`damage_bonus` 要整张写);
- 写 `null` 让一行失效(如 `"skills": {"firearms": null}`);
- `_` 开头的键忽略,可以当注释。

```json
{
  "referee_difficulty": { "hard": 16 },
  "dc_numbers": "keep",
  "actions": { "pray": { "zh": "祈祷", "en": "Pray", "attr": "cha", "aliases": ["祷告"] } },
  "role_panels": { "gate_guard": { "attributes": { "str": 7, "vit": 7, "int": 4 } } }
}
```

参考:内置世界 `src/neonrp/templates/stoneford-elena/game/rules/rules.json`(13 个身份面板)。

---

## 4. 规则面板与回退链 · 已实装

规则面板 = 检定要读的那些数(属性、技能)。玩家、soul、NPC 用同一套(`packs/rpg/panel.py`)。**缺值从不拒绝检定**,沿下面的链往下找:

| 层 | 来源 | `source` 记作 |
|---|---|---|
| 1 sheet | 角色自己的记录:玩家 `game/player/stats.json`;soul 的 `character/stats.json`;NPC 在 `npcs.json` 里那一行(`attributes` / `skills`) | `sheet` |
| 2 本局已补 | 这一局之前补过的值:`game/states/<id>.json` 的 `panel` | 当初补它的那一层 |
| 3 身份面板 | 规则表 `role_panels[<身份>]`;身份 = 记录的 `role`(soul 取 playthrough souls 行的 `role`)。先精确匹配,再取身份字串里包含的**最长**键(「北门守门人」→ `守门人`) | `role:<键>` |
| 4 基线 | 规则表 `baseline` | `baseline` |

- 规则书没提过的属性:取基线各属性的中位数,仍记 `baseline`。
- 技能(pct):自己的值(任一名字)→ 本局已补 → 身份面板的 `skills` → 行的 `base`(`dex*2` 这种按属性链算,来源记 `base(<属性的来源>)`)→ 表里没有这项技能:`fallback_attr` × `attr_x`,结果带 `via: fallback_attr:<属性>`。
- 人物卡写了别名(如 `app`、`vit`):按 `attrs` 的 aliases 读成正名。

**写回**:从第 3、4 层(或 base)补到的值写进 `game/states/<id>.json`:

```json
{ "panel": { "attributes": { "cha": 7 }, "skills": { "spot": 25 },
             "source": { "attributes.cha": "role:shopkeeper", "skills.spot": "baseline" } } }
```

同一个角色下次读到同一个数,玩家也看得到它从哪来。作者的记录(sheet)在游玩中**从不改写**;soul 的文件夹保持干净,可以带去别的世界。

`game/states/<id>.json` 同时放这一局的角色状态:`hp` / `max_hp`(仅当该类 schema 声明了 `hp`)、`down` / `dead` / `stable` / `down_pass` / `down_fail`(`packs/rpg/character_state.py`)。

---

## 5. 检定与对抗

### 5.1 分工 · 已实装

- **主持(GM)只选,不写数字**:谁检定、对谁(对抗)、用什么(属性名或技能 / 名目)、哪一档难度、哪些状态算进来、为了什么。
- **引擎出数字**:读面板、加状态修正、掷骰、判成败。每一次掷骰都走同一个骰子工具(一个随机数后端、记账本、屏幕上的骰子行),按回合和检定内容播种:同一局重放掷出同样的点。

主持(GM)约定的检定在结算时交给接缝 `roll_check`(`rpg` → `packs/rpg/referee.py:roll_check`,`pct` → `packs/pct/rules.py:roll_check`)。一条检定写成:

```
<谁> [vs <谁>] <属性 | 技能 / 名目> <档位> [状态:<名字>] 为了<理由>
玩家 DEX normal 状态:扭伤 为了翻过矮墙
玩家 察觉 为了找暗门
旅人 vs 艾琳娜 力量 甩开她
```

档位是规则表里的键(`easy` / `normal` / `hard` …);理由不参与找技能。主持(GM)如果写了一个修正数字(`-9(扭伤)`),只记录为 `host_adj`,**不计入**;计入的是状态自己那一行的数(§6.3)。

### 5.2 `rpg`:d20 · 已实装

- 属性:检定点名的属性;否则按 `actions` 表从检定字眼里找;否则 `fallback_attr`。
- 修正 = 面板属性值 − `attr_mod_base` + 状态修正。
- DC:档位 → `referee_difficulty`;数字按 `dc_numbers`(§3.1);没写 → `normal`。
- 成功:1d20 + 修正 ≥ DC。
- **对抗**(`vs`):双方各掷 1d20 + 自己同一属性的修正;发起方总值 ≥ 对方总值即成功(平手归发起方)。

### 5.3 `pct`:d100 · 已实装

- 目标值:点名属性 → 属性 × `attr_x`;否则技能(§4 的技能链)。
- 难度档位乘目标值(`difficulty`);写数字时不缩放。
- 状态修正直接加在目标值上(百分点),最后夹在 1–99。
- 成功等级(`level`):`fumble`(99 / 00)→ `crit`(≤ ⌈目标/20⌉)→ `special`(≤ ⌈目标/5⌉)→ `success`(≤ 目标)→ `fail`。大失败先判。
- **对抗**:对方用发起技能行的 `opposed` 技能,没有就用同一项;等级高的赢,同为成功等级比余量(目标 − 掷出)大者,完全相同或都失败时发起方不算赢。

### 5.4 结果里有什么 · 已实装

每一方:`who` / `roll` / `mod` / `total` / `value`(面板值)/ `source`(§4)/ `effects`(计入的状态,如 `["扭伤-2"]`);`pct` 另有 `target` / `level` / `label`,可能带 `via`。整体:`result`(`success` / `fail`)、`dc` 或对方的 `b`、`tier`、`attr_how`(`named` / `action:<行>` / `fallback_attr`)。

来源的显示词在 `src/neonrp/prompts/rpg_pack.<lang>.json` 的 `panel_src_*`(面板 / 已补全 / 按身份补全 / 规则基线 / 由属性算),由 `panel.source_text` 拼成骰子行旁的标注。

### 5.5 叙事者能直接写的骰子工具 · 已实装

| op | 写法 | `rpg` | `pct` |
|---|---|---|---|
| `roll` | `[roll 1d6]` | 普通掷骰;远行路上有待定的事时,这一骰决定它 | 同 |
| `dice` | `[dice 1d20+2 vs 12]判定什么、为什么[/dice]` | 掷骰 + 过 / 未过(总值 ≥ vs) | `[dice 1d100 vs 60]` 低于等于成功并给等级;`[dice 察觉]` 直接按名字找玩家的技能 / 属性;`[dice 1d6+1d4]` 求和 |
| `referee` | `[referee 玩家想做的事]` | 规则裁判层给 JSON 裁定;要检定时它给难度档(或 DC)和属性,引擎掷 | 裁定给 `{skill, modifier}`(百分点),引擎掷;裁判不写 DC |
| `san` | `[san 0/1d6 看见尸体]` | — | d100 ≤ 当前 SAN:成功扣前者、失败扣后者,写回人物卡 |

点数永远由引擎出,模型只写要掷什么和为什么。

---

## 6. 状态表

### 6.1 行语法 · 已实装

内置包的 `data/status.<lang>.md`,或世界的 `game/rules/status.md`。一行一条,`#` 开头是注释:

```
<名字>: <规则,随便怎么写,用 · 分句>
轻伤: 持续 3 次结算 · 检定 -1,只作用于用到伤处的动作 · 皮肉伤,动起来牵着疼 · 包扎后下一次结算就好
疲惫: 持续 8 小时 · 检定 -1,作用于所有动作 · 腿发沉、反应慢 · 睡一觉可解
流血: 持续 2 次结算 · 每次结算 player.hp -1 · 伤口在渗血 · 包扎或止血草立止
```

冒号全角半角都行。引擎只认下面四种机制(`core/effect_rules.py:parse_rule`),其余文字给叙事者和主持(GM)读:

| 机制 | 写法(四语任一) | 落成属性 |
|---|---|---|
| 次数倒计时 | `持续 3 次结算` / `lasts 3 turns` / `3ターン` / `3턴` | `turns` |
| 游戏时间倒计时 | `持续 12 小时` / `持续 2 天` / `lasts 8 hours` | `hours`(天 × 24) |
| 每次结算的变化 | `每次结算 player.hp -1` / `each resolve player.hp -1`(同一分句里) | `each` = `player.hp:-1` |
| 检定修正 | `检定 -2` / `判定 -10` / `checks -2` / `판정 -10` | `check` |

分句符:`·` `;` `,` `。` `、` `|` 或 ` - `。四语的单位词表在 `src/neonrp/prompts/effect_rules.<lang>.json`,任何语言的行都按全部四语的词识别。

### 6.2 状态实例 · 已实装

状态是一个 **effect 类**(`rpg` 的 `status`,存在 `game/player/stats.json#status_effects`)。叙事者写 `new status <名字>`,引擎按表补全(`effect_rules.fill`):名字去掉尾巴上的数字,`turns` / `hours` / `each` 从规则行补,整行存进 `rule`。

| 属性 | 含义 |
|---|---|
| `on` | 挂在谁身上(默认玩家) |
| `turns` | 剩几次结算;每次结算减 1,到 0 移除 |
| `hours` → `until` / `until_text` | 游戏时间到期(见 §7) |
| `each` | 每次结算的变量变化;挂在别人身上时 `player.*` 改写成 `char.<id>.*` |
| `check` | 显式检定修正(优先于规则行) |
| `rule` / `note` | 规则原文 / 备注 |

表里没有的名字:用模型自己写的规则行,而且**追加进世界的 `game/rules/status.md`**,下次同名读同一条规则。表在世界文件改动后自动重读。

### 6.3 检定里的状态:`状态:名字` 与 ±n · 已实装

- 修正的**数字是规则行的**(`检定 -2`),由引擎加;状态实例上显式的 `check` 优先。规则行改了,下一次掷骰起就生效。
- **哪些状态适用于这一骰,是主持(GM)的判断**(「只作用于用到伤处的动作」这类话引擎不解析):主持在检定里写 `状态:<名字>`(多个就写多个名字),只有点名的那些计入。
- 检定一个状态都没点名 → 身上所有带修正的状态都计入。
- 对抗时,对方一侧计入它身上全部带修正的状态。

---

## 7. 时钟只进不退 · 已实装

`rpg` 的时间是两个变量,存在 `game/meta/run_state.json` 的 `time`:

| 变量 | 类型 | 规则 |
|---|---|---|
| `time.day` | int | 只增不减(`monotonic`);一回合的 op 最多推进 1(`max_step: 1`) |
| `time.clock` | `"HH:MM"` | 只增不减;设成更早的时刻:早 4 小时以上 = 第二天(`time.day` 自动 +1,`carry`),不到 4 小时 = 拒绝 |

- 往回拨会被拒绝,理由告诉模型「写这一刻发生了什么,时间由引擎推进」。玩家说「过了三天」是意图,不是已经过去的时间。
- 跨天的远行由引擎自己推进日历(§8.3),不是 op。
- 状态的游戏时间倒计时(`effects_clock` tick):第一次结算把 `hours` 换算成世界时钟上的 `until`(分钟)和 `until_text`(如 `D2 15:00`),之后时钟一过就移除——睡一大觉能一次过掉好几个小时的状态。没有时钟的世界只用次数倒计时。
- 自己的变量也可以声明 `monotonic` / `carry` / `max_step`(`game/meta/variables.json` 或 `pack.variables`)。

---

## 8. 战斗 / 倒地 / 旅行 / gates

### 8.1 战斗层 · 已实装

- 进入:叙事者写 `[combat 山贼×5 独眼虎×1]为什么打起来[/combat]`;标签里的 `名字×数` 是花名册(按 `foes` 表的名字 / 别名,任一语言,每种最多 6 个)。花名册里点到的是世界里已有的人(soul / NPC),她以自己的身份和 hp 上场。
- 没写花名册时依次取:路上待定的事的 `hazards.foes` → 当前房间的遭遇表(`encounters: [{enemy, count: "1-3", chance}]`)→ 交接词里提到的 → 一个 `foe`。
- 在层内:敌人是变量 `foe.<id>.hp` / `foe.<id>.status`;只能写层内的 op(`dice` `roll` `flag` `end_combat` `need` `map`,`pct` 另加 `san`),每次都要有 `[dice]`。
- 离开:`end_combat outcome=won|fled|lost`;路上待定的事随之结算(赢 = 过,其他 = 付出代价)。上一场的摘要留在 `run_state.json` 的 `last_combat`。
- 走进有遭遇表的地城房间,按 `chance` 播种掷一次,命中则下一回合进入战斗层;清过的房间不再掷。

### 8.2 倒地与死亡(`downed` tick)· 已实装

每次结算后跑,对玩家和所有 soul / NPC:

- hp 到 0(该类有 hp)→ 倒地:`down = 1`,挂「倒地」状态;这一次结算不掷。没有 hp 的类由叙事把 `char.<id>.down` 设为 1。
- 倒地、未稳住、未死:每次结算按 `down_rule` 掷一次:

| `down_rule` | 规则 |
|---|---|
| `srd` | d20 ≥ 10 算一次成功;掷出 1 算两次失败;掷出 20 直接以 1 hp 起身;三次成功稳住,三次失败死亡 |
| `simple` | d20 + VIT 修正 ≥ 12 活下来;一次失败即死;三次成功稳住 |
| `pct` | d100 ≤ CON × `attr_x`;一次失败即死;三次成功稳住 |

- hp 回到 1 以上 → 起身,计数清零,状态移除。
- 死亡:`dead = 1`,「死亡」替换「倒地」;她的 agent 不再行动。三个状态名可用 `down_names` 改。

`pct` 另有自己的 tick:一击掉最大 hp 的 `major_wound_ratio` 以上 → 「重伤」;理智工具留下的临时 / 永久疯狂落成状态;SAN 到 0 → 一次 `insane` 事件(合约的死亡规则决定它意味着什么)。

### 8.3 远行 · 已实装

- 世界地图的路线有 `distance`;天数 = ⌈距离 / `travel_per_day`⌉(不到半天路程算当天)。
- 路线的 `tags` 对上 `hazards` 表:按 `p` 播种决定这一趟遇到哪些事、在第几天。遇到时队伍停在那天,叙事者收到 `<event>`;叙事写到被拦为止,不写抵达。
- 待定的事:叙事者写 `[roll 1d6]`(≥ `dc` 过,否则多耗 `fail_days` 天),或 `[referee …]`,或打起来(战斗结局决定)。
- 日历由引擎推进,不是 op。

### 8.4 gates(回合前)· 已实装

接缝 `gate`(`packs/rpg/gates.py:pre_turn`):

- 路上有待定的事、玩家要动手 → 这一回合直接从战斗层开始;
- 玩家问地图 / 怎么走 → 引擎直接发 `map`;玩家要看属性 / 背包 → 引擎直接发 `sheet`(面板给玩家看,叙事里不念数值)。

---

## 9. 提示词与四语 · 已实装

| 东西 | 位置 | 语言回落 |
|---|---|---|
| 层提示词 | `packs/<包>/prompts/<层>.md`(中文原文)+ `<层>.en.md` / `.ja.md` / `.ko.md` | 本局语言 → en → zh |
| 包的字符串(op 说明、类标题、状态块) | `src/neonrp/prompts/rpg_pack.<lang>.json`、`rpg_i18n.<lang>.json`、`pct.<lang>.json` 等 | 本局语言 → en → zh |
| 状态表 | `packs/<包>/data/status.<lang>.md` | 本局语言 → en → zh |
| 状态表的单位词 | `src/neonrp/prompts/effect_rules.<lang>.json` | 四语一起识别 |
| 规则表里的名字 | 行内的 `zh` / `en` / `ja` / `ko` | 本局语言 → zh / en |

- op 的说明写在 `doc`(中文 / 默认)和 `doc_i18n`(`{en, ja, ko}`);`pack.json` 里 `doc` 也可以直接写成 `{zh, en, ja, ko}`。
- 规则表、状态表、技能名是**数据**,每种语言是原生写的,不是从中文翻的;新加一行时四语都给。
- 状态表进入叙事者每回合的世界上下文(「状态表」一节),规则文本 `game/rules/*.md` 进入战斗层 / 裁判层的读取块。

---

## 10. 授权

| 规则来源 | 用在哪 | 授权 |
|---|---|---|
| **SRD 5.2**(System Reference Document 5.2,Wizards of the Coast LLC) | `rpg` 的 d20 检定与倒地规则(`down_rule: srd`)、`core/dice.py` 的 `srd` ruleset | CC-BY-4.0 |
| **BRP**(*Basic Roleplaying: Universal Game Engine*,Chaosium Inc.) | `pct` 包的百分骰规则与 `data/` 下的规则表、`core/dice.py` 的 `brp` ruleset | ORC License |

- 包 id 仍叫 `pct`(百分骰);骰子核心的 ruleset id 是 `srd` / `brp`,旧 id `5e` / `coc` 仍被接受,分别读作 `srd` / `brp`(`core/dice.py:canonical_ruleset`)。
- 完整署名见 `src/neonrp/templates/CONTENT-LICENSE.md` 和 `src/neonrp/packs/pct/NOTICE.md`。"Basic Roleplaying" 与 "BRP" 是 Chaosium Inc. 的商标,本包与其无关联、未获背书。
- 自己写的规则包:用开放规则就照上面署名;不要在包名、提示词、显示名里用商业规则书的商标,用通用说法(d20、百分骰、沙盒跑团)。

---

## 11. 写一个规则包:最短路径

**只改数值(最常见)**——不写包,改世界:

1. 世界 `manifest.json`:`{"template": "rpg"}`(或 `pct`)。
2. `game/rules/rules.json`:要改的档位、名目、身份面板(§3.4)。
3. `game/rules/status.md`:本世界的状态行(§6.1),同名覆盖包的。
4. `game/rules/*.md`:给战斗 / 裁判层读的规则文本。

**改玩法**——写 JSON 包:

1. `<world>/template/<名字>/pack.json`,`"extends": "rpg"`,只写差异(§1.3)。
2. 新的检定名目、技能、身份仍写在世界的 `game/rules/rules.json`;状态行写在 `game/rules/status.md`(§2.4)。
3. 要用的层(战斗 / 裁判 / 地城)各给一份提示词:`ui.prompts["modes.<层>"]`(§2.4)。
4. 世界 `manifest.json`:`{"template": "<名字>"}`。

检查:

```
neonrp spec ops --pack <名字>      # 包加载得了吗、有哪些 op / 类 / 变量 / 接缝
neonrp validate                    # 世界(JSON 能解析、引用不悬空)
neonrp template lint <dir>         # 模板:ref.pack / pack.mixin / pack.engine
```

---

## 12. 参考实现位置

| 主题 | 位置 |
|---|---|
| Pack 定义、JSON 包、extends、mixin 组合、ui 合并、解析 | `src/neonrp/packs/__init__.py:Pack`、`from_dict`、`compose`、`merge_ui`、`load`、`template_of`、`resolve` |
| rpg 的类 / op / 模式 / 接缝 / tick | `src/neonrp/packs/rpg/pack.py:CLASSES`、`ACTIONS`、`MODES`、`MECHANICS`、`LOOP` |
| pct 在 rpg 上换了什么 | `src/neonrp/packs/pct/pack.py` |
| 规则表与叠加 | `src/neonrp/packs/rpg/data.py:table`、`rules`;`packs/rpg/data/rules.json`、`foes.json`、`hazards.json`;`packs/pct/data/rules.json`、`foes.json` |
| 规则面板与回退链 | `src/neonrp/packs/rpg/panel.py:attr`、`skill`、`action_attr`、`find`、`status_mod`、`nearest_tier`、`source_text` |
| 角色状态文件 | `src/neonrp/packs/rpg/character_state.py` |
| d20 检定 / 规则裁判 | `src/neonrp/packs/rpg/referee.py:roll_check`、`ruling` |
| d100 检定 / 等级 / 对抗 / 伤害加值 | `src/neonrp/packs/pct/rules.py:roll_check`、`level`、`better`、`damage_bonus`、`down_roll`;`packs/pct/tools.py:dice`、`san`;`packs/pct/referee.py` |
| 骰子核心与 ruleset | `src/neonrp/core/dice.py:roll_check`、`canonical_ruleset`、`roll_expr`、`rng_for` |
| 骰子工具 | `src/neonrp/packs/rpg/tools.py:roll`、`dice`、`sheet` |
| 状态表行语法 | `src/neonrp/core/effect_rules.py:parse_rule`、`table`、`lookup`、`fill`、`check_of`;`src/neonrp/prompts/effect_rules.<lang>.json` |
| 状态倒计时与每回合变化 | `src/neonrp/core/effects.py:tick_ops`、`instances` |
| 时钟只进不退 | `src/neonrp/packs/rpg/loaders.py:_load_variables`(`time.day` / `time.clock`)、`src/neonrp/core/sdk.py:_clock_back`;`src/neonrp/core/registry.py:VarSpec` |
| 状态的游戏时间到期 | `src/neonrp/packs/rpg/effects_clock.py:tick` |
| 倒地 / 死亡 | `src/neonrp/packs/rpg/downed.py:tick` |
| pct 的重伤 / 疯狂 | `src/neonrp/packs/pct/tick.py:tick` |
| 战斗层 | `src/neonrp/packs/rpg/combat.py:spawn`、`end`、`maybe_encounter`;`src/neonrp/packs/pct/combat.py` |
| 远行 | `src/neonrp/packs/rpg/travel.py:plan`、`referee`、`resolve`、`route_days` |
| 回合前 gates | `src/neonrp/packs/rpg/gates.py:pre_turn` |
| 层提示词解析 | `src/neonrp/core/modes.py:prompt_source`、`layer_system`;`packs/rpg/prompts/`、`packs/pct/prompts/` |
| 接缝 | `src/neonrp/core/mechanics.py:SEAMS` |
| mixin | `src/neonrp/packs/mixins/economy.py`、`factions.py` |
| 授权 | `src/neonrp/templates/CONTENT-LICENSE.md`、`src/neonrp/packs/pct/NOTICE.md` |
