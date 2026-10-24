# Template 规范(`worldlines.template/1`)

> 状态标记:**已实装** = 代码里有,本规范按代码写(对应 neonrp 1.0.3)。只做元数据、运行时不读的字段会单独写明。
> 相关规范:[World 规范](./world.zh.md) · [Soul 规范](./soul.zh.md)

---

## 1. 是什么

一局能玩的游戏,最少只要三样东西:

| 层 | 是什么 | 规范 |
|---|---|---|
| **pack** | 引擎层:agent loop、基础规则、基础 prompt、op | 内置 `rpg` / `pct` / `werewolf` / `monopoly`,或 `pack.json` 文件夹 |
| **world** | 数据:地点、NPC、物品、条目、注册表(开放 schema) | [world.zh.md](./world.zh.md) |
| **souls** | 谁在演:世界自带的灵魂,或从外面带进来的灵魂 | [soul.zh.md](./soul.zh.md) |

**Template 是可选的上一层**。它不改引擎内核,只做两件事:

1. **绑定**:选哪个 world、哪些 souls、哪个 pack(+ mixins)、引擎开关;
2. **加东西**:prompt 层、剧情包(plots)、模式(结局 × 自由度)、卡面(card)、素材槽位、lint 规则。

Template 也是**发布单位**:上架、分享、"新开一局"都以一个 `<id>.template/` 文件夹为单位。`build` 之后得到的是一个普通的 run 文件夹 —— 当前引擎本来就能玩的那种世界。

| 能力 | 状态 |
|---|---|
| 加载 / build / lint / 发现 / 新开一局 | 已实装 |
| world 三种绑定(builtin / path)+ overlay + shuffle | 已实装 |
| souls 固定列表 + 抽池 | 已实装 |
| prompt 层(世界侧 + 角色侧覆盖) | 已实装 |
| plots(阶段 / 触发 / 结局 / 揭晓) | 已实装 |
| ui:slots / views / panels / 命名 prompt / budget | 已实装 |
| 本地化层 `i18n/<lang>/`(按这一局的语言盖层 + glossary 残留检查,见 4.1) | 已实装 |
| 素材槽位上传 / 生成 | 已实装(生成需要配置图像后端) |
| 编排模板 `uses`(一回合走一拍还是两拍,见 §2a) | 已实装 |
| 区(`zone`)、发布到 Hub、获取官方世界(见 §9) | 已实装 |
| `mode.freedom` | 只是元数据:lint 检查取值,运行时不读 |
| `lint.assets` 里 `soul` / `item` / `ending` 的规则 | 不强制。只有 `card.cover` 由它检查;立绘等素材的强制走 `ui.slots[].required`(rpg 包的 `soul.portrait` 是 `publish`,见 6.1) |

---

## 2. 目录结构

```
<id>.template/
  template.json                 必需。schema = "worldlines.template/1"
  orchestration.json            可选。编排图补丁(template.json 的 orchestration 指向它,见 3.1)
  world/                        可选。模板自带的世界(world.path 指向它;结构见 world spec)
  world/runtime_contract.json   可选。自带世界的运行时契约源形状,开局时复制进这一局的 .neonrp/
  world/playthrough.json        可选。自带世界的演员表源形状(同上)
  world-overlay/                可选。盖在世界上的数据补丁(默认目录名,存在即生效)
  souls/<sid>/                  可选。从外面带进来的灵魂(souls[].path 指向它)
  prompts/world.json | *.md     可选。世界侧 prompt 层
  prompts/souls/<sid>/…         可选。角色侧 prompt 层:只能覆盖 soul.md / persona/ / rules/ / agents/(见 3.7)
  plots/<id>/plot.json          可选。剧情包(+ 它自己的 assets/)
  assets/                       可选。卡面封面、开场 CG、自带音频等
  i18n/<lang>/…                 可选。本地化层:和模板同路径的文件(见 4.1);i18n/glossary.json 专有名词对照
  spec/  AGENTS.md  CLAUDE.md   生成的。给编码 agent 读的规范副本和说明(`neonrp spec sync` 写入;fork 时也会写)
  frontends/<name>/             可选。这个世界自己的前端;只在本机用,导出和发布都不带
```

两个内置模板的实际树(省略图片和 `i18n/` 的内容):

**pct-house 灰橡宅**(自带世界,`pct` 包,`mystery-trpg` 合约,多结局)
```
template.json
assets/cover.jpg  assets/opening/cg-*.webp
plots/P01/plot.json
world/                         整个世界:game/、souls/、agents/、playthrough.json、runtime_contract.json
world-overlay/assets/maps/     地图图片和冻结的坐标变换
i18n/{en,ja,ko}/template.json  i18n/glossary.json
spec/  AGENTS.md  CLAUDE.md
```

**stoneford-town 石津镇 · 雾退之夜**(绑定内置世界 `stoneford-elena`,`rpg` 包 + `economy` mixin,`open-adventure` 合约,多结局)
```
template.json
orchestration.json             编排图补丁(交互节点:换场景 / 查看 / 交谈 …)
assets/cover.png
plots/P20/plot.json
prompts/world.json  prompts/voice.md  prompts/town.json
world-overlay/game/world/economy.json
world-overlay/game/locations/T001/{gate_north,road_camp}/location.json
world-overlay/game/meta/{game-start,run_state,interactions}.json
world-overlay/game/towns/T001/{npcs,quests}.json  …
i18n/{zh,en,ja,ko}/…  i18n/glossary.json
spec/  AGENTS.md  CLAUDE.md
```

## 2a. 回合 = 编排模板

一个模板不自己写"一回合怎么走",而是在 `uses` 里点名一个**编排模板**(`core/orch_templates`)。编排模板只管回合的形状,不带玩法合约,也不带规则包;同一个编排模板可以给很多世界用。

| 编排模板 | 一回合 | 在哪 |
|---|---|---|
| `one_beat` | 只有**清算拍**:世界写叙事,在场角色各自行动,引擎写状态、校验、落地 | 开源引擎自带(`neonrp/orchestrations/one_beat/`) |
| `two_beat` | 先**商量拍**,再清算拍。商量拍里主持接住玩家的话、把话递给在场角色、列出花费 / 检定 / 时间;这一拍不改世界、时钟不走。谈妥(判官判断,或玩家说"定")后进清算拍 | PyPI 发布的 `neonrp` / `worldlines` 自带 |

- 两个内置模板都写 `"uses": {"template": "two_beat", "version": "1.0", "soul": "S-judge"}`。
- 从 PyPI 装的包含完整的两拍编排;从开源仓源码装的引擎只有一拍。引擎没有模板点名的编排时,退回第一个开源编排(`one_beat`),`uses.soul` 照旧——世界照样能玩,只是一回合走一拍。
- `uses.soul` 是另一条轴:在场角色怎么出手(`legacy` · `S-judge` · `S-direct` · `S-free`);不写 = 编排模板的默认。
- `uses.params` 选编排模板给的参数,例如两拍的 `pace: normal | quick`(quick = 商量拍更快收束)。参数选错 → lint `uses.param`(warn)。
- 编排模板的设置在运行时叠加(见 8.2 的 `orchestration` 层),**不复制进存档**。
- Hub 网页和 iOS 的创作台只能从几个编排选项里挑(如 `two_beat`、`two_beat?pace=quick`),看到的是只读图;能改图的只有本机的编排台,改动存成模板的 `orchestration`(见 3.1)。

**清算拍里写状态的方式**(两种编排都一样):

1. 叙事调用只写正文;结果决定下文的东西写成工具行——`[op]` 同步(引擎当场回答,模型接着写)、`[~op]` 不等待(地图、面板)。
2. 一次干净上下文的"写状态"调用读正文和工具回答,输出 `<vars>`(已登记变量的新值)和 `<files>`(文件系统变化)。这是默认的 `pseudo` 方式;编排图里 `nodes.resolve.state = "jev"` 改成由判官逐行填工具调用,没有快速判官时退回 `pseudo`。
3. 提供商支持按请求关掉思考时(如 deepseek),写状态分两份:关思考的快答案先落地,开思考的慢答案在后台跑,回来后逐个变量纠正(这期间被别的东西改过的不动;工具和引擎的裁定优先),最多等 `turn.transition_slow_timeout_s`(默认 90 s);玩家先说下一句就取消。前端收到 `write_down.pending`,然后是 `write_down.corrected` / `same` / `cut` / `timeout` / `failed`。不支持开关的提供商只发一次调用。
4. 校验(字段 → 实体 → 世界);可修的拒绝只让第 2 步重写,正文不动。之后落地,每回合一个世界提交。

---

## 3. `template.json` 字段

读取入口:`neonrp.template:load`。所有字段都有容错:缺省的对象字段按 `{}`,列表按 `[]`。

### 3.1 顶层

