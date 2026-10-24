# 玩法合约规范(`worldlines.play-contract/1`)

> 状态:字段、lint、结算 **已实装**(`src/neonrp/template/contract.py` · `src/neonrp/core/settlement.py`);
> §6 角色协议 **设计中**。现行四份合约的原文:`neonrp spec contracts`。

## 1. 是什么

一份玩法合约规定**一种玩法原型必须给玩家的体验**:怎么进、怎么出、要几个结局、给什么奖励、死亡怎么结算、
结束时固定输出什么,以及发布的门槛。模板用顶层 `"play_contract": "<id>@<版本>"` 声明它承诺哪一份。

- 合约**只管体验,不管编排**:一回合怎么跑由模板的 `uses` 点名的编排模板决定(如 `two_beat` 两拍、`one_beat` 一拍),模板的 `orchestration` 只是在它上面打补丁(template spec 3.1)。同一份合约可以配不同的编排。
- lint 按合约做静态检查(§4);测试台跑到出口时引擎写结算(§5)。
- 文件:`<id>.play-contract.json`。查找顺序:`NEONRP_PLAY_CONTRACT_PATH`(`:` 分隔)→ 源码的 `worldlines/contracts/` → 安装包带的那份。

官方四份:

| id | 名称 | 出口 | 结局 | 发布门槛 |
|---|---|---|---|---|
| `mystery-trpg` | 沙盒跑团 | 到达结局,谜底必须揭晓 | ≥ 3,含真相结局 | lint 无 block + 跑通一个结局 |
| `open-adventure` | 开放冒险 | 段落结算(一天) | 不要求 | lint 无 block + 结算一段 |
| `murder-mystery` | 解谜型剧本杀 | 指认真凶后进结局,真相必须揭晓 | ≥ 2,含真相结局 | lint 无 block + 跑通一个结局 |
| `romance-companion` | 恋爱陪伴 | 段落结算(一次约会) | 不要求 | lint 无 block + 结算一段 |

## 2. 最小例子

```json
{
  "schema": "worldlines.play-contract/1",
  "id": "my-mystery",
  "version": 1,
  "title": {"zh": "我的解谜", "en": "My Mystery"},
  "pitch": {"zh": "一句话说这种玩法给玩家什么。"},
  "entry": {"opening": "required", "cast": "fixed"},
  "exit": {"on": "ending", "reveal": "required"},
  "endings": {"min": 2, "require": ["true"]},
  "rewards": {"player": ["ending_cg"], "soul": ["memory_carry"], "world": []},
  "deaths": {"player": {"exit": "ending", "ending_kind": "fail"}},
  "outputs": ["ending_id", "truth_reveal", "cg_unlocked"],
  "publish": {"lint": "no_block", "test_run": "reach_one_ending"}
}
```

## 3. 字段

