---
title: "角色与多 Agent"
description: "一个世界以两种方式之一运行:编排式的 World-Agent 带 sub-agents(town / dungeon / npc),或多智能体村庄 —— 其中每个角色都是它自己的 Character-Agent,一个一等公民身份,拥有自己的灵魂、记忆、声线与 sub-agents。两者今天都已发布。"
---

<!-- section: today -->
## 今天 —— World-Agent + sub-agents

在 v0.1 中,世界里的每一个实体都通过一个顶层的 **World-Agent**(orchestrator / 叙述者)来触达。World-Agent 通过 `task()` 委托给它的 **sub-agents**:

| World-Agent 下的 Sub-agent  | 职责                                                         |
|-----------------------------|--------------------------------------------------------------|
| **Town sub-agent**          | 城镇内的地点、流动商贩、事件                                 |
| **Dungeon sub-agent**       | 地下城的地貌、陷阱、遭遇节奏                                 |
| **NPC sub-agent**           | 单个 NPC 的对白与反应(今天是共享池)                        |

这能跑通 —— 但每一个 NPC 都共享同一套叙事视角(World-Agent 的 system 提示词),而他们的"人格"是每回合从静态的角色 JSON 中重新拼出来的。

<!-- section: character-agent -->
## Character-Agent —— 一条并行分支 ✅

> **v0.2.3 已发布(本地)** —— 这就是多智能体村庄。见 [Multi-Agent 模式](/docs/core-concepts/engine-modes#multi-agent)。

World-Agent 与每个角色(一个 **灵魂 agent**)都是独立的 agent,通过一条共享的 **消息总线** 对话 —— 叙述者从不操纵角色:

```
   world-agent  ◄─────►┌────────────────┐◄─────►  soul-agents
   (host /             │  message bus   │         ┌─ Elena  (soul.md · memory · voice · subs)
    narrator)          └────────────────┘         ├─ Rowan  (its own mind)
                                                   └─ …

   The world-agent posts the scene to the bus; the souls present this turn
   each read it, decide their own speech / action / inner voice, and post
   back; the world-agent weaves the replies into a single narration.
```

每个灵魂拥有:

- **`soul.md`** —— 一份身份文档。核心价值观、过往经历、人际关系、心结。写一次,在重大剧情节点更新。
- **长期记忆** —— 跨会话的亲历经验。被压缩、可检索,能从 snapshot / load 中存活下来。
- **短期记忆** —— 当前场景的上下文。随着场景推移而衰减 / 压缩。
- **个性** —— 结构化特质(big-five、自定义维度,随作者所想)。
- **叙事风格** —— 她的声线,以提示词片段的形式存在。跨回合保持一致;即使 World-Agent 在她身边叙述,她的直接台词也保持人设。
- **自定义 sub-agents** —— 作者可以给一个角色她专属的委托者(Elena 可能有一个 `innkeeper` 技能 sub-agent 来处理菜单定价,一个 `confidante` sub-agent 用于促膝长谈的时刻)。按角色可组合,而不是被硬塞进共享的 NPC 池。

<!-- section: why-parallel -->
## 为什么并行,而不是嵌套

把 Character-Agent 放在 World-Agent **旁边**(而不是下面)之所以重要,是因为:

- 一个角色的身份不应该是世界逻辑的一个分支。当场景切换到新城镇时,Elena 应该还是 Elena。
- 记忆范围不同:World-Agent 记住世界事件;Character-Agent 记住*她的*事件。
- 声线能熬过场景切换 —— 同一个 Character-Agent 在她身处酒馆(town sub-agent)还是在地下城中逃亡(dungeon sub-agent)时,说话都是同一个她。
- 每个角色的自定义 sub-agents,比把它们全堆进共享 NPC 池更具扩展性。

这正是 **Multi-Agent 模式 —— 村庄**(✅ v0.2.3 已发布,见 [Router 模式](/docs/core-concepts/engine-modes#multi-agent))所承载的东西:每个角色都是它自己的 agent,跨回合握住笔并保有自己的记忆,而不是每回合被叙述者从头重新配音。

<!-- section: bridge -->
## 编排式或村庄 —— 今天两者都已发布

**编排式世界**(如 `stoneford`)把 NPC 当作 `game/npc/` 下的数据,通过 World-Agent 共享的 sub-agent 池来发声。简单、便宜,非常适合规则繁重的玩法。

**村庄世界**(如 `kagura-island` 和 `stoneford-elena`)给每个角色它自己的 Character-Agent:把一个 NPC 提升为 `souls/` 下的灵魂文件夹 + 一个 `playthrough.json`,它就会跨回合为自己思考。见 [Multi-Agent 模式](/docs/core-concepts/engine-modes#multi-agent)。

底层的 agent 结构见 [Agent 与编排](/docs/core-concepts/agents-orchestration),创作流程见 [构建角色 Agent](/docs/guides/building-character-agents)。
