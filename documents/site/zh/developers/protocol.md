---
title: "协议"
description: "引擎对外的两层接口:worldlines.net/1(JSON-RPC,给自己做的客户端)和 HTTP 读写接口。所有世界都一样。"
---

<!-- section: host -->
## 起一个引擎

```bash
neonrp template build pct-house ./house       # 一个可玩的世界文件夹
neonrp serve --project ./house --port 8788
# → {"url": "http://127.0.0.1:8788", "token": "…", "protocol": "worldlines.net/1"}
```

`neonrp serve` 只挂引擎接口(没有网页界面),给自带界面的前端用:Godot、自己的网页、远程的 TUI(`neonrp tui --connect <url> --token <token>`)。玩家用的本机网页 `worldlines` 也提供下面的 HTTP 接口。

引擎进程是这一局唯一的真相:客户端只发意图,引擎裁定、落地。

<!-- section: rpc -->
## worldlines.net/1

JSON-RPC 2.0,两个端点,都要 `Authorization: Bearer <token>`:

```text
POST /rpc           一个请求 → 一个回答(turn.send 等这一回合做完才回)
GET  /rpc/events    SSE:这一局的消息总线,每条是一个 JSON-RPC 消息;?since=<seq> 补断线期间的
```

| 方法 | 作用 |
|---|---|
| `session.hello {protocol}` | 先握手,版本不对返回 -32003 |
| `turn.send {text, client?}` | 说一句;返回这一回合的结果。另一句还在跑时 -32002。只有玩家座位能调 |
| `turn.cancel` | 让正在跑的回合做完当前这一步就停 |
| `session.state` · `session.messages` · `session.clear` · `session.set_mode` | 读状态 / 消息,清空,切模式 |
| `session.whoami` | 这个凭据是哪个座位 |
| `room.invite` · `room.seats` · `room.pending` · `room.approve` · `room.deny` · `room.revoke` · `room.auto_approve` | 多人:邀请、审批、收回座位(只有主机 token 能调) |
| `session.join {invite}` · `session.join_status` | 拿邀请换一个座位凭据 |
| `reply {id, result}` | 回答主机发来的请求(`ask_user`) |

`/rpc/events` 上的通知是 `{"method": "bus.message", "params": {topic, seq, payload}}`。前端主要接三个 topic:`engine/stream`(叙事逐字)· `engine/beat`(拍事件,见[实时事件流](/docs/developers/events))· `engine/event`。座位凭据只看到属于自己那一份。

完整的客户端实现:`worldlines/examples/clients/ts/src/client.ts`(一个文件)和 `worldlines/examples/clients/godot/addons/worldlines/client.gd`。

<!-- section: http -->
## HTTP 接口

不经 JSON-RPC 也能直接用的读写:

```text
POST /cmd {"text": "…"}                          说一句(202;另一句在跑时 409)
GET  /events                                     SSE:回合流(见实时事件流)
POST /cancel                                     停下当前回合
GET  /state                                      谁在哪(只含玩家认识的角色)
POST /rollback {"commit": "<id>"}                从这次提交另开一条分支,当前线保留

GET  /api/v1/play/schema[/history|/events|/stream]   变量、类、op、触发器;变化;订阅
POST /api/v1/play/engine/tick {"turns": 1..50}   世界自己走几拍(不调模型;回合进行中 409)
GET  /api/v1/play/engine/beats?since=N           拍事件补拉
GET  /api/v1/play/engine/beat-kinds              这一局的拍怎么显示(名字、颜色、提示)
GET  /api/v1/play/engine/commits                 这一局的提交图
GET  /api/v1/play/engine/contract                这一局的玩法合约
GET  /api/v1/local/templates/<id>/contract[?fmt=ts|gd]   模板的接口契约 / 生成的客户端
```

全表随引擎生成:`neonrp spec http`。

<!-- section: verbs -->
## 动词对照

| 想做的事 | 用什么 |
|---|---|
| 提出一个动作 | 说一句(`turn.send` / `POST /cmd`),或前端的结构化操作 `POST /cmd {"action": "inspect" \| "pick", "target"}` / `{"action": "skill", "skill", "target"?}` |
| 读变量 / 历史 | `GET /api/v1/play/schema` · `…/history?var=` · Python `load_registry` · `sdk.history` |
| 订阅变化 | `GET /api/v1/play/schema/stream?pattern=` · Python `sdk.on` · `neonrp schema watch` |
| 注册 | Python `registry.register` · `neonrp schema register` · 编辑会话的 `…/schema/register` |
| 世界自己走 | `POST /api/v1/play/engine/tick` · Python `sdk.tick` |
| 世界线 | `GET …/engine/commits` · `POST /rollback` · `neonrp commit log / checkout / branch` |
