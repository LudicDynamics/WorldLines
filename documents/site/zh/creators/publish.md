---
title: "发布到 Hub"
description: "两个区:自由区先上后管,默认区审核后上架。发布前引擎先查五件事。"
---

<!-- section: zones -->
## 两个区

> **状态:随 1.0 发布**

| | 自由区 | 默认区 |
|---|---|---|
| 怎么进 | 用账号发布,检查通过就公开 | 审核通过才上架 |
| 管理方式 | 先上后管:有人举报或管理员发现问题再下架 | 上架前看过 |
| 能不能导出成包 | 能 | 不能(只能玩) |
| 发奖励卡、让玩家带走角色 | 不发 | 发 |
| `template.json` 的 `zone` | `open`(不写也按自由区) | `reviewed` |

官方世界(灰橡宅、石津镇等)都在默认区。

<!-- section: flow -->
## 怎么发

**本机创作台**(`worldlines` 打开的本地网页):

1. 登录 Worldlines 账号(游客账号不能发布)。
2. 在 Template 页点「发布」。引擎先跑发布前检查(见下),过了就上传,作品**立刻**出现在自由区。
3. 想进默认区:在「我的已发布」里点「申请进默认区」。等审核期间作品照常留在自由区。

**网页 Hub 创作台 / iOS 创作台**可以直接提交到默认区:快审期间 30 分钟内没人提出问题就自动通过,通过以前别人看不到。

同一个模板再发一次 = 给同一个作品加一个新版本。已经公开的作品不能直接换区,要走「申请进默认区」。

**官方账号**用命令行发默认区:

```bash
neonrp template publish stoneford-town --official
```

每次发布前先把 `template.json` 的 `version` 调大。普通账号用 `--official` 会被拒。

**获取**默认区的世界(要用正式账号登录):

```bash
neonrp template fetch <作品 id>     # 下载或更新到 ~/.worldlines/official
```

<!-- section: checks -->
## 发布前检查

引擎在上传之前查五件事,有一件不过就什么都不发,并列出要改的地方:

| 检查 | 不过时 |
|---|---|
| 链接的角色都在本机角色库 | 模板里 `{"lib": …}` 指向的角色找不到 |
| 没有密钥 | 模板或它链接的角色里有像 API key 的字符串、凭据文件 |
| [Lint](/docs/creators/lint) 没有 block | 还有必须改的问题 |
| 四语卡面 | 中 / 英 / 日 / 韩 任一种缺标题或一句话简介(写在 `i18n/<语言>/template.json` 的 `card` 里) |
| 有封面 | `card.cover` 没指向模板里的一张图 |

平台收到后还会再跑一遍自己的自动检查。

<!-- section: zone-lint -->
## 按区分级的检查

有几项检查在两个区严格程度不同:

| 检查 | 默认区 | 自由区 |
|---|---|---|
| 真相三问(`mystery-trpg` 合约要求的 `truth_quiz`) | block | warn |
| 模板自带音频文件时写明来源和授权(`audio.credits` 指向如 `assets/audio/CREDITS.md`) | block | warn |

<!-- section: export -->
## 导出

只有自由区的作品能导出成包。默认区的世界如果标了 `forkable: true`(两个内置世界都标了),先「复制一份来改」,复制出来的就是你自己的作品,可以导出、可以发到自由区。见[导出与导入](/docs/creators/export-import)。

<!-- section: http -->
## 接口

```
GET  /api/v1/local/templates/<id>/publish            演练:只查不传,返回 {checks, work, signed_in}
POST /api/v1/local/templates/<id>/publish            发布到自由区
POST /api/v1/local/templates/<id>/publish  {"zone": "curated"}   提交默认区审核
GET  /api/v1/local/hub/mine                           我的已发布
POST /api/v1/local/hub/submit {id}                    申请进默认区
POST /api/v1/local/hub/unpublish {id}                 撤下
```

检查不过返回 `422 checks_failed` 和问题列表;没登录 `401 not_signed_in`。
