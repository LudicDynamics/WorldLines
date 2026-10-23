---
title: "实时事件流"
description: "重前端要接的:说一句、收逐字流、收拍事件、停止、结算。"
---

<!-- section: loop -->
## 一回合的往返

> **状态:随 1.0 发布**

```text
POST /cmd {"text": "我去后院看看"}          → 回合开始(另一句还在跑时 409)
GET  /events                                ← SSE:chunk … chunk → 拍事件 … → positions → turn_done
POST /cancel                                → 让正在跑的回合做完当前这一步就停
```

页面先连 `/events`(一条长连接,收到 `hello` 就是连上了),再发 `/cmd`。

<!-- section: stream -->
## `/events` 上的消息

| kind | 什么时候 | 字段 |
|---|---|---|
| `hello` | 连上时 | 这一局的概况 |
| `turn_start` | 一句开始 | `text` |
| `chunk` | 叙事逐字到达 | `text`;角色说的每个字带 `[[subagent:名字]]`,没带的是主持 |
| `thinking` | 模型的思考(如果提供) | `text` |
| `tool` | 回合中调用了工具 | `name` |
| `soul_status` | 角色的状态变了 | `statuses` |
| 拍事件 | 一句落定后,按顺序 | 见下表 |
| `positions` | 拍事件之后 | 谁在哪 |
| `turn_done` | 一句结束 | `success` · `error` · `narration` |
| `rebound` | 引擎换了一局 | 这条流属于旧一局:断开重连 |

<!-- section: beats -->
## 拍事件

| kind | 是什么 | 主要字段 |
|---|---|---|
| `node.enter` / `node.leave` | 进 / 出编排图的节点(商量 · 清算 · 战斗层 …) | `node` |
| `plan.beat` | 商量拍:主持的话、递话筒给谁、约好的检定 | `script` · `mic` · `board` · `checks` |
| `resolve.beat` | 清算拍:谁推进的、叙事、选项 | `text` · `options` · `rolled` |
| `dice` | 每一次掷骰 | `request` · `answer` |
| `tool` | 其他工具调用 | `request` · `answer` · `async` |
| `state.changed` | 落到世界上的改动 | `applied` · `created` · `refused` |
| `run.settled` | 到出口了 | 结算(见下) |

断线重连后补历史:`GET /api/v1/play/engine/beats?since=N` → `{events, next}`,和实时流同名同形。

<!-- section: reads -->
## 随时可读

```
GET /api/v1/play/engine/settlement        这一局的结算(没到出口时为空)
GET /api/v1/play/engine/entities?cls=status   某一类实体和属性(如你身上的状况)
GET /api/v1/play/engine/graph             生效的编排图
GET /api/v1/play/engine/contract          这一局的合约
GET /traces · /trace?i=N                  每一句的完整记录
```

前端台「事件流」里能实时看到这些事件,每条带 Godot / TS 的接法。字段全表:模板文件夹里的 `spec/` 和 `neonrp spec http`。