| 键 | 类型 | 含义 | 状态 |
|---|---|---|---|
| `schema` | str | 固定 `"worldlines.play-contract/1"` | 已实装 |
| `id` · `version` | str · int | 模板引用写 `"<id>@<version>"`;只写 id 取当前版本 | 已实装 |
| `title` · `pitch` | 多语言对象 | 卡面上的名称和一句话;`{zh, en, ja, ko}` 任选 | 已实装 |
| `entry.opening` | `"required"` | 必须有开场(世界 `game-start.json` 的 `startup.opening_scene`) | 已实装(lint) |
| `entry.cast` | `"fixed"` \| `"open"` | fixed:模板必须定好演员(演员表、世界原生角色或规则包的座位类);open:玩家可以带人进来 | 已实装(lint · fixed) |
| `entry.roles` | `"assigned"` | 开局给每个角色发身份(剧本杀 / 狼人杀) | 约定 |
| `exit.on` | `"ending"` \| `"segment"` | 到结局结束;或按段落结算、游戏继续 | 已实装 |
| `exit.segment` | `"day"` \| `"date"` … | 段落是什么;`day` 由引擎在 `time.day` 前进时结算 | `day` 已实装 |
| `exit.via` | str | 怎么到结局(如 `accusation` 指认) | 约定 |
| `exit.reveal` | `"required"` | 结局时必须揭晓真相:每个有结局的剧情都要有 `reveal` | 已实装(lint) |
| `endings.min` | int | 至少几个结局 | 已实装(lint) |
| `endings.require` | list[str] | 必须有的结局种类(结局的 `kind`,如 `true` · `fail`) | 已实装(lint) |
| `rewards.player` · `.soul` · `.world` | list[str] | 一局给什么:`ending_cg` · `clue_codex` · `trust` · `affection` · `memory_carry` · `map_unlock` … | 记录已实装;带走多数是约定 |
| `deaths` | object | 死亡怎么结算,见 3.1 | 已实装 |
| `outputs` | list[str] | 结算必须给出的东西:`ending_id` · `truth_reveal` · `accusation` · `cg_unlocked` · `segment_id` … | `truth_reveal` · `accusation` 已实装 |
| `settlement.truth_quiz` | `"required"` | 结算后的「真相三问」**必须有**,而且必须由剧情包写:`plot.json` 的 `truth_quiz.questions`(3 题,题目和选项四语,`answer` 是正确序号;`reward_soul` 写了就必须是演员表里的 sid,且角色可以带走)。`mystery-trpg` 带这一项。引擎按谜底出题只是兜底(自由区 / 旧模板),不是正路(见 5.1) | 已实装(lint · 10-16) |
| `settlement.truth_quiz_points` | `{settle, per_right, fallback}` | 真相三问发的 Worldlines 额度(整数 ≥ 0):每局给 `settle + per_right × 答对数`;没有角色跟玩家走时(没全对 · 没题的局 · 全对但那位早已带着完整记忆在收藏里)另加 `fallback` 保底。`mystery-trpg` 默认 200 / 100 / 0(完成一局 200,每对一题 +100,最多 500);模板 `template.json` 的 `settlement.truth_quiz_points` 可覆盖其中几项。数额是数据,引擎里不写;都没写 = 0(lint `truth_quiz.points` warn)。额度记为待发放 | 已实装(10-20) |
| `publish.lint` | `"no_block"` | 发布前 lint 不能有 block | 已实装 |
| `publish.test_run` | `"reach_one_ending"` \| `"settle_one_segment"` | 发布前测试台要跑到的地方 | 约定 |
| `engine` | object | 兼容旧包用(可选):写进引擎配置,排在规则包之后、编排模板之前(世界自己的 `game/meta/engine.json` 仍可覆盖)。新模板用 `uses` 选编排,不靠这一段;没写 `uses` 的旧包 / 旧存档,有合约就按两拍的设置跑(引擎里没有两拍时退回一拍)。公开合约不带这一段;发布版另有取值,运行时叠上,不进存档 | 已实装 |

### 3.1 `deaths`

```json
"deaths": {
  "player":    {"exit": "ending", "ending_kind": "fail"},
  "companion": {"settle": "record", "plot": "optional"},
  "other":     {"settle": "record"},
  "insanity":  {"exit": "ending", "ending_kind": "fail"}
}
```

- `player` 玩家 · `companion` 带进来的角色(soul)· `other` 世界里的其他人 · `insanity` 心智归零(只对有心智类数值的世界;键名沿用 insanity)。
- `{"exit": "ending", "ending_kind": "fail"}`:游戏到出口,走模板剧情里第一个这种 `kind` 的结局(带 CG / 尾声);模板没有 → 引擎给一个普通的死亡出口(lint `contract.deaths` warn)。
- `{"settle": "record"}`:只记进结算的 `deaths`,游戏继续;`"plot": "optional"` = 模板可以用一条剧情接住这次死亡。
- 没写的:玩家默认出口,其他人默认记录。

## 4. lint(按合约)

| code | 级别 | 什么时候报 |
|---|---|---|
| `contract.unknown` | block | `play_contract` 指的合约找不到 |
| `contract.entry` | block | 要开场却没有;要固定演员却没定 |
| `contract.exit` | block | 到结局结束,但没有任何触发器能到达一个结局 |
| `contract.endings` | block | 结局数不够 `min`;缺 `require` 里的种类 |
| `contract.reveal` | block | 要揭晓真相,但有结局的剧情没写 `reveal` |
| `contract.rewards` | block | 奖励里有 `ending_cg`,但有结局没有图片槽 |
| `contract.deaths` | warn | 死亡要走某种结局,但模板没有这种结局 |
| `contract.truth_quiz` | 默认区 block · 自由区 warn | 合约要真相三问(`settlement.truth_quiz: required`),但没有剧情包写 `truth_quiz.questions` |
| `truth_quiz.schema` | 默认区 block · 自由区 warn | `truth_quiz` 形状不对:不是 3 题、题目 / 选项缺、`answer` 不是选项序号(某个语言层改坏了也算,`where` 带 `[语言]`) |
| `truth_quiz.lang` | 默认区 block · 自由区 warn | 四语(zh · en · ja · ko)里某种语言缺题目或选项:写成 `{zh, en, ja, ko}`,或在 `i18n/<lang>/plots/<P>/plot.json` 里翻 `truth_quiz`;语言层改了正确答案也报 |
| `truth_quiz.reward_soul` | 默认区 block · 自由区 warn | `reward_soul` 不是演员表里的 sid,或那个角色 `takeable: false`(三题全对也带不走) |
| `truth_quiz.points` | warn | 合约和模板都没写 `settlement.truth_quiz_points`(这局真相三问给 0 额度),或写的不是 `{settle, per_right, fallback}` 的非负整数 |

