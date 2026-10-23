# Stoneford Elena — 石津镇·艾琳娜

> 基于 `llm-rpg-starter`/`stoneford-orch` 真实 contract 的混合模板：旧 world contract 保留，新的 soul runtime 已接入。

`stoneford-elena` 不是把 `stoneford-orch` 全盘推倒重写，而是在它真实跑通过的
world-agent / town-agent / rules-referee contract 上，叠加 `playthrough.json + souls/`
与 `soul.md`。

## What This Demo Is

- 一个可测试的第二世界
- 一个保留 `game/player/` 兼容层的 soul-native 过渡模板
- 一个拥有明确 heroine 的 Stone Ford 变体

## Runtime Shape

At runtime, this world behaves as:

`world-agent -> active souls -> world-agent`

while still retaining the Stone Ford domain-agent contract family under `agents/`.

## Source Of Truth

- `game/` remains world-agent-owned world state.
- `souls/elena-si-elena0001/` is Elena's soul truth.
- `game/player/*` is a compatibility projection for the current orchestrator-era
  Stone Ford contract. It is useful, but it is not the only truth source anymore.

If soul identity and `game/player/*` drift, treat the soul folder as the long-term
character source and `game/player/*` as the local world-facing projection that should be
reconciled.

## Included Souls

- `elena-si-elena0001` — heroine / player soul
- `rowan-si-rowan0001` — 碧石镇的年轻冒险者 soul，追逐“世界边界”的深洞传说

## Why This Exists

Kagura proves the pure soul-native path. Stoneford Elena proves the migration path:
you can keep a proven world contract while gradually moving protagonist logic from
`game/player/` toward explicit soul bundles.
