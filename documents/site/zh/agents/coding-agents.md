---
title: "用 Codex / Claude Code 创作"
description: "装上 world-creation skill,把一份世界设定稿交给 coding agent:它按规格改文件,你在本机网页看进度,lint 清零就能玩、能发布。"
---

<!-- section: what -->
## 这一页讲什么

在终端里用 Claude Code 或 Codex 这类 coding agent 做一个世界:你写一份设定稿,agent 把它写成一个模板文件夹,你在本机网页工作台看结果、补图。

先讲四件事:WorldLines 怎么看世界、一局怎么推进、agent 改的是什么、怎么保证引擎跑得动。然后是实操步骤。

<!-- section: ideas -->
## 四个基本想法

| 想法 | 意思 | 对 agent 意味着 |
|---|---|---|
| **三方** | 世界、角色、玩家各有主体性,互相隔离。玩家的话是一次尝试,后果由世界决定;角色的想法由角色自己结算 | 不要在文件里替角色写好结局,也不要预先写满角色的日记和状态 |
| **文件系统即界面** | 世界、角色、模板都是文件夹。文件夹是唯一的真相;网页、TUI 只是把它渲染出来 | agent 改文件就够了。网页上看到的就是磁盘上的文件 |
| **效果归引擎,定制只管控制** | 抢劫被围、乱吃东西生病这类效果由引擎的机制给出,零配置也要成立;创作者的表和规则只用来**改**结果 | 不要写长提示词去「教」引擎怎么演;写数据:价目、路程、谁在哪、会同意什么 |
| **模板 = 世界 + 角色 + 玩法包 + 合约** | 模板绑定一个世界、一组角色、一个规则包(`rpg` / `pct` / `werewolf` / `monopoly`)和一份玩法合约,再选一个编排。它是被玩、被导出、被发布的单位 | agent 的产出是一个 `<id>.template/` 文件夹 |

角色住在角色库,模板里只放 link。世界里的地名、状态名、阵营名只进这个模板的数据,不进引擎代码。

<!-- section: orchestration -->
## 编排:一局怎么推进

编排是一张状态机图:节点是「这一拍在做什么」,连线是「什么时候换到下一个节点」。模板在 `template.json` 的 `uses` 里点名一个编排模板,它不带规则包,也不带合约,同一个编排可以给很多世界用。

| 编排 | 一回合 |
|---|---|
| `one_beat` | 只有清算拍:世界写叙事,在场角色各自行动,引擎写状态、校验、落地 |
| `two_beat` | 先商量拍,再清算拍。商量拍里主持把话递给在场角色、列出花费 / 检定 / 时间,世界不动;谈妥后进清算拍 |

PyPI 上的 `worldlines` / `neonrp` 自带两拍;从开源仓源码装的引擎只有一拍。模板点名的编排引擎没有时,退回一拍,世界照样能玩。

看一个模板现在用的图:

```bash
neonrp engine graph --template <模板文件夹>
```

改图(加连线、改触发条件)在本机编排台做,存成模板里相对默认图的补丁。agent 不需要手写编排图。

<!-- section: ops -->
## 工具调用:agent 改文件,引擎执行 op

两件事分开:

- **创作时**,agent 改的是文件:`template.json`、`world/` 下的地图和数据、角色文件夹、剧情包。
- **游玩时**,世界每一拍只能「提出」变化,形式是 op(移动、改变量、新建实例……)。引擎校验后才落地。op 由规则包登记。

叙事里的工具用括号写,形状就是等不等:

| 写法 | 意思 |
|---|---|
| `[op 参数]` | 同步工具:写到这里停,引擎回答后接着写。例:`[dice 1d20+2 vs 12]` · `[ask 艾琳娜]` · `[player.gold -12]` |
| `[~op 参数]` | 不等的工具:引擎照做,叙事接着写。例:`[~map]` |
| `<…>` | 引擎发给模型的消息,模型不写 |

所以 agent 不往文件里写 op,也不伪造运行状态。它写的是 op 要读的数据:变量的范围、地点之间的连接、价目表、剧情触发的条件。细节见 [提出 → 校验 → 落地](/docs/concepts/ops) 和 [一回合怎么走](/docs/concepts/turn-flow)。

<!-- section: install -->
## 装 skill

