---
title: "接口契约"
description: "一个模板对外有什么:变量、类、op、事件、素材槽、视图。按需生成,worldlines.contract/0.1。"
---

<!-- section: what -->
## 契约是什么

协议是「怎么说话」,接口契约是「这个世界有什么可说」。引擎把模板搭到一个临时目录、读出它的注册表,生成一份 JSON。它不存成文件,每次按需生成:

```bash
neonrp template contract stoneford-town            # JSON
neonrp template contract stoneford-town --ts       # 生成的 TypeScript
neonrp template contract stoneford-town --gd       # 生成的 GDScript
```

```text
GET /api/v1/local/templates/<id>/contract[?fmt=ts|gd]
```

**别和玩法合约混了。** 玩法合约(`play_contract`,如 `open-adventure@1`)是体验约定:回合、死亡、结局,见[玩法合约](/docs/creators/contracts);一局的玩法合约在 `GET /api/v1/play/engine/contract`。本页讲的接口契约是给客户端代码用的类型清单。

<!-- section: shape -->
## 形状

石津镇(节选):

```json
{
  "$schema": "worldlines.contract/0.1",
  "world": "stoneford-town",
  "template": {"base": "rpg", "mixins": ["economy"]},
  "vars":    [{"name": "player.gold", "type": "int", "min": 0, "at": "game/player/wallet.json"},
              {"name": "price.T001.grain", "type": "int", "min": 1, "max": 9999, "at": "game/towns/T001/market.json", "readonly": true}],
  "classes": [{"name": "caravan", "policy": "auto", "required": ["name"], "slots": ["icon"]}],
  "ops":     [{"op": "trade", "kind": "action", "fields": {"good": "any", "qty": "any"}, "owner": "economy"}],
  "events":  ["var.changed", "entity.created", "entry.entered", "flag.set", "trigger.fired", "ending.reached", "pending", "commit"],
  "beat_events": ["node.enter", "node.leave", "plan.beat", "resolve.beat", "dice", "tool", "state.changed", "run.settled", "…"],
  "triggers": [{"id": "P20.pass.guild", "when": {"text": "both"}}],
  "slots":   [{"id": "level.map", "kind": "image", "required": "publish", "ratio": "3:2", "hotspots": true, "dir": "assets/level/map/"}],
  "views":   [{"id": "alert", "widget": "gauge", "bind": ["town.alert"], "layout": {"area": "right", "order": 1, "range": [0, 5]}}],
  "panels":  [{"id": "formation", "tag": "formation", "format": "text", "schema": {"…": "…"}}],
  "transport": {"rpc": "…", "stream": "…"},
  "interaction": {"requests": ["…"], "switches": [], "exits": [], "panels": ["…"], "engine": ["…"]},
  "version": "0.1",
  "hash": "1a8b17c389cd"
}
```

| 键 | 内容 |
|---|---|
| `template` | 基础规则包和片段(mixin) |
| `vars` | 闭 schema 变量:类型、范围、存在哪个文件、是否只读 |
| `classes` | 开 schema 的类:增长策略、必填属性、它们的素材槽 |
| `ops` | 这一局能落地的 op,`owner` 是登记它的包或片段 |
| `events` | 账本 / 订阅上的事件类型 |
| `beat_events` | 回合流上的拍事件(见[实时事件流](/docs/developers/events)) |
| `slots` · `views` · `panels` | 素材槽、视图、面板(规则包 + 片段 + 模板的 `ui` 合并后) |
| `interaction` | 规则包声明的停顿点、切层、出口、面板、引擎主动发起的点 |
| `transport` | 接口提示(以[协议](/docs/developers/protocol)页为准) |

<!-- section: hash -->
## 哈希

`hash` 是除 `version` 外全部内容的哈希,内容一变就变。生成的客户端把它写成常量 `CONTRACT_HASH`;用它判断手上的生成代码是不是过期了,例如在构建时对比 `GET …/contract` 的 `hash`。引擎连接时不校验它。
