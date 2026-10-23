---
title: "常见任务"
description: "新建模板、选角、声明合约、加结局、导出 —— 每一步改哪个文件、用哪条命令。"
---

<!-- section: new -->
## 从一个现成的模板开始

> **状态:随 1.0 发布**

```bash
neonrp template list                              # 有哪些
neonrp template fork pct-house my-house --title "我的宅子"
cd <模板库>/my-house.template && cat AGENTS.md
```

<!-- section: cast -->
## 把角色库里的角色放进来

`template.json` 的 `souls`(`spec/template.md` §3.6):

```json
"souls": [
  {"sid": "chara", "role": "npc"},
  {"lib": "mira", "role": "companion"}
]
```

`lib` 是角色库里的文件夹名。她在这个世界里的身份写 `prompts/souls/mira/soul.md`(只能覆盖 `soul.md` · `persona/` · `rules/` · `agents/`)。改完 `neonrp template lint .`:link 断了会报 `ref.soul`。

<!-- section: contract -->
## 声明一份合约

```bash
neonrp template contracts                         # 四份官方合约,以及谁声明了
neonrp template set-contract my-house mystery-trpg
neonrp template lint .                            # 按合约查:开场 · 阵容 · 结局数 · 真相 · 结局 CG
```

每条 `contract.*` 是什么意思:`spec/contract.md` §4。

<!-- section: ending -->
## 加一个结局

在剧情包 `plots/<id>/plot.json` 的 `endings` 里加一条(`spec/template.md` §5):`title`、`kind`(`true` / `fail` / …)、`text`;合约要结局 CG 的,加 `assets.image` 并把图放进 `plots/<id>/assets/`;再在 `triggers` 里写一条 `"then": [{"to": "end", "ending": "<id>"}]` 让它可达。lint 会查「结局可达」「同一分支不发两个结局」「结局要有标题」。

<!-- section: map -->
## 给世界加地点、连路

地点是文件夹(`spec/world.md`):`world/game/locations/<镇>/<地点>/location.json`,放在哪个文件夹里就在哪一层,`connections` 写和谁相连。改完进 `world/` 跑 `neonrp validate`。

<!-- section: share -->
## 打包带走

```bash
neonrp template export my-house                   # → my-house.template.zip(带上它 link 的角色)
neonrp template import my-house.template.zip --id my-house-2
```
