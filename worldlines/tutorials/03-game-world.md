# 03 · 照内置模板搭一整套模板

**目标:** 用 AI 助手做一个**模板(template)**:一个能直接开局、能检查、能发布的世界包。
**用到的 skill:** `template-authoring`(写模板时自动触发),`entity-authoring`(改世界里的地点、NPC、物品时自动触发)。
**参考范本:** [`worldlines/templates/pct-house.template`](../templates/pct-house.template)(灰橡宅:一夜的百分骰推理,世界就装在模板里)、
[`worldlines/templates/stoneford-town.template`](../templates/stoneford-town.template)(石津镇:开放小镇,绑定引擎内置的世界,再用 `world-overlay/` 改数据)。
**产出:** `my/<id>.template/`,`neonrp tui --from my/<id>.template` 直接能玩。

> 模板 = **世界 + 角色 + 玩法包 + 卡面 + 剧情 + 玩法合约**。它有固定骨架,不要从白纸开始:
> 让助手「照着灰橡宅的结构」改写成你的题材,是最快的路。

## 模板的骨架

以灰橡宅为例:

```
my/<id>.template/
  template.json          # 卡面(标题、一句话简介、标签、封面)、玩法包、玩法合约、角色、剧情、开场 CG
  world/                 # 世界本身(也可以不放,改成绑定引擎内置的世界)
    game/meta/game-start.json   # 开场叙述 + 首批选项
    game/towns/ · game/locations/  # 地点
    game/lore/*.md       # 设定、真相、传闻(主持读)
    game/player/         # 玩家是谁、身上有什么
    game/rules/          # 规则(检定、状态)
    souls/<sid>-<实例>/  # 世界自带的角色
  plots/P01/plot.json    # 剧情:分几段、每段目标、结局、线索
  world-overlay/         # 覆盖到世界上的文件(地图、场景图、立绘……)
  assets/                # 封面、开场 CG
  spec/ · AGENTS.md · CLAUDE.md  # 给 AI 助手读的规格(跟着引擎版本生成)
```

规格在 `documents/spec/template.zh.md`(世界、角色、玩法合约、玩法包各有一份)。模板文件夹里的 `spec/` 是同一套,助手会先读它。

## 一步步

### 1. 复制最接近的范本

```bash
mkdir -p my
cp -R worldlines/templates/pct-house.template my/fog-bar.template
```

想要开放小镇、有经济系统的,复制 `stoneford-town.template`。

### 2. 让助手改写题材(可直接抄)

> 用 template-authoring,把 `my/fog-bar.template` 改成一个新模板,id 用 `fog-bar`。
> 题材:**赛博朋克酒吧的一夜**。玩家是新来的调酒学徒,酒吧明早就要被收购;
> 三个常客各自藏着一件和收购有关的事。保留百分骰和「解谜跑团」玩法合约,
> 剧情分四段,至少三个结局,其中一个是真相结局。
> 地点、角色、开场、剧情都按新题材重写;`template.json` 里的 `uses` 和 `pack.engine` 两块照抄范本,不要改;
> `zone`、`forkable` 是官方模板才写的,删掉。
> 中文写内容,id、字段名、文件名用英文。

助手会逐个文件改写;`entity-authoring` 会保证 `game/` 下实体的 id、类型、路径一致,引用不悬空。

### 3. 先把最影响体验的几处定下来

让助手一个个跟你确认:

- **开场**:`world/game/meta/game-start.json` 的 `opening_scene`(开场叙述)和 `opening_choices`(首批选项)。
  有角色的世界开局时原样给玩家,不调模型,所以这是第一印象,值得多打磨。
- **角色**:每个角色要能「表态」:她会同意什么、拒绝什么、怎么讨价还价。世界自带的角色放在 `world/souls/`;
  想用你角色库里的角色,在 `template.json` 的 `souls` 里写一行 `{"lib": "<角色 id>", "role": "npc"}`(见[教程 04](./04-soul-multi-agent.md))。
- **剧情和结局**:`plots/P01/plot.json` 里每一段的目标、推进条件、结局。玩法合约会检查结局数量和真相结局。
- **主持能读的真实数据**:价目、路程、谁在哪、真相写在哪(`game/lore/`)。主持靠这些落账,而不是靠编。

### 4. 检查

```bash
neonrp template lint  my/fog-bar.template     # 全部问题;block 会挡发布,warn 只提醒
neonrp template slots my/fog-bar.template     # 还缺哪些图(封面、立绘、场景、地图)
```

lint 有 block 就让助手修,并把每条 block 的原文和修法告诉你。

### 5. 试玩

```bash
neonrp tui --from my/fog-bar.template
```

这会用模板在 `~/.worldlines/plays/` 里开一局新的,直接进游玩;模板文件夹本身不会被改。
也可以先组装成一局再进去:`neonrp template build my/fog-bar.template /tmp/try-fog-bar`,然后 `cd /tmp/try-fog-bar && neonrp tui --play`。

玩几回合,看这几件事:

- 商量拍里角色有没有接话、有没有自己的主意?
- 清算之后,钱、位置、物品有没有真的写进世界(`/status` 看得到)?
- 推进条件能不能触发?能不能走到结局?

### 6. 分享和发布

- **打包给朋友**:放进 `~/.worldlines/templates/` 后,本地网页的 Template 页能「导出」成一个 `.zip`;对方「导入…」就能玩。
- **上传到 Hub**:见 [docs.worldlines.gg 的发布说明](https://docs.worldlines.gg/docs/creators/publish)。上传前会检查密钥、封面、立绘和四种语言的标题简介。

## 小抄

- **别从白纸搭,照范本改。** 灰橡宅是自带世界的范本,石津镇是「绑定内置世界 + overlay」的范本。
- **内容用目标语言写,id、字段名、文件名用 ASCII。**
- **世界的词只写进数据。** 地名、状态名、阵营名都放在模板和世界的数据里。
- `worldlines/examples/worlds/` 里是旧格式(orchestrator 时代)的示例世界,可以当题材和文风的素材看;新做的世界请用模板。

---

下一篇:**[04 · 角色与多角色世界](./04-soul-multi-agent.md)** —— 做有独立心智的角色,放进你的模板。
