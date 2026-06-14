# 用 AI 编程助手创作 WorldLines 内容

这套教程写给**把这个仓库 clone 下来、用 [Claude Code](https://claude.com/claude-code) 或
[Codex](https://openai.com/codex/) 这类 AI 编程助手来创作**的人。

WorldLines 仓库本身就是一个「创作工作台」：`.claude/skills/` 里集成了几个**创作 skill**,
当你在 AI 助手里说「帮我做一张角色卡 / 搭一个世界 / 写一个 soul」时,助手会**自动加载对应
skill**,按 WorldLines 的真实 schema 帮你产出文件 —— 你不用记格式,只描述你要的内容。

> 不想写代码、只想在浏览器里玩或建世界?那走 **[hub.worldlines.gg](https://hub.worldlines.gg)**,
> 这套教程不是给你的。这里讲的是**本地 + AI 助手**的创作流。

## 先准备

1. **拿到仓库**
   ```
   git clone https://github.com/LudicDynamics/WorldLines.git
   cd WorldLines
   ```
2. **用 AI 助手打开这个目录**
   - **Claude Code**:在仓库根目录直接 `claude`,它会读到 `CLAUDE.md` 与 `.claude/skills/`。
   - **Codex / 其他**:在仓库根打开,确保助手能读到 `.claude/skills/` 下的 `SKILL.md`。
3. **（要试玩才需要）装引擎**
   ```
   curl -LsSf https://worldlines.gg/install.sh | sh
   ```
   之后 `neonrp tui --from <世界目录>` 就能在终端里跑你做的世界。

## 集成了哪些 skill

| Skill | 你想做的事 | 产出到哪 |
|---|---|---|
| `character-card-authoring` | 一张 SillyTavern 兼容的**角色卡**(V2/V3) | `cards/character/<id>.json` |
| `world-card-authoring` | 一张 SillyTavern 兼容的**世界卡 / lorebook** | `world/lorebook/<name>.json` |
| `entity-authoring` | 给 NeonRP 世界加 **NPC / 地点 / 物品**等原生实体 | `game/<kind>/<id>.json` |
| `soul-authoring` | 一个**角色灵魂包(soul)**,可单独对话也可放进世界 | `souls/<sid>/...` |

> skill 是**自动触发**的:你只要用自然语言描述意图,助手会自己判断该用哪个。
> 下面每篇教程会给你**可以直接抄的示范 prompt**。

## 该读哪一篇

| 你的目标 | 教程 |
|---|---|
| 做一张能导进酒馆(SillyTavern)分享的角色卡 | **[01 · 角色卡](./01-character-card.md)** |
| 做一张世界设定 / lorebook,挂在角色或世界上 | **[02 · 世界卡](./02-world-card.md)** |
| 从零搭一个**会呼吸的完整世界**(orch 模式,像樱坂走廊 / 引魂灯) | **[03 · 完整世界](./03-game-world.md)** |
| 做一个有**自己心智与记忆的 soul**,搭多 agent 世界 | **[04 · Soul 与多 agent](./04-soul-multi-agent.md)** |

## 三种引擎模式(先有个概念)

你做的世界会落在三种运行模式之一,详见 [examples/](../examples/) 与
[docs.worldlines.gg](https://docs.worldlines.gg/docs/core-concepts):

- **fast** — 单个 world-agent,最快、单一声口。
- **orch** — 一个 world-agent 编排多个领域 agent(城镇 / 战斗 / 心动判定…),NPC 是它发声的数据。教程 03 做的就是这个。
- **multi-agent** — world-agent 包裹多个**独立 soul**,每个 soul 有自己的心智、记忆、目的。教程 04 做的就是这个。

---

*这些教程随仓库更新。发现 skill 行为和教程对不上,欢迎提 issue 或在
[Discord](https://discord.gg/worldlines) 里说一声。*
