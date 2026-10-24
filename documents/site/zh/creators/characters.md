---
title: "角色库与选角"
description: "角色不属于任何世界:放在角色库里,模板只放 link,开局才实体化。"
---

<!-- section: library -->
## 角色库

> **状态:随 1.0 发布**

角色(soul)的家是角色库 `~/.worldlines/souls/<名字>/`:人格、记忆、外貌、立绘都在这里,不属于任何世界。

- 一个角色可以进很多个世界,一个世界可以选很多个角色。
- 世界里放的不是角色的副本,是一个 **link**。
- 只有真正开局(模板变成一局)时,角色才被复制进这一局;之后这一局里的记忆和状态只属于这一局。
- 你在角色库里改了角色,下一局开局就拿到新的。

<!-- section: cast -->
## 选角:模板的演员表

> **状态:随 1.0 发布**

模板的 `souls` 一行就是一个演员:

```json
"souls": [
  {"sid": "chara", "role": "npc"},
  {"sid": "mira", "lib": "mira", "role": "companion"},
  {"sid": "guide", "path": "souls/guide"},
  {"pool": [{"sid": "a", "lib": "a"}, {"sid": "b", "lib": "b"}, {"sid": "c"}], "pick": 2}
]
```

| 写法 | 是什么 |
|---|---|
| `{"sid": …}` | 世界自带的角色(灰橡宅的管家、石津镇的艾琳娜这类) |
| `{"sid": …, "lib": …}` | 角色库里的角色 —— link。手写 `template.json` 时 `sid` 必须写,缺了 Lint 报 `ref.soul`、开局会跳过这一行 |
| `{"sid": …, "path": …}` | 放在模板文件夹里的角色 |
| `{"pool": [...], "pick": N}` | 卡池,每局抽 N 个(狼人杀、随机组合) |
| `role` | `npc` 世界 NPC(默认)· `companion` 同伴 · `player` 主角,由玩家扮演(最多一个) |

石津镇的演员表是两个世界原生角色:`{"sid": "elena", "role": "npc"}`、`{"sid": "rowan", "role": "npc"}`。

创作时用作者操作 `set_cast` 整张写入:`{"lib": …}` 没写 `sid` 时它从角色的 `soul.json` 补上;link 断了、同一个角色写两次、定位写错、两个主角,都会整批拒绝,什么都不写。

<!-- section: switches -->
## 角色自己的开关

写在角色的 `soul.json` 里:

| 字段 | 意思 |
|---|---|
| `standalone: true` | 没获得也能单独聊 |
| `takeable`(默认 `true`)· `take_when` | 满足条件时玩家能把它带回家,带着完整记忆。`take_when` 是 `companion_at_ending`(默认:结局时跟在玩家身边)或 `ending:<结局 id>`。自由区的局不让带走 |
| `assets: {"sprite": "portrait"}` | 站姿直接用立绘(立绘本身是全身像时),不另存一张 |

<!-- section: per-world -->
## 同一个角色,在每个世界里不一样

> **状态:随 1.0 发布**

同一个角色进了灰橡宅是「委托人的朋友」,进了石津镇是「失忆的旅人」—— 这些差异写在**模板**里,角色库本体不动:

- `prompts/souls/<sid>/`:只能覆盖 `soul.md`、`persona/`、`rules/`、`agents/`(人格和说话方式这一层);
- `world-overlay/`:换这个世界里的立绘。

想知道一个角色在哪些世界里:`GET /api/v1/local/souls/<名字>/bindings`。

<!-- section: protocol -->
## 角色协议:合约对角色的要求

> **状态:还没实装** —— 下面是已定的方向。

不同玩法对角色的要求不一样:解谜跑团要一张调查员卡,剧本杀要给每人发身份和秘密。合约里会加一节 `souls`:

- **进** —— 要什么卡、要不要主角、必须有什么素材;角色缺卡时开局由转换器现生成一张,按合约存在 `character/sheets/<合约>.json`;
- **在** —— 世界发给角色的身份、秘密只活在这一局,不会跟着角色去别的世界;
- **出** —— 只有合约列出的东西(记忆、信任、好感)写回角色库。

主角也会走角色库:从角色库挑,或者新建一个。

细节:合约 spec · `neonrp spec contract`。
