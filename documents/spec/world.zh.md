# World 规范(世界文件夹)

> 状态标记:**已实装** = 引擎代码会读 / 会校验;**约定** = 引擎代码不解析,由 agent 按提示词自行读取;**设计中** = 有文档或数据,但没有代码读取。
> 本页对应引擎当前源码(`src/neonrp/`)。字段表只列代码实际读取的键,其余键允许存在(开放 schema),引擎会原样保留。

---

## 1. 是什么

**world** 是一个世界的数据层:地图层级(世界 → 镇 / 地下城 → 地点)、镇、地点、NPC、道具、传说文本、开场,加上世界自带的 agent 定义。它是一个普通文件夹,大部分内容放在 `game/` 下;引擎每回合从这些文件**读时归一**,生成一张注册表(`src/neonrp/core/registry.py:load_registry`),里面有 variables / entries / classes / actions / triggers 五张表。

分层(已定):

```
最小可运行 = pack(规则,在引擎里) + world(数据,本页) + souls(角色,数据)
template   = 可选的上层,把三者绑在一起
```

- **pack** 决定"怎么读这个世界"。默认 pack 是 `rpg`(`src/neonrp/packs/rpg/`),本页描述的目录结构就是 rpg pack 的加载器(`src/neonrp/packs/rpg/loaders.py:load`)读的结构;`pct`(百分骰调查,BRP 一系)建在 rpg 上,读同一套结构。其他 pack(`werewolf`、`monopoly`)只靠通用的类文件夹(见 §3.9)。
- **souls** 是有自己 agent 的角色,放在 `souls/` 下,规范见 [soul.md](./soul.zh.md)。
- **template** 负责绑定(`playthrough.json`、选哪个 pack、提示词 / 剧情包),规范见 [template.md](./template.zh.md)。

本页只讲世界文件夹本身。

---

## 2. 目录结构

以内置世界 `src/neonrp/templates/stoneford-elena` 为准(省略了 `souls/`,那一层属于 soul 规范):

```
<world>/
├── manifest.json                 可选 · 世界语言 / pack 名 / 提示词条目 / 触发器
├── agents/                       世界自己的 agent(运行时真正读的位置)
│   ├── world-agent/
│   │   ├── agent.json            路由 / 叙述 agent(必须有一个,缺了启动时自动补)
│   │   ├── system.md
│   │   └── voice.md              可选 · v3 回合的叙述口吻
│   └── town-agent/ …             可选 · 子 agent,每个一个文件夹
├── assets/                       可选 · 图片
│   ├── cover.png
│   ├── art-style.md
│   ├── maps/<层级>.webp|.json|.guide.png
│   └── places/<镇>__<地点>.webp
└── game/                         数据目录
    ├── world/world_map.json      世界层:镇 / 地下城 / 区域节点 + 道路
    ├── towns/<T###>/
    │   ├── town.json             镇的属性
    │   ├── town_map.json         镇内地点图(带门)
    │   ├── npcs.json             可选 · 轻量 NPC
    │   ├── quests.json           可选 · 公会委托
    │   └── facilities/*.json     可选 · 设施细节
    ├── dungeons/<D###>/          可选 · 地下城
    │   ├── dungeon.json
    │   ├── layout.json
    │   ├── rooms/<房间id>.json
    │   ├── encounter_tables.json
    │   └── loot_tables.json
    ├── locations/*.json          可选 · 扁平地点(合并进镇内地点)
    ├── npc/*.json                可选 · 扁平 NPC
    ├── item/**/*.json            可选 · 道具(也认 items/)
    ├── lore/
    │   ├── story.md              主线 / 世界介绍
    │   ├── rumors.md             传闻
    │   ├── notes.md              GM 笔记(角色不可读)
    │   └── gm-truth.md           GM 真相(角色不可读)
    ├── rules/*.md                可选 · 规则文本(检定、战斗)
    ├── secrets/*.json            可选 · 秘密覆盖层
    ├── timeline/current.json     可选 · 当前时间 / 天气 / 进行中的线索
    ├── player/                   玩家起始状态
    │   ├── profile.json  stats.json  wallet.json
    │   ├── equipment.json  inventory.json  flags.json
    │   ├── controller.json  journal.md
    │   └── assets/portrait.png
    ├── agents/manifest.json      可选 · 世界 agent 阵容的模板
    └── meta/
        ├── run_state.json        玩家位置 / 时间 / 回合数
        ├── game-start.json       开场
        ├── active-agent.json     当前路由 agent(引擎维护)
        ├── prompt.json           可选 · 提示词条目
        ├── engine.json           可选 · 回合引擎配置
        ├── variables.json  classes.json  entries.json
        ├── actions.json  triggers.json   可选 · 五张表的覆盖层
        ├── roster.json           可选 · 演员表(只给 world-agent 看)
        ├── schedule.json         约定 · 定时事件
        └── flag_aliases.json     约定 · flag 别名
```

`.neonrp/` 由引擎管理(会话、事件、存档、`manifest.json`、`runtime_contract.json`、`playthrough.json`),**不是**创作内容。内置模板把 `runtime_contract.json` 和 `playthrough.json` 放在根目录作为源形状,搭建时复制进 `.neonrp/`(`src/neonrp/core/template_assets.py:copy_souls_and_playthrough_from_template`,`src/neonrp/worlds.py` 里新局的迁移)。

数据目录名默认是 `game`,可以由 `.neonrp/runtime_contract.json` 的 `data_dir` 改名,但地图导航、校验器和创建流程里有几处直接写死 `game/`(`src/neonrp/core/place_nav.py:load_world_map`、`src/neonrp/core/validation.py:_known_locations`)。**请保持 `game`。**

