---
title: "接入 Godot"
description: "Godot 游戏连一个本地引擎进程:一个客户端节点讲 worldlines.net/1,素材走美术包。"
---

<!-- section: arch -->
## 架构

```text
Godot 游戏  ── JSON-RPC (POST /rpc) + SSE (/rpc/events) ──>  neonrp serve(引擎进程)
```

Godot 连一个本地引擎进程(像语言服务器那样),而不是把引擎塞进游戏。引擎是这一局唯一的真相:游戏发一句话或一个操作,引擎裁定、落地,再把叙事和拍事件推回来。引擎本身以 Apache-2.0 开源;PyPI 发布版另带不开源的两拍编排,游戏这一侧的代码两种都能接。

完整示例在 `worldlines/examples/clients/godot`(Godot 4.5,灰橡宅):标题画面、随移动切换的场景、在场人物、逐字出现的对话、屏幕上掷的 d100、线索、宅邸地图、带 CG 的结局。

<!-- section: run -->
## 跑起来

```bash
neonrp template build pct-house ./house
neonrp serve --project ./house --port 8788      # 打印 url 和 token
godot --path worldlines/examples/clients/godot  # 填 host + token → 进入
```

`template build` 搭出来的局还没有指定模型,会按你的全局设置找默认模型,找不到就是不调模型的占位回答。最省事的做法:用 `worldlines` 开一局灰橡宅(开局时会选好模型),再把 `neonrp serve --project` 指向 `~/.worldlines/plays/` 下那一局的文件夹。

<!-- section: node -->
## 客户端节点

协议都在一个文件里:把 `addons/worldlines/` 拷进你的项目。

```gdscript
var wl := preload("res://addons/worldlines/client.gd").new()
add_child(wl)
wl.chunk.connect(func(text, who, beat): …)     # 叙事逐字到达(who = 角色名,"" = 主持)
wl.beat.connect(func(event, data): …)          # node.enter · plan.beat / resolve.beat · dice · state.changed · run.settled …
wl.beat_kinds_loaded.connect(func(k): …)       # 这一局的拍怎么显示
wl.ask_user.connect(func(id, q, options): wl.answer(id, options[0]))
wl.failed.connect(func(message): …)            # 一句能读懂的话:token 不对、连不上、上一句还在跑
await wl.connect_to_host("http://127.0.0.1:8788", token)
var result: Dictionary = await wl.send_line("看看四周。")
```

| 信号 / 调用 | |
|---|---|
| `connect_to_host(url, token)` | `session.hello` → `beat_kinds_loaded` → 开始收事件流 |
| `send_line(text)` | `turn.send`;回合结束才返回(期间叙事陆续到达) |
| `cancel()` · `answer(id, value)` | `turn.cancel` · 回答主机的 `ask_user` |
| `chunk` · `beat` · `turn_started` · `turn_finished` | 来自 `/rpc/events`(`engine/stream` · `engine/beat` · `engine/event`) |
| `get_json(path)` | 直接读 HTTP 接口,如 `/state`、`/api/v1/play/schema` |

游戏不认识任何具体的拍:名字、颜色、输入提示、分隔都来自主机的 `beat-kinds`。所以开源引擎(只有清算拍)和发布版(商量拍 + 清算拍)用同一份代码。

事件流用原始 TCP(+ TLS)读,不用 `HTTPClient`:主机按 HTTP/1.0 无长度回答,`HTTPClient` 会当成空响应。断线后它会重连并用 `since` 补上漏掉的。

<!-- section: types -->
## 类型

要变量的类型化属性,可以再生成一份 GDScript 镜像:`neonrp template contract pct-house --gd`(见[代码生成](/docs/developers/codegen))。它不联网,把收到的变量变化交给 `apply_change` 就行。

<!-- section: assets -->
## 素材

示例读一个美术包:`worldlines/examples/clients/art/<世界>/art.json`(哪张图配哪个地点、人物、结局、线索),`WL_ART_DIR` 可以指到别处。还没画的图用占位。`art/pull.sh` 从模板的 `assets/` 拷图并缩放。

<!-- section: checks -->
## 检查

```bash
godot --headless --path . -s tests/scene_check.gd                          # 能编译
WL_HOST=… WL_TOKEN=… godot --headless --path . -s tests/smoke.gd           # 经客户端节点走一句
```
