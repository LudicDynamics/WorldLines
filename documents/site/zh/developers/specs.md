---
title: "规格 Spec"
description: "世界、角色、Template、规则包(Pack)、玩法合约的规格全文:写什么、放哪、引擎怎么读。"
---

<!-- section: specs -->
## 规格

写世界、角色、模板或规则包之前先读对应的规格。它们也是 agent(Claude Code / Codex)创作时读的同一份文件。

| 规格 | 讲什么 | 中文 | English |
|---|---|---|---|
| 世界 World | 世界文件夹:地图、地点、人物、物品、规则表、开场 | [world.zh.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/world.zh.md) | [world.en.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/world.en.md) |
| 角色 Soul | 角色包:身份、人设、记忆、RPG 身体、立绘 | [soul.zh.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/soul.zh.md) | [soul.en.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/soul.en.md) |
| 模板 Template | 把世界 + 角色 + 规则包绑成一个可玩、可发布的包 | [template.zh.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/template.zh.md) | [template.en.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/template.en.md) |
| 规则包 RPG Pack | 规则表、规则面板、检定与对抗、状态表、时钟(`rpg` / `pct`) | [pack.zh.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/pack.zh.md) | [pack.en.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/pack.en.md) |
| 玩法合约 Contract | 体验约定:回合、死亡、结局 | [contract.zh.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/contract.zh.md) | [contract.en.md](https://github.com/LudicDynamics/WorldLines/blob/main/documents/spec/contract.en.md) |

装好引擎后也能直接在终端读:

```bash
neonrp spec                 # 列出全部规格
neonrp spec pack            # 读一份(--lang en 读英文)
neonrp spec ops --pack rpg  # 一个规则包能用的操作、类、变量
```