---

## 3. 文件逐个说明

### 3.1 地址规则(先读这个)

| 规则 | 说明 | 实现 |
|---|---|---|
| 镇 / 地下城 / 区域 id | 必须匹配 `^[A-Z]{1,3}\d{2,4}$`,例如 `T001`、`D001`、`R003`。不匹配的 id 会被当成镇内地点 id | `src/neonrp/core/place_nav.py:_TOWN_ID_RE` |
| 镇内地点地址 | `T001/gate_north`(镇 id + `/` + 节点 id)。单写 `gate_north` 时,先在玩家当前所在的镇里找,找不到再取第一个含有它的镇 | `place_nav.py:qualify_location`、`split_location` |
| 地下城房间地址 | `D001/D001_R002` | `loaders.py:_load_dungeons` |
| 门 | 节点 `type: "gate"`(或 id 以 `gate` 开头)。在镇与镇之间移动要经过门 | `place_nav.py:_gate_of` |

### 3.2 `game/world/world_map.json` — 世界层 · 已实装

读取方:`src/neonrp/packs/rpg/loaders.py:_load_world`(注册表)、`src/neonrp/core/worldmap.py:build_map_tree`(地图树)、`src/neonrp/core/place_nav.py:load_world_map` / `_world_route`(跨镇移动判定)。

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `world_id` | str | 建议 | 世界条目的 id;缺省为 `"world"` |
| `name` | str | 建议 | 世界名 |
| `nodes[]` | list | 是(rpg) | 世界层节点 |
| `nodes[].id` | str | 是 | `T001` / `D001` / `R003`(见 §3.1) |
| `nodes[].type` | str | 是 | `town` / `city` / `village` / `dungeon` / `region` 等。注册表里只有 `town` 注册为 town 类,其余都注册为 region 类(有 `game/dungeons/<id>/` 时改为 dungeon 类);跨镇路线判定把 `town` / `city` / `village` 都当成镇 |
| `nodes[].name` | str | 是 | 显示名 |
| `nodes[].pos` | `[x, y]` | 画地图时需要 | 世界层坐标;只有所有子节点都有坐标的层级才能出图 |
| `nodes[].links` | list[str] | 否 | 相邻节点或道路 id。没有声明成节点的道路 id 也算连接点,所以两个镇 link 同一个 `R001` 就算连通 |
| `nodes[].summary` / `state` / `lore` / `travel_info` / `region` | 任意 | 否 | 原样进条目属性和地图树 |
| `routes[]` | list | 否 | 道路:`{id, from, to, kind, distance, tags, state: {blocked}}`,地图树画成边 |
| `foreign_lands[]` | list | 否 | 地图边界外的地方,进地图树的 `frontier` |
| `parent_territory` | str | 否 | 地图树根节点的说明文字 |

```json
{
  "world_id": "W001",
  "name": "灰雾北境",
  "nodes": [
    { "id": "T001", "type": "town", "name": "石津镇", "pos": [12, 7],
      "summary": "河港贸易小镇,雾常年不散。", "links": ["R001", "R002"],
      "state": { "discovered": true, "danger_nearby": 2 } }
  ],
  "routes": [
    { "id": "R002", "from": "T001", "to": "D001", "kind": "trail", "distance": 6,
      "tags": ["foggy", "beasts"], "state": { "blocked": false } }
  ]
}
```

### 3.3 `game/towns/<T###>/` — 镇 · 已实装

文件夹名就是镇 id;它应当同时作为节点出现在 `world_map.json` 里,否则地图树报 `orphan`。

**`town.json`** — 读取方 `loaders.py:_load_towns`(除 `id` 外所有键并进 town 条目)、`worldmap.py:build_map_tree`(`overview`、`tags`、`economy`、`laws`、`state`)、`loaders.py:_load_variables`(`state.alert` → 变量 `town.alert`,0–5)。

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | str | 镇名(缺省用文件夹名) |
| `overview` | str | 一段介绍,进叙述上下文(`town` 类的渲染模板是 `## 镇 {id} {name}\n{overview}`) |
| `state.alert` | int | 有这个键才会注册 `town.alert` 变量 |
| 其他(`tags`、`economy`、`laws`、`entry_points`…) | 任意 | 原样保留 |

**`town_map.json`** — 读取方 `loaders.py:_load_towns`、`worldmap.py:build_map_tree`、`place_nav.py`(移动判定)、`validation.py:_travel_graph_issues`。

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `town_id` | str | 建议 | 缺省用文件夹名 |
| `nodes[].id` | str | 是 | 镇内节点 id;地址是 `T001/<id>` |
| `nodes[].name` | str | 建议 | 显示名 |
| `nodes[].type` | str | 建议 | `gate`(门,每个在世界地图上的镇至少要一个)、`street`、`facility`、`dock` 等 |
| `nodes[].links` | list[str] | 建议 | 同一镇内相邻的节点 id。所有节点都应当能从某个门沿 links 走到 |
| `nodes[].pos` | `{x, y}` 或 `[x, y]` | 画地图时需要 | 镇层坐标 |
| `nodes[].parent` | str | 否 | 把这个节点放进另一个节点里面(下一层),进出都经过父节点 |
| `nodes[].facility_file` | str | 否 | 相对镇文件夹的路径,例如 `facilities/inn.json`;内容并进地点属性 `facility` |
| `nodes[].description` | str | 否 | 地图树里的地点摘要 |
| `state.discovered_nodes` | list[str] | 否 | 有这个列表时,只有列出的节点算已发现 |

