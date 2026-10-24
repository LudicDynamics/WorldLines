---
title: "玩法合约"
description: "选一份合约,就是向玩家承诺一种体验:怎么开始、怎么结束、几个结局、给什么奖励。"
---

<!-- section: what -->
## 合约是什么

> **状态:随 1.0 发布**(角色协议还没实装)

合约规定**一种玩法必须给玩家的体验**,不管拍怎么跑(那是[编排图](/docs/creators/workbench)的事)。你的模板声明一份,Lint 就按它查,测试台跑到出口时引擎按它结算。

| 合约 | 适合 | 怎么结束 | 结局 |
|---|---|---|---|
| `mystery-trpg` 沙盒跑团 | 百分骰的调查、探索(灰橡宅) | 到结局,谜底必须揭晓 | ≥ 3 个,含真相结局 |
| `open-adventure` 开放冒险 | 没有必须结局的世界(石津镇) | 每过一天结算一段,继续玩;剧情包的结局触发时整局结束 | 不要求 |
| `murder-mystery` 解谜型剧本杀 | 一桌人各有剧本和秘密(狼人杀类) | 指认之后进结局,真相揭晓 | ≥ 2 个,含真相结局 |
| `romance-companion` 恋爱陪伴 | 和一个角色的关系线 | 每次约会结算一段 | 不要求 |

<!-- section: declare -->
## 声明一份

- 界面:Template 页「合约」一栏选一份;
- 命令行:`neonrp template set-contract <模板> mystery-trpg`(`neonrp template contracts` 列出所有合约和用它的模板);
- 文件:`template.json` 顶层 `"play_contract": "mystery-trpg@1"`。

内置模板只读,先「复制一份来改」。合约文件在 `worldlines/contracts/<id>.play-contract.json`。

<!-- section: checks -->
## Lint 按合约查什么

| 合约要求 | 没做到时 |
|---|---|
| 要有开场 | 拦下:世界的 `game-start.json` 没有开场 |
| 阵容固定 | 拦下:模板一个角色都没定 |
| 到结局结束 | 拦下:没有任何触发器能到达一个结局 |
| 结局数 / 结局种类 | 拦下:不够 `min` 个,或缺真相结局 |
| 揭晓真相 | 拦下:有结局的剧情没写 `reveal` |
| 结局 CG 是奖励 | 拦下:有结局没有图片槽 |
| 死亡走失败结局 | 警告:模板没有失败结局,引擎会给一个普通的死亡出口 |
| 真相三问(`mystery-trpg`) | 剧情包没写 `truth_quiz.questions`:默认区 block,自由区 warn |

<!-- section: death -->
## 死亡与结算

合约还定死亡怎么算:玩家死了走模板的失败结局(带 CG 和尾声);同伴、NPC 死了通常记进结算,游戏继续,剧情可以接住。例外:`romance-companion` 里同伴死了也直接走失败结局;`mystery-trpg` 里心智归零(`san` 到 0)也算失败出口。到出口时引擎写一份结算(出口、解锁的 CG、尾声、死亡、奖励、真相),游玩界面据此画结局卡。

<!-- section: souls -->
## 角色协议

> **状态:还没实装**

合约会规定角色进来要带什么卡、世界发给角色的东西(身份、秘密)只活在这一局、结束时什么写回角色库。见[角色库与选角](/docs/creators/characters)。完整字段:模板文件夹里的 `spec/contract.md`。