skill 在开源仓 [WorldLines](https://github.com/LudicDynamics/WorldLines) 的根目录:

| agent | 放哪 | 说明文件 |
|---|---|---|
| Claude Code | `.claude/skills/world-creation/`(只在这个仓库里用)或 `~/.claude/skills/world-creation/`(在任何文件夹里都能用) | `CLAUDE.md` |
| Codex | `.agents/skills/world-creation/` | `AGENTS.md` |

最简单的做法:clone 开源仓,在仓库根目录打开 Claude Code 或 Codex。根目录的 `CLAUDE.md` / `AGENTS.md` 已经列出这个 skill。

想在自己的模板库里直接用:把 `.claude/skills/world-creation/` 复制到 `~/.claude/skills/`。

引擎:

```bash
uv tool install worldlines      # 同时装上 worldlines 和 neonrp
```

<!-- section: flow -->
## 实操

**1. 写设定稿。** 按 skill 里的 `references/world-spec-template.md` 填:id、语言、规则包、合约、地点、人物、开场、剧情和结局、世界数据。内容用目标语言直接写,id 用 ASCII。示例:`examples/tidepool/world-spec.md`。

**2. 交给 agent。** 「按这份设定稿造一个模板。」agent 会:

```bash
neonrp template new tidepool --title "潮池镇" --lang zh --pack rpg --contract open-adventure@1 --store ~/.worldlines/templates
```

接近内置模板时改用 `neonrp template fork pct-house <id>` 或 `fork stoneford-town <id>`。设定稿复制进模板文件夹,作为这次工作的来源。

**3. 打开本机网页看进度。**

```bash
worldlines --no-browser         # http://127.0.0.1:8787;端口被占用时加 --port
```

| 地址 | 看什么 |
|---|---|
| `/local?screen=tpl&edit=<id>` | Template:卡面、合约、Lint、素材槽(在这里上传或生成图) |
| `/local?screen=duo&edit=<id>` | 世界 · 角色:地图、剧情、Schema、数据 |

网页读的就是磁盘上的文件,agent 每写完一段,刷新就能看到。

![Template 页:合约、Lint、素材槽](../../images/coding-agents/template.jpg)

![世界 · 角色页:按文件夹画出的地图](../../images/coding-agents/world.jpg)

**4. agent 分段写。** 卡面与模式 → 地图 → 传说与数据 → 人物 → 开场 → 剧情与结局 → 素材提示。每段写完跑一次 lint,告诉你改了什么。图由你在 Template 页上传或生成。

**5. 试玩。** 会用到你配置的模型。网页:Template 页的「去测试台跑 →」;终端:运行 `neonrp`,在 Launcher 里选这个模板。

<!-- section: lint -->
## 用 lint 保证引擎跑得动

lint 先把模板建成一局,再查引用、素材、提示词、剧情、合约、语言。每一项是 **block**(拦下发布)或 **warn**(只提醒)。

```bash
neonrp template lint <模板文件夹>      # 最后一行:publishable / NOT publishable
(cd <模板文件夹>/world && neonrp validate)
neonrp template build <模板文件夹> /tmp/try-<id>
```

agent 的规矩:**改到 0 block 为止**。每条 block 的原文和修法都告诉作者;warn 逐条读,能修的修。

发布时还有一道检查。本机网页 Template 页点「发布」,引擎先查五件事,有一件不过就什么都不发:

| 检查 | 不过时 |
|---|---|
| 链接的角色都在本机角色库 | `{"lib": …}` 指向的角色找不到 |
| 没有密钥 | 文件里有像 API key 的字符串 |
| Lint 没有 block | 还有必须改的问题 |
| 四语卡面 | 中 / 英 / 日 / 韩任一种缺标题或简介 |
| 有封面 | `card.cover` 没指向模板里的一张图 |

平台收到后还会再跑一遍自己的自动检查。详见 [Lint](/docs/creators/lint) 和 [发布到 Hub](/docs/creators/publish)。发布由作者自己点。

<!-- section: skill -->
## skill 的位置

| 文件 | 内容 |
|---|---|
| `.claude/skills/world-creation/SKILL.md` | 步骤:准备 → 读设定稿 → 建模板 → 打开网页 → 分段写 → 不调模型的检查 → 试玩 → 交付 |
| `.claude/skills/world-creation/references/world-spec-template.md` | 设定稿的填写格式,四份合约速查 |
| `.claude/skills/world-creation/references/spec-to-files.md` | 设定稿每一段写进哪些文件,附实测例子 |
| `.claude/skills/world-creation/examples/tidepool/world-spec.md` | 一份完整的小设定稿 |

Codex 用的同一份在 `.agents/skills/world-creation/`。每个模板文件夹里还有 `AGENTS.md` 和 `spec/`,agent 改之前会先读,见 [给 agent](/docs/agents/overview)。

引擎包里也带着同一份:`neonrp spec skill` 打印它在本机的文件夹,`neonrp spec skill world-creation` 打印 `SKILL.md`。引擎不会把它装进任何 agent,要用时按上面「装 skill」放到 agent 的 skills 目录。