```json
{
  "town_id": "T001",
  "nodes": [
    { "id": "gate_north", "name": "北门", "type": "gate",
      "pos": { "x": 236, "y": 153 }, "links": ["main_street"] },
    { "id": "inn", "name": "河灯旅店", "type": "facility",
      "facility_file": "facilities/inn.json",
      "pos": { "x": 621, "y": 268 }, "links": ["main_street"] }
  ]
}
```

**`npcs.json`** — 轻量 NPC(由叙述者扮演,**没有**自己的 agent)。读取方 `loaders.py:_load_npcs`、`worldmap.py:build_map_tree`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `npcs[].id` | str | 必需;和其他条目重名时变成 `T001/<id>` |
| `npcs[].name` | str | 末尾括号里的身份会被去掉作为短名,例如 `赫伦(公会管事)` → `赫伦` |
| `npcs[].role` / `traits` / `state` | 任意 | 进 npc 条目 |
| `npcs[].location` | str | 镇内节点 id;缺省就在整个镇 |
| `npcs[].state.soul_ref` | str | 指向一个 soul 文件夹时,地图上用 soul 代替这个 NPC |

```json
{ "town_id": "T001", "npcs": [
  { "id": "NPC003", "name": "米拉(旅店老板娘)", "role": "innkeeper",
    "traits": ["热情", "消息灵通"], "state": { "met": false }, "location": "inn" } ] }
```

**`quests.json`** — 公会委托,每行一个 `job` 条目,id 为 `T001/<qid>`。读取方 `loaders.py:_load_quests`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `quests[].qid`(或 `id`) | str | 必需 |
| `title` / `tier` / `summary` | str / int / str | 显示与排序 |
| `state` | str | 缺省 `available` |
| `reward` | `{gold, item: {id, name, qty}}` | 生成 `reward_text` |
| `hooks` / `unlocks` / 其他 | 任意 | 原样保留(游玩中写进去的进度键读回时也保留) |

**`facilities/*.json`** — 只在被 `town_map.json` 的 `facility_file` 引用时读取;除 `facility_id`、`rumor_pool_ref` 外的键进地点属性。

### 3.4 `game/dungeons/<D###>/` — 地下城 · 已实装

读取方 `loaders.py:_load_dungeons`、`worldmap.py:build_map_tree`。文件夹名应当作为 `type: "dungeon"` 的节点出现在 `world_map.json` 里。

| 文件 | 读取的键 |
|---|---|
| `dungeon.json` | `id`、`name`、`theme`、`danger`、`recommended_level`、`boss`、`state.{discovered, cleared}`、`entrance_from` |
| `layout.json` | `rooms[].{id, name, type, links, state}`、`state.current_room`。房间没有坐标,地图按 BFS 自动排版 |
| `rooms/<id>.json` | `name`、`description`、`features`、`state` |
| `encounter_tables.json` | `tables.<房间id>[] = {enemy, count, chance}` |
| `loot_tables.json` | `tables`(挂在地下城条目上) |

`world_map.json` 与 `dungeon.json` 的 `discovered` / `danger` 不一致时,地图树报 `conflict`。

### 3.5 `game/locations/` — 扁平地点 · 已实装

读取方 `loaders.py:_load_locations`、`worldmap.py:build_map_tree`。主要用于给镇内节点补充描述:按 id(经 `canonical_node` 归一)或名字匹配到镇内节点后,只补 `summary`、`tags`、`notes` 三个键,并把文件 id 登记成别名。匹配不到时成为独立的 place 条目,`parent` 缺省为玩家当前所在的镇,`connections` 作为出口。也支持场景文件夹 `game/locations/<节点>/location.json`。

```json
{ "id": "north-gate", "kind": "location", "name": "石津镇·北门",
  "summary": "歪斜的木栅门,湿冷的晨雾…", "connections": ["market-square", "old-road"] }
```

名字写成 `镇名·地点名` 时,地图树也能据此匹配到镇内节点;匹配不到时地图树报 `unresolved`。

### 3.6 NPC 与道具 · 已实装

| 路径 | 读取方 | 规则 |
|---|---|---|
| `game/npc/*.json` | `loaders.py:_load_npcs` | 需要 `id`;`location` 缺省为当前镇;其余键进属性 |
| `game/item/**/*.json`、`game/items/**/*.json` | `loaders.py:_load_items` | 需要 `id`;`owner` 或 `location` 作为 parent |

```json
{ "id": "elena-locket", "kind": "item", "name": "艾琳娜的银坠",
  "summary": "一枚磨得发亮的银质小坠…", "owner": "elena" }
```

注意:**轻量 NPC ≠ soul**。`npcs.json` / `game/npc/` 里的人物由叙述者代演。需要自己思考、有记忆的角色请做成 soul(见 [soul.md](./soul.zh.md))。一个世界在没有 `.neonrp/manifest.json` 时直接开玩,启动流程会把 `game/npc/*.json` 自动转换成 soul 文件夹(前提是还没有 `souls/`;`src/neonrp/core/created_world.py:finalize_created_world`)。

### 3.7 传说与规则文本 · 已实装

| 路径 | 读取方 | 用途 |
|---|---|---|
| `game/lore/story.md` | `loaders.py:load` → `reg.texts["lore"]`(前 4000 字) | 世界介绍,进叙述上下文;也用来判断世界语言 |
| `game/lore/rumors.md` | 同上 → `texts["rumors"]`(前 800 字) | 传闻 |
| `game/rules/*.md` | 同上 → `texts["rules"]`(每个文件前 3000 字) | 裁判 / 战斗层读取 |
| `game/lore/notes.md`、`game/lore/gm-truth.md` | `src/neonrp/core/soul_agent.py`(soul 的 `deny_globs`) | GM 专用,soul 读不到;agent 按提示词自行读取 |

