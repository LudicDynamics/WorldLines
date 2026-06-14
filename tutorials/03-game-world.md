# 03 · 从零搭一个会呼吸的世界（orch）

**目标:** 用 AI 助手搭一个完整的、可在终端里玩的 **orch 世界** ——
一个 world-agent 当旁白主控,编排若干领域 agent,NPC 是它发声的数据。
**用到的 skill:** `entity-authoring`(写 `game/` 实体时自动触发)。
**参考范本:** [`examples/orch/sakura-hallway`](../examples/orch/sakura-hallway)(校园恋爱)、
[`examples/orch/otome-lamp`](../examples/orch/otome-lamp)(国风乙女宫廷)。
**产出:** 一个 `<世界>/zh/` 目录,`neonrp tui --from` 直接能跑。

> orch 世界 = **结构 + 数据 + agent 提示词**。好消息是它有**固定骨架**,你不用从白纸开始 ——
> 让助手「照着 sakura-hallway 的结构」改写成你的题材,是最快的路。

## orch 世界的骨架

照 `examples/orch/sakura-hallway/zh/` 看,一个 orch 世界长这样:

```
<世界>/zh/
  .neonrp/config.json            # LLM provider、narrator agent
  .neonrp/runtime_contract.json  # 路由:玩家所在地点 → 哪个 agent
  .claude/agents/*.md            # 每个 agent 的薄包装(给 Claude Code 跑时用)
  agents/<id>/agent.json         # agent 的能力/读写权限/角色名
  agents/<id>/system.md          # agent 的规范提示词(灵魂所在)
  game/agents/manifest.json      # 编排说明:谁是 Layer1、谁返回 JSON
  game/meta/game-start.json      # 开场场景 + 首批选项
  game/meta/run_state.json       # 运行时状态(天数/计时器/焦点角色…)
  game/meta/active-agent.json    # 当前活跃 agent
  game/player/player.json        # 玩家是谁
  game/npc/<id>.json             # 每个 NPC = 一份数据(性格/好感/记忆)
  game/location/<id>.json        # 每个地点
  game/rules/*.md                # 规则(好感系统、结局表…)
```

典型的 orch 恋爱世界用**两个 agent**:
- `world-agent`(Layer 1)—— 旁白主控:替所有 NPC 发声、推进时间线、调子 agent、**落盘**。
- `heart`(Layer 2)—— 只做一件结构化判定(好感增减),返回 JSON,**不写文件**(world-agent 落盘)。

这套「一个主控 + 一个只返回 JSON 的判定 agent」是 orch 最容易上手的形态。

## 一步步

### 1. 让助手照范本改写题材（可直接抄）

> 照 `examples/orch/sakura-hallway/zh/` 的**完整结构**,帮我搭一个新 orch 世界,放到
> `examples/orch/<我的slug>/zh/`。题材换成:**赛博朋克酒吧里的调酒师恋爱** ——
> 玩家是新来的调酒学徒,攻略对象是 3 个常客。把「樱花飘落的计时器」换成「店要被收购前的倒计时」,
> 「好感」保留。NPC、地点、开场、规则都按新题材重写,**结构和 agent 分层不要改**。
> 中文写内容,id/字段名英文。

助手会逐个文件改写,`entity-authoring` skill 会保证 `game/` 下实体的
`id` / `kind` / 路径三者一致、引用不悬空。

### 2. 先把「数据三件套」定下来

最影响体验的是这三类文件,让助手一个个跟你确认:

- **`game/npc/<id>.json`** —— 每个攻略对象。关键字段:`personality`(性格)、
  `speaking_style`(声口)、`likes` / `cares_about`(在意什么)、`secret`(软肋/隐秘)、
  `affection`+`affection_level`(好感)、`memory: []`(空数组,玩时填)。
- **`game/meta/game-start.json`** —— `opening_scene`(开场叙述)+ `opening_choices`(首批选项)。
  这是第一印象,值得多打磨。
- **`game/rules/affection.md`** —— 好感分几级、每级什么表现、计时器怎么减。
  world-agent 全靠它守基调。

### 3. 写好两个 agent 的 system.md（世界的灵魂)

- `agents/world-agent/system.md` —— 定**铁律**:每拍调 heart→立刻把好感/记忆写回文件、
  一拍一停、记忆会回响、什么时候到结局。照范本的「⛔ 铁律」段改最稳。
- `agents/heart/system.md` —— 定**判定边界**:delta 范围、什么加分什么减分、只回 JSON。

> 想看一个**加了机制**的范本:`examples/orch/otome-lamp` 在恋爱骨架上加了
> 「3 处命运抉择 × 8 种结局」和「四轴心迹」,都写在 `game/rules/endings.md` 里 ——
> 可以直接让助手「参考 otome-lamp 的 endings.md 给我的世界加一套分支结局」。

### 4. 校验 + 试玩

```
# JSON 全部合法?让助手跑一遍,或:
find examples/orch/<我的slug> -name '*.json' -exec python3 -m json.tool {} \; >/dev/null

# 装了引擎就能直接玩:
neonrp tui --from examples/orch/<我的slug>/zh
```

进去打「开始游戏」,world-agent 会读 `game-start.json` 开场。玩几拍,检查:
- 好感有没有**真的写回** `game/npc/<id>.json`?(玩完看文件 `affection` 变没变)
- 角色会不会**提起你之前说的话**?(`memory` 数组有没有累积)
- 计时器有没有在减?到点/满好感有没有走结局?

这三点对了,你的 orch 世界就立住了。

## 小抄

- **别从白纸搭,照范本改。** sakura-hallway 是最小恋爱范本,otome-lamp 是加机制的范本。
- **world-agent 负责落盘,子 agent 只返回 JSON。** 这是 orch 不失忆的关键,别让子 agent 写文件。
- **一拍一停。** 在 system.md 里把这条写死,否则模型会一口气把关系演完。
- 想让世界跑在云端 hub(别人浏览器直接玩):orch 世界是支持的,做完后参考
  [docs.worldlines.gg](https://docs.worldlines.gg) 的发布流程导入。

---

下一篇:**[04 · Soul 与多 agent](./04-soul-multi-agent.md)** —— 做有独立心智的角色,搭多 agent 世界。
