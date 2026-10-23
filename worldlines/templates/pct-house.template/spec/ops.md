# Play pack `pct`

percentile investigation (pct): d100 skills, composure, dying CON checks, percentile combat — built on rpg

Built on `rpg` (its layer prompts are the fallback)

## Ops

| op | alias | kind | fields | scope | validated | doc |
|---|---|---|---|---|---|---|
| `move_to` | move | action | who, to | world | ✓ | 移动:谁 = player 或在场角色 / NPC 的名字,去哪 = 本镇地点 id,或一个新地名(地图上还没有就当场建出来)。写这回合最终到达的地点,不写途经;镇内任何地点一回合都能到 |
| `engage` |  | action | who, note | world |  | v2b 的转述;v3 的 ② 已并行跑过所有在场角色,世界侧不再出(niko 09-27 Q7) |
| `need` | ask | request | who | world |  | 请求:需要某个在场角色先回话才能写下去;一回合最多两个 |
| `set` |  | update | var, value | world |  | 变量表里的键 = 值 |
| `add` |  | update | var, delta | world |  | 变量表里的整数键 += delta |
| `flag` |  | update | key | world |  | story flag |
| `new_location` |  | action | name, parent, links | world | ✓ | 新地点(writer):new_location <名字> 加一个关系说它在地图的哪一层——near=<A>[,<B>] 和它们同层、挨着;between=<A>,<B> 在两地之间的路上;in=<A> 在 A 里面(下一层,只能从 A 进出);over=<A>,<B> 把同层的几处包进来(上一层,比如一个街区)。说不清就不写,引擎先挂在玩家旁边,回合后再按叙事挂好 |
| `link` |  | action | a, b | world | ✓ | 新连一条路:link <地点A> <地点B>(同一个镇里本来不通的两处,比如发现了一条近道) |
| `unlink` |  | action | a, b | world | ✓ | 断一条路:unlink <地点A> <地点B>(桥塌了、路被封了;断了会让镇上有地方走不到就不行) |
| `new_town` |  | action | name, from, days, summary, tags | world | ✓ | 新城镇(writer):玩家要去一个世界地图上还没有的城镇时,世界当场长出来——new_town <名字> from=<从哪个镇修路过去> days=<路上几天> summary=<一句话> tags=<路况,逗号分隔>;之后照常赶路过去 |
| `new_npc` |  | action | name, at, role | world | ✓ | 新路人(writer) |
| `new` |  | action | class, name | world |  | 开放 schema:新建一个登记类的实例,写成 new <类> <名字> 属性=值 …(哪些类、哪些属性见词条包「可登记的类」) |
| `patch` |  | update | who, props | world |  | 开放 schema:给任何一个人 / 物 / 地方写属性,写成 patch <名字> 属性=值 …;新属性直接加,写进它自己的记录(声明过的属性只限可变的;名字、id、位置不能改——让谁去哪儿用 move) |
| `remove` |  | update | who | world |  | 开放 schema:一个实例离开世界(用光了、结束了),写成 remove <名字> |
| `write` |  | action | path | world |  | 文件:新建或覆盖世界文件夹里的一个 .json / .md / .txt 文件,写成 [~write 路径]内容[/write](JSON 要能解析;路径相对世界文件夹,见「世界文件夹」) |
| `edit` |  | action | path | world |  | 文件:改一个 JSON 文件里的键,写成 edit <路径> 键=值 …(点号表示嵌套,新键直接加) |
| `rm` |  | action | path | world |  | 文件:删除一个文件,写成 rm <路径>(只限游玩中写的、或开放 schema 目录里的) |
| `mkdir` |  | action | path | world |  | 文件夹:新建一个文件夹,写成 mkdir <路径> |
| `rmdir` |  | action | path | world |  | 文件夹:删除一个游玩中建的文件夹(连同里面的文件),写成 rmdir <路径> |
| `define` |  | action | kind, name | world |  | 开放 schema:世界里需要一种还没有的东西时当场定义——define class <类名> <标题> 属性=类型 …(类型 int/str/bool/list,选项写 a\|b\|c)mutable=可改的属性,…(effect=yes:随回合生效的状态);define var <名字> <类型> <初始值> min= max=。定义之后马上可以 new / patch / remove / 写变量 |
| `mood` |  | update | who, value | souls |  | 角色情绪;soul 侧 SoulPatch 专用,世界侧不出 |
| `roll` |  | tool | dice | world |  | 请求:掷骰,写 1d6 / 2d10 / 2d6+1 这种,不要自己编点数 |
| `dice` |  | tool | dice, vs | world |  | 检定:[dice 察觉]判定什么、为什么[/dice] 或 [dice 1d100 vs 60]…[/dice](百分骰:掷出 ≤ 技能值算成功,技能值 1/20 以内大成功、1/5 以内特殊成功,99 / 00 大失败);伤害或别的数:[dice 1d6+1d4]。点数和成败引擎出,理由你写 |
| `map` |  | tool |  | world |  | 地图:[~map] 引擎按真实状态画一张当前位置的字符地图(镇内 / 地穴 / 路上)直接给玩家看;不等回包,lines 照常往下写;不要自己画图 |
| `sheet` |  | tool |  | world |  | 人物卡:[~sheet] 引擎把玩家的属性 / 背包 / 钱袋画成面板直接给玩家看;不等回包;叙事里不要念数值 |
| `referee` |  | tool | question | world |  | 请求裁判:[referee 玩家想做的不确定 / 过分的事];规则裁判读规则和人物卡给裁定(能不能、要不要检定、后果),你按裁定写 |
| `combat` |  | tool | roster, note | world | ✓ | 交手:[combat 山贼×5 独眼虎×1]这一拍各人怎么打(谁攻谁、谁守、谁跑)[/combat];战斗层按规则结算这一回合(引擎掷命中 / 伤害、扣 hp),回包后按结果接着写;下一拍还在打就再调一次;名字×数 = 对面的花名册(已在打的就不用写) |
| `end_combat` |  | update | outcome | plugin |  | 引擎写:战斗结束(敌人全倒或逃走 won / 玩家离开 fled);叙事和战斗层都不写 |
| `san` |  | tool | spec | world |  | 理智检定:[san 成功损失/失败损失 理由],例 [san 0/1d6 看见那具尸体];引擎掷 d100 对当前 SAN,扣理智、必要时判临时疯狂,回包后你按结果写 |