### 3.8 `game/meta/` · 已实装(除标注外)

**`run_state.json`** — 玩家位置与时间。读取方 `loaders.py:load`、`_load_variables`、`worldmap.py:build_map_tree`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `location.node_id` | str | 玩家所在的镇,例如 `T001` |
| `location.subnode_id`(或 `node`) | str | 镇内节点;也可以直接写 `T001/gate_north` |
| `location.display` | str | 显示用 |
| `time.day` / `time.clock` | int / str | 变量 `time.day`(≥1,每回合最多 +1)、`time.clock` |
| `turn_count` | int | 只读变量 `turn` |
| `travel` | object | 在路上时由引擎写入,生成一个 `road` 条目 |
| `party.player.location` | str | 若与 `location` 不一致,地图树报 `conflict` |

```json
{ "location": { "scope": "town", "node_id": "T001", "subnode_id": "gate_north",
                "node": "gate_north", "display": "石津镇·北门" },
  "time": { "day": 1, "clock": "08:30" }, "turn_count": 0 }
```

**`game-start.json`** — 开场,见 §3.12。

**`active-agent.json`** — `{"active_agent": "world-agent", …}`,路由状态,由引擎维护;指向不存在的 agent 时 validate 给警告(`src/neonrp/core/active_agent.py:validate_active_agent`)。

**`prompt.json`** — 世界级提示词条目,叠加顺序是 pack 的 `prompt` < 根目录 `manifest.json` 的 `prompt` < `game/meta/prompt.json`(`src/neonrp/core/adv.py:prompt_spec`)。

| 字段 | 说明 |
|---|---|
| `entries[] = {id, text, when}` | `when`:`"always"`(进系统提示)、`"post"`(放在系统提示最后)、`{"keyword": [...]}` 或触发器 IF 语法的条件(命中时注入) |
| `voice` / `rules` / `blocks` / `ops_docs` / `examples` | 可选覆盖 |

```json
{ "entries": [
  { "id": "town_attitude", "text": "石津镇对新来的冒险者并不热情,但会记住肯付账和肯守约的人。", "when": "always" },
  { "id": "rowan_legend", "text": "碧石镇有个年轻冒险者罗文…", "when": { "keyword": ["罗文", "碧石"] } } ] }
```

**`engine.json`** — 本世界的回合引擎配置,叠加顺序是内置默认 < pack.loop < 合约的 engine 段 < `game/meta/engine.json` < `.neonrp/playthrough.json["engine"]` < 环境变量(`src/neonrp/core/engine_config.py`)。例:`{"turn": {"mode": "v3"}}`。

**五张表的覆盖层** — `variables.json`、`classes.json`、`entries.json`、`actions.json`、`triggers.json`,形状是 `{id: spec}`。读取方 `src/neonrp/core/registry.py:_apply_overlays` / `_load_triggers`。请用 `neonrp schema register` 写入,它会先校验再写(`registry.py:register`)。`actions.json` 里某个 op 写成 `null` 就是禁用这个 op。

**玩家的 `/` 行动** — 同一份 `actions.json` 的 `actions` 列表:`[{name, help, args_hint, prompt, label?, common?}]`(`name` 用字母 / 数字 / 连字符;`prompt` 里的 `{args}` 换成命令后面的字)。TUI 把它们做成 `/` 命令,网页前端从 `GET /api/v1/play/engine/actions` 拿来做补全和快捷条;玩家直接发「/go 3车」引擎也会展开成 prompt 那句话(`src/neonrp/core/play_menu.py`、`player_action.py:prepare`)。`common: true` 标常用的(上快捷条);一条都没标 → 按写的顺序前 4 条算常用。`label` 是界面上显示的名字(字符串,或 `{zh, en, ja, ko}`;缺省时常用动词 go / talk / look / search … 由引擎给本局语言的名字,其余 = `name`)。本地化层 `i18n/<lang>/` 照常覆盖 `help` / `prompt` / `label`。

**枚举的显示词(`game/meta/labels.json`,10-15)** — `{"mood": {"yearning": {"zh": "思念", …}}, "disposition": {…}, "role": {"gate-guard": {…}}}`:角色心情、关系、NPC 身份这些英文键给玩家看的词(本地化层照常覆盖;值也可以直接是本局语言的字符串)。没写:英文局把键拆成词,其它语言局不显示。读取方 `src/neonrp/core/labels.py`。

**技能 / 属性的名字和说明** — 玩家卡(`player/stats.json`)的 `attributes` / `skills` 键不本地化;显示名和一句说明来自规则包的规则表(rpg 系:`rules.json` 的 `attrs` / `skills` 行 `{zh, en, ja, ko, desc: {zh, en, …}}`),世界在 `game/rules/rules.json` 里加行或覆盖(按键深合并)。世界自己加的技能(如「定力」)要有说明就在这里写 `desc`。前端读 `GET /api/v1/play/engine/sheet`(`src/neonrp/core/sheet.py`)。

**`roster.json`** — 演员表。引擎代码不解析;它被明确排除在 soul 的可读范围之外,只给 world-agent 看(`soul_agent.py`)。

**`schedule.json`、`flag_aliases.json`** — **约定**:引擎代码不解析,子 agent 按提示词读取。