| 键 | 类型 | 必需 | 默认 | 含义 | 读取位置 | 状态 |
|---|---|---|---|---|---|---|
| `schema` | str | 否 | — | 固定 `"worldlines.template/1"`;写别的值 lint 报 `schema`(warn) | `template:lint` | 已实装 |
| `id` | str | 否 | 文件夹名去掉 `.template` | 模板 id;发现、新开一局、run 目录名都用它 | `template:load` | 已实装 |
| `version` | str | 否 | `""` | 模板版本;带进来的 soul 没有 hash 时也用它 | `template:load` / `build` | 已实装 |
| `card` | object | 是(要 `title`) | — | 卡面,见 3.2 | `template:lint` / `build` | 已实装 |
| `mode` | object | 否 | `{}` → `ending: open` | 模式,见 3.3 | `template:loop_problems` | 已实装 |
| `world` | object \| str | 是 | — | 世界绑定,见 3.4;写成字符串等于 `{"path": …}` | `template:world_dir` | 已实装 |
| `pack` | object \| str | 否 | `rpg` | 引擎层,见 3.5;写成字符串等于 `{"name": …}` | `Template.pack_name` | 已实装 |
| `souls` | list | 否 | `[]` = 用世界自带的全部 | 演员表,见 3.6;元素可以是字符串 sid | `template:draw_souls` | 已实装 |
| `prompts` | list[str] | 否 | `[]` | prompt 文件 / 目录列表,见 3.7 | `template:prompt_layer` | 已实装 |
| `plots` | list[str] | 否 | `[]` | 剧情包目录(相对模板),见 §5 | `template:build` | 已实装 |
| `recipe` | object | 否 | `{backend:"", style:""}` | 素材生成配方的全局设置,见 §6 | `template.v3:ui` | 已实装 |
| `ui` | object | 否 | 继承 pack | slots / views / panels / prompts / budget,见 §6;`ui.beats` = 节拍怎么显示:`{"start": <编排图节点 id>, "kinds": {<节点 id>: {…}}}`(如石津镇 `{"start": "interaction.move"}`),按节点合并,`start` 整个替换 | `template.v3:ui` · `core.orchestration` | 已实装 |
| `slots` `views` `panels` `budget` | — | 否 | — | 也可以直接写在顶层,等价于写进 `ui` | `template.v3:ui` | 已实装 |
| `lint` | object | 否 | `{}` | lint 规则,见 3.8 | `template:lint` | 部分实装 |
| `models` | object | 否 | `{}` | 推荐模型,见 3.9 | `template:new_run` | 已实装 |
| `seed` | str | 否 | run 目录名 | 抽池 / 洗牌的随机种子;固定后每次 build 演员和身份不变 | `template:build` | 已实装 |
| `play_contract` | str | 否 | — | 这个模板承诺的体验:`"<合约 id>@<版本>"`,见 `contract` spec;lint 按合约查 | `template.contract` | 已实装 |
| `uses` | obj | 否 | 见右 | 这个世界用哪个编排模板:`{"template": "<编排模板 id>", "version": "<x.y>", "soul": "<角色编排>", "params": {…}}`,见 §2a。形状不对 → `uses.shape`(block)。不写 `uses` = 旧包:有玩法合约的按合约当年对应的编排跑,没有合约的不叠编排设置 | `core.orch_templates` | 已实装 |
| `orchestration` | object \| str | 否 | 玩法包的默认图 | 编排图:相对默认图的补丁 `{nodes, remove, add}`,或指向 `orchestration.json`;作者操作 `set_orchestration` 写它。`nodes.resolve.state` = `pseudo`(默认)\| `jev`,见 §2a | `core.orchestration:graph` | 已实装 |
| `zone` | str | 否 | 不写 = 自由区 | 作品在 Hub 的哪个区:`reviewed` = 默认区(审核后上架;官方世界在这里)· `open` = 自由区。其他值 → `meta.zone`(block)。默认区作品不能导出;`truth_quiz`、`audio.credits` 等检查在默认区是 block、自由区是 warn;自由区作品不发奖励卡。官方世界写 `reviewed`;fork 出来的副本会去掉 `zone`,成为作者自己的作品(见 §9) | `template:load` · `core.template_publish` | 已实装 |
| `player` | object | 否 | — | 玩家:`player.builder` = 开局前让玩家自己捏角色(面板玩家),见 3.11;`player.fixed: true \| false` = 直说这个世界有没有固定主角(不写时看世界 `playthrough.json` 的 `players[0].name` 是不是占位名)。不写 = 照旧开局 | `template.builder` · `template:pc_meta` | 已实装 |
| `rewards` | list | 否 | `[]` | 奖励卡 `[{id, kind: "card", title, desc, rarity: common\|rare\|epic, when, image? \| slot?}]`(title / desc 四语);`when` 用成就的条件写法,写成列表 = 全部成立。玩法合约 `rewards.player` 里没有 `cards` 时不发;自由区不发。到手时把图复制进玩家记录,作者以后删掉也不收回。事件 `reward.granted` | `core.rewards` | 已实装 |
| `creation` | object | 否 | 不写 = 不开放 | 这个模板对创作台开放哪一层:`{"add": [soul\|plot\|ending\|clue\|rule], "triggers": {"when": […], "then": […]}, "collect": [clear\|ending\|flag]}`。创作台只往这一层**加**数据,不改模板本身。未知名字 → `creation.schema`(warn) | `template.creation` | 已实装 |
| `settlement` | object | 否 | 合约的 | 结算数额盖在玩法合约上:目前是 `{"truth_quiz_points": {settle, per_right, fallback}}`(非负整数),否则 `truth_quiz.points`(warn) | `core.truth_quiz:points` | 已实装 |
| `opening` | object | 否 | — | 开场 CG:`{"cg": [{image, video?, caption?, camera?, prompt?, id?}, …]}`,按顺序在第一拍前播,见 6.6 | `core.scene_cg` / `template:build` | 已实装 |
| `milestones` | bool | 否 | `open-adventure` 合约 = true,其余 false | 开放冒险的里程碑开关;作者只写有 / 没有,里程碑由引擎自己找(新地点 · 完成委托 · 过了一天),离开时结算,见 contract spec 5.1 | `core.milestones` | 已实装(10-15) |
| `realtime_art` | string | 否 | `off` | 游玩中「画这一幕」(实时生图,平台按额度扣)的世界开关:`off` = 不实时画(作者预生成的图照常「看这一幕」)· `scene_only` = 只画地点、不画人 · `full` = 地点和在场的人;别的值 → `meta.realtime_art`(block)。默认关 | `core.scene_art` | 已实装(10-16) |
| `forkable` | bool | 否 | false | 官方模板给不给「复制一份来改」:本地版只内置的两个(灰橡宅 · 石津镇)写 true;其他官方世界只能玩,复制 / 导出都拒绝(`not_forkable`)。作者自己的作品(写入仓里的)总能复制,不用写;非 bool → `meta.forkable`(block),写在不是默认区的模板上 → warn。登录获取的官方世界由引擎写 `official: true` / `hub_ref` / `hub_revision`(作者别写) | `template.can_fork` | 已实装(10-17) |
| `achievements` | list | 否 | `[]` | 这个模板自己的成就 `[{id, title, desc?, when, points?}]`(title / desc 可四语);`when` 只从列表里选一个:`ending:<id>` · `flag:<key>` · `stage:<剧情>:<n>` · `places:<n>` · `character:<sid>` · `milestone:<n>` · `quiz_perfect`,不写 if / else;id 不能和内置的重名 | `core.achievements` | 已实装(10-15) |
| `audio` | object | 否 | 按合约 + 地名给默认 | 声音:主题曲 / 环境音 / 紧张危机曲 / 按地点 / 自带音频的来源,见 6.7 | `core/audio` | 已实装(10-15) |

> 注意:顶层 `prompts` 是 **prompt 文件列表**;命名 prompt(给素材配方用的模板文字)放在 `ui.prompts`。

### 3.2 `card`

| 键 | 类型 | 必需 | 含义 | 状态 |
|---|---|---|---|---|
| `title` | str | **是** | 卡面标题;缺了 lint 报 `meta.card`(block)。build 时写进 `game/meta/game-start.json` 的 `name` | 已实装 |
| `pitch` | str | 否 | 一句话卖点;缺了报 `meta.card`(warn) | 已实装 |
| `cover` | str | 否 | 封面图,相对模板目录;build 时复制到 run 的 `assets/template-cover.<ext>` | 已实装 |
| `lang` | str | 否 | 卡面语言(`zh` / `en` / `ja` …) | 已实装(元数据) |
| `tags` | list[str] | 否 | 标签 | 已实装(元数据) |

### 3.3 `mode`

| 键 | 取值 | 默认 | 含义 | 状态 |
|---|---|---|---|---|
| `ending` | `open` \| `single` \| `multi` | `open` | `open`:可以没有结局;`single`:恰好 1 个可达结局;`multi`:≥2 个可达结局。其他值 → `meta.mode`(block) | 已实装 |
| `freedom` | `free` \| `semi` \| `guided` | — | 玩家自由度。未知值 → `meta.mode`(warn) | 只是元数据(运行时不读) |
| `reveal` | bool | `false` | 开启后,每个剧情包都必须带 `reveal`(谜底),否则 `loop.reveal`(block) | 已实装 |

### 3.4 `world`

| 键 | 类型 | 含义 | 状态 |
|---|---|---|---|
| `builtin` | str | 绑定引擎自带的内置世界(随 `neonrp` 包发布,如 `stoneford-elena`) | 已实装 |
| `path` | str | 模板自带的世界目录,相对模板(如 `"world"`)。`path` 优先于 `builtin` | 已实装 |
| `overlay` | str | overlay 目录名,默认 `world-overlay`(存在即生效,不必声明),见 §4 | 已实装 |
| `prompts` | `"replace"` | 世界自己的 `game/meta/prompt.json` 整个丢弃,只用模板的 prompt 层(适用于"prompt 已经从世界数据里抽出来"的模板)。不写 = 世界的 prompt 垫在模板 prompt 下面合并 | 已实装 |
| `shuffle` | object \| list | 每局重新发某个属性:`{"folder": "game/seats", "prop": "role"}` —— 把该目录下所有 `*.json` 的 `props.<prop>` 值洗牌再发回去(狼人杀发身份、阿瓦隆阵营、剧本杀分角色)。可写多条 | 已实装 |

`builtin` 与 `path` 至少给一个,否则 `ref.world`(block)。

### 3.5 `pack`

| 键 | 类型 | 默认 | 含义 | 读取位置 | 状态 |
|---|---|---|---|---|---|
| `name` | str | `rpg` | 基础 pack:内置名、`pack.json` 文件夹路径、`module:PACK`,或 `NEONRP_TEMPLATE_PATH` 上的名字 | `packs:load` | 已实装 |
| `mixins` | list[str] | `[]` | 叠加的 mixin(内置 `economy`、`factions`,或含 `mixin.json` 的目录)。引擎实际解析的名字是 `rpg+economy+factions` | `packs:compose` | 已实装 |
| `engine` | object | `{}` | 引擎配置片段,build 时**深合并进 run 的 `game/meta/engine.json`** | `template:build` → `core.engine_config` | 已实装 |

**mixin 需要世界数据**。mixin 的规则在引擎里,数据在世界里:

| mixin | 需要的世界文件 | 装上后注册的封闭 schema | 开放类 |
|---|---|---|---|
| `economy` | `game/world/economy.json`(`currency` / `goods` / `markets` / `routes` / `caravan_every`) | `stock.<T>.<g>`、`price.<T>.<g>`、`inv.<g>`、`econ.index` | `caravan` |
| `factions` | `game/world/factions.json`(`factions` / `relations` / `rumors` / `premiums` / `routes` / `strike` / `bounty`) | `faction.<k>.power\|wealth`、`rep.<k>`、`rel.<a>.<b>` | `faction`、`rumor`、`quest` |

世界和 overlay 里都没有这份文件 → `pack.mixin.data`(warn),mixin 不生效;而且 mixin 自带的视图会因绑不到变量而报 `schema.view`(block)。通常的做法是把数据放进 `world-overlay/game/world/<mixin>.json`。build 时调用每个 mixin 的 `install(run)`,把变量写进 `game/meta/variables.json` 并播种初值(只补缺,装两次不变)。

**`pack.engine` 常用键**(完整默认值见 `neonrp.core.engine_config.DEFAULTS`):

| 键 | 取值 | 引擎默认 | 含义 | 状态 |
|---|---|---|---|---|
| `turn.mode` | `v2b` \| `v3` | `v2b`(`rpg` pack 的 loop 设为 `v3`) | 回合循环。lint 只接受这两个值,否则 `pack.engine`(block) | 已实装 |
| `turn.parallel.souls.default_variant` | `legacy` \| `S-judge` \| `S-direct` \| `S-free` | `legacy`(`rpg` pack 设为 `S-judge`) | 在场角色这一步的形态;`uses.soul` 写了时由编排层给 | 已实装 |
| `turn.parallel.souls.per_soul.<sid>` | 同上 | — | 单个角色的形态;作者操作 `set_engine_setting` 写它 | 已实装 |

叙事怎么转成状态不在 `pack.engine` 里,由编排图的 `nodes.resolve.state` 决定(§2a)。

### 3.6 `souls`

每个元素是**一个灵魂**或**一个抽池**:

```json
"souls": [
  {"sid": "elena", "role": "npc"},
  {"sid": "guest", "path": "souls/guest", "instance_id": "si-guest-1"},
  {"sid": "mira", "lib": "mira", "role": "companion"},
  {"pool": [{"sid": "a"}, {"sid": "b", "path": "souls/b"}, "c"], "pick": 2, "role": "npc"}
]
```

| 键 | 类型 | 含义 | 状态 |
|---|---|---|---|
| `sid` | str | **每一行都必须写**(抽池里的元素也是)。没有 `path` / `lib` 时必须是世界自带的(世界 `playthrough.json` 的 `souls[]`)。缺 sid → `ref.soul`(block),开局时这一行被跳过 | 已实装 |
| `lib` | str | **角色库里的角色**(`~/.worldlines/souls/<lib>/`)。模板里只是 link:开局 build 时才复制进这一局,角色库改了下一局就拿到新的。见 soul spec「角色库」 | 已实装 |
| `path` | str | 带进来的灵魂目录(相对模板)。build 时复制到 run 的 `souls/<sid>-<instance_id>/` | 已实装 |
| `instance_id` | str | 带进来的灵魂的实例 id;默认 `si-<sid>-<template id>`(截 48 字符) | 已实装 |
| `role` | str | 角色定位:`npc`(默认)· `companion` · `player`;最多一个 `player` | 已实装(`player` 目前只记下定位,开局不会把这个角色接成主角) |
| `pool` | list | 候选列表(元素可为字符串 sid) | 已实装 |
| `pick` | int | 从池里抽几个,默认 1;大于池子 → `ref.soul.pool`(block) | 已实装 |