默认区 / 自由区 = 模板的 `zone`(`reviewed` / `open`);没写按自由区。剧情包自己的检查(`src/neonrp/packs/rpg/plot.py:lint`,没有单独的命令)不知道分区,形状问题只报 warn;`neonrp template lint` 再按分区定级。

## 5. 结算(到出口时引擎写的)

`game/meta/settlement.json`(`worldlines.settlement/1`),同时发 `run.settled` 事件:

```json
{"schema": "worldlines.settlement/1",
 "exit": {"kind": "ending" | "death" | "insanity", "id": "E01", "turn": 12},
 "cg_unlocked": ["E01"], "epilogue": "…", "deaths": [{"who": "…", "name": "…", "kind": "player", "turn": 9, "cause": "…"}],
 "rewards": {"player": {"ending_cg": ["E01"]}, "soul": {"trust": {"温妮": 3}}},
 "contract": "mystery-trpg@1",
 "truth_reveal": {"text": "…"}, "accusation": []}
```

段落合约(`exit.on: segment`)每段写一份 `game/meta/segments/day-<n>.json`,游戏继续。

### 5.1 结算之后:真相三问 · 里程碑 · 成就 · 待发奖励(10-15)

| 接口 | 做什么 |
|---|---|
| `GET /api/v1/play/engine/settlement/quiz` | 沙盒跑团(`mystery-trpg`)的真相三问:`{state: locked\|open\|answered\|unavailable, questions: [{id, q, options}], reward_soul, points: {settle, per_right, fallback}, result?}`。结算前 `locked`,不出题;题目用剧情包 `truth_quiz.questions` —— `mystery-trpg` 合约**要求必须写**(§3 `settlement.truth_quiz`,lint §4);`by` = `author`。兜底(自由区 / 旧模板没写时,不是正路):引擎按谜底出一次(`by: model`,存 `meta/truth_quiz.json`),模型出不来 = `unavailable`(`by: none`,玩家直接领保底额度:`POST {answers: []}`) |
| `POST /api/v1/play/engine/settlement/quiz {answers: [i,i,i]}` | 判分一次(再交返回第一次的结果):三题全对 → `reward_soul` 带完整记忆回家(`memory: full`;已在收集里但记忆从头开始 = 升级,算送到);没送到人(没全对 · 没题 · 那位早已带完整记忆)→ 保底额度 `fallback`;每局另给 `settle + per_right × 答对数`(§3 `settlement.truth_quiz_points`)。都记为待发。结果带 `delivered` · `fallback` · `no_questions`。保底不再是「带走一个角色」;老客户端传的 `take` 忽略 |
| `GET /api/v1/play/engine/settlement/milestones` | 开放冒险这一局的里程碑 `{enabled, milestones: [{id, type: place\|job\|day\|stretch, label, points, art, generate}], settled}` |
| `POST /api/v1/play/engine/settlement/leave` | 玩家离开:上次离开之后的里程碑结算,额度(暂定:地点 30 · 委托 75 · 一天 45 · 一段路 30)和图记为待发;地点只算有图的(作者的图或场景图),每局最多 10 个;再离开只结新的 |
| `GET /api/v1/play/engine/achievements` | 这一局能解锁的全部成就(内置 + 模板自己的),带 `unlocked` / `at` |

开放冒险可以一直玩下去:一段时间(12 拍)没有里程碑,「这段路又往前走了一程」本身就是一个(`stretch`)。里程碑不要求有专属图,`art` 按顺序取:作者的图(这个地点 / 委托的剧情图)`{kind: cg, slot}` → 引擎给零件、前端合成 `{kind: composite, scene: <当前地点的场景图槽>, souls: [{iid, sid, name, slot: <sprite,没有就 portrait>}], caption}` → `generate: {scene, caption}` 给前端的「实时生图」按钮(Voyager 可点,其他人灰着、点了去升级页;引擎自己不生图)。

