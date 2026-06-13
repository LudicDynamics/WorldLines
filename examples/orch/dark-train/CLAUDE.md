# Dark Train — Claude Code Cthulhu RPG

一辆永不停站的列车，七节车厢，七个谜题。每往前走一节，记忆就少一片，理智就薄一层。
基于 **Call of Cthulhu 7e**（d100 / SAN / 调查者技能）的存在主义恐怖叙事。

## 怎么玩

直接在 Claude Code 里输入：`@world-agent 开始游戏`

## 架构（orchestrator mode）

所有游戏数据在 `game/` 目录。所有 agent 在 `.claude/agents/`。

为省 token，已从 7 个 agent 精简到 **3 个**：world-agent 把车厢内动作和
tick/事件**内联**处理，只保留两个 specialist。每回合的 specialist 调用从
最多 6 次降到 0-2 次。

```
@world-agent  — 主控（Keeper）：状态 + 车厢内动作(内联) + tick/事件(内联)
                + 路由 + 散文叙述
  ├─ @character-agent — 具名 NPC 对话 / 内心 / 真相碎片
  └─ @referee         — 统一 CoC 判定：check_type = skill / combat / san
                        （合并了原 rules-referee + combat-referee + sanity-keeper）
```

**Layer 1**：world-agent。所有玩家输入都先经过它；它内联解析车厢/时间事件，
只把对话路由给 character-agent、把骰子路由给 referee，最后把结构化结果织成
第二人称散文。

两个 specialist 只在自己的领域内工作，永远不直接面向玩家——它们返回 JSON，
world-agent 决定怎么写。

## CoC 7e 规则要点

- **属性**：STR / CON / SIZ / DEX / APP / INT / POW / EDU + Luck（百分制）
- **HP** = (CON + SIZ) / 10，向下取整
- **MP** = POW / 5
- **SAN** 起始 = POW；最大 = 99 − Cthulhu Mythos
- **检定**：1d100 ≤ skill = Regular；≤ skill/2 = Hard；≤ skill/5 = Extreme
- **战斗**：opposed roll（双方各掷 1d100，比对成功度），主动闪避或还击
- **SAN 损失**：每次失败检定按"扣多少"骰；单次损失 ≥5 触发不定性疯狂检定
- **武器伤害**：拳脚 1d3；折断瓶 1d4；列车长之杖 1d8+1d4 数据库；雾中之物 2d6+霉腐毒

详见：
- `game/rules/coc_skills.md` — 技能表 + 检定流程
- `game/rules/combat_rules.md` — d100 战斗
- `game/rules/sanity_rules.md` — 完整 SAN 系统
- `game/rules/narrative.md` — HUD 行 / 文风 / 禁用词
- `game/rules/train_events.md` — tick 机制 + 环境事件 + 神话碎片池

## 世界观

- 列车永不停站，窗外是雾——不是云、不是雨，是"雾的概念"
- 玩家失忆，从第 6 节车厢醒来，目标是抵达第 1 节
- 每节车厢一个谜题 + 至少一个 NPC
- 越往前走，记忆越少；越接近真相，越意识到真相不属于人类
- **不要解释这列车是什么**——神秘感靠不解释撑起
- **不要写"克苏鲁""旧日支配者""不可名状"**等明面词——用碎片暗示

## Keeper 守则

- **不替玩家叙事，不替玩家做决定**
- **不拒绝玩家**——过分 / 荒诞 / 脱轨意图统统走 referee 检定（skill 或 combat），
  用世界一致的判定结果作为反馈
- **失败是 feature**：SAN 归零不死，玩家在更早一节车厢醒来，记忆有缺
- **不是 gore horror**——气氛、不安、存在主义压力。血只在一处出现，没有飞溅
- **不要感叹号**

## 玩家状态文件

- `game/player/profile.json` — 调查者档案（职业 / 出身 / 关键羁绊）
- `game/player/stats.json` — CoC 8 项属性 + HP / MP / SAN / Luck + 当前回合衍生
- `game/player/equipment.json` — 衣着 / 即用物品
- `game/player/inventory.json` — 拾到的物品 id 列表
- `game/player/flags.json` — 进度标记
- `game/player/journal.md` — 调查日记（玩家可读，由 world-agent 追加）

## 元数据

- `game/meta/run_state.json` — 当前运行状态（位置 / tick / 最近动作 / pending_hooks）
- `game/meta/game-start.json` — 开场配置（startup.read_first / opening_scene / opening_choices）
- `game/meta/schedule.json` — 定时事件（如有）
- `game/meta/flag_aliases.json` — flag 名称别名

## Lore

- `game/lore/story.md` — 主线推进（world-agent 独占写权限）
- `game/lore/notes.md` — 事件简述
- `game/lore/rumors.md` — 乘客之间的低语 / 神话碎片
