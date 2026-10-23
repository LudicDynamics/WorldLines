# Soul 规范(角色文件夹)

> 适用于 NeonRP 引擎当前实现。最小可运行单元 = **pack**(引擎规则)+ **world**(数据)+ **souls**(数据);**template** 可选地把三者绑在一起。本文只讲 souls。world 见 [world.zh.md](world.zh.md),template 见 [template.zh.md](template.zh.md)。
>
> 状态标记:**已实装** = 代码里有、今天就生效;**设计中** = 字段/位置已预留或已声明,但引擎尚未完整使用。

---

## 1. 是什么

一个 **soul** 是一个角色的自包含文件夹:身份、人格、行为规则、记忆、运行状态、立绘,以及"这个角色作为一个 agent 能写什么"的清单。

- soul 与世界无关,可以复用:同一个 soul 可以被放进(cast)不同的世界。
- 进入世界后,每个 soul 实例是**一个独立的 agent**(1 soul = 1 agent)。它只读写自己的文件夹,对世界只读。
- 世界(叙事者 / world-agent)**不能**改写 soul 的状态和日记;那些只由 soul 自己的回包或引擎的 soul 结算写入(见 §5)。

soul 存在两个地方:

| 位置 | 路径 | 用途 | 状态 |
|---|---|---|---|
| 世界内(实例) | `<world>/souls/<sid>-<instance_id>/` | 正在某个世界里"活着"的那份拷贝,运行时状态写在这里 | 已实装 |
| 角色库 | `~/.worldlines/souls/<sid>/` 或 `~/.worldlines/souls/<sid>-<时间戳>/` | 与世界无关的原件,可被 cast 进任意世界 | 已实装 |

---

## 2. 目录结构

以内置世界 `stoneford-elena` 中的艾琳娜为例(`souls/elena-si-elena0001/`):

```
elena-si-elena0001/
├── soul.json                 # 身份信封(必需)
├── soul.md                   # 角色宪章:声音、驱动力、压力模式、盲点
├── run_state.json            # 运行时状态:位置、hp、mood、trust、intention
├── agents/
│   ├── manifest.json         # agent 清单:写权限 write_globs
│   ├── contracts.md          # 契约说明(给人看)
│   └── soul-agent/system.md  # (可选)覆盖引擎默认的 soul 系统提示
├── persona/                  # 人格内核(创作后不可变)
│   ├── core_traits.json
│   ├── motivations.json
│   ├── values.json
│   └── relationships.json
├── background/               # 出身/经历/秘密(创作后不可变)
│   ├── origin.md
│   ├── history.md
│   └── secrets.md
├── rules/                    # 行为规则(创作后不可变)
│   ├── action_rules.md
│   ├── decision_rules.md
│   └── interaction_rules.md
├── character/                # RPG 身体:档案、属性、装备、背包、钱包、状态
│   ├── profile.json
│   ├── stats.json
│   ├── status.json
│   ├── equipment.json
│   ├── inventory.json
│   └── wallet.json
├── short-term-memo/          # 短期记忆(运行时写)
│   ├── current_context.json
│   ├── conversation_cache.json
│   ├── recent_events.json
│   └── perceived.json        # 运行时由引擎生成:她视角下的每拍叙事
├── long-term-memo/           # 长期记忆(种子由作者写,运行时追加)
│   ├── important_events.md
│   ├── learned_facts.json
│   └── emotional_memories.json
├── trajectory/
│   └── action_log.md         # 行动轨迹(append-only)
└── assets/
    ├── portrait.png          # 立绘
    └── sprite.webp           # (可选)小人图
```

引擎新建 soul 时生成的骨架子目录是:`agents persona background character rules short-term-memo long-term-memo trajectory .commits`(`src/neonrp/core/souls.py:SOUL_SUBFOLDERS`),外加 `assets/`。所有子目录都是**可选**的——缺了会降级而不是崩溃(见 §7)。

---

## 3. 文件逐个说明

"谁写"一列:**作者** = 创作时写好;**soul** = 运行时 soul 自己的 agent 在写权限内写;**引擎** = 引擎代码确定性地写。

### 3.1 根文件

| 路径 | 必需 | 谁写 | 关键字段 | 读取方 | 状态 |
|---|---|---|---|---|---|
| `soul.json` | **必需**(`sid`、`name`) | 作者 | 见下表 | 身份、显示名、cast、soul 后端选择 | 已实装 |
| `soul.md` | 推荐 | 作者 | Markdown;`## Core Presence`、`## Voice And Social Posture` 段会被抽取为摘要/语气 | 注入 soul 系统提示(前 ~900 字进入场景登记) | 已实装 |
| `run_state.json` | 推荐 | 作者给初值;运行时引擎写 | 见 §3.2 | 位置、mood、hp、trust、intention | 已实装 |

**`soul.json` 字段**

