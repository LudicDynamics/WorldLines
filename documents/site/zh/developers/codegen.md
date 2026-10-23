---
title: "代码生成"
description: "从同一份契约生成各端客户端。"
---

<!-- section: targets -->
## 目标

> **状态:设计中 · 接口为拟定** —— 3.0 定下的设计,名字和字段在实装前可能还会改。

| 目标 | 生成物 |
|---|---|
| TypeScript | `stoneford.world.ts`:类型化客户端,WorldLines 的界面和工作台直接用 |
| Godot | `stoneford_world.gd`:每个变量一个带类型的属性,每个 hook 一个 `signal`,每个 op 一个方法 |
| Python | 类型化包装,给测试与 benchmark |
| LLM | 同一份契约的文字版 |

<!-- section: ts -->
## TypeScript

```ts
const w = await StonefordWorld.connect("http://localhost:8788");
w.on("price.T001.jade", (v) => hud.set(v));
const r = await w.trade({ town: "T001", good: "grain", qty: 3 });
if (!r.ok) toast(r.refused[0].why);   // 「钱不够:要 36 铜,你只有 20 铜」
```
