# ⛩ 神楽島 Kagura Island — 多智能体世界

**Language:** [English](./README.md) · [简体中文](./README.zh.md) · [日本語](./README.ja.md) · [한국어](./README.ko.md)

> 引擎模式:**multi-agent**。和风悬疑 · 时间循环 · Yith 神话。一座岛上**七个活的灵魂** —— WorldLines 最丰富的多智能体社会。CoC 式判定(非 d20 战斗)。

**[▶ 在线游玩 →](https://hub.worldlines.gg/play/worlds/kagura-island)**

## 为什么这是 multi-agent

`fast` 和 `orch` 模式跑 **world-agent + domain agents**,NPC 是数据。**multi-agent** 多了 `souls/` 文件夹,每个 soul 是**独立心智的角色 agent**。神楽島是旗舰展示:**七个 soul** 并行思考、谋算、记忆,由 world-agent 包装:

```
world-agent  →  active souls (本回合的 actor)  →  world-agent
  (主权编排器)    每个 soul:说话 / 行动 /          (单一世界收口边界,
                  内心独白,各有自己的盘算)            向你叙述)
```

`playthrough.json` 声明每回合哪些 soul 激活。Soul 是隔离的 actor —— 不是对等网,而是 world-agent **主导的 actor 集合**,只有一个世界收口边界。岛会记住;循环转动;每个 soul 带着自己的秘密穿过它。

```bash
neonrp tui --from examples/kagura-island
```

## 七个灵魂

| Soul | id |
|---|---|
| **镜子** Kagami | `kagami-si-kagami001` |
| **羽** Hane | `hane-si-hane0001` |
| **真琴** Makoto | `makoto-si-makoto001` |
| **宫司** Miyaji | `miyaji-si-miyaji001` |
| **白** Shiro | `shiro-si-shiro0001` |
| **翼** Tsubasa | `tsubasa-si-tsubasa01` |
| **悠人** Yuto | `yuto-si-yuto0001` |

每个 soul 文件夹遵循 bundle 结构:`soul.json` / `soul.md`(身份)、`persona/`(特质、价值、关系)、`background/`(历史、出身、秘密)、`character/`(档案、属性、物品)、记忆(`long-term-memo/` + `short-term-memo/`)、`rules/`(每个 soul 的守则)、`agents/`(soul 的心智)、`trajectory/`(经历)。

## 世界

`agents/` = world-agent + 城镇 / 战斗 / 故事 / 世界构建 / NPC 构建 / 规则裁判。`game/` 保存岛的真相(lore、地点、物品、时间线;GM 真相在 `game/lore/gm-truth.md` —— 仅 world-agent 可读)。`runtime_contract.json` 保留路由外壳;因为根目录有 `playthrough.json + souls/`,运行时进入 soul 包装流程。

> 时间循环 · 理智 · 禁忌:不可逆后果,CoC 式。玩家是**人类**,绝不扮演任何具名 soul。

## 许可证

**AGPL-3.0** —— fork、修改、发布你自己的。引擎(`neonrp`)是专有预览版。