| 字段 | 类型 | 必需 | 说明 | 状态 |
|---|---|---|---|---|
| `sid` | string | 是 | 角色 id,跨世界稳定(如 `elena`) | 已实装 |
| `name` | string | 是 | 主名(如 `Elena Vale`) | 已实装 |
| `name_local` | string | 否 | 本地语言名(如 `艾琳娜`);场景里优先用它称呼 | 已实装 |
| `schema_version` | int | 否 | 当前为 `1` | 已实装 |
| `version` | string | 否 | 作者版本,默认 `"1.0"`;cast 时写进 playthrough 的 `version_hash` | 已实装 |
| `created_at` | string | 否 | ISO 时间 | 已实装 |
| `source` | object | 否 | `{kind: soulhub\|builtin\|local-create, hash, version}` 来源 | 已实装 |
| `agent_template` | string | 否 | 创作口味标记(如 `heroine-classic`);不改变运行时阵容 | 已实装 |
| `tags` | string[] | 否 | 标签;`pc`/`player` 等在投影成 NPC 时被丢弃 | 已实装 |
| `source_lang`、`name_i18n`、`summary_i18n`、`voice_i18n` | string / `{en,zh,ja,ko}` | 否 | 多语言展示 | 已实装 |
| `standalone` | bool | 否 | 作者同意这个角色离开世界:不用先获得就能单独聊、单独发布;聊过只记进玩家数据的 `talked`,**不算获得**(获得只走 `takeable` + `take_when`)。模板列表 `standalone`、`/api/v1/local/souls` 每行 `standalone` 带出;只认 true / false(lint `soul.standalone`)。主角在 `game/player/profile.json` 同样写 `standalone: true`(列表里记作 `player`) | 已实装(10-15) |
| `takeable` · `take_when` | bool · string | 否 | 能不能被玩家带走(默认 true)、在什么条件下带走(默认 `companion_at_ending` = 走到结局时是同伴;或 `ending:<结局 id>`)。满足就记为获得、带完整记忆(玩家数据 `memory: full`)。模板 meta `take: {sid: 条件 \| null}`、`/api/v1/local/souls` 每行 `takeable` / `take_when`;lint `soul.takeable` / `soul.take_when`(结局 id 要是本世界的) | 已实装(10-15) |
| `intro_i18n` | `{en,zh,ja,ko}` | 否 | 卡片简介(展示层读取) | 已实装(展示用) |
| `backend` | string | 否 | `internal-llm`(默认)/ `stub` / `http`;未知值回退默认 | 已实装 |
| `backend_url`、`backend_timeout_s` | string / number | `backend=http` 时 | 外部 soul 服务地址与超时 | 已实装 |
| 其它后端(如外部前端、真人) | — | — | 同一消息契约后的预留接口 | 设计中 |

艾琳娜的 `soul.json`(节选):

```json
{
  "schema_version": 1,
  "sid": "elena",
  "name": "Elena Vale",
  "name_local": "艾琳娜",
  "version": "1.0",
  "source": { "kind": "builtin", "hash": "stonefordelena001", "version": "1.0" },
  "agent_template": "heroine-classic",
  "tags": ["pc", "heroine", "adventurer", "stoneford"]
}
```

### 3.2 `run_state.json`

| 字段 | 类型 | 谁写 | 说明 | 状态 |
|---|---|---|---|---|
| `sid` | string | 作者/引擎 | 与 `soul.json` 一致 | 已实装 |
| `instance_id` | string | 作者/引擎 | 与文件夹名后缀一致 | 已实装 |
| `location` | string | 作者给初值;运行时只由引擎的 `move` 落地 | 地点 id;裸节点(如 `gate_north`)会按当前镇补全成 `T001/gate_north`。缺失 = 不在任何地点 | 已实装 |
| `status.hp` / `status.max_hp` | int | 作者;soul | 体力 | 已实装 |
| `status.mood` | string | 作者给初值;运行时引擎(soul 结算) | 情绪。结算时取自 `calm warm curious hopeful alert anxious guarded angry hurt sad tired`(或保持原值) | 已实装 |
| `status.trust.player` | int,-10…10 | **只由引擎(soul 结算)写** | 对玩家的信任;每回合变化 -2…+2 | 已实装 |
| `status.intention` | string | **只由引擎(soul 结算)写** | 当前最想推进的目标,取自 `persona/motivations.json` | 已实装 |
| `turn_count` | int | 引擎 | 回合计数 | 已实装 |
| 其它键(如 `loop_state`) | any | 作者 | 开放字段,世界自己的数据 | 已实装(透传) |

艾琳娜的初始值:

```json
{
  "sid": "elena",
  "instance_id": "si-elena0001",
  "location": "gate_north",
  "status": { "hp": 24, "max_hp": 24, "memory": "amnesia", "mood": "alert" },
  "turn_count": 0
}
```

### 3.3 `agents/`

| 路径 | 必需 | 谁写 | 说明 | 状态 |
|---|---|---|---|---|
| `agents/manifest.json` | 推荐(缺失时运行时自动补) | 作者 / 引擎 | `{schema_version, agent_template, agents:[{id, role, write_globs}]}`。`write_globs` 相对 soul 文件夹,决定 soul agent 能写哪里 | 已实装 |
| `agents/contracts.md` | 否 | 作者 / 引擎 | 契约说明,给人读,引擎不解析 | 已实装 |
| `agents/soul-agent/system.md` | 否 | 作者 | 整体替换引擎默认的 soul 系统提示。可用占位符 `{name} {sid} {soul_rel} {role_contract} {charter} {persona}` | 已实装 |

标准清单(所有 soul 统一为单个 agent):

