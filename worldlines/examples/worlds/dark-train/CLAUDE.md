# Dark Train — Claude Code 沙盒跑团（BRP）

一辆永不停站的列车，七节车厢，七个谜题。每往前走一节，记忆就少一片，理智就薄一层。
基于 **BRP**（Chaosium《Basic Roleplaying: Universal Game Engine》，ORC License；d100 / 理智 / 技能）
加本世界自有规则的存在主义恐怖叙事。设定内容采用 CC-BY-4.0。

## 怎么玩

直接在 Claude Code 里输入：`@world-agent 开始游戏`

## 架构（orchestrator mode）

所有游戏数据在 `game/` 目录。所有 agent 在 `.claude/agents/`。

为省 token，已从 7 个 agent 精简到 **3 个**：world-agent 把车厢内动作和
tick/事件**内联**处理，只保留两个 specialist。每回合的 specialist 调用从
最多 6 次降到 0-2 次。

```
@world-agent  — 主控（主持 / GM）：状态 + 车厢内动作(内联) + tick/事件(内联)
                + 路由 + 散文叙述
  ├─ @character-agent — 具名 NPC 对话 / 内心 / 真相碎片
  └─ @referee         — 统一 BRP 判定：check_type = skill / combat / san
                        （合并了原 rules-referee + combat-referee + sanity-referee）
```

**Layer 1**：world-agent。所有玩家输入都先经过它；它内联解析车厢/时间事件，
只把对话路由给 character-agent、把骰子路由给 referee，最后把结构化结果织成
第二人称散文。

两个 specialist 只在自己的领域内工作，永远不直接面向玩家——它们返回 JSON，
world-agent 决定怎么写。

## BRP 规则要点

- **属性**：STR / CON / SIZ / INT / POW / DEX / CHA + EDU，3–18
- **HP** = (CON + SIZ) / 2，向上取整；单次伤害 ≥ 最大 HP 一半 = 重伤
- **伤害加值**：按 STR + SIZ 查表（17–24 无，25–32 +1D4，13–16 −1D4）
- **检定**：1d100 ≤ 技能 = 成功；≤ 1/5 = special；≤ 1/20 = critical；99/00 = fumble
- **难度**：Easy ×2 / Average / Difficult ×½
- **战斗**：按 DEX 由高到低行动；攻击成功后防守方可闪避，等级不低于攻击即挡下
- **理智（可选规则）**：SAN 起始 = POW × 5，上限 99；d100 对当前 SAN，失败（有时成功也）扣；
  一拍之内失去当时 SAN 的一半 → 临时疯狂

## 本世界自有规则

- **禁知（Forbidden Lore）**：理解这列车是什么的程度，从 0 起；每 1 点让最大 SAN −1；
  可掷来认出征兆，成功要付 SAN
- **付代价再试**：普通失败后可再试一次，但要先说出主持接受的具体代价
  （声响 / 工具坏掉 / NPC 的信任 / 下一次理智损失 +1）；再试出 fumble，这条路就关了
- **记忆碎片**：乘客醒来时不记得任何训练；找回一片记忆，相关技能 +1D6+5%
- **SAN 或 HP 归零不死**：在更早的车厢醒来（dispersal），记忆有缺
- **临时疯狂表 / 残留印记表**：本世界自写的列车主题表

详见：
- `game/rules/skills.md` — 技能表 + 检定流程 + 付代价再试 + 记忆碎片
- `game/rules/combat_rules.md` — d100 战斗
- `game/rules/sanity_rules.md` — 理智 + 临时疯狂 + 禁知 + dispersal
- `game/rules/narrative.md` — HUD 行 / 文风 / 禁用词
- `game/rules/train_events.md` — tick 机制 + 环境事件 + 低语碎片池

## 世界观

- 列车永不停站，窗外是雾——不是云、不是雨，是"雾的概念"
- 玩家失忆，从第 6 节车厢醒来，目标是抵达第 1 节
- 每节车厢一个谜题 + 至少一个 NPC
- 越往前走，记忆越少；越接近真相，越意识到真相不属于人类
- **不要解释这列车是什么**——神秘感靠不解释撑起
- **永远不要给那个东西起名字**，也不写「不可名状」之类的明面词——用碎片暗示

## 主持守则

- **不替玩家叙事，不替玩家做决定**
- **不拒绝玩家**——过分 / 荒诞 / 脱轨意图统统走 referee 检定（skill 或 combat），
  用世界一致的判定结果作为反馈
- **失败是 feature**：SAN 归零不死，玩家在更早一节车厢醒来，记忆有缺
- **不是 gore horror**——气氛、不安、存在主义压力。血只在一处出现，没有飞溅
- **不要感叹号**

## 玩家状态文件

- `game/player/profile.json` — 乘客档案（职业 / 出身 / 关键羁绊）
- `game/player/stats.json` — BRP 属性（3–18）+ HP / SAN / 禁知 + 技能
- `game/player/equipment.json` — 衣着 / 即用物品
- `game/player/inventory.json` — 拾到的物品 id 列表
- `game/player/flags.json` — 进度标记
- `game/player/journal.md` — 乘客日记（玩家可读，由 world-agent 追加）

## 元数据

- `game/meta/run_state.json` — 当前运行状态（位置 / tick / 最近动作 / pending_hooks）
- `game/meta/game-start.json` — 开场配置（startup.read_first / opening_scene / opening_choices）
- `game/meta/schedule.json` — 定时事件（如有）
- `game/meta/flag_aliases.json` — flag 名称别名

## Lore

- `game/lore/story.md` — 主线推进（world-agent 独占写权限）
- `game/lore/notes.md` — 事件简述
- `game/lore/rumors.md` — 乘客之间的低语 / 碎片