规则(`template:draw_souls` / `build`):

- 同一个 sid 不能出现两次;`lib` 指的角色不在角色库 → `ref.soul`(block)。
- 世界里的角色是 link,不是副本:每个世界自己的差异(这个世界里的身份、关系、立绘)写在模板的
  `prompts/souls/<sid>/`(只覆盖 `soul.md` · `persona/` · `rules/` · `agents/`)和 `world-overlay/`,角色库本体不动。
- 写了 `souls` 就以它为准:世界自带但没列出的灵魂留在磁盘上,不激活;不写 = 世界自带的全部上场。
- 抽池用 `seed`(默认 run 目录名)播种:同一个 run 重建,演员不变;新开一局重新抽。同一个 sid 不会出现两次。
- lint 时按"全员到场"做参考 build,所以剧情里对池中角色的引用能解析;只在池里的角色被剧情点名时报 `loop.pool`(warn)。
- 某局没抽到的角色,剧情里 `to: soul` 发给他的那一条在本局被丢掉(触发的其他效果照常),记在 `built.dropped_soul_emits`。

### 3.7 `prompts`(prompt 层)

`prompts` 是相对模板的文件或目录列表(目录展开为其中 `.json` / `.md` / `.txt`,排序;`souls/` 子目录不算世界侧)。

| 文件 | 解析方式 |
|---|---|
| `*.json` | 一个 prompt spec(`neonrp.core.adv` 形状:`entries` / `rules` / `voice` …;也可包在 `{"prompt": {…}}` 里) |
| `*.md` / `*.txt` | 一条 entry:`id` = 文件名去后缀,`when: always`。首行可写 `<!-- when: post -->` 或 `<!-- keyword: 罗文, 碧石 -->` 改触发方式 |

**合并顺序**(后者覆盖前者,写进 run 的 `game/meta/prompt.json`):

```
世界自己的 prompt.json(world.prompts = "replace" 时丢弃)  <  模板 prompts(按列表顺序)  <  各剧情包的 prompt
```

**角色侧 prompt 层**:`prompts/souls/<sid>/` 下的文件按相对路径复制进对应灵魂目录,但只允许 `soul.md`、`persona/`、`rules/`、`agents/`(`SOUL_PROMPT_PATHS`)。其他路径属于灵魂数据,lint 报 `prompt.soul.data`(block),build 时跳过。

> 已知问题:作者操作 `set_soul_orchestration` / `set_soul_ambient` 会写 `prompts/souls/<sid>/orchestration.json` 和 `prompts/souls/<sid>/ambient/world.json`,这两个路径目前不在上面的白名单里,lint 会把它们判成 `prompt.soul.data`。在修好之前,发布级模板别用这两个操作。

### 3.8 `lint`

| 键 | 类型 | 默认 | 含义 | 状态 |
|---|---|---|---|---|
| `level` | `publish` \| `draft` | 见下 | 发布级:缺失/过期的必需素材、缺封面、超预算从 warn 升为 block | 已实装 |
| `assets` | object `{cls: [kind, …]}` | `{soul:[portrait], card:[cover]}` | 素材要求;`"a\|b"` = 二选一 | 只有 `card: [cover]` 被检查;其余键能写、会合并,但不强制。立绘等素材的强制走 `ui.slots[].required`(6.1) |

`level` 不写时有个不对称:素材槽位检查(`asset.missing` / `asset.stale` / `token.over`)按 **publish** 处理;封面检查 `asset.card` 只有显式写 `"publish"` 才是 block,否则 warn。

两个内置模板都写 `"lint": {"level": "draft"}`:缺图、过期、超预算都只是 warn。按区分级的检查(`truth_quiz.*`、`contract.truth_quiz`、`audio.credits`)不看 `level`,看 `zone`。

### 3.9 `models`

| 键 | 类型 | 含义 | 状态 |
|---|---|---|---|
| `play` | str | 推荐的游玩模型。`new_run` 只有在值是 `provider/model` 形式(含 `/`)时才写进新 run 的配置,否则用用户默认模型 | 已实装 |

### 3.10 最小可用模板

已在临时目录验证(绑定内置世界 `stoneford-elena`):

```json
{
  "schema": "worldlines.template/1",
  "id": "min",
  "card": {"title": "最小模板"},
  "world": {"builtin": "stoneford-elena"}
}
```

`neonrp template lint ./min.template` 输出:

```
[warn ] meta.card        card.pitch: no pitch (one line on the card)
[warn ] asset.optional   slots: 15 个可选槽位没填(有兜底的用兜底)
[warn ] token.unmeasured budget: 还没有回合——用这个模板玩一回合才量得出每回合 token
[warn ] asset.card       card.cover: no cover file
publishable — 0 block, 4 warn
```

`neonrp template build ./min.template run-min` 输出:`built min → run-min  pack=rpg souls=elena,rowan plots=- prompt-overlays=0`。
真正必需的只有 `card.title` 和 `world`;pack 默认 `rpg`,souls 默认用世界自带的。

### 3.11 `player.builder`(捏人 · 面板玩家)

模板声明玩家角色要哪些字段和规则,界面照着渲染,玩家开局自己捏一个角色,捏完写进这一局的玩家文件,再选 companion,然后开场。
**不写 = 照旧开局**(世界自带的 `game/player/*` 原样)。所有文字字段可写字符串或 `{zh, en, ja, ko}`。

```json
"player": {"builder": {
  "title": {"zh": "捏一个读者", "en": "Make your reader"},
  "fields": [
    {"id": "name",   "kind": "text", "label": {"zh": "名字"}, "required": true, "max": 24,
     "to": "player/profile.json:name", "random": ["真白", "灰原"]},
    {"id": "look",   "kind": "text", "multiline": true, "label": {"zh": "外貌"}, "to": "player/profile.json:appearance"},
    {"id": "origin", "kind": "choice", "required": true, "label": {"zh": "出身"}, "to": "player/profile.json:origin",
     "options": [{"id": "student", "label": {"zh": "学生"}, "desc": {"zh": "……"},
                  "grants": {"set":    {"meta/run_state.json:location": {"node_id": "T001", "subnode_id": "campus"}},
                             "append": {"player/stats.json:skills": [{"name": "潜行", "value": 40}]},
                             "add":    {"player/stats.json:attributes.ji": 1}}}]},
    {"id": "traits", "kind": "multi", "min": 0, "max": 2, "options": [{"id": "calm", "label": "冷静"}], "to": "player/profile.json:traits"},
    {"id": "attrs",  "kind": "points", "label": {"zh": "属性"}, "total": 20, "min": 1, "max": 8, "exact": true,
     "stats": [{"id": "ti", "label": {"zh": "体"}, "desc": {"zh": "体能、耐受"}}, {"id": "ji", "label": {"zh": "技"}}],
     "to": "player/stats.json:attributes", "var": "player.attr"},
    {"id": "face",   "kind": "portrait", "label": {"zh": "头像"}, "options": [{"id": "a", "src": "assets/player/a.png"}]}
  ],
  "companion": {"from": ["cast"], "role": "companion", "pick": 1, "required": true, "label": {"zh": "选一个同伴"},
                "cards": {"<sid>": {"tier": {"zh": "S · 守城"}, "blurb": {"zh": "……"}}}}
}}
```

| 键 | 含义 |
|---|---|
| `fields[].id` / `kind` | 字段 id(唯一)· `text` \| `choice` \| `multi` \| `points` \| `portrait` |
| `portrait`:`options[]` · `default` | `{id, src}`(图在模板里);`default` = 选项 id:不捏人直接开局、或草稿没选头像时玩家用这张(世界自己给了玩家头像就不覆盖);不是选项之一 → `player.builder` block(10-15) |
| `label` / `desc` / `placeholder` | 显示文字 |
| `required` | 必填(`multi` 时最少选 1,除非写了 `min`) |
| `to` | 写到哪:`<game 目录下的 .json 文件>:<点号键>`。引擎照写,不认任何世界专有词;不能有 `..` / 绝对路径 |
| `text`:`max` · `multiline` · `random` | 最长字数(上限 4000)· 多行 · 「随机」时从这里挑 |
| `choice` / `multi`:`options[]` | `{id, label, desc?, grants?}`;`multi` 另有 `min` / `max` |
| `options[].grants` | 选中后的效果,同样的寻址:`set`(覆盖)· `append`(往列表追加)· `add`(数字累加)。开场地点 = `set` 写 `meta/run_state.json:location` |
| `points`:`stats[]` · `total` · `min` / `max` · `exact` | 每项 `min..max`,总和 ≤ `total`;`exact: true` = 必须正好用完 |
| `points`:`var` | 给了就把每项注册成 int 变量 `<var>.<stat id>`(写进 `game/meta/variables.json`,绑到 `to` 的文件) |
| `portrait`:`options[].src` | 模板里的图(png / jpg / webp);选中的复制成 `game/player/assets/portrait.<ext>` —— 游玩界面的玩家头像 |
| `companion.from` | 候选来源:`cast` = 模板 `souls` 里 `role` 为 `companion.role`(默认 `companion`)的行;加 `library` = 角色库全部角色也能选(选中时以 link 加进演员表) |
| `companion.pick` / `required` | 选几个(默认 1)/ 是否必选(默认是) |
| `companion.cards.<sid>` | 卡片补充:`title` · `tier`(能力档位)· `blurb`(简介)· 其他键;名字 / 立绘 / intro 从 soul 文件夹读 |
| `companion.rows` | `[{key, label}]`:卡片上 `cards` 里其他键(如出自 / 绝招 / 弱点)的标签和顺序 |
| `steps` | 可选,分步:`[{id, title}]`;字段写 `step`、`companion.step` 归到哪一步;没有内容的一步 = 确认开场页。不写 = 字段 → 选同伴 → 开场 三步 |
| `fields[].hint` | 字段下面的提示 |
| `labels` | 可选,给出身等选项 `grants.add` 加的数字起名(不是点数栏里的属性时):`{"<目标> 或 点号键 或 最后一段": 标签}`,如 `{"attributes.int": {"zh": "智力"}}`;卡片上写「带来 智力 +1」。点数栏的属性自带名字;都没有时显示键名,lint 报 `player.builder`(warn)。`GET …/builder` 给每个带 grants 的选项算好 `brings` |
| `derive` | 可选,派生值:`[{to, also?, base, per: {stat id: 倍数}, div?, label?}]` = `base + floor(Σ 属性×倍数 / div)`,按出身等加成**之后**写进去的属性算;`also` 同值多写几处(如 `hp.max`);有 `label` 的显示在面板上。例:生命 = 6 + 体×2 → `{"to": "player/stats.json:hp.current", "also": ["player/stats.json:hp.max"], "base": 6, "per": {"体": 2}}`;共鸣 = 2 + floor(魂/3) → `{"base": 2, "per": {"魂": 1}, "div": 3}` |
| `text`:`generate` · `example` | `generate: true`(或一句提示)= 界面给「随机生成」按钮,配置的模型按玩家已填的内容写这一格(**不带世界设定**:生平是玩家自己的,随便定,写进去就是这一局的现实);没配模型 / stub 时用 `example`(字符串或四语对象,可给多条)。长文本最多 4000 字 |
| 属性 id | 可以用中文(`体` `技` …),引擎原样写进 `to` 的对象 |