```json
{
  "schema_version": 1,
  "agent_template": "heroine-classic",
  "agents": [
    {
      "id": "soul-agent",
      "role": "soul",
      "write_globs": ["run_state.json", "trajectory/**", "short-term-memo/**", "long-term-memo/**", "character/**"]
    }
  ]
}
```

运行时 soul agent 的权限(`src/neonrp/core/soul_agent.py:resolve_soul_agent_data`):

| 权限 | 范围 |
|---|---|
| 读 | 自己的 `souls/<sid>-<iid>/**`;世界的 `game/meta/run_state.json`、`game/timeline/**`、`game/locations/**` |
| 写 | manifest 里各条 `write_globs` 的并集,定位到自己的文件夹 |
| 禁止 | 自己的 `persona/**`、`background/**`、`rules/**`(创作后不可变);`game/lore/gm-truth.md`、`game/lore/notes.md`、`game/secrets/**`、`.neonrp/**`、`agents/**`;别的 soul 的文件夹(不在允许范围内);玩家的 `game/player/*` |

### 3.4 `persona/`(不可变)

| 文件 | 关键字段 | 读取方 | 状态 |
|---|---|---|---|
| `core_traits.json` | `personality_type`: string;`core_traits`: `[{trait, intensity, description}]` | 系统提示(全文注入);场景登记取前 6 个 `trait` | 已实装 |
| `motivations.json` | `motivations`: string[](也接受 `goals`) | 目标列表(前 6 条);soul 结算从中选 `intention` | 已实装 |
| `values.json` | `values`: string[] | 系统提示(全文注入) | 已实装 |
| `relationships.json` | `relationships`: `{<sid>: {disposition, known, truth, …}}` | 场景登记只带入 `known != false` 的条目 | 已实装 |

`persona/` 下所有 `*.json` 都会原样注入 soul 的系统提示。示例(艾琳娜 `motivations.json`):

```json
{ "sid": "elena", "motivations": ["在石津镇拿到第一份真正像样的契约", "靠自己的本事挣出名声", "弄清灰雾北境究竟藏着什么"] }
```

### 3.5 `background/` 与 `rules/`(不可变)

| 文件 | 内容 | 读取方 | 状态 |
|---|---|---|---|
| `background/origin.md`、`history.md` | 出身、经历 | soul 自己可读;orchestrator 模式下并入 NPC 记录 | 已实装 |
| `background/secrets.md` | 只有 GM 和角色自己知道的事 | 同上;玩家不可见 | 已实装 |
| `rules/decision_rules.md` | 决策规则 | 场景登记取前 ~500 字 | 已实装 |
| `rules/action_rules.md`、`interaction_rules.md` | 行动/互动规则 | soul 自己可读;orchestrator 模式下并入 NPC 记录 | 已实装 |

### 3.6 `character/`

RPG 身体。soul agent 可写(在 `write_globs` 内)。

| 文件 | 关键字段(艾琳娜) | 状态 |
|---|---|---|
| `profile.json` | `sid, display_name, name_local, age, role, tags, appearance{…}, summary` | 已实装 |
| `stats.json` | `hp, max_hp, skills[]` | 已实装 |
| `status.json` | `mood, memory, flags{…}` | 已实装 |
| `equipment.json` | `equipped{weapon, armor, cloak}` | 已实装 |
| `inventory.json` | `items[]` | 已实装 |
| `wallet.json` | `currency` | 已实装 |

注意:`profile.json` 的 `role` 只在没有 playthrough 时作兜底;角色在某个世界里的真实身份以 playthrough 的 `role` 为准(艾琳娜的 profile 写着 `player`,但在 stoneford-elena 里她以 `npc` 身份被放入)。没有 `soul.json` 的文件夹(例如部分 Hub 下载包)会退回用 `profile.json` 的 `sid / display_name / name_local` 识别身份。

### 3.7 记忆与轨迹

| 文件 | 结构 | 谁写 | 状态 |
|---|---|---|---|
| `short-term-memo/recent_events.json` | `{events:[{turn, event, my_reaction, affect, important?, trust_delta?, by}]}`,保留最近 40 条 | 引擎(soul 结算,`by: "engine.settle"`);旧回合引擎下由 soul agent 自己追加 | 已实装 |
| `short-term-memo/perceived.json` | `{beats:[{turn, place, text}]}`,保留最近 30 条 | 引擎:把本回合叙事改写成她视角下看到/听到的内容 | 已实装 |
| `short-term-memo/current_context.json` | `{scene, turn, notes[]}` | 作者给初值;soul | 已实装 |
| `short-term-memo/conversation_cache.json` | `{exchanges[]}` | soul | 已实装 |
| `long-term-memo/important_events.md` | Markdown | 作者种子;soul | 已实装 |
| `long-term-memo/learned_facts.json` | `{facts[]}` | 作者种子;soul | 已实装 |
| `long-term-memo/emotional_memories.json` | `{memories[]}` | 作者种子;soul | 已实装 |
| `trajectory/action_log.md` | append-only,每回合一行 `- [回合] 我做了/想了什么` | soul | 已实装 |
| `.commits/` | soul 自己的版本库 | 引擎 | 设计中(骨架已创建) |

