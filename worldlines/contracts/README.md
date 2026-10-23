# 玩法合约 · Play contracts

一份玩法合约(`worldlines.play-contract/1`)规定一种玩法原型必须具备的体验:入口、出口、结局、奖励、死亡怎么结算、固定输出,
以及在 Hub 发布的门槛。模板用 `"play_contract": "<id>@<version>"` 声明;lint 按合约做静态检查,测试台跑到出口做动态检查。

A play contract declares what a kind of game must deliver — entry, exit, endings, rewards, how deaths settle, fixed outputs —
and what it takes to publish on the Hub. A template opts in with `"play_contract": "<id>@<version>"`.

| id | 名称 | 出口 | 结局 | 死亡 | 发布门槛 |
|---|---|---|---|---|---|
| `mystery-trpg` | 沙盒跑团 | 到达结局(谜底必须揭晓;结算后真相三问,剧情包**必须**写 `truth_quiz`) | ≥ 3,含真相结局 | 玩家死 / 心智归零 → 失败结局;同伴、其他人记入结算 | lint 无 block + 跑通一个结局 |
| `open-adventure` | 开放冒险 | 段落结算(一天) | 不要求 | 玩家死 → 失败结局;同伴、其他人记入结算 | lint 无 block + 结算一段 |
| `murder-mystery` | 解谜型剧本杀 | 指认真凶后进结局(真相必须揭晓) | ≥ 2,含真相结局 | 玩家死 → 失败结局;同伴、其他人记入结算(案中死者属剧情) | lint 无 block + 跑通一个结局 |
| `romance-companion` | 恋爱陪伴 | 段落结算(一次约会) | 不要求(线路结局可选) | 玩家死 / 同伴(恋人)死 → 失败结局;其他人记入结算 | lint 无 block + 结算一段 |

## 死亡 · `deaths`

```json
"deaths": {
  "player":    {"exit": "ending", "ending_kind": "fail"},
  "companion": {"settle": "record", "plot": "optional"},
  "other":     {"settle": "record"},
  "insanity":  {"exit": "ending", "ending_kind": "fail"}
}
```

- `player` 玩家 · `companion` 带进来的角色(soul)· `other` 世界里的其他人(NPC)· `insanity` 心智归零(只对有心智类数值的世界;键名沿用 insanity)。
- `{"exit": "ending", "ending_kind": "fail"}`:游戏到出口,走模板剧情里第一个 `kind: fail` 的结局(带 CG / 尾声);模板没有就由引擎给一个「死亡」出口。
- `{"settle": "record"}`:记进结算的 `deaths`,游戏继续;`"plot": "optional"` 表示模板可以用一条剧情接住这次死亡。
- 没写的:玩家默认出口,其他人默认记录。

到出口时引擎写 `game/meta/settlement.json`(出口 · 解锁的 CG · 尾声 · 死亡 · 奖励 · 合约)并发 `run.settled` 事件。

合约只管体验,不管编排:拍怎么跑由 pack 的编排图决定(见编排台),同一份合约可以配不同的编排。
第一版只有官方合约;引擎读取 · 按合约 lint · 结算已实现(`neonrp.template.contract` · `neonrp.core.settlement`)。

## 回合怎么走 · `engine`

一局怎么推进也可以属于玩法:合约可以带一个 `engine` 段,写进引擎配置,排在规则包之后、世界自己的 `game/meta/engine.json`
之前(世界仍可覆盖)。**这里的四份公开合约不带 `engine` 段** —— 开源版引擎按自己的默认推进。WorldLines 发布版的回合设定
在私有层(`contracts/<id>.engine.json`,运行时叠上去,不进存档;见引擎的 `core/engine_config.py`)。

How a turn runs may belong to the kind of game too: a contract can carry an `engine` block, merged after the rule pack and
before the world's own `engine.json` (which can still override it). **The four public contracts here carry none** — the open
engine runs with its defaults. WorldLines' released turn settings live in the private layer (`contracts/<id>.engine.json`,
laid on at run time, never written into a save).
