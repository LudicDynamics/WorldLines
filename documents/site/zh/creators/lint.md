---
title: "Lint:发布前的检查"
description: "先把模板建成一局,再查引用、素材、提示词、token、剧情、合约、语言。有 block 就不能发布。"
---

<!-- section: what -->
## 什么时候跑

> **状态:随 1.0 发布** —— `neonrp template lint`、Template 页「Lint」一栏;每一项的代码见模板文件夹里的 `spec/template.md` §7。

```bash
neonrp template lint stoneford-town            # 每行 [级别] 代码 位置: 说明;最后一行 publishable / NOT publishable
neonrp template lint stoneford-town --json
```

引擎先在临时目录里把模板**建成一局**(卡池里的角色全员到场、剧情包装好),再对着这一局查,所以剧情和素材槽是对着真实世界检查的。每一项分两级:**block**(拦下发布)或 **warn**(只提醒)。创作者操作每改一次模板也会重新跑一遍。

<!-- section: level -->
## `lint.level`:草稿还是发布

`template.json` 里写 `"lint": {"level": "draft"}`,缺图(必需槽位没填或过期)、缺封面、每回合 token 超预算都只报 warn;不写或写 `"publish"` 时这几项是 block。两个内置模板现在都是 `draft`。

<!-- section: checks -->
## 查什么

| 类 | 检查什么 | 例子 |
|---|---|---|
| **卡面与模式** | 有标题;`mode.ending` 是 open / single / multi;`zone`、`forkable` 写法对 | 没有标题 → block |
| **世界与规则包** | 世界找得到;规则包和片段能加载;片段要的世界数据在 | 装了 `economy` 但没有 `game/world/economy.json` → warn(片段不起作用) |
| **角色** | 演员表每一行都能找到角色(角色库的 link 断了也算);卡池 `pick` 不超过池子 | `{"lib": "mira"}` 没写 `sid` → block |
| **提示词** | 提示词文件存在;`prompts/souls/<sid>/` 只放人格层(`soul.md` · `persona/` · `rules/` · `agents/`);每个 `{占位符}` 都能取到 | 生图提示引用 `{weather}`,但没注册 → block |
| **schema** | 视图绑定的变量都已注册;视图里的动作有处理器 | 视图「集市」绑定 `price.{town}.*`,但经济片段没装 → block |
| **素材** | 每个必需槽位都有文件,而且没过期 | 地图过期:路上长出了新地点,热点对不上 |
| **token 预算** | 读这个模板最近的真实对局,算每回合平均 token;还没玩过就只报 `token.unmeasured` | 每回合均值 24,000,预算 20,000 |
| **剧情** | 剧情包能解析,引用的文件存在,结局可达 | 没有任何触发器能到达一个结局 |
| **合约** | 按你声明的[玩法合约](/docs/creators/contracts)查开场、阵容、结局数、真相、结局 CG、真相三问 | `mystery-trpg` 少于 3 个结局 → block |
| **编排** | `uses` 写法对;参数是这个编排有的选项。引擎没有的编排不算错(退回单拍) | |
| **其他** | 开场 CG、奖励卡、音频、创作层 `creation`、玩家建角、地图 | |
| **语言** | 英日韩翻译层的结构和覆盖率(`--i18n-deep` 查得更细) | |

<!-- section: zone -->
## 按区分级

少数检查按模板的 `zone` 定级:真相三问、音频来源在默认区是 block,在自由区是 warn。见[发布到 Hub](/docs/creators/publish)。

<!-- section: after -->
## 通过之后

没有 block 就是 `publishable`。发布前引擎还会再查链接的角色、密钥、四语卡面和封面,见[发布到 Hub](/docs/creators/publish)。要给游戏客户端生成接口契约,用 `neonrp template contract`(见[接口契约](/docs/developers/contract))。
