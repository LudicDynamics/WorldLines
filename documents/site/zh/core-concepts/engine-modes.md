---
title: "引擎模式 —— 多智能体模拟(+ 轻量的 Fast / Orchestrator)"
description: "WorldLines 本身就是一个多智能体模拟:一个 world-agent 包裹着一群独立的灵魂。Fast 和 Orchestrator 是面向更简单单线场景的轻量模式。"
---

<!-- section: comparison -->
## 一览

| 模式             | 每回合谁在跑                                                     | 状态                          |
|------------------|------------------------------------------------------------------|-------------------------------|
| **Multi-Agent**  | 一个 world-agent 包装**活动灵魂** —— 每个都是有自己心智的独立角色 agent | ✅ 已发布(v0.2.3,本地)     |
| **Orchestrator** | 一个 world-agent 通过 `task()` 路由到 domain agent              | ✅ 已发布                      |
| **Fast**         | 单个 agent,最少路由                                              | ✅ 已发布                      |

**多智能体(Multi-Agent)就是引擎本体** —— 一个 world-agent 包裹着一个由独立灵魂组成的社会,每个都有自己的心智。这就是村庄模型,也是每个世界的归宿。**Orchestrator**(world-agent 路由到数据驱动 NPC 的领域 agent)和 **Fast**(单个 agent)是面向更简单单线场景的轻量模式。三者写入相同的事件日志格式、持久化状态完全相同 —— 区别只在于**每个回合是什么在思考**。

**多智能体在本地运行**(TUI / CLI);hosted play 目前提供轻量的 Fast + Orchestrator。它可复现:任何带 `souls/` 文件夹 + `playthrough.json` 的世界都会启用它。见 [worldlines/templates/stoneford-town.template](https://github.com/LudicDynamics/WorldLines/tree/main/worldlines/templates/stoneford-town.template)(石津镇)和 [worldlines/templates/pct-house.template](https://github.com/LudicDynamics/WorldLines/tree/main/worldlines/templates/pct-house.template)(灰橡宅,2 个灵魂)。

<!-- section: fast -->
## Fast 模式

**单个 agent** 端到端地处理这一回合。没有 orchestrator,没有委托,也不调用 `task()`。

**适合**:
- 每回合 LLM 成本最低
- 创作时的快速迭代
- 无需路由的重叙述场景

**局限**:
- 没有子 agent 的专长 —— 战斗问题与叙述由同一个 agent 处理
- 在跨领域的复杂场景中,状态漂移风险更高

<!-- section: orchestrator -->
## Orchestrator 模式

Stoneford 的默认模式。一个 **orchestrator** / 叙述者 agent 位于领域 agent(town / dungeon / combat-referee / world-builder / rules-referee)之上,**每回合通过 `task()` 工具重新路由**。

**适合**:
- 跨越多个领域的场景(城镇中的战斗、地下城里的仪式等)
- 任何需要规则一致性的时刻
- 经典玩法循环

**成本**:
- 每回合都要支付 orchestrator + 至少一个领域 agent 的成本
- 延迟有上限,但比 Fast 高

<!-- section: multi-agent -->
## Multi-Agent 模式 —— 村庄模型 ✅

**v0.2.3 已发布(本地)。** 这就是**村庄**。不再由一个叙述者扮演每个角色,而是**每个角色都是它自己的 AI agent** —— 一个"灵魂",有自己的个性、记忆、秘密和目标。它们为自己思考。

一个 **world-agent** 像游戏主持人一样主持场景:每回合它唤醒在场的角色,让每个角色决定说什么、做什么,再把它们的行动编织成一段统一的叙述。

```
              world-agent  (the host / narrator)
                    │  wakes whoever is in the scene
          ┌─────────┼─────────┐
       Kagami     Hane      Shiro      ← each an independent soul:
      (own mind) (own mind) (own mind)    its own memory, agenda, voice
          └─────────┼─────────┘
                    ▼
              world-agent  → narrates the turn; the world remembers
```

**为什么重要**

- **每个角色都是真实的。** Elena 不是叙述者替她写的一句台词 —— 她是一个为自己做决定、能让你意外的 agent。
- **它们会记住。** 灵魂跨回合保留自己的记忆、关系和个人弧线,于是村庄会演化,角色会提起你早先做过的事。
- **灵魂可携带。** 因为每个灵魂都是自包含的,同一个 Elena 可以从 Stoneford 走进 Kagura Island,依然是她自己。

**试一试**(目前本地运行):

```bash
neonrp template build worldlines/templates/pct-house.template /tmp/pct-house && neonrp play --project /tmp/pct-house   # 灰橡宅
neonrp template build worldlines/templates/stoneford-town.template /tmp/stoneford-town && neonrp play --project /tmp/stoneford-town   # 石津镇
```

任何带 `souls/` 文件夹 + 一个 `playthrough.json` 的世界都会自动变成一座村庄。用 `soul-authoring` 工作流创作你自己的角色。

hosted play(WebHub)目前覆盖 Fast + Orchestrator;让村庄上线是另一条独立的工作线。

<!-- section: switching -->
## 切换 router 模式

Router 模式是逐回合的,不是逐项目的。在 TUI 中切换:

```
/router-mode fast
/router-mode orchestrator
/router-mode multi-agent
```

或者给 `neonrp run` 传 `--router-mode <mode>`。session 日志会在每个事件上记录 router 模式,使回放始终忠实。