**作者给的初始记忆写成列表**(10-20):`long-term-memo/*.md` 这类作者种子写成顶层列表,一件事一条,按主题用 `## ` 分组;作者给初值的 JSON 记忆,列表元素带 `id`。玩家带走这个角色以后,作者再改 —— 玩家会看到一份 diff 逐条选「留我的 / 用作者的」(顶层列表项、每个 `## ` 段的正文各算一条;JSON 按字段、带 `id` 的列表按 id),写成大段散文就只能整段选。

### 3.8 `assets/`

| 文件 | 说明 | 状态 |
|---|---|---|
| `portrait.*` | 立绘(`.png/.jpg/.webp`);界面中作头像。cast 时随文件夹一起复制 | 已实装 |
| `sprite.*` | 小人图 | 已实装 |
| 发布前必须有立绘的校验 | template 层已声明"soul 需要 portrait",lint 尚未对 soul 强制检查 | 设计中 |

---

## 4. sid 与实例、放进世界

| 概念 | 例子 | 含义 |
|---|---|---|
| `sid` | `elena` | 角色 id。同一角色在所有世界里相同 |
| `instance_id` | `si-elena0001` | 这个角色在**某一个世界**里的这一份拷贝。cast 时自动生成为 `si-<12 位 hex>` |
| 文件夹名 | `elena-si-elena0001` | 固定为 `<sid>-<instance_id>`,引擎靠它定位 soul |
| agent id | `soul:elena:si-elena0001` | 运行时这个 soul 作为 agent 的 id |

同一 `sid` 可以在不同世界(甚至同一世界)有多个实例,各自的记忆和状态互不影响。

### 4.1 playthrough 里的 souls 行

世界通过 `.neonrp/playthrough.json`(模板里放在世界根的 `playthrough.json`)登记它的 soul。每一行的五个字段都**必需**(`src/neonrp/core/playthrough.py:_parse_souls`):

```json
"souls": [
  { "sid": "elena", "instance_id": "si-elena0001", "version_hash": "stonefordelena001",
    "head_commit": "seed-soul-elena-0001", "role": "npc" }
],
"active_souls": ["si-elena0001", "si-rowan0001"]
```

| 字段 | 说明 |
|---|---|
| `sid`、`instance_id` | 指向 `souls/<sid>-<instance_id>/` |
| `version_hash` | 放入时 soul 的版本(cast 时取 `soul.json.version`) |
| `head_commit` | 种子 commit 标记;cast 时为空字符串 |
| `role` | `npc` 或 `player` |
| `active_souls` | 当前在场、会被调度的实例。运行中由引擎的场景理解步骤按回合改写;不在场的 soul 不调用 LLM |

### 4.2 `neonrp cast`

```
neonrp cast <sid|soul 文件夹路径> [--into <世界文件夹>] [--as npc|player] [--location …] [--id …] [--force] [--adapt]
```

- `<sid>`:在角色库 `~/.worldlines/souls/` 里找名字等于 `sid` 或以 `sid-` 开头的文件夹(取最新);`<路径>`:必须是含 `soul.json` 的文件夹。
- 落点取决于世界的 `execution_mode`(读 `.neonrp/runtime_contract.json`):

| 世界模式 | `--as npc` | `--as player` |
|---|---|---|
| `multi-agent` | 整个文件夹复制到 `souls/<sid>-si-<hex>/`,追加 souls 行,并加入 `active_souls` | 在 playthrough 的 `players[]` 里写一个 `pid: "player"` 条目(玩家不是 soul) |
| `orchestrator` | 压平为一个世界 NPC `game/npc/<id>.json`(不建 soul 文件夹、无独立 agent) | 写入 `game/player/profile.json` |

- multi-agent 世界必须已有 playthrough.json,否则拒绝。世界若声明了 NPC 上限,超过时拒绝(`--force` 覆盖)。
- CLI 的 `neonrp cast` 原样复制文件夹,不写位置。创作 agent 的 cast 工具(`src/neonrp/core/skills.py`)在此之外还会:给 soul 写 `run_state.json.location`(指定地点,或默认玩家所在处;`src/neonrp/core/placement.py:seed_soul_location`),并把角色归档一份到角色库(不带 `run_state.json`,因为运行状态属于世界实例)。

### 4.3 template 能改什么

template 可以为某个 soul 提供"提示层覆盖"(`prompts/souls/<sid>/…`),但只允许覆盖 `soul.md`、`persona/`、`rules/`、`agents/`(`src/neonrp/template/__init__.py:SOUL_PROMPT_PATHS`)。`character/`、记忆、`soul.json`、`run_state.json` 属于 soul 数据,template 不能覆盖,lint 会报 `prompt.soul.data` 阻断。详见 [template.zh.md](template.zh.md)。

### 4.4 角色库与 link(10-08)

角色库 `~/.worldlines/souls/<名字>/` 是角色的家,不属于任何世界。一个角色可以 link 进很多模板,一个模板可以 link 很多角色。

