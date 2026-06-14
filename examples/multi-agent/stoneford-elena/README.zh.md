# 🌿 石津镇 · 艾莲娜 — 多智能体世界

**Language:** [English](./README.md) · [简体中文](./README.zh.md) · [日本語](./README.ja.md) · [한국어](./README.ko.md)

> 引擎模式:**multi-agent**。石津镇世界,现在住进了活的灵魂 —— **Elena**(艾莲娜)和 **Rowan**(罗恩)—— 她们自己思考、记忆、行动。

> **本地运行**(TUI / CLI):`neonrp tui --from examples/orch/stoneford-elena`。Elena 另有在线 soul 对话:**[和 Elena 对话 →](https://hub.worldlines.gg/play/souls/elena)**

## 为什么这是 multi-agent

`fast` 和 `orch` 模式跑的是 **world-agent + domain agents**(城镇、地下城、战斗)。NPC 是数据,由编排器代言。

**multi-agent** 多了一个 `souls/` 文件夹。每个 soul 是**独立的角色 agent**,有自己的人格、记忆、秘密和目标 —— 它们为自己思考。运行时进入 soul 包装流程:

```
world-agent  →  active souls (Elena, Rowan)  →  world-agent
  (主权编排器)    每个 soul 自己决定                (收束这一回合,
                  说什么 / 做什么 / 内心独白)          向你叙述)
```

Soul 是隔离的 actor —— 不共享文件夹,也不拥有世界状态。Elena 记得你三天前说过的话;Rowan 追逐自己的目的,不管你在不在。这就是**村庄/社会**模型的实践。

```bash
neonrp tui --from examples/orch/stoneford-elena
```

## 灵魂

| Soul | 是谁 |
|---|---|
| **Elena**（`elena-si-elena0001`） | 会记住的治愈师 —— 温柔、敏锐,背着自己的过去 |
| **Rowan**（`rowan-si-rowan0001`） | 有自己的动机,有自己的时间线 |

每个 soul 文件夹遵循 bundle 结构:`soul.json` / `soul.md`(身份)、`persona/`(特质、价值、关系)、`background/`(历史、出身、秘密)、`character/`(档案、属性、物品)、`long-term-memo/` + `short-term-memo/`(记忆)、`rules/`(每个 soul 的守则)、`agents/`(soul 的 6-agent 心智)、`trajectory/`(它经历过什么)。

## 世界

建在 Stoneford orch 世界之上(`agents/` = world-agent + 城镇 / 地下城 / 战斗 / 故事 / 世界构建 / 规则 / 时钟 / 演变 / 角色 agent),`game/` 保存世界真相。灵魂活在它之上。

## 许可证

**AGPL-3.0** —— fork、修改、发布你自己的。引擎(`neonrp`)是专有预览版。
