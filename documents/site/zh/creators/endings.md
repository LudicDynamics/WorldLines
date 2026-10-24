---
title: "结局"
description: "结局是触发规则的一种输出。触发后这一局就到了出口:写尾声、结算。"
---

<!-- section: emit -->
## 结局 = 触发规则的一种输出

> **状态:随 1.0 发布**

石津镇剧情包 `P20` 里的一条:

```json
"P20.E1": {"when": {"flag": "coffin_answered"}, "if": [{"flag": "amu_found"}],
           "then": [{"to": "end", "ending": "E1"}], "once": true}
```

`{"to": "end"}` 触发后,**整局**到了出口:

- 写 `game/meta/ending.json`,立 `ended` flag,账本记一条 `turn.ended`;
- 下一次叙事是尾声,只收住这条线,不再开新的事;
- 引擎按[玩法合约](/docs/creators/contracts)写一份结算 `game/meta/settlement.json`(出口、解锁的 CG、死亡、奖励、真相),游玩界面据此画结局卡。

一局里只会有一个结局:第一个触发的算数。

<!-- section: modes -->
## 三种结局模式

`template.json` 的 `mode.ending`:

| 模式 | 意思 | 例子 |
|---|---|---|
| `open` | 没有必须的结局,可以一直玩 | |
| `single` | 一个结局 | |
| `multi` | 多个结局 | 石津镇(4 个:真相 E1、两个别的结局 E2 / E3、失败 E9);灰橡宅(3 个) |

结局在剧情包的 `endings` 里定义,`kind` 写 `true`(真相结局)、`alt`、`fail`(失败结局)。合约要求的结局数和种类由 [Lint](/docs/creators/lint) 检查,比如 `mystery-trpg` 要至少 3 个、含一个真相结局。

<!-- section: segment -->
## 开放世界:分段结算

`open-adventure` 合约的出口是**段落**(`exit.on: segment`,一段 = 一天):每过一天引擎记一段结算,这一局继续玩。

但只要剧情包里有 `{"to": "end"}` 触发了,不管模式是什么,这一局都结束。石津镇是开放冒险合约,同时有 4 个结局:到第 8 天还没走到最后一个阶段、或者玩家倒下,都会触发失败结局 E9。

<!-- section: truth -->
## 真相

剧情包里写 `reveal`(谜底,分语言),到结局时揭晓。`mystery-trpg` 合约还要求结算后有「真相三问」:剧情包的 `truth_quiz.questions` 写三道题,答对的给额度,全对可以把指定的角色带回家。见[剧情包](/docs/creators/plot-packs)。
