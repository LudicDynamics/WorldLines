---
title: "一份模板,多个重前端"
description: "同一份模板和同一局数据,怎么被网页、Godot、TypeScript 前端各自读取;自己写前端要接哪些接口和事件。"
---

<!-- section: picture -->
## 关系

```text
模板(template.json · world/ · souls · plots/ · 素材)
   │  开局:搭成一局
   ▼
引擎进程 —— 这一局唯一的真相
   │  POST /rpc · GET /rpc/events · HTTP 读接口
   ├── 标准网页前端(Hub、iOS 上玩家看到的;不开源)
   ├── Godot 示例   worldlines/examples/clients/godot
   ├── TS 示例      worldlines/examples/clients/ts
   └── 你的前端
```

前端不改世界。它发一句话或一个操作,引擎裁定、落地,再把叙事、拍事件和状态推回来。画面上的一切都来自引擎给的数据和模板的素材。

所以一份模板不用为每个前端各写一遍:前端只认接口,不认具体的世界。

<!-- section: host -->
## 连上哪个引擎

| 引擎 | 怎么起 | 令牌(token) |
|---|---|---|
| 本机工作台 | `worldlines`(默认 `http://127.0.0.1:8787`) | 工作台「前端」页点「复制令牌」;或 `curl -s http://127.0.0.1:8787/api/v1/local/frontends/_/connect`(只回答本机请求) |
| 单个世界文件夹 | `neonrp serve --project <文件夹> --port 8788` | 启动时打印 `{"url", "token", "protocol"}` |

做前端时推荐连本机工作台:测试台和你的前端接的是同一局,一边调试一边看画面。`neonrp serve` 适合只跑一个世界、不需要工作台的场合(见[协议](/docs/developers/protocol))。

<!-- section: five -->
## 前端要接的六样

| 要什么 | 从哪来 |
|---|---|
| 连接 | `POST /rpc` 调 `session.hello {protocol: "worldlines.net/1"}`;每个请求带 `Authorization: Bearer <token>` |
| 拍怎么显示 | `GET /api/v1/play/engine/beat-kinds`:每种拍的名字、色调、输入提示、建议、分隔 |
| 叙事和拍事件 | `GET /rpc/events`(SSE):`engine/stream` 是逐字叙事,`engine/beat` 是拍事件,`engine/event` 是回合开始 / 结束 |
| 状态 | `GET /state`(谁在哪)· `GET /api/v1/play/schema`(变量)· `GET /api/v1/play/engine/entities?cls=<类>` · `GET /api/v1/play/engine/views` · `GET /api/v1/play/engine/settlement` |
| 素材 | 这一局的图按地址取(`/api/v1/play/place-image?addr=` 等);CG、结局图等用槽位 id 指明(见下文「素材」) |
| 类型 | `neonrp template contract <id> --ts` / `--gd`:变量、类、op、事件、素材槽的类型清单(见[接口契约](/docs/developers/contract)) |

说一句:`turn.send {text}`,回合结束才返回,期间叙事从 `/rpc/events` 陆续到达。停下:`turn.cancel`。主机提问(`ask_user`)时用 `reply {id, result}` 回答。

前端不认识任何具体的拍。开源引擎一回合只有清算拍,PyPI 版有商量拍和清算拍;同一份前端代码两种都能接,名字和样式都从 `beat-kinds` 读。

<!-- section: events -->
## 拍事件和画面

| 事件 | 前端可以做 |
|---|---|
| `node.enter` / `node.leave` | 切换这一拍的样式(按 `beat-kinds` 里的名字和色调) |
| `plan.beat` / `resolve.beat` | 落一段叙事;`options` 做成选项按钮 |
| `dice` | 在屏幕上掷骰:`total` · `vs` · `level` |
| `state.changed` | 刷新数值;`applied` 里每条是 `{var, from, to}`,`refused` 是没落地的改动 |
| `place.discovered` | 地图上点亮新地点:`addr` · `name` |
| `party.join` / `party.leave` | 同伴上场 / 离开 |
| `stage.changed` | 剧情阶段变了;带 `cg` 时放过场图 |
| `show` | 现在放一张模板图:`slot` 就是素材槽 id |
| `audio.cue` | 换音乐 / 环境声 |
| `run.settled` | 到出口了:读 `GET /api/v1/play/engine/settlement` 画结局 |