事件(`/engine/beats`):`milestone {id, type, label, points, art, generate}` · `achievement.unlocked {id, title, desc, scope, points}`。
内置成就:`first_ending` · `first_character` · `characters_5` · `first_milestone`(每个玩家一次)· `true_ending` · `all_endings` · `quiz_perfect` · `places_5` · `places_10` · `run_complete`(每个世界一次),四语名在 `prompts/achievements.<lang>.json`。
玩家数据(`~/.worldlines/player-data/<player>.json`)多了 `rewards: [{id, kind: points, amount, cg?, world, source, status: pending}]`——发额度要平台接口,引擎只记待发。

### 5.2 奖励卡 · 合约自己的成就 · 「打完一局」(10-18)

模板用数据声明自己的奖励卡 —— `template.json` 的 `rewards`(引擎不写任何世界的词):

```json
"rewards": [{"id": "half_burnt_diary", "kind": "card", "rarity": "common",
             "title": {"zh": "…", "en": "…", "ja": "…", "ko": "…"}, "desc": {…},
             "when": "stage:P01:1",                       // 也可以是列表:全部成立
             "slot": "item.icon:I801"}]                   // 或 "image": "assets/reward-<id>.webp"
```

- `when` —— 和成就同一套条件:`ending:<id>` · `ending_kind:<kind>` · `flag:<key>` · `stage:<plot>:<n>` · `var:<key>:<n>`(≥ n)· `places:<n>` · `character:<sid>` · `milestone:<n>` · `quiz_perfect` · `run_end`
- `kind` —— `card`(Hub 的收集卡片);别的 kind 照写照存、按卡片显示(lint 警告)。`rarity` —— common · rare · epic
- 图 —— `slot` = 用模板里已有的一张图;否则用这张卡自己的槽 `reward:<id>`(素材台里和别的槽一样补)
- 合约放行:`rewards.player` 里有 `cards`(四份官方合约都有);没合约 = 放行;自由区模板(`zone: open`)一张都不发。lint:读不了的行 block,其余都是警告
- 每个世界每张一次;存进玩家记录(`cards`,图复制到记录旁边)—— 收集到的不会被收回,作者删了也不收。每张卡记着拿到时的模板版本;作者出新版,Hub 提示可以拉取新的卡面(获得的角色同理拉新人设,记忆保留)
- 结算里列出这一局拿到的卡:`rewards.player.cards: [id, …]`

合约可以带自己的 `achievements`(和模板的同一种行),对按它玩的每个世界都有效 —— 只能用不点名世界东西的条件:`ending_kind:<kind>` · `places:<n>` · `milestone:<n>` · `quiz_perfect` · `run_end`。

「打完一局」= 这一局到了出口(`run.settled`)。玩家记录多一行 `runs {world, run, exit, ending?, version}`,内置成就 `run_complete`(每个世界一次)解锁。

事件:`reward.granted {id, kind, world, title, desc, rarity, image?}`。接口:`GET /api/v1/local/player-data?lang=` → `cards: [{id, world, kind, title, desc, rarity, image, version, upd, gone}]`、`characters[].upd` · `POST /api/v1/local/player-data/refresh {kind: cards|characters, world, id}` · `GET /api/v1/local/player-data/card?world=&id=`(存下来的图)。

## 6. 角色协议 `souls`(设计中)

合约规定角色进来要满足什么、在这一局里拿到什么、结束时什么写回角色库(soul spec 4.4)。

```jsonc
"souls": {
  "in":     {"sheet": "pct", "player": "required", "companion": {"min": 0, "max": 3}, "assets": ["portrait"]},
  "assign": ["role", "secret"],
  "out":    ["memory_carry", "trust"]
}
```

| 段 | 含义 |
|---|---|
| `in.sheet` | 要什么卡:`pct`(属性 + d100 技能 + 心智类数值)· `rpg` · `none`;link 进来的角色缺卡 → 开局跑转换器生成 `character/sheets/<合约 id>.json` |
| `in.player` · `in.companion` · `in.assets` | 主角要不要、同伴几个、必须有的素材 |
| `assign` | 世界发给角色的东西(身份、秘密、座位、阵营),只活在这一局,永不写回角色库 |
| `out` | 一局结束写回角色库的东西;取代现在的 `rewards.soul` |

## 7. 参考实现位置

| 内容 | 位置 |
|---|---|
| 读取 · 查找 · 按合约 lint · 死亡规则 | `src/neonrp/template/contract.py` |
| 结算 · 段落 · 固定输出 | `src/neonrp/core/settlement.py` |
| 官方合约 | `worldlines/contracts/*.play-contract.json` |
| 作者操作 `set_play_contract` · 命令行 `neonrp template set-contract` / `contracts` | `src/neonrp/template/author.py` · `src/neonrp/commands/template_cmd.py` |