### 3.9 通用类文件夹(任意 pack) · 已实装

在 `game/meta/classes.json` 里登记一个类并给出 `folder`,引擎就会把该文件夹里每个 JSON 加载成一条该类的条目,不用写代码(`registry.py:_load_class_folders`)。条目文件形状:`{id, parent, links, props, aliases, rels}`。`folder` 写成 `game/player/inventory.json#items` 时,表示一个文件里的列表,每项一条条目(`_load_list_store`)。

```json
{ "quest": { "folder": "game/quests", "required": ["name"], "scope": "town",
             "render": "- {id} {name} 阶段{stage}",
             "props": { "stage": { "type": "int", "min": 0, "max": 5 } }, "mutable": ["stage"] } }
```

### 3.10 `game/secrets/` — 秘密覆盖层 · 已实装

一个文件对应一个宿主条目。读取方 `src/neonrp/core/secrets.py:load_secrets`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `about` | str | 宿主条目在 `game/` 下的相对路径,不带扩展名,例如 `location/cafe-basement`,对应的文件必须存在 |
| `audience` | list[str] | `gm` / `player` / `npc:<id>` / `soul:<sid>` / `agent:<id>` |
| `content` | object | 揭示时并回宿主条目(`summary_hidden` → `summary` 等) |
| `revealed_when` | list | 机器可判条件;带 `judgment` 的是交给模型判定的模糊条件 |

格式不对的秘密按"仅 GM 可见、永远不揭示"处理,不会让游戏崩溃。

### 3.11 `game/player/` — 玩家起始状态 · 已实装

玩家不是 soul;这个文件夹由玩家自己拥有。读取方 `loaders.py:_load_player`、`_load_variables`、`src/neonrp/core/player_controller.py`。

| 文件 | 读取的键 → 变量 |
|---|---|
| `profile.json` | `name`(或 `display_name`)、`class`、`background`、`summary`、`origin` |
| `stats.json` | `level`、`hp: {current, max}` → `player.hp`、`mp`、`attributes`、`skills[]` |
| `wallet.json` | `gold` / `silver` / `copper` → `player.gold` 等 |
| `equipment.json` | `weapon`、`armor`、`accessories` |
| `inventory.json` | `items[] = {id, name, qty}`(rpg 的 `carry` 类) |
| `flags.json` | `story_flags` → `flag.*`;`reputation` → `reputation.*` |
| `controller.json` | 玩家操控策略(`player_controller.py`) |
| `journal.md` | 玩家 agent 的日志 |
| `assets/portrait.*` | 头像 |

全部可选:缺失时玩家名为 `player`,对应的变量不注册。

### 3.12 开场 `game/meta/game-start.json` · 已实装