| 事 | 怎么做 | 状态 |
|---|---|---|
| 把角色放进一个世界 | 模板的演员表写 `{"lib": "<名字>", "role": "npc"\|"companion"\|"player"}`(template spec 3.6);作者操作 `set_cast` | 已实装 |
| 什么时候实体化 | 开局(模板 build 成一局)时才复制进这一局的 `souls/<sid>-<instance_id>/`;之前模板里只有 link | 已实装 |
| 这个世界里的差异 | 模板的 `prompts/souls/<sid>/`(4.3)和 `world-overlay/`;角色库本体不动 | 已实装 |
| 这个角色在哪些世界里 | `template.bindings_of(<名字>)` · `GET /api/v1/local/souls/<名字>/bindings` | 已实装 |
| 带走 / 带回 | `neonrp template export --soul <名字>`;模板包会带上它 link 的角色(template spec 9.2) | 已实装 |
| 按合约的卡 | `character/sheets/<合约 id>.json`:同一个角色在每种玩法里各一张卡,互不覆盖;缺卡时开局跑转换器生成 | 设计中 |
| 一局结束写回什么 | 只写回合约 `souls.out` 列的东西(记忆、信任、好感);世界发给角色的身份 / 秘密只活在这一局 | 设计中 |
| 主角也走角色库 | 从角色库挑或新建;`role: player` 的 link 开局时接成这一局的主角 | 设计中 |

### 4.5 离开世界:直聊(10-15)

玩家可以在世界外(手机聊天界面)和角色单独聊天。代码在 `src/neonrp/core/soul_chat.py`,路由在 `src/neonrp/webui/launcher_routes.py:_chat_route`;本机和浏览器版用同一套 HTTP。

谁能聊:`standalone: true` 的角色(作者同意它离开世界),或玩家已经获得的角色(玩家数据 `characters`,见 3.1 的 `takeable` / `take_when`)。其余角色是 `locked`。

| 接口 | 返回 | 状态 |
|---|---|---|
| `GET /api/v1/chat/souls?lang=` | `{souls: [{tpl, sid, name, avatar_url, avatar_thumb_url, world, standalone, obtained, talked, memory: full\|trial, last: {from, kind, text?, sticker?, at} \| null}]}`;列 standalone、已获得、聊过的角色;`world` = 来自的世界(模板标题，按 lang);同一角色(sid + 名字相同)在多个模板里只列一次：玩家碰过的那份(获得 / 聊过 / 有记录;获得的就是获得那个世界的);都没碰过就列官方上架世界(模板 `zone: reviewed`)那份，其他变体不列;`avatar_url` = 模板立绘槽 `soul.portrait:<sid>`,`avatar_thumb_url` = 同一张的 256 px 小图(模板图都可加 `&w=<px>`) | 已实装 |
| `GET /api/v1/chat/thread?tpl=&sid=&lang=` | `{soul: {tpl, sid, name, avatar_url, avatar_thumb_url, tagline, world, lang}, access: standalone\|obtained\|locked, memory, messages: [{id, from: me\|soul, kind: text\|sticker, text?, sticker?, at}], stickers: {soul: [{id, label, url}]}}` | 已实装 |
| `POST /api/v1/chat/send` `{tpl, sid, lang?, kind: text\|sticker, text?, sticker?}` | 200 `{messages: [角色回的 1–5 条], usage, ms}`(同步,不走 events);玩家那条也写进记录 | 已实装 |
| `GET /api/v1/chat/sticker?tpl=&sid=&id=` | 角色专属表情图 | 已实装 |

错误码:`403` locked · `404` 没有这个角色 · `409` 这个角色上一句还在回 · `400` 文字 / 表情为空 · `502` 模型出错 `{error, billing?}`(`billing` 与回合的 billing_stop 同结构)。失败的一次发送不留任何记录。

| 事 | 规则 | 状态 |
|---|---|---|
| 角色知道什么 | 自己文件夹里的 `soul.md`、`persona/`、`background/`、`character/profile.json`、`long-term-memo/`、`short-term-memo/`(截 9000 字),加最近 24 条聊天记录 | 已实装 |
| 记忆从哪来 | 已获得:获得那一刻把这一局的角色文件夹快照到 `~/.worldlines/player-data/<player>/souls/<tpl>/<sid>/`(`assets/` 不复制),`memory: full`;没获得:用模板里的文件夹,`memory: trial` | 已实装 |
| 聊天记录 | `~/.worldlines/player-data/<player>/chats/<tpl>__<sid>.jsonl`,属于玩家,不进模板 | 已实装 |
| talked | 第一次和 standalone 角色聊天记进玩家数据 `talked`,**不算获得** | 已实装 |
| 表情 | 内置 `wl:<id>` 共 16 个:hello happy laugh shy love thanks ok think surprised sad cry angry sleepy sorry cheer bye(前端画);角色专属 `soul:<id>` = 文件夹里的 `stickers/<id>.png`,含义写在 `stickers/stickers.json`(`{<id>: {label: {zh, en, ja, ko}, when}}`:面板按聊天语言显示 label,模型看到 label + 什么时候发);从来源读(模板 / 角色库,已获得的角色之后加的表情也有),来源没有才读快照。角色单独一行写 `[sticker <id>]` 就是发表情,不认识的 id 丢掉;`[~image …]` / `[image …]` 行(生图,只留接口)直接丢掉、不当文字显示。编排台读写:`GET /api/v1/souls/stickers?ref=` · `POST /api/v1/souls/stickers?ref=&id=`(PNG ≤ 2 MB)· `/stickers/meta {ref, id, label, when}` · `/stickers/remove {ref, id}`(Local;内置模板只读) | 已实装 |
| 模型与计费 | 有正在玩的局就用这局的 provider,否则用玩家默认的 provider;每条消息一次调用,和回合一样计费;提示词四语 `prompts/soul_chat.<lang>.json` | 已实装 |
| 工具(生图等) | 由编排图的 chat 节点 `tools` 决定:`sticker` 已实装;`image.generate`(`[~image …]` 异步)、`image.crop`、`memo.write` 只留接口(lint 报 `orch.tool_off`) | 部分已实装(10-16) |
| 三类角色(10-16) | `tpl` + `sid`,或一个 `ref`:`lib:<文件夹>` = 角色库里的角色(玩家自己的,直接能聊,`access: library`,记忆就是那个文件夹;聊天记录 `chats/lib__<文件夹>__<sid>.jsonl`)· `tpl:<模板>/<sid>` = 世界里的角色;`/chat/souls` 在世界角色之后列出角色库的角色(`library: true`)。同一个角色先试聊、后来获得,聊天记录是同一条 | 已实装 |

