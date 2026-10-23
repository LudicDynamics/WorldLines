# documents/spec — 基础规格 · Basic specs

| 层 · Layer | 中文 | English | 是什么 · What |
|---|---|---|---|
| world | [world.zh.md](./world.zh.md) | [world.en.md](./world.en.md) | 世界文件夹:地图层级、镇、地点、NPC、物品、传说、开场 · the world folder |
| soul | [soul.zh.md](./soul.zh.md) | [soul.en.md](./soul.en.md) | 角色文件夹:身份、人格、规则、记忆、状态、立绘 · the character folder |
| template | [template.zh.md](./template.zh.md) | [template.en.md](./template.en.md) | 模板:把世界 + 角色 + 玩法包绑起来,加卡面 / 模式 / 剧情 / 素材槽 / lint · binds them into a playable, publishable package |
| contract | [contract.zh.md](./contract.zh.md) | [contract.en.md](./contract.en.md) | 玩法合约:一种玩法必须给的体验(入口 · 出口 · 结局 · 奖励 · 死亡 · 输出 · 发布门槛)· what a kind of game must deliver |
| player | [player.zh.md](./player.zh.md) | [player.en.md](./player.en.md) | 玩家侧数据:分身、跨局记录(获得 / 聊过 / 结局 / 成就 / 奖励)、聊天记录;不进模板 · the player's own data, never in a template |
| pack | [pack.zh.md](./pack.zh.md) | [pack.en.md](./pack.en.md) | 规则包:规则表、规则面板、检定与对抗、状态表、时钟、战斗 / 倒地 / 远行,怎么写 / 改一个包 · the rule pack and how to write one |

**分层 · Layering:** 玩法包 pack(规则,在引擎里)+ world + souls = 最小可玩;template 是可选的上层,也是发布的单位。
pack (rules, in the engine) + world + souls is the minimum that plays; a template is the optional layer on top and the unit you publish.

- 代码位置写作 `src/neonrp/...:symbol`,在开源仓里位于 `neonrp/src/neonrp/...`。 · Code locations are relative to the engine folder (`neonrp/` in the public repository).
- 每一项都标了状态:已实装 / 约定 / 设计中。 · Every item is marked implemented / convention / in design.
- 检查命令 · Check with: `neonrp validate`(世界 · a world)· `neonrp template lint <dir>`(模板 · a template)。

## 给 agent 读 · For agents

引擎自己就能给出这些 spec(pip 装的引擎也带着),外加从代码现读的四份(操作空间 `ops` · 作者操作 `authoring` · 现行合约 `contracts` · HTTP 路径 `http`):
The engine serves these specs itself (an installed engine carries them), plus four generated from the code:

```
neonrp spec                         # 列表 · list
neonrp spec template --lang en      # 一份 · one
neonrp spec ops --pack pct          # 一个玩法包的操作空间 · one pack's op space
curl http://127.0.0.1:8787/llms.txt              # 索引 · index
curl http://127.0.0.1:8787/api/v1/spec/contract  # 同一份文本 · the same text
```

写世界 / 角色 / 模板 / 合约 / 规则包之前,先读对应的 spec;写完用 `neonrp validate` / `neonrp template lint` 检查。
Read the spec before writing a world / soul / template / contract / pack; check with `neonrp validate` / `neonrp template lint`.

