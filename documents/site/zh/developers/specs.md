---
title: "规格 Spec"
description: "世界、角色、模板、规则包、玩法合约、玩家数据的规格全文,以及模板、一局、角色库在磁盘上的样子。"
---

<!-- section: specs -->
## 规格

写世界、角色、模板或规则包之前先读对应的规格。它们也是 agent(Claude Code / Codex)创作时读的同一份文件。

| 规格 | 讲什么 | 中文 | English |
|---|---|---|---|
| 世界 World | 世界文件夹:地点树、人物、物品、规则表、开场 | [world.zh.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/world.zh.md) | [world.en.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/world.en.md) |
| 角色 Soul | 角色包:身份、人设、记忆、RPG 身体、立绘;角色库 | [soul.zh.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/soul.zh.md) | [soul.en.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/soul.en.md) |
| 模板 Template | 把世界 + 角色 + 规则包 + 编排绑成一个可玩、可发布的包 | [template.zh.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/template.zh.md) | [template.en.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/template.en.md) |
| 规则包 Pack | 规则表、规则面板、检定与对抗、状态表、时钟(`rpg` / `pct`) | [pack.zh.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/pack.zh.md) | [pack.en.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/pack.en.md) |
| 玩法合约 Contract | 体验约定:回合、死亡、结局 | [contract.zh.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/contract.zh.md) | [contract.en.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/contract.en.md) |
| 玩家 Player | 玩家自己的数据:分身、跨局记录、聊天 | [player.zh.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/player.zh.md) | [player.en.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/player.en.md) |

另有四份每次从代码生成、不会过时的:`ops`(每个规则包的 op、类、变量、触发器、接缝、模式层)· `authoring`(模板的创作操作)· `contracts`(现行的玩法合约)· `http`(引擎回答的每个 HTTP 路径)。

装好引擎后也能直接在终端读:

```bash
neonrp spec                 # 列出全部规格
neonrp spec pack            # 读一份(--lang en 读英文)
neonrp spec ops --pack rpg  # 一个规则包能用的操作、类、变量
neonrp spec http            # 全部 HTTP 路径
```

<!-- section: layout -->
## 磁盘上的样子

**一个模板**(`<id>.template/`,创作和发布的单位):

```
stoneford-town.template/
├── template.json           # 卡片、模式、区、编排 uses、规则包、卡司、剧情、lint、ui、奖励…
├── world-overlay/          # 叠在内置世界上的改动(或 world/:自带的整个世界)
├── prompts/                # 提示词层(世界 / 模板 / 角色 prompts/souls/<sid>/)
├── plots/                  # 剧情包
├── i18n/<lang>/            # 其他语言的层
├── assets/                 # 素材槽:assets/<类>/<槽位>/
├── orchestration.json      # 编排图的补丁(可选)
├── frontends/              # 这个世界自己的前端(可选,不随导出)
├── spec/ · AGENTS.md · CLAUDE.md   # 生成的,给 agent 读
```

**一局**(`template build` 或开新局搭出来的世界文件夹;`worldlines` 开的局在 `~/.worldlines/plays/` 下):

```
<局>/
├── manifest.json           # template = 规则包组合名(如 rpg+economy)
├── playthrough.json        # 卡司和角色实例
├── game/
│   ├── meta/               # 引擎状态:run_state、engine.json、variables / classes / actions / triggers / entries 覆盖层、
│   │                       #   events.jsonl(事件账本)、template.json、play_contract.json、orchestration.json …
│   ├── locations/<T>/<地点>/location.json   # 地点树
│   ├── world/              # 世界数据(world_map、片段数据如 economy.json)
│   ├── player/             # 玩家状态:钱包、物品、属性
│   ├── rules/ · lore/ · plots/ · item/ …
├── souls/<sid>-<实例>/     # 这一局里的角色实例:soul.json、soul.md、persona/、character/、记忆 …
└── .neonrp/                # 会话、存档、分支、本局设置
```

**`~/.worldlines/`**(本机网页和 TUI 共用):

```
~/.worldlines/
├── templates/              # 你自己的模板(fork / 导入 / 新建)
├── official/               # 用账号拉下来的默认区世界
├── souls/<名字>/           # 角色库:模板里写 {"lib": "<名字>"} 链过来,开局时才复制进这一局
├── plays/                  # 每一局一个文件夹
├── replays/<id>/           # 导出的回放
└── commits/                # 世界提交:worlds/、refs/<局>/{HEAD,branches/*}、blobs/
```

每回合落地时做一次世界提交(内容寻址,提交 id 就是内容的哈希);角色实例的提交在它自己的 `.commits/` 里。回退 = 从某个提交另开一条分支,原来那条线保留。时间戳不进身份,只当标签。