### 4.6 角色自己的编排图(10-16)

角色编排台(只在 Local)编辑的图。格式同世界的 `worldlines.orchestration/1`,加 `subject: "soul"`。代码 `src/neonrp/core/soul_orchestration.py`。

| 事 | 规则 | 状态 |
|---|---|---|
| 节点种类 | `chat`(一条消息进来,回 1–5 条;参数 `history` · `docs` · `doc_cap` · `max_bubbles` · `tools`)· `tick`(自由行动;参数 `interval_min` 1–1440 · `daily_max` 1–288 · `proactive_daily` 0–20 · `prompt`,空 = 引擎默认)· `reflect`(记忆整理;参数 `every` 0–100,0 = 关,缺省 0 · `keep` 1–40)· `in_world`(世界的回合调它那一拍:不是这张图的节点,编排台显示它在世界里的真实设置,见下)。每种节点的真实步骤 / 参数 / 范围 = `describe()`(`GET /api/v1/souls/orchestration` 的 `hooks`),编排台照着画 | 已实装 |
| 边 | `{id, from, to, on, when?}`;`on`:`{chat: "message"}` · `{tick: <名>}`(前台时钟,每 `interval_min` 一次)· `{idle: <分钟>}`(只有 idle 边时:小手机开着、玩家这么久没发消息 → tick 一次,一段安静只一次,玩家再发消息算新的一段)。`always` 没人读,不再列出 | 已实装 |
| 记忆整理(reflect) | 图里有 reflect 节点且 `every` ≥ 1:每 `every` 次 tick 之后一次便宜模型调用(≤ 400 token),读 `short-term-memo/recent_events.json` + 已有的 `long-term-memo/reflections.md`,回 `{"keep": [≤ 5 句]}` → 追加进 `reflections.md`,短期只留最后 `keep` 条;模型失败什么都不动,下次 tick 再试 | 已实装 |
| 世界里那一拍(in_world) | 角色在它世界里的真实设置:回合模式 · 变体(`turn.parallel.souls.per_soul[sid]`,没设用 `default_variant`;不是 v3 一律 legacy)和哪一层定的 · 按 depth 分流(silent 跳过 · gesture 无模型 · speak / act 走变体 · away 一律 S-direct)· 用到的提示词名(私有层替换了的只标出名字,不给正文)。角色库角色按绑定它的世界(`?world=`,缺省第一个)。变体写回 `POST /api/v1/souls/in_world {ref, variant, world?}` → 作者操作 `set_engine_setting`(写模板 `template.json` 的 `pack.engine`,build 时并进 `game/meta/engine.json`;内置模板只读)。一回合跑完 trace 的 `timing.soul_variants` 记每个角色实际用的变体 | 已实装 |
| 自由行动(tick) | `src/neonrp/core/soul_tick.py`。只 tick 玩家自己的角色(角色库的 / 已获得的),图里要有 tick 节点,**玩家开关默认关**(花额度);没有后台:小手机在前台时每分钟问一次 `POST /api/v1/chat/tick {ref, catchup?}`,引擎管节奏(按 tick 节点的 `interval_min` · `daily_max`,缺省 10 分钟一次 · 每天 24 次);打开对话补一次。一次 = 一次模型调用(自己的文档 + 简单世界观里这个时段的作息 + 最近几条对话 + 最近做过的事)→ 写 `trajectory/action_log.md` 一行 + `short-term-memo/recent_events.json` 一条(`by: soul.tick`);每天最多 `proactive_daily`(缺省 2)条主动消息进对话(`origin: tick`)。`GET /api/v1/chat/tick?ref=` 状态 · `POST /api/v1/chat/tick/settings {ref, on}` | 已实装 |
| 简单世界观 | `ambient/world.json`(`worldlines.soul-ambient/1`:setting · places ≤ 6 · routine 早上 / 下午 / 傍晚 / 夜里 · people ≤ 4 · clock real)。世界里的角色没有就从原来的世界复刻(卡面简介 · 它所在的镇 · 周围地点 · persona 里认识的人;不读 GM 真相 / notes / secrets);角色库的角色要自动生成(一次模型调用)或自己写。模板覆盖 `prompts/souls/<sid>/ambient/world.json`(作者操作 `set_soul_ambient`)。接口 `GET /api/v1/souls/ambient?ref=[&replicate=1]` · `POST /api/v1/souls/ambient {ref, world}` · `POST /api/v1/souls/ambient/generate {ref}`(Local) | 已实装 |
| 从哪来(后者盖前者) | 引擎默认图(= 10-15 的小手机行为)→ 角色文件夹 `agents/orchestration.json` → 模板覆盖 `prompts/souls/<sid>/orchestration.json`(只改这个世界)。文件是整张图或补丁 `{nodes, remove, add}` | 已实装 |
| 已获得的角色 | 图从来源读(模板 / 角色库),记忆从玩家的快照读:改了编排,带走的角色跟着变,记忆不丢 | 已实装 |
| 规范版本 | 图写 `targets: {soul_spec, world_spec}`;引擎读 `SOUL_SPEC = 1` / `WORLD_SPEC = 1`。要的比引擎新 → block `orch.spec_mismatch`;角色文件夹(`soul.json` 的 `spec_version`,缺省取 `schema_version`)比图要的旧 → warn | 已实装 |
| lint | `orch.subject` · `orch.spec_mismatch` · `orch.start` · `orch.node_kind` · `orch.edge` · `orch.param_range`(参数 / idle 分钟超出范围)(block);`orch.tool_unknown` · `orch.tool_off`(工具没上线或这种节点不调:`memo.write` 只在 tick / reflect,chat 不写记忆)· `orch.on_unknown` · `orch.on_target`(tick / idle 只能连 tick 节点)· `orch.node_off`(reflect 的 every = 0)· `orch.no_chat`(warn) | 已实装 |
| 写回 | 角色库的角色 → 它文件夹的 `agents/orchestration.json`;世界里的角色 → 模板作者操作 `set_soul_orchestration {sid, graph}`(内置模板只读,先复制);存成相对「没有这份文件时」的补丁,和默认一样 = `{}` | 已实装 |

