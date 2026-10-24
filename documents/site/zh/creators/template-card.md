---
title: "模板:template.json"
description: "一个模板就是一个 <id>.template/ 文件夹,入口是 template.json。每个字段做什么,用石津镇和灰橡宅的真实写法说明。"
---

<!-- section: folder -->
## 文件夹

> **状态:随 1.0 发布** —— 完整字段表和每项 lint 代码见模板文件夹里的 `spec/template.md`。

一个模板是一个文件夹,名字是 `<id>.template/`。石津镇长这样:

```text
stoneford-town.template/
  template.json          ← 入口:这一页讲的就是它
  world-overlay/         ← 叠在内置世界上的改动(地图、地点、经济数据……)
  prompts/               ← 提示词层(世界规则、口吻、条目)
  plots/P20/plot.json    ← 剧情包:阶段、触发器、结局
  orchestration.json     ← 编排图补丁(编排台写的)
  i18n/<语言>/           ← 英日韩的翻译层
  assets/                ← 封面、结局 CG 等图片
  AGENTS.md  CLAUDE.md  spec/   ← 给 coding agent 读的说明和规格(引擎生成)
```

灰橡宅不借内置世界,世界整个放在模板里的 `world/`。

<!-- section: example -->
## 石津镇的 template.json(节选)

```json
{
  "schema": "worldlines.template/1",
  "id": "stoneford-town",
  "version": "0.1",
  "zone": "reviewed",
  "forkable": true,
  "card": {"title": "石津镇 · 雾退之夜", "pitch": "一年只有一夜,雾会从北路上退开……",
           "cover": "assets/cover.png", "lang": "zh", "tags": ["奇幻", "雾", "小镇"]},
  "mode": {"ending": "multi", "freedom": "semi"},
  "play_contract": "open-adventure@1",
  "world": {"builtin": "stoneford-elena", "prompts": "replace", "overlay": "world-overlay"},
  "uses": {"template": "two_beat", "version": "1.0", "soul": "S-judge"},
  "pack": {"name": "rpg", "mixins": ["economy"], "engine": {"turn": {"mode": "v3"}}},
  "souls": [{"sid": "elena", "role": "npc"}, {"sid": "rowan", "role": "npc"}],
  "prompts": ["prompts/world.json", "prompts/voice.md", "prompts/town.json"],
  "plots": ["plots/P20"],
  "lint": {"level": "draft"},
  "orchestration": "orchestration.json",
  "creation": {"add": ["soul", "plot", "ending", "clue", "rule"], "…": "…"},
  "audio": {"theme": "emberglass", "ambient": "fireplace"},
  "rewards": [{"id": "old_fog_map", "kind": "card", "rarity": "common", "when": "flag:has_map", "title": {"zh": "旧雾路图", "…": "…"}}]
}
```

<!-- section: fields -->
## 字段

| 字段 | 写什么 |
|---|---|
| `card` | 卡面:`title`、`pitch`(一句话简介)、`cover`(模板里的一张图)、`lang`、`tags`。其他语言的卡面写在 `i18n/<语言>/template.json` |
| `mode` | `ending`:`open`(没有结局)· `single`(一个结局)· `multi`(多个结局);`freedom`:`free` · `semi` · `guided`(玩家能走多远) |
| `zone` | `reviewed` = 默认区,`open` = 自由区;不写按自由区。见[发布到 Hub](/docs/creators/publish) |
| `forkable` | `true` = 这个默认区世界允许「复制一份来改」。你自己的作品总能复制,不用写 |
| `play_contract` | 承诺哪一种体验,如 `mystery-trpg@1`、`open-adventure@1`。见[玩法合约](/docs/creators/contracts) |
| `world` | 世界从哪来:`path`(模板里的文件夹)或 `builtin`(引擎内置世界);`overlay` 叠一层改动;`prompts: "replace"` = 用模板的提示词层代替世界自带的 |
| `uses` | 这个世界用哪种编排(一回合怎么推进):`template` 是编排名,`soul` 是在场角色的行动方式,`params` 选参数(如 `{"pace": "quick"}`)。见下一节 |
| `pack` | 规则包:`name` 是 `rpg` · `pct` · `werewolf` · `monopoly` 之一;`mixins` 叠加片段(`economy` · `factions`);`engine` 写进这一局的引擎设置 |
| `souls` | 演员表。见[角色库与选角](/docs/creators/characters) |
| `prompts` | 提示词层文件列表 |
| `plots` | 剧情包文件夹列表。见[剧情包](/docs/creators/plot-packs) |
| `lint` | `level: "draft"` 时缺图、超 token 预算只警告;不写或 `"publish"` 时会拦下。见 [Lint](/docs/creators/lint) |
| `ui` | 素材槽位 `slots`、视图 `views`、具名生图提示 `prompts`、每回合 token 预算 `budget`。见[素材](/docs/creators/assets) |
| `opening` | `cg`:开场时按顺序播放的几张图,每张带 `image`、`caption` |
| `audio` | 音乐和环境声:`theme`、`ambient`,可按地点覆盖(`places`) |
| `rewards` | 奖励卡:`when` 满足时发给玩家(自由区不发) |
| `creation` | 创作台能往这个模板里**加**什么:`add`(角色、剧情、结局、线索、规则)、`triggers` 允许的触发器种类、`collect` 角色怎么收集。不写 = 不开放 |
| `orchestration` | 编排台改出来的图补丁文件 |
| `models` | `play` 指定这一局默认用的模型,写成 `provider/model` |

<!-- section: uses -->
## `uses`:一回合怎么推进

`uses` 选的是**编排**,和玩法内容无关。两个内置模板都写 `"template": "two_beat"`:一回合分商量和清算两拍(见[商量与清算](/docs/concepts/planning-resolve))。

- 从 PyPI 装的 `worldlines` / `neonrp` 自带两拍编排。
- 从开源仓库源码装的引擎只有单拍(`one_beat`)。模板写了 `two_beat` 也照样能玩,退回单拍,在场角色的行动方式保持模板写的。

网页 Hub 和 iOS 创作台只能从几种编排里选一种,图只读;只有本机编排台能改图。

<!-- section: mixins -->
## 规则包与片段

`pack.name` 选一种玩法规则,`pack.mixins` 叠加系统片段。内置规则包四个:`rpg`(d20)、`pct`(百分骰调查)、`werewolf`、`monopoly`;片段两个:`economy`(集市、价格、商队)、`factions`(势力、传闻、委托)。见[片段](/docs/creators/fragments)。

<!-- section: next -->
## 改一个模板

内置模板只读。先复制一份:

```bash
neonrp template fork stoneford-town my-town --store ~/.worldlines/templates
neonrp template lint ~/.worldlines/templates/my-town.template
```

或者在本机创作台 Template 页点「复制一份来改」。