读取方:`src/neonrp/core/opening.py:authored_opening`、`is_start_cue`,`src/neonrp/core/output_lang.py:pick_opening`,`src/neonrp/core/player_controller.py`(开局的场景包),`src/neonrp/core/runtime_contract.py:get_startup_entry_agent`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` / `kind` / `name` | str | 建议写 `game-start` / `meta` / 任意名字,这样实体检查不会警告 |
| `tags` | list[str] | 玩家输入**正好等于**其中某个标签(长度 ≥ 2)时也算开局指令 |
| `startup.opening_scene` | str 或 `{zh,en,ja,ko}` | 开场旁白 |
| `startup.opening_choices` | list[str] / `{lang: [...]}` / `[{lang: text}]` | 第一组选项,最多显示 4 个,编号 ①②③④ |
| `startup.read_first` | list[str] | **约定**:给 world-agent 的提示,列出开局先读的文件 |
| `agent_routing.entry_agent` | str | 入口(路由)agent;启动时会被修正为真实存在的路由 agent |
| `agent_routing.router_type` | str | 只实现了 `sticky` |
| `world_info` | object | **约定**:给 agent 看的世界简介 |

开场怎么发生:

1. 新开一局时,启动器自动发出开局指令(TUI 按本局语言发出 `开始游戏` / `Start the game` / `ゲーム開始` / `게임 시작`,`src/neonrp/commands/tui.py`)。
2. `is_start_cue` 认出开局指令(内置一组多语言写法,或命中 `tags`)。
3. 如果这一局还没有任何回合,而且世界写了 `opening_scene`,引擎的开场节点(`src/neonrp/core/opening.py`)直接把 `opening_scene` 加上选项作为主持人的第一拍输出,**不调用模型**,之后再发开局指令就当普通的一句话。这条路径在多角色(soul 队伍)回合里运行。
4. 其他情况(世界里没有 soul,或没写 `opening_scene`):开场作为场景包的一部分交给入口 agent,由模型以它为基础叙述开场(会调用模型)。

语言:按 `prompt_lang` 选,缺失时回落顺序是 本局语言 → en → zh → 任意一种。世界语言依次取自:根目录 `manifest.json` 的 `lang` → `playthrough.json` 的 `lang` → 文件夹名后缀(`-en` / `-ja` / `-ko` / `-zh`)→ `game/lore/*.md` 的文字(汉字少于 20 个判为 en)(`src/neonrp/core/adv.py:world_lang_raw`)。

```json
{
  "id": "game-start", "kind": "meta", "name": "Stoneford Elena — 游戏开始引导",
  "tags": ["entrypoint", "start", "开始游戏", "开始冒险"],
  "startup": {
    "opening_scene": { "zh": "黎明前的雾像湿布一样压在驿路上……", "en": "The pre-dawn fog presses down on the post road…" },
    "opening_choices": { "zh": ["自由行动", "和守门人说话", "直接走向镇中央", "先观察雾中的街道和旅店灯光"],
                         "en": ["Act freely", "Speak with the gatekeeper", "Head straight for the town center", "First take in the fog-bound streets"] }
  },
  "agent_routing": { "entry_agent": "world-agent", "router_type": "sticky" }
}
```

### 3.13 世界自己的 agent · 已实装

| 路径 | 读取方 | 说明 |
|---|---|---|
| `agents/<id>/agent.json` | `src/neonrp/core/dispatcher.py:AgentSpec.from_json`、`src/neonrp/core/conversation.py` | 运行时真正加载的 agent 定义 |
| `agents/<id>/system.md` | 同上(`system_prompt` 指向的文件) | 系统提示 |
| `agents/world-agent/voice.md` | `src/neonrp/packs/rpg/contract.py:_voice`(前 1500 字) | v3 回合的叙述口吻;`narrative.md` 在 v3 中不使用 |
| `game/agents/manifest.json` | 新局创建时作为 `playthrough.json` 的 `world_agent_team.seeded_from` | 世界 agent 阵容的模板;运行中以 playthrough 为准 |
| `game/agents/contracts/*.md` | **约定** | 给 agent 读的 IO 契约说明 |
| `.claude/agents/*.md` | 引擎运行时不读 | 给外部编码助手用 |

`agent.json` 的字段:

| 字段 | 类型 | 缺省 | 说明 |
|---|---|---|---|
| `id` | str | — | 必须等于文件夹名 |
| `name` / `description` / `version` | str | — | |
| `system_prompt` | str | `system.md` | 相对 agent 文件夹 |
| `triggers` | list[regex] | `[]` | 分派时匹配玩家输入 |
| `tags` / `priority` | list / int | `[]` / 0 | 分派排序 |
| `context_limit` | int | 20 | |
| `permissions.{read_globs, write_globs, deny_globs, direct_write_globs}` | list[glob] | — | 文件权限,deny 优先 |
| `defaults` / `llm` | object | — | 温度等;`llm` 可以给这个 agent 单独指定模型 |
| `presentation_roles` / `presentation_hidden` | object / bool | — | 界面上的称呼 |

路由 agent:按 `narrator` → `orchestrator` → `world-agent` 的顺序找第一个存在的。一个都没有时,`ensure_playable_world` 在每次开玩前补救:只有一个 agent 就把它改名为 `world-agent`,一个都没有就写一个最小的 `agents/world-agent/`,然后写 `.neonrp/runtime_contract.json` 并修正 `game-start.json` 的 `entry_agent`(`src/neonrp/core/runtime_contract.py:ensure_playable_world`)。

```json
{ "id": "world-agent", "name": "World Agent", "system_prompt": "system.md",
  "context_limit": 30, "triggers": [".*"], "priority": 100,
  "permissions": { "read_globs": ["game/**", ".neonrp/**"],
                   "write_globs": ["game/meta/run_state.json", "game/lore/**", "game/player/*.json"],
                   "deny_globs": [] } }
```

### 3.14 根目录 `manifest.json` · 已实装

注意和 `.neonrp/manifest.json`(引擎的项目清单)不是同一个文件。

| 字段 | 读取方 | 说明 |
|---|---|---|
| `lang`(或 `language` / `source_lang`) | `adv.py:world_lang_raw` | 世界语言 `zh` / `en` / `ja` / `ko` |
| `template` | `src/neonrp/packs/__init__.py:resolve` | 使用哪个 pack,优先级高于 `playthrough.json`;缺省 `rpg`(属于 template 层,见 [template.md](./template.zh.md)) |
| `prompt` | `adv.py:prompt_spec` | 和 `game/meta/prompt.json` 同形,优先级更低 |
| `triggers` | `registry.py:_load_triggers` | 和 `game/meta/triggers.json` 同形,优先级更低 |

### 3.15 `assets/` — 图片 · 已实装

| 路径 | 读取方 | 说明 |
|---|---|---|
| `assets/maps/<层级>.webp` | `worldmap.py:map_image_path` | 层级图;层级是 `world`、`T001`、`D001` 这类地址,`/` 换成 `__` |
| `assets/maps/<层级>.json` | `worldmap.py:level_fit`、`map_status` | 出图时冻结的坐标变换 `fit {px, py, x0, y0, sx, sy}`,加上 `layout_hash`;布局变了就标记 `stale` |
| `assets/maps/<层级>.guide.png` | `worldmap.py:draw_guide` | 给出图模型用的布局引导图 |
| `assets/places/<镇>__<节点>.{webp,png,jpg,jpeg}` | `worldmap.py:scene_image_path` | 地点场景图,例如 `T001__inn.webp` |
| `assets/art-style.md` | `worldmap.py:art_style` | 出图风格提示 |
| `assets/cover.png` | 启动器 / 网页端 | 世界封面 |

图片全部可选,没有图也能玩。用 `neonrp map generate` / `neonrp map scene` 生成(需要配置出图后端)。

### 3.16 设计中

| 路径 | 现状 |
|---|---|
| `game/world/regions.json` | 旧文档和 agent 权限里出现过,引擎代码不读 |
| `game/world/factions.json`、`game/world/economy.json` | 只有在 pack 组合了 `factions` / `economy` mixin 时才读(`src/neonrp/packs/mixins/`);默认的 rpg pack 不读 |

---

## 4. 最小可用世界

**结论:** `neonrp validate` 对空文件夹也会通过(判为 `build` 状态,没有任何检查对象)。真正能被 rpg pack 玩起来的最小世界是下面 5 个文件,路由 agent 可以不写(开玩时自动补)。

```
mini/
├── manifest.json                    {"lang": "zh"}   (可选,但小世界没有 lore 时语言会被判成 en)
└── game/
    ├── world/world_map.json
    ├── towns/T001/town.json
    ├── towns/T001/town_map.json
    └── meta/
        ├── run_state.json
        └── game-start.json
```

```json
// game/world/world_map.json
{ "world_id": "W001", "name": "灰岸",
  "nodes": [ { "id": "T001", "type": "town", "name": "渡口镇", "pos": [0, 0], "links": [] } ] }
```
```json
// game/towns/T001/town.json
{ "name": "渡口镇", "overview": "河边的小镇,雾很重。" }
```
```json
// game/towns/T001/town_map.json
{ "town_id": "T001", "nodes": [
  { "id": "gate",   "name": "镇门", "type": "gate",     "pos": { "x": 0,   "y": 0 },  "links": ["square"] },
  { "id": "square", "name": "广场", "type": "street",   "pos": { "x": 100, "y": 60 }, "links": ["gate", "inn"] },
  { "id": "inn",    "name": "旅店", "type": "facility", "pos": { "x": 200, "y": 40 }, "links": ["square"] } ] }
```
```json
// game/meta/run_state.json
{ "location": { "node_id": "T001", "subnode_id": "gate" }, "time": { "day": 1, "clock": "08:00" }, "turn_count": 0 }
```
```json
// game/meta/game-start.json
{ "id": "game-start", "kind": "meta", "name": "开场",
  "startup": {
    "opening_scene":   { "zh": "雾从河面漫上来,你站在渡口镇的镇门下。", "en": "Fog rolls off the river; you stand under the gate of the ferry town." },
    "opening_choices": { "zh": ["进镇", "先看看四周"], "en": ["Walk in", "Look around first"] } },
  "agent_routing": { "entry_agent": "world-agent", "router_type": "sticky" } }
```

实测结果(在临时目录里搭的这个世界):

| 检查 | 结果 |
|---|---|
| `neonrp validate`(没有 `agents/`) | `✓ playable — build · 3 location(s)`,只检查 JSON 和实体,不检查开场 |
| 补上路由 agent 后(`ensure_playable_world` 写入 `agents/world-agent/` 和 `.neonrp/runtime_contract.json`) | `✓ playable — orchestrator · 3 location(s) · router 'world-agent'`,0 个阻断项 |
| `neonrp schema list entries` | 6 条:`W001` world、`T001` town、`T001/gate` / `T001/square` / `T001/inn` place、`player`(位于 `T001/gate`) |
| `neonrp map status` | `world`、`T001` 两个层级,图片都是 missing(正常) |
| `authored_opening` | 加了 `manifest.json {"lang":"zh"}` 时输出中文开场 + `① 进镇 / ② 先看看四周`;不加时输出英文 |
| `neonrp play "开始游戏"`(另外放入一个 soul,使用不调用真实模型的 stub 模型) | 原样输出开场旁白和选项,没有调用模型;不放 soul 时,同一指令交给了模型 |

警告:这个最小世界会有约 11 条 `structure` 警告,见 §6 的第一条,属于正常现象。

想要角色:在世界里放 soul(见 [soul.md](./soul.zh.md)),或者用 `neonrp cast <soul>` 投放。

---

## 5. 校验

```
neonrp validate          # 人读
neonrp validate --json   # {ok, playable, flavor, blockers[], warnings[], stats}
```

退出码:`0` 可玩(允许有警告)· `1` 有阻断项 · `2` 系统错误。实现在 `src/neonrp/commands/validate.py` → `src/neonrp/core/validation.py:check_world`,按层检查:

| 层 | 检查内容 | 严重度 |
|---|---|---|
| 1 json | `game/**`、`souls/**`、`agents/**`、`.neonrp/*.json` 都能解析 | 阻断 |
| 2 playthrough | `.neonrp/playthrough.json` 符合 schema(属于 template / soul 层) | 阻断 |
| 3 scaffold | 路由 agent 存在;`active-agent.json` 指向真实 agent | 警告(开玩时自动修) |
| 4 souls | 被演员表引用的 soul 文件夹存在且完整 | 文件夹缺失 = 阻断,文件不全 = 警告 |
| 5 references | soul 的位置能在镇内地图里找到;所有节点都能从门走到;在世界地图上的镇有门 | 警告 |
| 5c secrets | 秘密文件格式正确,宿主条目存在 | 警告 |
| 6 opening | 有 `game-start.json`(`build` 状态下跳过) | 警告 |
| 7 structure / constraint | `game/` 下的 JSON 按实体 schema 检查(必须有 `id` / `kind` / `name`,`kind` 等于 `game/` 下的第一层文件夹名,`id` 等于文件名) | 警告;**重复 id = 阻断** |

其他检查工具:

| 命令 | 用途 |
|---|---|
| `neonrp map status [--world DIR]` | 列出各地图层级、地点数、图片是否 missing / stale,以及地图树问题(`orphan` / `missing` / `conflict` / `unresolved` / `coarse`) |
| `neonrp schema list [variables\|classes\|actions\|triggers\|entries] [--class C] [--json]` | 看引擎实际读出来的注册表 |
| `neonrp schema register` / `unregister` | 往 `game/meta/<表>.json` 写覆盖层(先校验) |

---

## 6. 常见错误

以下信息都是 validator 或地图树实际输出的文字(用临时世界复现过)。

| 信息 | 原因 | 怎么修 |
|---|---|---|
| `game/meta/run_state.json: 'id' is a required property`(同类还有 `world_map.json`、`town_map.json`、`town.json`、`player/*.json`、`facilities/*.json`) | 第 7 层的实体 schema 会检查 `game/` 下**每一个** JSON,而这些文件本来就不是实体。内置世界也有这类警告(stoneford-elena 有 116 条) | 可以忽略,不影响能不能玩 |
| `… is not of type 'string'`(`run_state.json` 的 `location`) | 实体 schema 的 `location` 是字符串,而 `run_state` 用的是对象 | 可以忽略 |
| `Invalid JSON: Expecting ',' delimiter (line 2, column 1)` | JSON 语法错;运行时会悄悄跳过这个文件,内容丢失 | **阻断**,修语法 |
| `Duplicate id 'lamp' also appears in game/item/lamp.json` | 两个实体文件 id 相同 | **阻断**,改成唯一 id |
| `kind 'location' does not match path segment 'locations'` | `kind` 必须等于 `game/` 下的第一层文件夹名。内置世界的 `game/locations/*.json` 也有这条警告 | 改 `kind`,或换文件夹(加载器两种都认) |
| `id 'wrongname' does not match filename 'a'` | 实体 id 必须等于文件名 | 改 id 或文件名 |
| `Town 'T001' has nodes unreachable from any gate: cellar` | 节点没有被 links 接到门上:角色可以被放在那里,但走不过去 | 补 `links` |
| `Town 'T002' is on the world map but has no gate node — travel in/out can't be staged` | 世界地图上的镇没有门 | 加一个 `"type": "gate"` 的节点 |
| `Soul '<sid>' is at '<loc>', which no game/towns/*/town_map.json defines` | soul 的 `run_state.location` 指向不存在的节点 | 改成 `T001/<节点>` |
| `unknown audience token(s) ['friend']` | 秘密的 audience 只能是 `gm` / `player` / `npc:` / `soul:` / `agent:` | 改 audience |
| `Secret 's1' is about 'item/ghost', which has no entity file` | `about` 指向的 `game/<kind>/<id>.json` 不存在 | 指向已有条目 |
| `No game-start file — the world opens without an authored opening scene` | 没有 `game/meta/game-start.json` | 按 §3.12 写一个 |
| `Router agent '<id>' has no agents/<id>/agent.json` | 没有路由 agent | 开玩时自动补;也可以自己写 |
| `active-agent.json: active_agent '<id>' has no corresponding agent directory at …` | 路由状态指向不存在的 agent | 开玩一次即可重置 |
| 地图:`! orphan: towns/T009 不在 world_map.nodes 里` | 有镇文件夹,但世界地图上没有这个节点(这个镇不会出现在地图树里) | 在 `world_map.json` 里加节点 |
| 地图:`<地址> 指向的 facilities/x.json 不存在` | `facility_file` 写错 | 修正路径 |
| 地图:`locations/x.json「…」在层级地图里找不到对应节点` | 扁平地点没有匹配到镇内节点 | 让 id 或 `镇名·地点名` 对得上 |
| (不报错)小世界的开场变成英文 | 没有 lore,也没写 `lang` | 根目录 `manifest.json` 写 `{"lang": "zh"}` |
| (不报错)镇 id 写成 `town1` 后地址解析错乱 | 镇 id 必须匹配 `^[A-Z]{1,3}\d{2,4}$` | 用 `T001` 这类 id |

---

## 7. 参考实现位置

| 主题 | 位置 |
|---|---|
| 注册表(五张表,读时归一) | `src/neonrp/core/registry.py:load_registry`、`_apply_overlays`、`_load_class_folders`、`register`、`check_envelope` |
| rpg pack 的世界加载器 | `src/neonrp/packs/rpg/loaders.py:load`、`_load_world`、`_load_towns`、`_load_locations`、`_load_dungeons`、`_load_quests`、`_load_player`、`_load_npcs`、`_load_items`、`_load_variables` |
| rpg 的内置类 | `src/neonrp/packs/rpg/pack.py:CLASSES`(world / town / place / region / player / soul / npc / item / job / dungeon / road / room / carry / status) |
| 选用哪个 pack | `src/neonrp/packs/__init__.py:resolve` |
| 地图树、出图、热点 | `src/neonrp/core/worldmap.py:build_map_tree`、`map_levels`、`hotspots`、`map_status`、`generate_map` |
| 地址与移动 | `src/neonrp/core/place_nav.py:qualify_location`、`split_location`、`_gate_of`、`load_world_map`、`_world_route` |
| 校验 | `src/neonrp/commands/validate.py`、`src/neonrp/core/validation.py:check_world`、`validate_game_data`;实体 schema `src/neonrp/schema/game_entity.schema.json`(可用 `rules/game_entity.schema.json` 覆盖) |
| 开场 | `src/neonrp/core/opening.py:authored_opening`、`is_start_cue`、`start_cue`;`src/neonrp/core/output_lang.py:pick_opening` |
| 路由 agent 补救 | `src/neonrp/core/runtime_contract.py:ensure_playable_world`、`load_runtime_contract`、`get_startup_entry_agent` |
| 秘密 | `src/neonrp/core/secrets.py:load_secrets` |
| 提示词条目 / 世界语言 | `src/neonrp/core/adv.py:prompt_spec`、`entries_for`、`world_lang_raw` |
| 回合引擎配置 | `src/neonrp/core/engine_config.py` |
| 参考世界 | `src/neonrp/templates/stoneford-elena`(完整)、`src/neonrp/templates/white-blank`(空白骨架) |