全表和字段见[实时事件流](/docs/developers/events)。断线后用 `GET /rpc/events?since=<seq>` 补上漏掉的。

<!-- section: slots -->
## 素材:按地址取这一局的图

这一局的图按地址取:

```text
GET /api/v1/play/place-image?addr=T001/hall      地点场景;地址和 /state 里的 player_location 一样
GET /api/v1/play/portrait?id=chara               角色立绘;id=player 是玩家头像
GET /api/v1/play/sprite?id=chara                 透明底站姿
GET /api/v1/play/map/image?level=T001            关卡地图;GET /api/v1/play/map 是地点和路的数据
```

没有图时返回 404,前端自己画占位。这些图在开局时从模板拷进这一局:模板换了图,新开一局才生效。

模板里每张图都有一个槽位 id。CG、结局图、封面、物品图标没有按地址取的接口。引擎用槽位 id 指它们:

| 槽位 id | 是什么 |
|---|---|
| `card:cover` | 模板封面 |
| `level.map:<关卡>` | 关卡地图,如 `level.map:T001` |
| `place.scene:<地址>` | 地点场景,如 `place.scene:T001/hall` |
| `soul.portrait:<角色>` · `soul.sprite:<角色>` | 立绘 · 透明底站姿 |
| `item.icon:<id>` | 物品图标 |
| `player.portrait:player` | 玩家头像 |
| `opening.cg:<n>` · `stage.cg:<剧情>.<n>` | 开场 CG · 剧情阶段 CG |
| `plot:<剧情文件夹>:ending:<结局>` | 结局图 |

拍事件 `show` 的 `slot`、`stage.changed` 的 `cg.slot` 是槽位 id;结局在 `GET /api/v1/play/engine/settlement` 的 `exit` 里。两个示例前端把这些图放在自己的美术包里(`art.json`,按结局 id、地点地址对应),收到事件时从包里取。槽位的种类(比例、是否必填)在 `neonrp template contract <id>` 的 `slots` 里;命令行看槽位填了没有:`neonrp template slots <id>`。

<!-- section: switch -->
## 换局时

本机工作台上,测试台开了另一局,或者在「游玩一览」新开一局,引擎就换到了新的一局:

- `/rpc/events` 不断,之后的事件属于新的一局;
- `GET /events` 上会收到一条 `rebound`;
- 前端收到后重读模板 id、`beat-kinds` 和素材,再重画。

测试台里的标准网页前端换局时整页重新载入,素材换成新模板的。两个示例只在连接时读一次:换局后要重新连接(TS 示例刷新页面,Godot 示例重开)。

<!-- section: three -->
## 三个前端各读什么

| | 标准网页前端 | Godot 示例 | TS 示例 |
|---|---|---|---|
| 在哪 | Hub、iOS | 开源仓 `worldlines/examples/clients/godot` | 开源仓 `worldlines/examples/clients/ts` |
| 协议 | 同一套接口 | `addons/worldlines/client.gd`(一个节点) | `src/client.ts`(一个文件) |
| 拍的显示 | `beat-kinds` | `beat-kinds` | `beat-kinds` |
| 素材 | 模板的素材槽 | 自带美术包 `art.json`,没画的图用占位 | 同 Godot,读同一份美术包 |

标准网页前端不开源;本页列的接口就是它用的接口。PyPI 版的测试台右栏有「标准前端」页签,可以和测试台并排看同一局。

两个示例怎么跑、怎么改:[Godot 与 TS 重前端](/docs/tutorials/frontend-examples)。

<!-- section: own -->
## 把前端放进模板

一个世界可以带自己的前端:`<模板>/frontends/<名字>/frontend.json`。

```json
{"schema": "worldlines.frontend/1", "kind": "web-ts", "title": "我的前端", "entry": "index.html",
 "events": ["node.enter", "resolve.beat", "dice", "state.changed", "run.settled"], "targets": ["local"]}
```

| 字段 | 意思 |
|---|---|
| `kind` | `web-ts` · `godot` · `chat` |
| `entry` | 入口文件,如 `index.html` / `project.godot` |
| `events` | 用到的事件,引擎按已知事件检查 |
| `targets` | 目前只有 `local` |

在工作台「前端」页点「+ 新建」,或在内置前端上点「复制一份到这个世界」。内置模板要先复制一份成你自己的。`frontends/` 只留在本机,不随导出。
