# 用 AI 编程助手创作 WorldLines 内容

这套教程写给**把这个仓库 clone 下来、用 [Claude Code](https://claude.com/claude-code) 或
[Codex](https://openai.com/codex/) 这类 AI 编程助手来创作**的人。

WorldLines 仓库本身就是一个「创作工作台」:`.claude/skills/`(Codex 读 `.agents/skills/`)里有几个**创作 skill**,
当你在 AI 助手里说「帮我做一张角色卡 / 搭一个模板 / 写一个角色」时,助手会**自动加载对应
skill**,按 WorldLines 的真实规格帮你产出文件,再用引擎检查。你不用记格式,只描述你要的内容。

> 只想玩?在线玩去 **[worldlines.gg](https://worldlines.gg)**;本地玩看
> [docs.worldlines.gg 的「开始玩」](https://docs.worldlines.gg/docs/players/quickstart)。这里讲的是**本地 + AI 助手**的创作流。

## 先准备

1. **拿到仓库**
   ```
   git clone https://github.com/LudicDynamics/WorldLines.git
   cd WorldLines
   ```
2. **用 AI 助手打开这个目录**
   - **Claude Code**:在仓库根目录直接 `claude`,它会读到 `CLAUDE.md` 与 `.claude/skills/`。
   - **Codex**:在仓库根打开,它会读到 `AGENTS.md` 与 `.agents/skills/`。
3. **(要检查和试玩才需要)装引擎**,需要 Python 3.10 或更新:
   ```
   pip install worldlines        # 或:uv tool install worldlines,会一起装上 neonrp
   ```
   之后模板这样检查和试玩:
   ```
   neonrp template lint  my/<id>.template
   neonrp tui --from my/<id>.template      # 用这个模板开一局新的,直接进游玩
   ```

## 集成了哪些 skill

| Skill | 你想做的事 | 产出到哪 |
|---|---|---|
| `character-card-authoring` | 一张 SillyTavern 兼容的**角色卡**(V2/V3) | `cards/character/<id>.json` |
| `world-card-authoring` | 一张 SillyTavern 兼容的**世界卡 / lorebook** | `world/lorebook/<name>.json` |
| `entity-authoring` | 给世界加 **NPC / 地点 / 物品 / 任务**等实体 | 世界的 `game/` 下 |
| `soul-authoring` | 一个**角色(soul)**:有自己的人格、记忆和目标,能进很多世界 | `my/souls/<sid>/` |
| `template-authoring` | 一整套能直接开局、能发布的**模板**(世界 + 角色 + 玩法包 + 卡面 + 剧情) | `my/<id>.template/` |

> skill 是**自动触发**的:你只要用自然语言描述意图,助手会自己判断该用哪个。
> 下面每篇教程会给你**可以直接抄的示范 prompt**。

## 该读哪一篇

| 你的目标 | 教程 |
|---|---|
| 做一张能导进酒馆(SillyTavern)分享的角色卡 | **[01 · 角色卡](./01-character-card.md)** |
| 做一张世界设定 / lorebook,挂在角色或世界上 | **[02 · 世界卡](./02-world-card.md)** |
| 照内置模板搭一整套**能玩、能发布的模板** | **[03 · 完整模板](./03-game-world.md)** |
| 做一个有**自己心智与记忆的角色**,放进你的世界 | **[04 · 角色与多角色世界](./04-soul-multi-agent.md)** |
| 在**终端里游玩与管理**(启动器 / 斜杠命令 / 设置) | **[05 · 终端指南](./05-tui-guide.md)** |

## 先有个概念

- **模板(template)是玩家挑选、创作者发布的单位**:它绑定一个世界、几个角色、一个玩法包(`rpg`、`pct`、`werewolf`、`monopoly`),
  再加卡面、剧情、结局和玩法合约。两个内置模板就是最好的范本:
  [`worldlines/templates/pct-house.template`](../templates/pct-house.template)(灰橡宅,百分骰推理)和
  [`worldlines/templates/stoneford-town.template`](../templates/stoneford-town.template)(石津镇,开放小镇)。
- **每一回合分两拍**:先商量(角色接话、谈计划),谈妥后清算(掷骰、写故事、把变化写进世界)。两个内置模板都这样走。
  设定要让角色能「表态」(会同意什么、拒绝什么),世界要给主持能读的真实数据(价目、路程、谁在哪)。

概念详见 [docs.worldlines.gg](https://docs.worldlines.gg/docs/concepts/overview)。

---

*这些教程随仓库更新。发现 skill 行为和教程对不上,欢迎提 issue 或在
[Discord](https://discord.gg/HJYWbdqWrE) 里说一声。*
