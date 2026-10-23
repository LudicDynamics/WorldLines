# 石津镇·艾琳娜

> 基于 `llm-rpg-starter`/`stoneford-orch` 真实契约的混合模板：旧的世界契约保留，新的 soul 运行时已接入。

`stoneford-elena` 不是把 `stoneford-orch` 全盘推倒重写，而是在它真实跑通过的
world-agent / town-agent / rules-referee 契约上，叠加 `playthrough.json + souls/`
与 `soul.md`。

## 这个 Demo 是什么

- 一个可测试的第二世界
- 一个保留 `game/player/` 兼容层的 soul 原生过渡模板
- 一个拥有明确女主角的石津镇变体

## 运行时形态

运行时，这个世界的流转是：

`world-agent -> 在场 souls -> world-agent`

同时仍在 `agents/` 下保留石津镇那一族领域代理契约。

## 真实来源

- `game/` 仍是 world-agent 所有的世界状态。
- `souls/elena-si-elena0001/` 是艾琳娜的 soul 真相。
- `game/player/*` 是面向当前 orchestrator 时代石津镇契约的兼容投影。它有用，
  但已不再是唯一的真实来源。

如果 soul 身份与 `game/player/*` 出现偏差，以 soul 文件夹作为长期的角色来源，
把 `game/player/*` 视为面向本地世界、需要对齐的投影。

## 内含的 souls

- `elena-si-elena0001` — 女主角 / 玩家 soul
- `rowan-si-rowan0001` — 碧石镇的年轻冒险者 soul，追逐“世界边界”的深洞传说

## 为什么有它

神乐岛验证的是纯 soul 原生路径。石津镇·艾琳娜验证的是迁移路径：
你可以保留一份已经跑通的世界契约，同时把主角逻辑逐步从
`game/player/` 迁向显式的 soul 包。