开局时(`new_run(ref, player=…)` / `POST /api/v1/play/session {slug: "tpl--<id>", player: {fields, companion}}`):

1. **先校验**:必填、选项合法、多选个数、点数(每项范围、总数、`exact`)、companion 是候选且个数对。不过 → `BuilderError` / HTTP 400 `{ok: false, errors: [...]}`,**什么都不建**。
2. 没被选中的 companion 候选不进这一局(从演员表去掉);角色库选来的以 `{sid, lib, role}` 加进去。
3. 照常 build,然后按字段顺序写 `to`,再按选中选项写 `grants`,注册 `var` 变量,复制头像。
4. 整张卡写进 `game/player/card.json`(`worldlines.player-card/1`:`values` 捏的值 · `labels` 选项显示名 · `companion` · `builder` 声明原文),这一局自带,游玩界面的面板读它。

草稿的形状:`{"fields": {"<id>": 值}, "companion": "<sid>" | [sid…]}`;`text` → 字符串,`choice` / `portrait` → 选项 id,`multi` → id 列表,`points` → `{stat: int}`。

HTTP:`GET /api/v1/local/templates/<id>/builder`(声明 + 解析好的 companion 候选;图只给有无,不给路径)·
`GET …/builder/image?field=&option=` / `?sid=` · `POST …/builder/check {fields, companion}` → `{ok, errors}` · `POST …/builder/generate {field, fields, lang}` → `{text, source}` ·
`GET /api/v1/play/engine/player-card`(这一局的卡;`live` = 从 `to` 读回的当前值,玩的过程中会变)。lint:`player.builder`(block)。

---

## 4. world-overlay

overlay 是"盖在世界上的数据补丁",让同一个世界换一套数据就成为另一个模板(例:`stoneford-town` 给内置世界 `stoneford-elena` 加上经济数据、北门外的驿路营地、新的开场和委托)。

| 规则 | 说明 |
|---|---|
| 位置 | `world.overlay` 指定的目录;不写时用 `world-overlay/`,存在即生效 |
| 时机 | 世界复制进 run 之后、shuffle / 选角 / 装 mixin / 装剧情之前 |
| 粒度 | **整文件替换**,不是 JSON 合并:overlay 里的 `game/meta/variables.json` 会整个顶替世界的那份 |
| 能放什么 | 任何世界路径:`game/world/<mixin>.json`、`game/meta/variables.json`、`game/meta/classes.json`、`game/locations/<T>/<地点>/location.json`(加地点或改一个地点)、`assets/…`(地图 / 场景图)、`souls/<sid>-<iid>/assets/…`(自带灵魂的立绘) |
| 素材落点 | 给内置世界的槽位填图时,图写进 overlay(模板里),不碰内置世界 |
| 自带世界 | `world.path` 的模板通常不需要 overlay,直接改自己的 `world/` |

因为是整文件替换,authoring API 修改 overlay 里的 JSON 时,会先从世界原有的那份开始改,避免丢内容。

## 4.1 本地化层 `i18n/<lang>/`(已实装)

一个模板用一种语言写(`card.lang`,主语言)。`i18n/<lang>/` 放这个模板在另一种语言里的**本地化版本**——不只是翻译:
地名、线路、人名、物品名、开场、规则说明、提示词、触发旁白、结局文字都可以换成那个国家/语言里自然的样子;
**id 不变**(sid、地点 id、物品 id、flag / 变量名),所以触发和规则照常工作。代码:`neonrp.template.i18n`。

```
<id>.template/
  i18n/
    glossary.json                  专有名词对照:每样东西在每种语言里叫什么(lint 用它查残留)
    ja/template.json               卡面(card.title / pitch / tags)
    ja/world/game/towns/T001/npcs.json
    ja/plots/P01/plot.json
    ja/prompts/world.md
    zh/…                           主语言也可以有自己的一层(例如把罗马字显示名换成中文)
```

| 规则 | 说明 |
|---|---|
| 路径 | 和模板里原文件**同路径**(`world/…`、`prompts/…`、`plots/…`、`template.json`);模板没有的路径照样加进去(lint warn `i18n.orphan`) |
| JSON | **深合并**进原文件:对象逐键合并;同长度数组逐项合并(不改的项写 `{}`);其他(长度不同的数组、字符串、四语对象)整个替换。所以本地化文件可以只写变了的字符串,`neonrp.template.i18n.tidy` 会把整份翻译副本压成只含文字差异的层 |
| 键不本地化 | 键就是 id(包括技能表 `skills: {侦查: 60}` 这种以名字为键的,以及指向它的 `"key": "skills.侦查"`),保持原样;要换的是显示名:规则包有名字表的(pct 的 `rules.json` `skills.<id>.{zh,en,ja,ko}`),这一局按本局语言显示;`{name, value}` 列表里的 `name` 是值,可以本地化 |
| 其他文件 | `.md` / `.txt` / 图片整份替换 |
| 时机 | 开局按这一局的语言,把层盖在模板的临时副本上再 build(`build(t, dest, lang=…)` / `new_run(…, lang=…)`);之后引擎和提示词只看到一种语言 |
| 四语对象 | build 完把这一局里所有 `{zh,en,ja,ko}` 文本对象收窄成 `{<这一局的语言>: 文本}`(lang → en → zh → 任一);带别的键的名字表(`{zh,en,ja,ko,base}`)不动 |
| 没有这一层 | 这一局用模板主语言;lint warn `i18n.missing`(只对 `template.json["i18n"]["langs"]` 声明或已经有层的语言) |
| 这一局的语言 | 写进 `run_state.json["output_lang"]`;`game/meta/template.json["i18n"]` 记 lang / 用到的层文件 |
| 卡面 | `meta()` 返回 `langs`(可本地化的语言,主语言在前)和 `cards`(每种语言的卡面),启动器按玩家语言显示 |

`glossary.json`:

```json
{"terms": [
  {"id": "soul:xiacheng", "zh": "夏澄", "ja": ["夏川 澄", "夏川"], "ko": "서하진", "en": ["Clara Shaw", "Clara"],
   "also": ["Xia Cheng"]}
]}
```

`also` = 主语言名字的旧音译(哪一局都不该再出现)。lint 对每种语言的本地化副本查:别的语言的写法、`also` 里的写法还在不在
(`i18n.residue`)。

开局:`POST /api/v1/play/session {"slug": "tpl--<id>", "output_lang": "ja"}` 用玩家的语言建这一局;TUI 用界面语言。
命令行:`neonrp template build <id> <dest> --lang ja`;`neonrp template lint <id> [--i18n-deep]` 打印每种语言的覆盖率,
`--i18n-deep` 再对每种语言的本地化版本整套 build + lint(block 报成 `i18n.build`)。

---

## 5. 剧情包 plots

`plots` 列出 `plots/<id>/` 目录;每个目录一个 `plot.json`(+ 可选 `assets/`)。由 `neonrp.packs.rpg.plot` 解析、校验、安装。

### 5.1 `plot.json` 字段

| 键 | 类型 | 含义 | 状态 |
|---|---|---|---|
| `id` | str | **必需**。剧情包 id(如 `P10`) | 已实装 |
| `title` | str | **必需**。标题 | 已实装 |
| `stages` | list[str \| {name, goal}] | 阶段名;自动声明变量 `<id>.stage`(0 起)。可写成 `{name, goal}`:`goal` 是给玩家的一句「这一段要做什么」(不剧透;字符串或 `{zh, en, ja, ko}`,本地化层照常翻),只在走到这一段后由 `GET /api/v1/play/engine/objective` 给出;`{name, goal, audio}` 的 `audio` 见 6.7 | 已实装(goal 10-15 · audio 10-15) |
| `stage_var` | str | 剧情阶段是另一个变量(世界的、或本包 `vars` 里的,如 `night`);不写 = `<id>.stage`。引擎在它变化时发 `stage.changed` | 已实装 |
| `stage_cg` | object | 阶段过场 `{阶段序号 \| 阶段名: {image, video?, caption?, camera?, prompt?}}`,路径相对剧情包目录;槽位 `stage.cg:<id>.<n>`,见 6.6 | 已实装 |
| `classes` | object | 自定义类(ClassSpec) | 已实装 |
| `vars` | object | 自定义变量 `{name: {type: int\|float\|bool\|str, min?, max?, doc?}}`,默认存 `game/meta/plot_vars.json` | 已实装 |
| `entries` | object | 新条目 `{id: {class: item\|place\|npc\|<自定义>, name, parent, links?, props?, assets?, clue?}}`。地点必须有 parent(所在镇)。`clue: true` = 这是一条线索(得到时 `gained[].kind` 为 `clue`;`entities?clue=1` 只给已发现的);整类都是线索就在 `classes` 里写 `clue: true` | 已实装(clue 10-15) |
| `triggers` | object | WHEN / IF / THEN / ELSE 规则,见 5.2 | 已实装 |
| `endings` | object | `{eid: {title, kind?, assets?: {image, video}, image_prompt?}}` | 已实装 |
| `notes` | any | 作者备注 | 已实装 |
| `prompt` | object | **模板专用**。追加的 prompt spec;entry id 自动加前缀 `<plot id>.`。build 时合并进 run 的 prompt,不进安装的 plot.json | 已实装 |
| `reveal` | object | **模板专用**。谜底(按语言 `{zh: …}`)。build 时存到 `game/plots/<id>/reveal.json`;**只有到达结局后**才由 `run_view` 给出 | 已实装 |
| `truth_quiz` | object | 沙盒跑团结算的「真相三问」:`{questions?: [{q, options: [..], answer: <正确序号>} ×3], reward_soul?: <sid>}`(q / options 可四语)。合约要求时(`mystery-trpg` 的 `settlement.truth_quiz: required`)**必须写 `questions`**,四语齐(`{zh, en, ja, ko}` 或 `i18n/<lang>/` 层);`reward_soul` = 三题全对时带完整记忆回家的角色(演员表里的 sid),不写默认结局时的同伴。不写 `questions` 时引擎按谜底(`reveal`,没有就 `gm-truth.md`)自己出三题 —— 只是自由区 / 旧模板的兜底。lint `contract.truth_quiz` · `truth_quiz.*`(默认区 block、自由区 warn)。见 contract spec §3 §4 §5.1 | 已实装(10-15;必填 10-16) |

素材种类(`assets` 的键):`image` `portrait` `video` `audio` `bgm` `sfx`,路径必须相对且留在剧情包目录内。

### 5.2 触发(triggers)

```json
"P10.clue": {
  "when": {"text": "both"},
  "if":   [{"text": ["护身符", "徽记"]}],
  "once": true,
  "then": [{"to": "var", "var": "P10.stage", "set": 1},
           {"to": "soul", "who": "艾琳娜", "text": "那个徽记让她头疼,像是见过。", "important": true}]
}
```

