# 04 · Soul 与多 agent 世界

**目标:** 用 AI 助手做一个 **soul(角色灵魂包)** —— 一个有自己心智、记忆、目的的角色,
可以单独对话(talk 模式),也可以放进世界跟别的 soul 共处(multi-agent)。
**用到的 skill:** `soul-authoring`(自动触发)。
**参考范本:** [`examples/multi-agent/kagura-island`](../examples/multi-agent/kagura-island)(7 个 soul)、
[`examples/multi-agent/stoneford-elena`](../examples/multi-agent/stoneford-elena)(2 个 soul)。
**产出:** `souls/<sid>/...` 一个自包含的角色包。

> soul 和 [教程 01](./01-character-card.md) 的角色卡**不是一回事**:角色卡是一段可移植的
> 人格描述,喂给模型;**soul 是一个会自己思考、行动、记事的 agent** —— 它有持久的内心状态,
> 玩的时候自己更新。multi-agent 世界 = world-agent 包裹多个独立 soul,这是 WorldLines
> 最核心、最像「社会」的玩法。

## soul 包的结构

照 `soul-authoring` skill,一个 soul 长这样:

```
souls/<sid>/
  soul.md                  # 散文宪章:声口、价值观、压力下的反应模式
  persona/                 # 不可变的心理内核
    core_traits.json       #   核心性格
    motivations.json       #   动机
    values.json            #   价值排序
    relationships.json     #   与他人的关系
  background/              # 不可变的来历
    origin.md / history.md / secrets.md
  character/              # RPG 数值(运行时可写)
    stats.json / inventory.json / equipment.json / wallet.json
  memory/                 # 种子记忆(玩时累积)
  …加上 6-agent 的 soul-agent manifest
```

关键区别:
- **persona / background 是「不可变内核」** —— 这个角色是谁,不会因为一局游戏改掉。
- **character / memory 是「运行时可写」** —— 数值会涨、记忆会累积,这是 soul「活着」的部分。

## 一步步

### 1. 在仓库根打开 AI 助手,描述这个灵魂（可直接抄）

> 用 soul-authoring 帮我做一个 soul,放到 `souls/`。
> 角色:**盐砚**,一个在边境驿站守了二十年的老兵,沉默、记仇、对年轻人却出奇地软。
> 表面只想守着驿站终老,心底藏着一桩没替战死的兄弟了结的事。
> 给我完整的 persona(性格/动机/价值观/关系)、background(来历/历史/秘密)、
> 起手数值,和几条种子记忆。中文写内容,字段名英文。

助手会:
- 自动加载 `soul-authoring` skill;
- scaffold 整个 `souls/盐砚/` 目录,写 `soul.md` 宪章 + persona/background/character/memory;
- 按 skill 的约定生成 soul-agent manifest(让这个 soul 能被当 agent 跑)。

### 2. 打磨「内核」三件事

soul 好不好,看这三块,挑重点让助手深化:
- **`soul.md`(宪章)** —— 一句话能不能说清「他在压力下会怎么反应」?让助手
  「在 soul.md 里写清楚:盐砚被触到那桩心事时,会怎么回避、又会在什么情况下松口」。
- **`persona/values.json`(价值排序)** —— 当两个价值冲突时他选哪个?这决定他的「人味」。
- **`background/secrets.md`(秘密)** —— 藏着的东西是角色的引擎。让它「把那桩没了结的事写具体」。

### 3. 单独跟他对话（talk 模式）

soul 可以不进任何世界,直接对话调教:

```
neonrp tui --from souls/盐砚      # 或参考 stoneford-elena 的 talk 入口
```

聊几轮,看他**记不记事**(memory 有没有更新)、**守不守人设**(会不会突然变性子)。

### 4. 把多个 soul 放进一个世界（multi-agent）

这是 multi-agent 的核心:一个 world-agent + 多个独立 soul。最快的路是照范本扩:

> 参考 `examples/multi-agent/stoneford-elena` 的结构,帮我搭一个 multi-agent 世界,
> 把我刚做的 `souls/盐砚` 和另一个 soul 一起放进去,world-agent 负责场景与撮合,
> 每个 soul 保持自己的心智。给我 `playthrough.json` 和 world-agent。

multi-agent 世界的签名是:`souls/` 目录 + `playthrough.json`。它**只在本地用
`neonrp play` 跑**(不是 hub 上的托管玩法):

```
neonrp play --project examples/multi-agent/<我的世界>
neonrp play --project examples/multi-agent/<我的世界> --json --trace   # 可脚本化/可复现
```

> 想做研究/复现实验,`--json --trace` 会把每个 soul 的决策链吐出来。
> 详见 [examples/multi-agent/](../examples/multi-agent/) 与 docs 的 multi-agent 教程。

## 小抄

- **soul ≠ 角色卡。** soul 有持久内心状态、会自己更新;角色卡是静态人格描述。
- **内核不可变,运行时可写。** persona/background 别让它在游戏里被改掉;character/memory 才是活的部分。
- **multi-agent 目前是本地玩法**(`neonrp play`),不是浏览器托管玩法 —— 这是有意的:
  让每个 soul 真正独立跑。
- 多个 soul 进一个世界,先各自单独调好再合 —— 范本是 kagura-island(7 soul)。

---

回到 **[教程总览](./README.md)**。做完东西想分享、想上 hub,去 [hub.worldlines.gg](https://hub.worldlines.gg)
或 [docs.worldlines.gg](https://docs.worldlines.gg)。
