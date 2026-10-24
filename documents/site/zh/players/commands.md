---
title: "终端命令"
description: "终端游戏里的全部斜杠命令,以及旧命令搬到了哪里。"
---

<!-- section: how -->
## 怎么用

在 `neonrp` 进入的终端游戏里,输入框里敲 `/` 就会列出命令和补全。不带参数的命令大多会弹出一个选单,不用先记 id。

除了下面这些,每个世界还可以带自己的命令,比如灰橡宅的技能 `/聆听`、`/察觉`:敲 `/` 时它们和引擎的命令列在一起。

<!-- section: play -->
## 玩

| 命令 | 作用 |
|---|---|
| `/open [世界或存档]` | 不带参数:列出能玩的世界和存档。带存档:接着玩。带世界:开一局新的 |
| `/init [世界]` | 用一个世界开一局新的;不带参数弹选单,选单里也能从零建一个空白世界 |
| `/load [存档或快照]` | 读一个存档接着玩,或读本局里的快照;不带参数弹选单 |
| `/save [名字]` | 在本局里存一个快照 |
| `/undo` | 退回上一步 |
| `/undo list` | 列出这条线上的回合 |
| `/undo <回合>` | 回到那一回合,另起一条新线;原来那条保留 |
| `/redo` | 把刚退掉的一步做回来 |
| `/status [页]` | 状态面板。页:`player` 你 · `agents` 角色 · `plan` 计划板 · `dice` 骰子 · `settlement` 结局与结算 · `contract` 玩法合约 · `account` 账号与判官 · `usage` 用量 · `room` 联网同桌 |
| `/lang [语言]` | 这一局用哪种语言讲故事:`zh` `en` `ja` `ko` |
| `/find <关键词>` | 在这个世界里搜地点、人物、物品 |
| `/clear` | 清空当前对话显示 |

<!-- section: characters -->
## 角色

| 命令 | 作用 |
|---|---|
| `/who [角色]` | 进一个角色的视角:它在哪、记得什么、最近几回合做了什么;在那里可以直接和它聊,或替它行动 |
| `/cast [角色] [身份]` | 把角色库里的角色请进这个世界,身份是 `npc` 或 `player`;不带参数列出可用的角色 |
| `/create <名字>` | 在 build 模式里造一个新角色,交给 agent 写 |
| `/remove <角色>` | 让角色离开这个世界(角色库里的它不受影响) |
| `/reset <角色>` | 让角色忘掉在这里的记忆和经历,设定不变 |
| `/import <文件>` | 导入世界包(`.zip`)或 SillyTavern 角色卡(`.png` / `.json`),按内容自动分辨 |

<!-- section: build -->
## 造世界

| 命令 | 作用 |
|---|---|
| `/mode [build 或 play]` | 在同一个世界里切换:build = 让 agent 改这个世界,play = 玩 |
| `/vault [build]` | 把这个世界投影成一个 Obsidian 库并打开;`build` 只生成、不打开 |
| `/dev [项]` | 给创作者和排障用:`graph` 编排图 · `dry-run` 试跑一拍 · `beats` 叙事里标出拍的骨架 · `template` 模板 · `validate` 检查世界 · `mcp` · `bridge` · `debug` |

<!-- section: app -->
## 账号、设置、更新

| 命令 | 作用 |
|---|---|
| `/login` | Worldlines 账号(可选):Jev 判官、模型中转、上传世界。`/login code` 没有浏览器时用验证码登录 · `/login status` 看状态 · `/login out` 退出 |
| `/settings` | 模型、key、Discord 桥接等设置 |
| `/update` | 检查更新。`/update apply` 安装 · `/update status` 看版本和设置 · `/update mode auto`、`prompt`、`notify` 改启动时的更新方式 · `/update channel` 换更新通道 |
| `/help` | 列出命令 |
| `/quit` · `/q` | 退出 |

<!-- section: input -->
## 输入框里的记号

| 写法 | 作用 |
|---|---|
| `@名字` | 对某个角色说话;敲 `@` 会补全在场的人 |
| `@dm` | 叫主持直接接下去:商量拍马上进清算拍 |
| 「定」 | 同上,表示谈妥了 |
| `#` | 句子里敲 `#` 补全地点和物品 |

<!-- section: removed -->
## 旧命令去哪了

1.0 起命令收成了上面这些。敲旧命令不会报「未知命令」,会告诉你现在用哪个:

| 旧命令 | 现在用 |
|---|---|
| `/branch` | `/undo list` · `/undo <回合>` |
| `/worlds` `/worldlines` `/continue` | `/open` |
| `/game` | `/open` · `/create` |
| `/sessions` | `/load` |
| `/models` `/auth` `/wl-model` `/locale` | `/settings` |
| `/load-world` | `/import` |
| `/export-world` | 命令行 `neonrp export-world` |
| `/context` | `/find` |
| `/replay` | `/dev dry-run` |
| `/compact` | `/clear` |
| `/copy` | `F6` |
| `/run` `/agent` | 直接说话 |
| `/index` | 引擎自动维护 |
| `/skills` | agent 自己会用 |
| `/files` | 命令行 git |

还有几条不再列出、但仍能直接敲:`/validate`(也在 `/dev validate`)、`/mcp`(也在 `/dev mcp`)、`/bridge`(也在 `/dev bridge`)、`/debug` 和 `/verbose`(合并为 `/dev debug`)、`/stats`(在 `/status usage`)、`/config`(平时用 `/settings`)。

`--mcp` 启动方式和 Claude Code 预设在 1.0.3 去掉了。