| 部分 | 写法(参考实现用到的) |
|---|---|
| `when` | `{"text": "player"\|"narration"\|"both"}` · `{"entry": "T004/chapel", "event": "enter"}` · `{"var": "player.hp"}` · `{"check": "急救"}`(这一回合玩家掷了这个名字的检定:`/急救` 命令、`[dice 急救]`、rpg 的理由以属性名开头;任何语言的名字都认) |
| `if` | `{"text": [关键词…], "in"?: "player"}` · `{"var": "P10.stage", ">=": 1}` · `{"var": "a", ">": {"var": "b"}}`(和另一个变量比)· `{"check": "急救", "passed": true, "level"?: "crit"}` · `{"who": "羽", "at": "player", "is"?: false}`(at: player = 和玩家同地;is: false 取反) |
| `then` / `else` | `{"to": "var", "var", "set"}` · `{"to": "narration", "text"}` · `{"to": "soul", "who", "text", "important"?}` · `{"to": "end", "ending": "E10"}` · `{"to": "move", "who": <角色>, "place"}`(世界挪走一个角色)· `{"to": "status", "name", "remove"?: true}`(给玩家加 / 去状态)· `{"to": "audio", "mood"?, "bgm"?, "ambient"?}`(换音乐 / 环境音,见 6.7) |
| `once` | 只触发一次 |
| `needs` | `<角色名>`:这一局没选上这个角色,整条触发跟着去掉 |

地点的进入条件写在 `location.json`:`"enter_if": [触发同款条件…]`(全部成立才能进;`at` 读的是走之前站在哪)+ `"enter_refused": {zh, en, ja, ko}`(拦下时给主持的理由)。只拦玩家的 move_to(verify 里)。

### 5.3 结局与 `mode.ending`

- 可达 = 至少有一个触发分支 `{"to": "end", "ending": …}` 发出它。pack 自己的触发(如狼人杀"好人胜/狼人胜")也算,记为 `kind: rule`。
- `kind`:`true` / `alt` / `fail` / `fallback` / `rule`。`single` / `multi` 模式下没有 `fail` / `fallback` / `rule` 类结局 → `loop.exit`(warn)。
- 同一个触发分支发出两个不同结局 → `loop.distinct`(block):结局必须有不同的条件。
- 有结局的剧情包应有 `stages` 和 `prompt`,否则 `loop.guide`(warn)。

---

## 6. 素材槽位 / ui

有效 ui = **pack(+ mixins)声明 < 模板 `ui`(及顶层 `slots` / `views` / `panels` / `budget`)**,由 `template.v3:ui` 计算,合并规则 `packs:merge_ui`:

| 部分 | 合并键 | 删除 |
|---|---|---|
| `slots` | `(cls, slot)` | 写 `{"cls", "slot", "remove": true}` |
| `views` / `panels` | `id` | 写 `{"id", "remove": true}` |
| `prompts` | 键名 | 值写 `null` |
| `budget` | 整体替换 | — |

build 时有效 ui 写进 run 的 `game/meta/template.json["ui"]`,游玩界面从这里读视图。

### 6.1 `slots`(素材槽位)

| 键 | 取值 | 含义 |
|---|---|---|
| `cls` | 注册表里的类(`soul` / `place` / `item` / `caravan` / `faction` …)或虚拟类 `level`(地图树的层级) | 槽位挂在哪个类上 |
| `slot` | str | 槽位名(`map` / `portrait` / `sprite` / `scene` / `icon` / `emblem` …) |
| `kind` | `image` \| `icon` \| `audio` | 素材种类 |
| `required` | `publish` \| `optional` | `publish` = 发布必需 |
| `recipe` | 内置 `map` / `scene` / `portrait` / `sprite`,或 `ui.prompts` 里的一个名字 | 生成配方;两者都不是 → `schema.slot`(block) |
| `ratio` | `"3:2"` / `"3:4"` / `"16:9"` … | 生成尺寸 |
| `scope` | `"class"` | 整个类共享一张(实例 id 记为 `*`) |
| `hotspots` | bool | 地图带可点热区 |
| `from` | 槽位名 | 从另一个槽位派生(如 sprite 来自 portrait) |
| `fallback` | str | 没填时的兜底说明 |

`rpg` pack 默认槽位:`level.map`(publish)、`soul.portrait`(publish)、`soul.sprite`、`place.scene`、`item.icon`(可选)。`economy` 加 `caravan.icon`(类级),`factions` 加 `faction.emblem`。

**槽位实例 id**:`<cls>.<slot>:<实例>`,如 `level.map:T001`、`soul.portrait:elena`、`caravan.icon:*`;另有模板级的 `card:cover`、`plot:<rel>:ending:<eid>`、`plot:<rel>:entry:<id>`(剧情包里没有类槽位覆盖的条目,如归乡 `cg` 类的插画;行里带 `cls` / `parent`)、`opening.cg:<n>`、`stage.cg:<plot>.<n>`(见 6.6)。

**图写到哪里**(`template.v3:_target`,永远在模板目录内,越界拒绝;PNG / JPEG / WebP,≤ 8 MB):

| 槽位 | 落点 |
|---|---|
| `card:cover` | `assets/cover.<ext>`,并改写 `card.cover` |
| 结局图 | `plots/<rel>/assets/ending-<eid>.<ext>`,并记进 plot.json |
| 剧情包定义的条目 | `plots/<rel>/assets/entry-<id>.<ext>`,并记进 plot.json |
| 开场 CG | `assets/opening/cg-<n>.<ext>`,并记进 `opening.cg[i].image` |
| 阶段过场 | `plots/<rel>/assets/stage-<n>.<ext>`,并记进 plot.json `stage_cg` |
| 带进来的灵魂 | `souls/<sid>/assets/<slot>.<ext>` |
| 世界自带的灵魂 | `world-overlay/souls/<sid>-<iid>/assets/<slot>.<ext>` |
| 玩家(`cls: player`,如 `player.portrait:player` = 游玩界面的玩家头像) | `world-overlay/game/player/assets/<slot>.<ext>`(开局落进 `game/player/assets/`,和捏人选的头像同一处) |
| 地图层级 | overlay 里地图图片的同一路径(并冻结当前布局的变换,热区跟数据走) |
| 场景 | `world-overlay/assets/places/<place>.<ext>` |
| 其他类实例 / 类级 | `world-overlay/assets/<cls>/<slot>/<inst 或 _class>.<ext>` |

**过期(stale)**:按解析后的输入(prompt 等)做内容哈希;输入变了,已填的图标为过期。

### 6.2 `prompts`(命名 prompt)与 `recipe`

命名 prompt 是给配方用的文字模板,占位符写 `{name}`,可用:

- 已注册变量(如 `{town.alert}`、`{time.day}`);
- 配方上下文 `PROMPT_CTX`:`world.name` `level.name` `nodes` `style` `place.name` `place.summary` `soul.name` `soul.persona` `time.day` `time.clock`;
- 实例属性 `{inst.<prop>}`。

`ui.prompts` 里出现未知占位符 → `prompt.placeholder`(block);prompt 层 entry 里带点号的未知占位符 → `prompt.placeholder`(warn,会原样输出)。

`recipe`:`{"backend": "…", "style": "暗色水彩 · 雾"}`。`style` 填进 `{style}`;不写时用世界的画风。实例自己的 `props.image_prompt` 优先于类配方。

### 6.3 `views`(数据视图)

| 键 | 含义 |
|---|---|
| `id` | 视图 id |
| `title` | 多语言 `{zh, en, ja}` |
| `bind` | 变量模式列表:精确名、`*` 通配一段、`{town}` = 玩家所在镇;或 `class:<cls>` 列出该类实例(最近 30 个) |
| `widget` | `table` `gauge` `bars` `meter` `sparkline` `list` `number`;未知 → `schema.view`(warn) |
| `actions` | 视图上可点的 op;没有处理器 → `schema.view`(block) |
| `layout` | `{area: right\|center\|studio, order, cols?, range?}` |

绑不到任何已注册变量 → `schema.view`(block)。`rpg` 默认视图:`alert`(警戒)、`purse`(钱袋)。

### 6.4 `panels`(面板)

层或工具画出来的东西(阵型、地图、角色卡)。pack 给默认,模板可覆盖 prompt 和格式。

| 键 | 含义 |
|---|---|
| `id` | 面板 id |
| `tag` | 模型输出里的块标签(如 `formation`) |
| `tool` | 由哪个工具画(如 `map`、`sheet`) |
| `format` | `text` \| `json`(配 `schema`)\| `image` |
| `prompt` / `schema` / `layout` | 写法提示 / 结构 / 布局 |

`rpg` 默认面板:`formation`、`map`、`sheet`。

### 6.5 `budget`

每回合世界侧 token 预算,默认 20000。lint 从本机最近的 `tpl-<id>-*` run 的回合 trace 里量平均值:没有回合 → `token.unmeasured`(warn);超过 → `token.over`(publish 级 block);超过 80% → `token.near`(warn)。

### 6.6 演出:开场 / 过场 / 剧情图 → 引擎事件

没有单独的演出协议:槽位决定有哪些素材,引擎在回合事件流里(本地 `/events`、浏览器版 `onEvent`、`/api/v1/play/engine/beats`)说**此刻**发生了什么,前端照着演。

| 槽位 | 什么时候播 | 事件 |
|---|---|---|
| `opening.cg:<n>`(`template.json` `opening.cg`) | 开场,第一拍之前,按顺序 | 开场的 `plan.beat` 带 `cg: [{slot, image, video?, caption?, camera?, template}]`;`run_view` 也给 `opening` |
| `stage.cg:<plot>.<n>`(plot.json `stage_cg`) | 剧情阶段变量到第 n 阶段 | `stage.changed {plot, var, from, to, name, cg?: {slot, …}}` |
| `plot:<rel>:entry:<id>`(条目有 `assets.image`、`parent` 是地点) | 玩家第一次走进 `parent`(每局一次) | `show {slot, template, cls, inst, label, by: "arrive"}` |
| 模板里任何槽位 | 主持在叙事里写 `[~show <槽位 \| 条目 id \| 名字>]` | `show {…, by: "host"}`;模板里没有的槽位 → 拒绝(留一条 `tool` 事件) |

`show` 这个 op 只在模板有「此刻可展示」的图(上面三类)时才注册,提示词里列出可展示的条目;别的世界提示词不变。取图:`GET /api/v1/local/templates/<模板>/assets/file?slot=<槽位>[&part=video]`。

**按同伴取不同版本(10-15)**:结局图、开场 CG、阶段过场画的是某个具体同伴时,按玩家捏人时选的同伴(`game/player/card.json` 的 `companion`;没捏人就取这一局唯一的 companion)换图,没有对应版本就用通用版。

```jsonc
// plot.json
"endings": {"E02": {"title": "…", "assets": {"image": "assets/ending-E02.webp",
                                            "variants": {"isse": "assets/ending-E02-isse.webp", "yomi": "assets/ending-E02-yomi.webp"}},
                    "image_shows": "isse"}}           // 可选:通用版其实画的是谁(lint 提醒其余同伴还缺自己的版本)
"stage_cg": {"1": {"image": "assets/stage-1.webp", "variants": {"yomi": "assets/stage-1-yomi.webp"}}}
// template.json
"opening": {"cg": [{"image": "assets/opening/cg-7.webp", "variants": {"isse": "assets/opening/cg-7-isse.webp"}}]}
```

- 槽位:`<槽位>@<sid>`(`plot:plots/P01:ending:E02@yomi`、`opening.cg:7@isse`、`stage.cg:P01.1@yomi`),列进 `asset_slots`(行带 `variant` / `variant_of`),上传 / 生成到这个槽位就记进 `variants`(文件名 = 通用版 + `-<sid>`)。
- 取图:`assets/file?slot=<通用槽位>&variant=<sid>`(没给 variant、而这一局正在玩这个模板时 = 这一局的同伴);那个版本没填 → 通用版。
- 这一局:`run_view` 带 `companion`,`opening.cg[]` / `plots[].stage_cg[]` / `plots[].endings.<id>.slot` / `ending.slot` 都已换成这一局的;开场 `plan.beat.cg[]`、`stage.changed.cg` 带 `{slot, image, variant}`(`variant: null` = 通用版);结算 `settlement.ending_cg = {id, slot, variant, image}`。
- lint:`variants` 的键不是这个模板的 soul → `asset.variant`(warn);写了 `image_shows` 而其余候选同伴没有自己的版本 → `asset.variant`(warn);`variants` 不是 `{sid: 图}` → 剧情包 lint 报错。

