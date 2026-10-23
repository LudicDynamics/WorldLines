---
title: "触发规则:WHEN / IF / THEN / ELSE"
description: "创作者写在闭 schema 上的规则。确定性求值,不调 LLM。"
---

<!-- section: shape -->
## 形状

> **状态:随 1.0 发布**

```json
{"when": {"var": "player.gold"},
 "if":   [{"var": "player.gold", "<": 3}],
 "then": [{"to": "narration", "text": "钱袋快空了({after} 枚)。"},
          {"to": "soul", "who": "艾琳娜", "text": "玩家的钱快花光了", "important": true}],
 "else": [],
 "edge": true, "once": false, "cooldown": 0}
```

放进 `game/meta/triggers.json`(`neonrp schema register triggers …`)或 `manifest.json["triggers"]`。每次 apply 之后求值。

<!-- section: when -->
## WHEN:什么唤醒它

| 写法 | 含义 |
|---|---|
| `{"var": "player.gold"}` | 变量变了 |
| `{"entry": "T001/inn", "event": "enter", "who": "player"}` | 实例事件:enter / leave / talk / patch / created |
| `{"entry": "F_bandits", "prop": "power"}` | 实例的属性变了 |
| `{"flag": "met_guard"}` | 设了 flag |
| `{"text": "player"}` | 这一回合来了文本(player / narration / both) |
| `{"turn": true}` | 每回合轮询 |

<!-- section: if -->
## IF 与 THEN / ELSE

**IF**(全部成立):变量比较、`delta<=`(这次的变化量)、flag、实例属性、文本关键词、`{"who": "player", "at": "T001/inn"}`、`{"any": [...]}`。

**THEN / ELSE** 发往:`narration` · `soul` · `flag` · `var`(set / add)· `tool` · `end`(结局)· `log`。

`edge: true` = 条件从假变真才触发;`once` / `cooldown` 控制次数。规则自己改了变量,其余规则在同一次 apply 里重新求值(最多 3 层)。每次触发都会记进账本(`trigger.fired`),带原因链。