## Classes (open schema)

| class | parent | folder | required | props | growth policy |
|---|---|---|---|---|---|
| `world` |  |  | name |  | auto |
| `town` | world |  | name |  | auto |
| `place` | town |  | name |  | auto |
| `region` | world |  | name |  | auto |
| `player` |  |  | name |  | auto |
| `soul` |  |  | name | hp, max_hp | auto |
| `npc` |  |  | name | hp, max_hp | auto |
| `item` |  |  | name |  | auto |
| `job` | town |  | name |  | auto |
| `dungeon` | world |  | name |  | auto |
| `road` | world |  | name |  | auto |
| `room` | dungeon |  | name |  | auto |
| `carry` |  | game/player/inventory.json#items | name | qty | auto |
| `status` |  | game/player/stats.json#status_effects | name | turns, check, each, note, rule, hours, until, until_text, on | auto |

## Mode layers

- `combat`: {"title": {"zh": "战斗裁判", "en": "Combat referee", "ja": "戦闘審判", "ko": "전투 심판"}, "prompt": "agents/combat-referee/system.md", "reads": ["rules"], "reads_title": {"zh": "规则", "en": "Rules", "ja": "ルール", "ko": "규칙"}, "one_shot": true, "ops": ["dice", "roll", "flag", "san"], "spawn": "neonrp.packs.pct.co…
- `dungeon`: {"title": {"zh": "地穴主持", "en": "Dungeon host", "ja": "ダンジョン進行役", "ko": "던전 진행자"}, "prompt": "agents/dungeon-agent/system.md", "reads": ["rules"], "here_class": "room", "ops": [], "tail": {"zh": "房间的可做 / 可能遭遇来自词条包;遭遇由引擎按遭遇表决定(见 # 引擎的消息),不要自己编敌人;打起来写 [combat]…[/combat]。", "en": "A room's things to do …
- `referee`: {"title": {"zh": "规则裁判", "en": "Rules referee", "ja": "ルール審判", "ko": "규칙 심판"}, "prompt": "agents/rules-referee/system.md", "reads": ["rules"], "output": "json", "one_shot": true, "strip": ["读写边界", "读什么文件", "语言匹配", "不出选项菜单", "Read/Write", "Language", "No menus"]}

## Mechanics seams

- `contract` → `neonrp.packs.rpg.contract:contract`
- `soul_turn` → `neonrp.packs.rpg.soul_step:soul_step`
- `observe` → `builtin:observe.pack`
- `settle` → `neonrp.packs.rpg.soul_settle:settle_souls`
- `after_turn` → `neonrp.packs.rpg.atlas.fix:after_turn`
- `roll_check` → `neonrp.packs.pct.rules:roll_check`
- `plan_event` → `neonrp.packs.rpg.travel:plan_event`
- `participation` → `neonrp.packs.rpg.atlas.move:colocated`
- `load` → `neonrp.packs.pct.loaders:load`
- `pack_hints` → `neonrp.packs.rpg.contract:pack_hints`
- `companions` → `neonrp.packs.rpg.rules:follow`
- `speech_rule` → `neonrp.packs.rpg.rules:missing_speech`
- `gate` → `neonrp.packs.rpg.gates:pre_turn`
- `post_solve` → `neonrp.packs.rpg.travel:overshoot`
- `understand` → `neonrp.packs.rpg.understand:understand`
- `sheet` → `neonrp.packs.pct.rules:sheet`
- `skill_check` → `neonrp.packs.pct.rules:skill_check`