同一条事件流里还有(10-14):

- `state.changed` 带 `gained` / `lost`:`[{who, id, cls, name, kind: item|effect, from|to, how}]`;`how`:得到 `new`(新造到手里)· `picked`(从地点 / 无主处拿到)· `given`(别人给的);失去 `gone`(用掉 / 过期)· `dropped`(留在地点)· `given`(给了别人)。不管是谁改的(模型的 op、模板 handler、tick、触发、效果到期)。
- `party.join` / `party.leave` `{sid, iid, name, why}`:捏人带进来的 `companion` 开局站在玩家身边 = 在队(`why: companion`);玩家走、和玩家一起落到新地点 = 入队(`follow`);玩家走了没跟上 = 离队(`stayed`),自己走开 = `left`。存 `game/meta/party.json`。
- `plan.beat` / `resolve.beat` 带 `mentions: [{id, cls, name, span: [起, 止], alt?}]`:这一拍叙事点到的人 / 物 / 地点和它在 `text` 里的位置。
- 玩家结构化动作:`POST /cmd {"action": "inspect" | "pick", "target": <条目 id 或名字>}`(`/session/<sid>/turn[/stream]` 同样)→ 一拍 `resolve.beat {advanced_by: inspect|pick, action: {kind, target, ok, why?}}`,不过模型、不替玩家说话。世界自己的规则照样生效:触发器 `when: {"entry": "I701", "event": "pick"}`,`text` 规则把物件名当成玩家这一拍关注的东西;包自己注册了 `inspect` / `pick` op 时走它。默认:查看 = 物件自己的 `summary` / `desc` …;拿起 = 玩家所在处的物件(不是人 / 地点 / 效果,没标 `fixed`)到玩家手里 → `gained`(`picked`)。
- 技能命令:`POST /cmd {"action": "skill", "skill": "侦查", "target": "井口"}`,或者直接发文字「/侦查 井口」(技能 / 属性的任何一种名字,多词名如「/First Aid 她」也认)。规则包有 `skill_check` 接缝时引擎**当场**检定(pct:d100 ≤ 技能值),这一拍的第一条 `dice` 事件就是它,结果写进给主持的事实里;包没有这个接缝或这个名字它不认 → 告诉主持「玩家用了这个技能」,按世界的检定规则自己掷。这一拍的玩家原话变成「我用「侦查」:井口。」,`resolve.beat.action = {kind: skill, skill, key?, target, rolled, total?, vs?, passed?, level?}`。文字「/go 3车」= 世界行动(`actions.json` 的 `actions`)那句 prompt。
- 读给前端的(本局语言):`GET /api/v1/play/engine/sheet` → `{lang, name, hp?, system?, attrs: [{key, label, value, desc, check?}], skills: [{key, name, label, value, desc, check?}]}`;`GET /api/v1/play/engine/actions` → `{lang, actions, verbs, skills, attrs, items, places, people, quick}`(`/` `@` `#` 的候选和快捷条,常用的带 `common`);`GET /api/v1/play/engine/template` 带 `lang`。
- 认识的人(10-15):`GET /api/v1/play/engine/people` → `{lang, people: [{id, sid?, kind: soul|npc, name, role_label, met, here, companion, addr, place, where, portrait_slot, last_seen?, mood_label?, trust?, relation?}]}`。只列玩家在场的人和见过的人;没见过名字的 NPC `name: ""`(只给 `role_label`)。角色和玩家同处一地(一拍之前或之后)引擎就写 `souls/<…>/run_state.json` 的 `status.met_player` 和 `last_seen {addr, turn}`,分开后还在 people / 地图上。play 侧 `entities?cls=soul|npc` 只给能给玩家看的字段(`core/people.PLAY_PROPS` + `mood_label` / `role_label`),`persona` / `rules` / `goals` / `relationships`(含 `truth`)只在调试读 `GET /api/v1/play/engine/debug/entities?cls=…`。
- `soul.mind {turn, iid, sid, name, attitude, attitude_label, thought?, intent, move_to?, follow, stay, trust_delta?}`:在场角色这一拍的心思(她自己那一拍的判断),每拍事件之后发,进 `/engine/beats`。`<fields>` 可写一行 `thought:`(一句,本局语言)。
- 目标与地图(10-15):`GET /api/v1/play/engine/objective` → `{lang, now: {plot, stage, name, goal}, plots: [{plot, title, stage, steps: [{index, name, goal, state: done|current|hidden}]}], jobs: [{id, name, summary, state: offered|active|done|failed|abandoned, state_label, active}], exit: {on, label}}`(没到的阶段不给名字;委托的状态词按 `core/objective.JOB_STATES` 收拢,`locked` 不列,没碰到过的委托不列)。`/api/v1/play/map` 每个节点带 `pos100`(在本层里的 0–100 位置);没有位置或和别人叠在一起的地点,引擎按连着的邻居或空位给一个位置(`pos_guess`),各层 `hotspots` 都在 2–98 内,估的放在 `hotspot_guess`。`place.discovered {turn, addr, name, parent, by: grow|arrive|reveal}`:引擎新长出的地点、第一次走到、上了玩家地图或被叙事点到,进 `/engine/beats`(第一次看这一局不发)。
- 玩家视角 vs 调试(10-15):play 侧接口只给玩家该知道的 —— `/state`(和 `/events` 的 hello / positions)只列认识的角色;`/trace?i=` 是玩家视角(叙事、选项、骰子、落账、在场角色的发言与心思,没有 `bus_messages` / `plan` / `spans` / 计划板 / 变量全表 / 异地角色);`/api/v1/play/schema` 不带触发器和变量 doc,`entries`(和 `entities?cls=…`)只列玩家碰到过的条目(地图上的地点、认识的人、在眼前 / 身上 / 被叙事点到过的东西,记在 `game/meta/seen.json`),没发现的线索不出名字;计划板 `plan.beat.board` 是这一桌各人说好的打算,照常给;`/events` 不发 thinking、不发不认识的角色的心象。完整数据走 `/api/v1/play/engine/debug/{state,traces,trace?i=,schema,entities?cls=}` 和 `/events?debug=1`,只在本机引擎开(`NEONRP_DEBUG_ROUTES=1|0`;不设 = 本机开、浏览器版关,测试台 bench.html 自己打开)。读取方 `src/neonrp/core/play_view.py`。

### 6.7 声音:主题曲 · 情绪 · 环境音(10-15,已实装)

一局有两条声道:**音乐**(同一时刻一首)和**环境音**。放什么由引擎定,前端只照着播(`core/audio.py`);作者**什么都不写也有声音**,写了的地方覆盖默认。

| 写在哪 | 写法 | 作用 |
|---|---|---|
| `template.json` `audio` | `{"theme": <音乐>, "ambient": <环境音>, "moods": {"tense": <音乐>, "crisis": <音乐>}, "places": {<地点地址>: {"ambient", "bgm"}}, "credits": "assets/audio/CREDITS.md"}` | 世界主题曲(平静时放)· 地名猜不出时的环境音 · 换掉紧张 / 危机曲 · 按地址给地点配声音 · 自带音频的来源 |
| `location.json` `audio` | `{"ambient": …, "bgm": …}` | 这个地点(和它里面的地点)的环境音 / 自己的曲子 |
| `plot.json` `stages[n].audio` | `{"mood"?: calm\|tense\|crisis, "bgm"?, "ambient"?}` | 这一阶段期间 |
| 触发 `then` | `{"to": "audio", "mood"?, "bgm"?, "ambient"?}` | 从这一拍起;写 `default` = 撤掉这一项 |

值:平台池 id(`worldlines/audio/catalog.json`:音乐 `calm` `tense` `crisis` `guixiang` `wuwu` `whitechapel` `divergence` `firstsnow` `emberglass` `mandongbu`,环境音 `rain` `fireplace` `cellar-drip` `storm` `snow-wind` `harbor-waves` `library` `city-night` `office-night` `cave-drip` `tavern-chatter` `cafe-murmur` `bell-church` `forge`)· 模板里的文件 `assets/audio/x.mp3`(mp3 / ogg / m4a / wav)· `silence`(没有音乐,主题曲也停)/ `none`(没有环境音)· `default`(当没写)。

**引擎怎么定**
- 情绪 `calm` / `tense` / `crisis`:作者的(触发 > 阶段)是底;剧情走到最后一个阶段 = `tense` 打底;这一拍落地的事往上抬 —— 进了战斗类模式层(`combat` 等)或玩家 hp ≤ 30% → `crisis`,这一拍掉了 hp / 理智 → `tense`;抬上去的撑 2 拍再回落。
- 音乐:`calm` 放触发 / 阶段 / 地点自己的曲子,没有就放主题曲,没有主题曲按合约给(`mystery-trpg` → `tense`、`open-adventure` → `emberglass`、`romance-companion` → `calm`、`murder-mystery` → `whitechapel`);`tense` / `crisis` 放 `moods` 或池子的同名曲。任何一处写了 `silence` = 不放音乐。
- 环境音:触发 > 阶段 > 地点(向上继承,`places` 补 `location.json` 没写的)> 按地名 / 地址 / 类型在池子关键词里猜(关键词是池子目录里的数据,不在引擎代码里)> `audio.ambient`。

**给前端的**:拍事件 `audio.cue {turn, music: {id, url, mood, title?} | null, ambient: {id, url} | null, mood, by: default|place|stage|trigger|mood, fade_ms, place}`,只在要放的变了才发;`GET /api/v1/play/engine/audio` = 现在这一份 + `credits`(池子每首的标题 / 作者 / 授权 / 来源,CC BY 在前)+ `template_credits`。URL 带内容哈希:池子 `/api/v1/audio/<kind>/<id>.<hash>.mp3`,模板 `/api/v1/local/templates/<id>/audio?path=…&h=<hash>`;哈希对得上 = `Cache-Control: public, max-age=31536000, immutable`,否则 ETag;都支持 Range(Safari / WKWebView 播媒体要它)。

**池子随产品走**:本地 = worldlines wheel 的 `worldlines_shim/audio/`(约 21 MB,`NEONRP_AUDIO_DIR` 可改);浏览器版 = `play/audio/<kind>/<id>.<hash>.mp3` 静态文件(不进引擎 / 世界 zip,所有世界共用,Service Worker 把 `/api/v1/audio/` 指过去);iOS = app 里本机引擎同源服务;Hub 模板包只带模板自己的音频,池子曲只按 id 引用。池子只收能再分发的:CC0,或 CC BY 4.0(三首,标准前端「菜单 → 声音 → 音乐鸣谢」署名);魔王魂 / Suno / 授权曲不收。

---

## 7. Lint(代码一览)

`neonrp template lint` 汇总所有检查,每条 `{level: block|warn, code, where, msg}`;有任何 block 即不可发布(退出码 1)。lint 会在临时目录做一次"全员到场"的参考 build,让剧情和槽位检查对着真实世界跑。