接口(Local;浏览器版引擎回 404):`GET /api/v1/souls/catalog?lang=`(三类角色一张表:`ref` · `kinds`(`library` / `independent` / `standalone` / `takeable`)· `worlds` · `chat` · `edit {to: library|template, id, writable}`)· `GET /api/v1/souls/orchestration?ref=`(`graph` · `base` · `default` · `layers` · `lint` · `hooks` · `edit`)· `POST /api/v1/souls/orchestration {ref, graph}`(403 只读 · 400 有 block)· `POST /api/v1/souls/orchestration/lint {graph}`。

---

## 5. 引擎在运行时写什么

### 5.1 三方隔离:世界不能写 soul

| 世界侧尝试 | 结果 | 代码 |
|---|---|---|
| `patch <角色> 属性=…` | 拒绝:"她的状态只由她自己的回包决定,世界侧不写" | `src/neonrp/core/sdk.py`(patch 校验,`env.cls == "soul"`) |
| `mood <角色> …` | 拒绝:这是 soul 侧操作,世界侧不出 | `src/neonrp/core/sdk.py`(`spec.scope == "souls"`) |
| 文件操作 `write/edit/rm` 到 `souls/` | 拒绝:文件操作沙箱只在世界数据目录(`game/`)内 | `src/neonrp/core/worldfiles.py:normalize` |
| `move <角色> <地点>` | 允许,但要过移动裁判;通过后由引擎写 `run_state.json.location` | `src/neonrp/packs/rpg/atlas/move.py:move` → `src/neonrp/core/ontology.py:move_entity` |

soul 自己提出的移动也只是提案,同样经过移动裁判才落地。

### 5.2 引擎写入清单

| 写入 | 文件 | 时机 | 状态 |
|---|---|---|---|
| soul 结算:`mood`、`trust.player`(±2/回合,夹在 -10…10)、`intention` | `run_state.json` 的 `status` | 回合结束后,依据**最终落地的叙事**判断(不是 soul 自己的提议);每题都有确定性兜底:mood 不变、trust 0、intention 不变 | 已实装(rpg pack 的 `settle` 接缝) |
| 一条事件记录 `{turn, event, my_reaction, affect, …, by:"engine.settle"}` | `short-term-memo/recent_events.json` | 同上,每个参与回合的 soul 一条 | 已实装 |
| 她视角的叙事 | `short-term-memo/perceived.json` | 回合后,对在场 soul 各写一条 | 已实装 |
| 位置 | `run_state.json.location` | `move` 通过裁判后 | 已实装 |
| 在场名单 | `.neonrp/playthrough.json` 的 `active_souls` | 每回合场景理解 | 已实装 |
| 缺失的 agent 清单 | `agents/manifest.json`、`agents/contracts.md` | soul agent 首次被解析时自愈补写 | 已实装 |

在 rpg pack 下,soul 每拍"判断 + 说话":判断是封闭选项(态度、语气、急迫度、是否想移动),之后一次 LLM 调用写 1–3 句台词;soul 结算不让 LLM 直接写记忆。在默认的旧回合引擎(world-agent 工具循环)下,soul agent 用工具在自己的 `write_globs` 内写 `recent_events.json`、`action_log.md`、`character/status.json`;越界写入被拒绝。

