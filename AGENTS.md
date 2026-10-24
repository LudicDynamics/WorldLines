# WorldLines 捏卡工作台 · 给 Codex 的说明

你在 **WorldLines 开源仓** 里,帮用户「捏卡」:做一个角色(soul)、一个世界(world),或者把它们组装成一个能玩、能发布的模板(template)。
所有东西都是文件夹 + JSON / Markdown;引擎是 `neonrp`(Apache-2.0),你只写数据,不改引擎代码。

> English summary (Codex): this repo is a card-crafting workbench. Help the user build a **soul** (character), a **world**, or a **template**
> that binds them, following the specs in `documents/spec/`, validate with `neonrp`, and play-test with the TUI. Never edit engine code.

## 先弄清用户要什么

只问最少的、具体的问题(不问哲学问题,一次问完):

| 用户想要 | 你产出 | 规格 |
|---|---|---|
| 一个角色,放进已有世界 | 一个 soul 文件夹 | `documents/spec/soul.zh.md` |
| 一个世界(地方、城镇、NPC、开场) | 一个 world 文件夹 | `documents/spec/world.zh.md` |
| 能直接开局、能发布的一整套 | 一个 `<id>.template/` 文件夹(绑定世界 + 角色 + 玩法包 + 卡面 + 剧情) | `documents/spec/template.zh.md` |
| 酒馆格式的角色卡 / 世界书 | SillyTavern V2/V3 卡片 | skill `character-card-authoring` / `world-card-authoring` |
| 一种玩法要给玩家的体验(入口、出口、结局、发布门槛) | 一份玩法合约,或在模板里选一份官方合约 | `documents/spec/contract.zh.md` |
| 了解玩法包(`rpg` / `pct` / `werewolf` / `monopoly`)的规则、状态和操作 | 只读,不写;在模板的 `pack` 里选用 | `documents/spec/pack.zh.md` |

分层(写之前心里要有):**玩法包 pack(引擎里的规则)+ 世界 world + 角色 souls = 最小可玩**;模板 template 是可选的上层,
加上卡面、模式、提示词、剧情、素材槽和 lint,也是发布的单位。世界和角色不依赖模板。

## 从参考开始,不要从空白开始

| 参考 | 位置 |
|---|---|
| 完整的世界(石津镇,艾琳娜与罗文) | `neonrp/src/neonrp/templates/stoneford-elena/` |
| 最小的世界 | `neonrp/src/neonrp/templates/white-blank/` |
| 最小的角色 | `documents/spec/soul.zh.md` 里「最小可用角色」一节(手写示例;`soul-blank/` 目前是艾琳娜的副本,不要拿它当空白) |
| 模板:百分骰调查、多结局(灰橡宅) | `worldlines/templates/pct-house.template/`(自带世界在 `world/` 里) |
| 模板:开放小镇 RPG、经济、多结局(石津镇·雾退之夜) | `worldlines/templates/stoneford-town.template/`(世界用内置的 `stoneford-elena`,差异放在 `world-overlay/`) |
| 旧格式的小示例世界 | `worldlines/examples/worlds/` |

做法:世界和角色,先复制最接近的参考到用户自己的目录(例如 `my/<id>/`),再按用户的设定逐个文件改。
模板用复制命令,它会顺手放好 `AGENTS.md` 和 `spec/`:`neonrp template fork stoneford-town my-town --store my/`。
改之前读一遍对应的规格;不确定某个字段是否被引擎读取,就去规格里的「参考实现位置」看代码,不要编字段。

## 写的规矩

- **内容用目标语言原生写**(中文 / 日文 / 英文……),不要先写一种再翻译;**id、字段名、文件名一律 ASCII**。
- 角色:先给具体画面和说话方式,再写设定;角色自己的状态和日记由引擎在运行时结算,不要预先写满。
- 世界:引擎代码不写具体世界的词——世界自己的规则、通缉、腹痛、山贼这类都写在世界数据里。
- 开场:写进 `game/meta/game-start.json` 的 `startup.opening_scene` / `opening_choices`。有角色(soul)的世界开局时原样给玩家,不调模型;
  没有 soul 的世界由入口 agent 以它为基础叙述开场(会调模型)。详见 `documents/spec/world.zh.md` 3.12。
- 不放任何密钥、个人路径、内部地址;图片只用用户自己有权使用的。

## 检查,然后试玩

```bash
neonrp template lint my/<id>.template          # 模板:全部问题(block 会挡发布,warn 只提醒)
neonrp template slots my/<id>.template         # 还缺哪些图(地图 / 立绘 / 场景 / 图标)
cd my/<world> && neonrp validate               # 单独的世界:JSON、角色、开场能不能跑
neonrp template build my/<id>.template /tmp/try-<id>   # 组装成一局
cd /tmp/try-<id> && neonrp tui --play          # 试玩:没玩过的局会自动开场
```

lint 有 block 就先修再试玩;把每条 block 的原文和你的修法告诉用户。没装引擎:`uv tool install worldlines`(会带上 `neonrp`)。

## 游玩是怎么走的(写设定时要考虑)

一回合怎么走,由模板 `uses` 点名的编排决定。两个内置模板都用两拍:

1. **商量拍**:主持接住玩家的话,把话递给在场的角色,列出要花的钱、要过的检定、要用的时间。这一拍世界不动、时钟不走;
   谈妥了(判官或本局模型判断,或玩家说「定」)才进下一拍。一句没什么可谈的话(走一步、没有花费)直接进清算。
2. **清算拍**:在场的角色各自行动,引擎掷该掷的骰子,主持先写叙述,再把变化写进世界(引擎校验;工具和引擎的裁定优先)。
   写状态先给一个快的结果,后台再用更细的一次修正(最多 90 秒),玩家先说下一句就取消修正。每回合落一个世界提交。

PyPI 上的 `worldlines` / `neonrp` 包带完整的两拍编排;从本仓源码装的引擎只跑清算拍(一拍),同一个模板照样能玩。

所以角色的设定要能「表态」(她会同意什么、拒绝什么、怎么讨价还价),世界要给主持能读的真实数据(价目、路程、谁在哪)。

## 可用的 skill

| skill | 用途 |
|---|---|
| `template-authoring` | 新建 / 修改一个模板(template.json、world-overlay、剧情、素材槽) |
| `soul-authoring` | 新建一个角色文件夹 |
| `entity-authoring` | 在世界的 `game/` 里加 / 改实体(地点、NPC、物品、任务) |
| `character-card-authoring` | 做 / 导出酒馆角色卡(V2/V3) |
| `world-card-authoring` | 做酒馆世界书 |
