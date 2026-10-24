---
title: "实时事件流"
description: "重前端要接的:说一句、收逐字流、收拍事件、停止、结算。"
---

<!-- section: loop -->
## 一回合的往返

```text
POST /cmd {"text": "我去后院看看"}          → 202,回合开始(另一句还在跑时 409 {"error": "busy"})
GET  /events                                ← SSE:chunk … 拍事件 … → positions → turn_done
POST /cancel                                → 让正在跑的回合做完当前这一步就停
```

页面先连 `/events`(一条长连接,收到 `hello` 就是连上了),再发 `/cmd`。走 JSON-RPC 时,同样的内容在 `/rpc/events` 的 `engine/stream` 和 `engine/beat` 上(见[协议](/docs/developers/protocol))。

**两种引擎出的拍不一样。** PyPI 发布版一回合可能有两拍:先商量(`plan.beat`,世界不动),谈妥后清算(`resolve.beat`)。从开源仓源码装的引擎只有清算拍,回合只出 `resolve.beat`(开场那一拍两种引擎都以 `plan.beat` 发出,带 `opening: true`)。同一份前端代码两种都能接:拍的名字和样式从 `GET /api/v1/play/engine/beat-kinds` 读,不要写死。

<!-- section: stream -->
## `/events` 上的消息

| kind | 什么时候 | 字段 |
|---|---|---|
| `hello` | 连上时 | 这一局的概况 |
| `turn_start` | 一句开始 | `text` |
| `chunk` | 叙事逐字到达 | `text`;角色说的每个字带 `[[subagent:名字]]`,没带的是主持 |
| `tool` | 回合中调用了工具 | `name` |
| `dice.rolled` | 骰子一掷出来就发,在叙事落地之前 | 和拍事件 `dice` 同样的数字(`total` · `vs` · `level` …);播过的可以按 `total`/`vs` 跳过后面那条 `dice` |
| `soul_status` | 角色的状态变了 | `statuses` |
| 拍事件 | 每一拍落地时,按顺序 | 见下表 |
| `trace` | 一句结束 | 这一句的回合记录(给玩家的页面会裁剪) |
| `positions` | 拍事件之后 | 谁在哪 |
| `turn_done` | 一句结束 | `success` · `error` · `route_decision` · `narration`;额度用完时带 `billing`,有拍超时时带 `timeouts` |
| `write_down.*` | 回合结束后 | 见下文「状态修正」 |
| `rebound` | 引擎换了一局 | 这条流属于旧一局:断开重连 |

模型的思考(`thinking`)只在测试台的 `/events?debug=1` 上出现。

<!-- section: beats -->
## 拍事件

每一拍落地时就单独推送:商量拍谈妥转清算时,`plan.beat` 先到,然后清算拍的叙事才开始流。

| kind | 是什么 | 主要字段 |
|---|---|---|
| `node.enter` / `node.leave` | 进 / 出编排图的节点(商量 · 清算 · 战斗等模式层) | `node` |
| `plan.beat` | 商量拍(发布版)或开场:主持的话、被问到的角色、计划板、谈定的检定 | `text` · `script` · `mic` · `board` · `checks` · `opening` · `ended_by`(谈妥转清算时) · `cg`(开场) |
| `resolve.beat` | 清算拍:叙事、选项 | `text` · `options` · `rolled` · `panels` · `advanced_by`;结构化操作带 `action` |
| `dice` | 这一拍的每一次掷骰 | `request` · `answer` · `total` · `vs` · `level` |
| `tool` | 其他工具调用 | `request` · `answer` · `async` |
| `state.changed` | 落到世界上的改动 | `applied` · `created` · `refused` · 得失 |
| `party.join` / `party.leave` | 角色跟上玩家 / 留下 | `sid` · `iid` · `name` · `why` |
| `stage.changed` | 剧情阶段变量变了 | `plot` · `var` · `from` · `to` · `cg?` |
| `show` | 现在该放一张模板图 | `slot` · `cls` · `inst` · `label` |
| `soul.mind` | 在场角色对这一拍的态度和打算 | `attitude` · `intent` · `follow` · `stay` … |
| `place.discovered` | 玩家知道了一个新地点 | `addr` · `name` · `parent` · `by` |
| `achievement.unlocked` · `reward.granted` · `milestone` | 成就 / 奖励卡 / 开放冒险的里程碑 | `id` · `title` … |
| `audio.cue` | 音乐 / 环境声换了 | `music` · `ambient` · `mood` · `fade_ms` |
| `run.settled` | 到出口了 | 结算 |

`plan.beat` / `resolve.beat` 带 `mentions`(正文里提到的实体及位置)。断线重连后补历史:`GET /api/v1/play/engine/beats?since=N` → `{events, next}`,和实时流同名同形。

<!-- section: writedown -->
## 状态修正

清算拍先写叙事,再把这一拍的结果写进状态。模型提供商支持按请求关掉思考时(如 deepseek),引擎先用不思考的快答案落地,同时在后台跑一次思考版;思考版回来后逐个变量替换快答案的值(期间被别的东西改过的不动,工具和引擎的裁定始终优先)。最多等 90 秒;玩家先发了下一句就取消。

前端在回合结束后可能还会收到:`write_down.pending`(修正进行中)→ `write_down.corrected`(带改了什么,紧跟一条 `state.changed`,其中 `corrected: true`)或 `write_down.same` / `.cut` / `.timeout` / `.failed`。

<!-- section: reads -->
## 随时可读

```
GET /api/v1/play/engine/settlement           这一局的结算(没到出口时为空)
GET /api/v1/play/engine/entities?cls=status  某一类实体和属性(如你身上的状况)
GET /api/v1/play/engine/graph                生效的编排图
GET /api/v1/play/engine/contract             这一局的玩法合约(不是接口契约,见[接口契约](/docs/developers/contract))
GET /api/v1/play/engine/audio                现在在放什么
GET /traces · /trace?i=N                     每一句的完整记录
```

字段全表:模板文件夹里的 `spec/` 和 `neonrp spec http`。