| code | level | 含义 |
|---|---|---|
| `schema` | block / warn | template.json 读不到或不是 JSON(block);`schema` 不是 `worldlines.template/1`(warn) |
| `meta.card` | block / warn | 缺 `card.title`(block);缺 `card.pitch`(warn) |
| `meta.mode` | block / warn | `mode.ending` 非法(block);`mode.freedom` 未知(warn) |
| `meta.zone` | block | `zone` 不是 `reviewed` / `open` |
| `meta.forkable` | block / warn | 不是 bool(block);写在不是默认区的模板上(warn) |
| `meta.milestones` · `meta.realtime_art` · `meta.achievements` | block | 取值不对 |
| `meta.rewards` | block / warn | `rewards` 写法读不了(block);图不在模板里、自由区不发、合约不发卡等(warn) |
| `soul.standalone` · `soul.takeable` · `soul.take_when` | block | 角色 `soul.json` 里这几个键的取值不对(见 soul spec) |
| `uses.shape` · `uses.param` | block · warn | `uses` 形状不对;`uses.params` 选了编排模板没有的参数(§2a) |
| `ref.world` | block | 没给世界,或世界目录不存在 |
| `ref.pack` | block | pack(含 mixin 组合)加载失败 |
| `pack.mixin` | block | mixin 名解析不到 |
| `pack.mixin.data` | warn | `economy` / `factions` 缺 `game/world/<mixin>.json`,mixin 不生效 |
| `pack.engine` | block | `pack.engine.turn.mode` 不是 `v2b` / `v3` |
| `ref.souls` | warn | 模板和世界都没有灵魂 |
| `ref.soul.pool` | block | `pick` 大于池子 |
| `ref.soul` | block | 灵魂缺 sid,或找不到(不是世界自带、`path` 无效) |
| `ref.prompt` | block | `prompts` 列出的文件不存在 |
| `prompt.parse` | block | prompt 文件解析失败 |
| `prompt.empty` | warn | 空 entry |
| `prompt.soul` | warn | `prompts/souls/<sid>` 对应的灵魂没上场 |
| `prompt.soul.data` | block | 角色侧 prompt 层写了灵魂数据路径 |
| `build` | block | 参考 build 失败 |
| `ref.plot` | block | 剧情包目录没有 plot.json |
| `plot.parse` | block | plot.json 解析失败 |
| `plot.lint` | block | 剧情包校验本身崩溃 |
| `plot` | block / warn | 剧情包校验结果(error → block,warn → warn):缺 id/title、未知类、地点缺 parent/links、变量缺 type、结局未声明/未知灵魂、结局不可达、stages 没人推进、素材种类/路径/文件不对、未引用的素材、未知顶层键 |
| `loop.pool` | warn | 剧情点名一个只在池里的灵魂:没抽到的局里这句话静默 |
| `v3.lint` | block | ui 检查本身崩溃 |
| `schema.view` | block / warn | 视图绑不到变量 / 绑了不存在的类 / 动作无处理器(block);未知 widget(warn) |
| `schema.slot` | block / warn | 配方既不是内置也不是命名 prompt(block);槽位挂在世界没有的类上(warn) |
| `schema.opening` | block | `opening.cg` 写错:一项既没图也没视频、路径出了模板、文件类型不对(还没填 = `asset.optional`,warn) |
| `audio.schema` | block / warn | `audio` 形状不对(block);未知键(warn) |
| `audio.ref` | block | 音频值解析不到:池子没有这个 id / 模板里没有这个文件 / 出了模板 / 不是 mp3·ogg·m4a·wav |
| `audio.size` | warn | 模板自带的一首超过 4 MB(玩家要下载) |
| `audio.credits` | block / warn | 模板自带音频却没写 `audio.credits`:默认区(`zone: reviewed`)block,自由区 warn |
| `asset.stale` | block / warn | 已填素材的输入变了(publish 且必需 → block) |
| `asset.missing` | block / warn | 必需槽位没填(publish → block) |
| `asset.optional` | warn | N 个可选槽位没填 |
| `prompt.placeholder` | block / warn | 命名 prompt 里的未知占位符(block);prompt 层 entry 里的未知点号占位符(warn) |
| `token.unmeasured` | warn | 还没有回合可量 |
| `token.over` | block / warn | 每回合均值超预算(publish → block) |
| `token.near` | warn | 超过预算 80% |
| `asset.card` | block / warn | 没有封面文件(`lint.level: "publish"` → block,否则 warn) |
| `loop.single` | block | `single` 模式不是恰好 1 个可达结局 |
| `loop.multi` | block | `multi` 模式可达结局少于 2 |
| `loop.reach` | block / warn | `single`/`multi` 下某结局无触发(block);`open` 下声明了结局但都不可达(warn) |
| `loop.distinct` | block | 同一触发分支发出两个结局 |
| `loop.guide` | warn | 有结局的剧情包没有 stages 或没有追加 prompt |
| `loop.exit` | warn | `single`/`multi` 下没有 `fail`/`fallback`/`rule` 结局 |
| `loop.epilogue` | warn | 结局没有标题 |
| `loop.reveal` | block | `mode.reveal` 开着但剧情包没有 `reveal` |
| `contract.unknown` · `contract.entry` · `contract.exit` · `contract.endings` · `contract.reveal` · `contract.rewards` | block | 玩法合约要求的东西缺了(见 contract spec) |
| `contract.deaths` | warn | 合约规定某类死亡走某种结局,而模板没有这种结局(引擎会给一个普通的死亡退场) |
| `contract.truth_quiz` · `truth_quiz.schema` · `truth_quiz.lang` · `truth_quiz.reward_soul` | 默认区 block / 自由区 warn | 合约要求「真相三问」而没写;写法不对;缺语言或某种语言改了正确答案;`reward_soul` 不在演员表里,或是 `takeable: false` |
| `truth_quiz.points` | warn | `settlement.truth_quiz_points` 不是非负整数 |
| `creation.schema` | block / warn | `creation` 不是对象(block);未知名字(warn,会被丢掉) |
| `collect.who` · `collect.on` · `collect.contract` | block | 收集规则指向的不是世界里的角色;`on` 不对或结局不存在;合约不允许收集或数量不够 |
| `collect.rarity` | warn | 稀有度不是 common / rare / epic |
| `asset.variant` | warn | 按同伴的图版本:键不是这个模板的角色;写了 `image_shows` 但其他候选同伴没有自己的版本(6.6) |
| `map.*` | warn | 绑定世界的地图问题:`map.dangling`(连接指向不存在的地点)· `map.port_unbound` · `map.port_dangling` · `map.isolated` · `map.legacy_level`(还是旧的 `nodes` 写法,见 world spec) |
| `frontend.*` | warn | `frontends/` 里世界自带前端的问题(只在本机用,不挡发布) |
| `player.builder` | block | 捏人声明不合法:字段缺 id / 重复 / 未知 kind、`to` 越出 game 目录、选项缺 id、grants 不是 set/append/add、点数分不完、头像图不在模板里、companion 候选不够 `pick` |
| `i18n.id` | block | 本地化层改了一个 id(ASCII 的 id / sid / 地点 / flag / 变量引用);id 要保持原样 |
| `i18n.parse` | block | 本地化层的 JSON 解析失败 |
| `i18n.build` | block | (`--i18n-deep`)某种语言的本地化版本 build / lint 出 block |
| `i18n.missing` | warn | 声明了的语言没有本地化层:这一局用主语言 |
| `i18n.partial` | warn | 本地化层还缺 N 个文件 / 字符串(回退主语言) |
| `i18n.residue` | warn | 这种语言的本地化版本里还留着别的语言的专有名词(glossary) |
| `i18n.key` / `i18n.list` / `i18n.orphan` | warn | 模板没有的键(可能打错;键是 id,不本地化)/ 数组长度不同被整个替换 / 模板没有的文件 |
| `i18n.card_lang` · `i18n.replaces` · `i18n.lint` | warn | 本地化层卡面的 `lang` 不是这一层的语言;本地化的 overlay 文件整份替换了世界原文件、丢了键;本地化检查本身出错 |

---

## 8. 从模板到一局

### 8.1 `build(template, dest)` 的步骤(`neonrp.template:build`)

0. 给了 `lang`:先把 `i18n/<lang>/` 盖在模板的临时副本上(见 4.1),以下步骤都对这份副本做;最后收窄四语对象、写 `output_lang`。
1. `dest` 必须不存在或为空。
2. 复制世界(`world.path` 或 `world.builtin`),跳过 `.neonrp/`、`__pycache__`。
3. 盖 overlay(整文件替换)。
4. `world.shuffle`:按 `seed` 洗牌发属性。
5. 选角:按 `souls` 抽取;`lib` / `path` 的角色**这时才**复制进这一局(`souls/<sid>-<instance_id>/`),世界自带的按 playthrough 行;写 `playthrough.json` 的 `souls` 和 `active_souls`。
6. 角色侧 prompt 层:只覆盖 `soul.md` / `persona/` / `rules/` / `agents/`。
7. 绑定 pack:`playthrough.json`(根目录和 `.neonrp/` 各一份)与 `manifest.json` 写 `"template": "<pack 名>"`,引擎靠它解析 pack。
8. 每个 mixin 执行 `install(run)`,注册封闭 schema 变量并播种。
9. `pack.engine` 深合并进 `game/meta/engine.json`。
10. prompt 层合并,写 `game/meta/prompt.json`。
11. 安装剧情包(去掉 `prompt` / `reveal` 后注册进世界,复制到 `game/plots/<id>/`;`reveal` 另存 `reveal.json`)。
12. 封面复制到 `assets/template-cover.<ext>`;`card.title` 写进 `game/meta/game-start.json` 的 `name`。
13. 写 `game/meta/template.json`:模板元数据(含 `uses`、`opening`、`audio`、`settlement`)+ `built`(souls / cast / plots / prompt_overlays / shuffled / mixins / dropped_soul_emits)+ 有效 `ui`。`neonrp template show` 和游玩界面都读这份记录。
14. 有玩法合约时写 `game/meta/play_contract.json`;有 `orchestration` 时写 `game/meta/orchestration.json`。

### 8.2 引擎配置怎么生效

```
builtin  <  pack(pack.loop)  <  contract(合约的 engine 段)  <  orchestration(uses 点名的编排模板)
         <  world(game/meta/engine.json)  <  graph(编排图的步骤参数)  <  playthrough(.neonrp/playthrough.json["engine"])  <  env(环境变量)
```

后者盖前者(`core/engine_config.py`)。模板的 `pack.engine` 在第 9 步落进 `game/meta/engine.json`,所以它**盖过 pack 自带的 loop 和编排模板**,但仍可被编排图、某一局的 playthrough 或实验用的环境变量覆盖。编排模板那一层不复制进存档,每次运行时叠上去。

用 `stoneford-town` build 出来的 run,在开源引擎上实测的各层:

| 键 | 值 | 来源层 |
|---|---|---|
| `turn.mode` | `v3` | pack(`rpg` 的 loop),world 层(模板 `pack.engine`)再写一次 |
| `turn.parallel.souls.default_variant` | `S-judge` | pack,orchestration 层(`uses.soul`)再写一次 |

在 PyPI 发布版上,orchestration 层还会带上两拍编排的设置(打开商量拍)。一回合里有哪些拍、叙事怎么转成状态,由编排模板和编排图决定(§2a),不在 `pack.engine` 里。

### 8.3 新开一局