---

## 6. 最小可用角色

**能被放进世界并运行**的最小 soul:

```
mina/
└── soul.json        {"sid": "mina", "name": "Mina"}
```

**推荐的最小集**(有声音、有目标、有位置):

```
mina/
├── soul.json                    {"sid": "mina", "name": "Mina", "name_local": "米娜"}
├── soul.md                      # 一段 ## Core Presence
├── persona/motivations.json     {"motivations": ["keep the ferry running", "learn who burned the old bridge"]}
└── run_state.json               {"sid": "mina", "location": "<地点 id>", "status": {"mood": "calm"}}
```

`agents/manifest.json` 可以省:运行时会自动补上标准清单。

已验证(在临时目录、复制内置 `stoneford-elena` 世界后):

1. 上面"推荐最小集"去掉 `run_state.json` 的版本,`neonrp cast <路径>` 成功:落到 `souls/mina-si-<hex>/`,playthrough 追加一行,`active_souls` 加入该实例。
2. `neonrp validate` → playable,仅一条警告(缺 `agents/manifest.json`)。
3. 引擎场景登记能读到这个 soul(显示名取 `name_local`,目标取自 `motivations`);首次解析 soul agent 时 `agents/manifest.json` 被自动补写。
4. 只有 `soul.json` 的版本:playable,三条警告(缺 `soul.md` / `persona` / `agents/manifest.json`)。
5. playthrough 登记了但文件夹不存在:**NOT playable**(阻断 `soul-missing`)。

注意:没有 `run_state.json.location` 的 soul 不在任何地点;在 rpg pack 下只有和玩家同处一地的 soul 参与回合,所以想让她出场就给一个地点。

---

## 7. 校验

`neonrp validate`(在世界文件夹内运行;`--json` 输出结构化结果)对 souls 做这些检查(`src/neonrp/core/validation.py:check_world`):

| 检查 | 级别 | code |
|---|---|---|
| playthrough 登记的 soul 没有 `souls/<sid>-<instance_id>/` 文件夹 | 阻断 | `soul-missing` |
| 缺 `soul.json`(身份退回 sid) | 警告 | `soul-incomplete` |
| 缺 `soul.md`(没有宪章声音) | 警告 | `soul-incomplete` |
| 缺 `persona/`(没有人格内核) | 警告 | `soul-incomplete` |
| 缺 `agents/manifest.json` | 警告 | `soul-incomplete` |
| `run_state.json.location` 不在任何 `game/towns/*/town_map.json` 中 | 警告 | `location-dangling` |
| souls 下所有 `*.json` 必须能解析 | 阻断 | JSON 完整性层 |
| playthrough souls 行缺必需字段 | 阻断(playthrough 无法解析) | playthrough 层 |

template lint(`neonrp template`)额外检查:template 引用的 soul 必须存在(`ref.soul`)、提示层只能覆盖允许的路径(`prompt.soul.data`)。

---

## 8. 参考实现位置

| 主题 | 位置 |
|---|---|
| 身份信封读写、角色库、骨架 | `src/neonrp/core/souls.py:SoulMeta`、`read_soul_json`、`create_soul_dir`、`SOUL_SUBFOLDERS`、`archive_soul` |
| cast 解析与落点 | `src/neonrp/core/placement.py:resolve_soul_dir`、`project_soul_multiagent`、`project_avatar_multiagent`、`project_soul_as_npc`、`load_soul_full` |
| CLI | `src/neonrp/commands/cast.py:cast`、`src/neonrp/commands/validate.py:validate` |
| playthrough souls 行 | `src/neonrp/core/playthrough.py:SoulRef`、`_parse_souls`、`set_active_souls` |
| soul → agent(提示、读写权限) | `src/neonrp/core/soul_agent.py:resolve_soul_agent_data`、`_system_template` |
| agent 清单与自愈 | `src/neonrp/core/soul_authoring.py:build_manifest`、`ensure_soul_agent` |
| soul 后端 | `src/neonrp/core/soul_backend.py:resolve_soul_backend` |
| 场景登记(引擎读哪些字段) | `src/neonrp/packs/rpg/loaders.py:_load_souls` |
| 每拍判断 + 说话 | `src/neonrp/packs/rpg/soul_step.py:soul_step`、`judge_soul` |
| 回合后结算(mood/trust/intention) | `src/neonrp/packs/rpg/soul_settle.py:settle_souls`、`_apply_patch` |
| 她视角的叙事 | `src/neonrp/core/soul_view.py:write_views` |
| 世界不能写 soul | `src/neonrp/core/sdk.py`(patch 校验)、`src/neonrp/core/worldfiles.py:normalize` |
| 移动落地 | `src/neonrp/packs/rpg/atlas/move.py:move`、`src/neonrp/core/ontology.py:move_entity` |
| template 覆盖范围 | `src/neonrp/template/__init__.py:SOUL_PROMPT_PATHS` |
| 校验 | `src/neonrp/core/validation.py:check_world`、`_SOUL_BUNDLE_WARN_PIECES` |
| 参考 soul | `src/neonrp/templates/stoneford-elena/souls/elena-si-elena0001/`、`rowan-si-rowan0001/` |