- `neonrp.template:new_run(ref)`:`ref` 可以是目录或模板 id;在 `~/.worldlines/plays/tpl-<id>-<YYYYMMDD-HHMMSS>/` 下 build,初始化 manifest,写入模型(见 3.9)。失败则删掉半成品。
- HTTP:`POST /api/v1/play/session {"slug": "tpl--<id>"}` 即新开该模板的一局。
- 模板声明了 `player.builder`(3.11):带上 `player: {fields, companion}` 即用玩家捏的角色开局;不带照旧开局。
- 模板发现顺序(`template:search_dirs` / `discover`):`NEONRP_TEMPLATE_PATH`(按系统路径分隔符分隔;WorldLines 会把玩家自己的模板库 `~/.worldlines/templates` 放在最前)→ PyPI 发布版额外带的模板目录(从开源源码装的没有)→ 产品目录(源码运行时是仓库里的 `worldlines/templates/`,安装后是 `worldlines` wheel 自带的模板)→ 用账号获取的官方世界 `~/.worldlines/official`。同 id 先到先得。
- 列表里 `shipped.json` 列出的两个内置模板(`pct-house`、`stoneford-town`)排最前。安装版只带这两个;其他官方世界登录后用 `neonrp template fetch <id>` 获取。源码运行时产品目录里的其他模板也会列出来,设 `NEONRP_TEMPLATES=shipped` 可以只看安装版那两个。

---

## 9. 命令行

```
neonrp template list                        列出可发现的模板:id、pack 名、结局模式、标题、目录
neonrp template lint <目录|id> [--json]     全部检查;不可发布时退出码 1
neonrp template build <目录|id> <dest> [--force] [--lang L]
                                            先 lint,有 block 就拒绝(--force 强行 build);--lang 盖本地化层
neonrp template show [--world <run 目录>]    已 build 的 run:卡面 / 模式 / 剧情阶段 / 结局;谜底只在结局后
neonrp template slots <目录|id>             每个素材槽位实例:ok / stale / MISSING(必需未填)/ -(可选未填)
neonrp template contract <目录|id> [--ts|--gd]
                                            导出 worldlines.contract/0.1(vars / classes / ops / events / triggers /
                                            slots / views / panels),或生成 TypeScript / GDScript 绑定
neonrp template contracts                   官方玩法合约,以及哪些模板声明了它
neonrp template fork <目录|id> <new-id> [--store DIR] [--title T]
                                            复制一份进你的模板库再改(内置的只读;官方世界只有 forkable 的能复制)
neonrp template set-contract <id> <合约[@版本]>|--clear
                                            声明这个模板承诺的体验;改完重跑 lint
neonrp template export <目录|id> [-o FILE]   打成一个包(.zip),它 link 的角色库角色一起带上;默认区作品拒绝(见 9.2)
neonrp template export --soul <名字> [-o]    角色库里的一个角色打成包
neonrp template import <FILE> [--id NEW] [--store DIR]
                                            导回来:模板进你的模板库,带着的角色进角色库(见 9.2)
neonrp template publish <目录|id> --official 以官方身份发到默认区(只有官方账号能用;再发 = 新 revision,先升 version)
neonrp template fetch <id>                  用 Worldlines 账号获取(或更新)一个默认区世界到 ~/.worldlines/official
neonrp spec sync [DIR …]                    把 AGENTS.md / CLAUDE.md / spec/ 写进每个模板、模板库和角色库
```

`fork` / `import` 要写进你的模板库:用 `--store DIR` 指定,或设 `NEONRP_TEMPLATE_WRITE_DIR`(`worldlines` 启动时会设成 `~/.worldlines/templates`)。只在命令行里跑时,改完再用路径引用这个副本,例如:

```
neonrp template fork stoneford-town my-town --store ~/.worldlines/templates
neonrp template lint ~/.worldlines/templates/my-town.template
neonrp template export ~/.worldlines/templates/my-town.template -o my-town.zip
```

`lint` 文本输出每行:`[level] code where: msg`,最后一行 `publishable|NOT publishable — N block, M warn`。`--json` 输出:

```json
{
  "problems": [{"level": "warn", "code": "meta.card", "where": "card.pitch", "msg": "no pitch (one line on the card)"}],
  "publishable": true,
  "meta": {"schema": "worldlines.template/1", "id": "min", "version": "", "card": {…}, "mode": {},
           "pack": "rpg", "plots": [], "souls": [], "models": {}},
  "counts": {"block": 0, "warn": 4}
}
```

两个内置模板(都是 `lint.level: draft`)当前的 lint 结果:`pct-house` 是 `publishable — 0 block, 1 warn`(`token.unmeasured`,本机还没玩过);`stoneford-town` 是 `0 block, 4 warn`(`asset.stale`、`asset.optional`、`token.unmeasured`、`i18n.residue`)。

### 9.1 Authoring API(简述)

`neonrp.template.author` 提供创作者编辑:

- 只能写 `NEONRP_TEMPLATE_WRITE_DIR` 下的模板;内置 / 示例模板只读,先 `fork(src, new_id)`。fork 出来的副本去掉 `zone` / `forkable` / `official`,是作者自己的作品(自由区,可以导出)。
- `apply_ops(t, ops)`:所有 op 先验证,一条被拒则全部不写,写完自动重新 lint。op:`edit_card` `set_mode` `set_mixins` `add_slot` `remove_slot` `edit_prompt` `edit_recipe` `set_view` `remove_view` `set_budget` `register_class` `set_policy` `set_world_data` `set_orchestration` `set_play_contract` `set_soul_orchestration` `set_engine_setting` `set_soul_ambient` `set_cast`。每个 op 的字段:`neonrp spec authoring`。
- `set_orchestration {graph}`:模板的编排图,存成相对玩法包默认图的补丁(`orchestration.json`);`nodes.resolve.state = pseudo | jev` 定清算拍怎么写状态(§2a)。
- `set_soul_orchestration {sid, graph}`:一个角色在这个世界里自己的编排图,写 `prompts/souls/<sid>/orchestration.json`。`set_soul_ambient {sid, world}`:一个角色在这个世界里的简单世界观,写 `prompts/souls/<sid>/ambient/world.json`。(两者都撞上 3.7 的已知问题。)
- `set_engine_setting {key, value}`:只允许白名单里的设置,写进 `pack.engine`:`turn.parallel.souls.default_variant`,或 `turn.parallel.souls.per_soul.<sid>`(这个模板的角色;`null` = 跟默认),取值 `legacy` · `S-judge` · `S-direct` · `S-free`。
- `set_cast {souls: [...]}`:整张演员表(3.6 的行);link 断了 / 重复 / 定位不认识 / 两个主角 → 整批拒。
- 设置 `WORLDLINES_ASSETS_DIR` 时,每张落进槽位的图另存一份到素材工坊,保留历史。
- 对应 HTTP:`/api/v1/local/templates/<id>/{lint,cover,contract,assets,ui,fork,ops,plots,graph-lint,export,publish}`;角色反查 `GET /api/v1/local/souls/<名字>/bindings`。

### 9.2 包:导出 / 导入(`neonrp.template.package`)

一种包装所有东西:zip,根目录一份 `pack.json`:

```json
{"schema": "worldlines.package/1", "kind": "template", "id": "my-house", "title": "灰橡宅 · 关上的门",
 "exported": "2026-10-08T09:00:00+00:00", "links": ["mira"]}
```

| kind | 包里有 | 导入到 |
|---|---|---|
| `template` | `<id>.template/…`(模板文件夹原样,不带 `frontends/`)+ `souls-lib/<名字>/…`(它 `lib` 的每个角色) | 模板 → `NEONRP_TEMPLATE_WRITE_DIR`;角色 → 角色库,行照旧 link |
| `soul` | `soul/…`(一个角色库角色) | 角色库 |

- 只有自由区作品能导出:默认区作品(`zone: reviewed`,以及获取来的官方世界)导出被拒(`ExportRefused`,code `default_zone`)。官方世界写了 `forkable: true` 的,先 `fork` 一份,副本就能导出。
- 导出前 link 的角色库角色必须都在,否则拒绝。
- id 被占 → 下一个空的 `-2`、`-3`……(`--id` 指定时被占就拒)。
- 角色库里已有同名角色:内容一模一样就复用;不一样就改名装进来,模板的行指过去,本机原来的不动。
- 先解到临时目录检查再落地:绝对路径 / `..` / 链接 / 代码文件(`.py` `.js` `.sh` …)/ 超过 5000 个文件或 300 MB → 整包拒。
- HTTP:`GET /api/v1/local/{templates|souls}/<id>/export` · `POST /api/v1/local/import/package[?id=]`(body = zip)。

### 9.3 发布到 Hub(`core.template_publish`)

Hub 分两个区。引擎里叫 `reviewed` / `open`,平台叫 `curated` / `open`:

| 区 | 是什么 | 怎么进 |
|---|---|---|
| **自由区**(`open`) | 检查通过即公开,事后管理;不发奖励卡 | 本机创作台用 Worldlines 账号发布:`POST /api/v1/local/templates/<id>/publish {lang?}` |
| **默认区**(`reviewed` / `curated`) | 审核后上架;官方世界也在这里 | 网页 Hub / iOS 创作台带 `{zone: "curated"}` 提交进审核队列;自由区作品之后可以 `POST /api/v1/local/hub/submit {id}` 申请;官方账号用 `neonrp template publish <id> --official` |

发布前引擎先跑同样的检查(`preflight`;`GET …/publish` 只检查不上传):

1. 模板 link 的角色库角色都在;
2. 会进包的文本里(模板和每个 link 的角色)没有密钥形状的字符串或凭据文件;
3. lint `publishable`(没有 block);
4. 卡面的中 / 英 / 日 / 韩标题和简介齐全(卡面本身或本地化层的卡面);
5. 有封面文件。

上传的是 `package.zip`(同 9.2,link 的角色复制进包)和封面。作品 id = `<模板 id>-<6 位 hex>`;同一模板再发 = 同一作品加一个 revision。平台检查不过返回 422 `checks_failed {problems}`。作者自己的作品:`GET /api/v1/local/hub/mine`,`POST …/hub/{unpublish,submit,withdraw} {id}`。

---

## 10. 参考实现位置

| 内容 | 位置 |
|---|---|
| 加载 / build / lint / 发现 / 新开一局 / 槽位上传生成 | `src/neonrp/template/__init__.py` |
| 有效 ui、槽位实例、视图绑定、ui lint、契约与代码生成 | `src/neonrp/template/v3.py` |
| 创作者 op、fork、素材工坊 | `src/neonrp/template/author.py` |
| pack 加载、mixin 组合、ui 合并 | `src/neonrp/packs/__init__.py` |
| mixin:经济 / 势力 | `src/neonrp/packs/mixins/economy.py`、`factions.py` |
| 剧情包解析、校验、安装 | `src/neonrp/packs/rpg/plot.py` |
| 引擎配置分层 | `src/neonrp/core/engine_config.py` |
| 命令行 | `src/neonrp/commands/template_cmd.py` |
| 包:导出 / 导入 | `src/neonrp/template/package.py` |
| 捏人(player.builder):声明检查 / 草稿校验 / 写进这一局 / 玩家卡 | `src/neonrp/template/builder.py` |
| 给 agent 读的 spec(`neonrp spec` · `/api/v1/spec` · `/llms.txt`) | `src/neonrp/spec.py` |
| HTTP | `src/neonrp/webui/template_routes.py` |
| 内置世界 | `src/neonrp/templates/<world id>/` |
| 发布到 Hub / 获取官方世界 | `src/neonrp/core/template_publish.py` |
| 编排模板 | `src/neonrp/core/orch_templates.py`、`src/neonrp/orchestrations/` |
| 写状态的后台纠正 | `src/neonrp/core/write_down_async.py` |
| 内置模板 | `worldlines/templates/{pct-house,stoneford-town}.template/`(`worldlines/templates/shipped.json`) |
