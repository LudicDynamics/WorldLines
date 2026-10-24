# 04 · 角色(soul)与多角色世界

**目标:** 用 AI 助手做一个**角色(soul)**:一个有自己心智、记忆、目标的角色,
可以单独聊天,也可以放进世界,和别的角色一起被你遇到。
**用到的 skill:** `soul-authoring`(自动触发)。
**参考范本:** 两个内置模板里的角色:[`templates/pct-house.template`](../templates/pct-house.template)(灰橡宅:温妮、管家奥斯温)、
[`templates/stoneford-town.template`](../templates/stoneford-town.template)(石津镇:艾琳娜、罗文)。
**产出:** `my/souls/<sid>/`,一个自包含的角色文件夹。

> 角色(soul)和[教程 01](./01-character-card.md) 的酒馆角色卡**不是一回事**:角色卡是一段可移植的
> 人格描述,喂给模型;**soul 是一个会自己判断、行动、记事的角色**,有持久的内心状态,
> 玩的时候由引擎更新。你说的话对它只是一次尝试,它会同意、会拒绝,也会照自己的打算行动。

## 角色文件夹的结构

照 `soul-authoring` skill(规格见 `documents/spec/soul.zh.md`),一个角色长这样:

```
souls/<sid>/
  soul.json                # 身份:sid、名字(必需)
  soul.md                  # 散文宪章:声口、价值观、压力下的反应模式
  run_state.json           # 起始状态:位置、心情(玩时由引擎更新)
  persona/                 # 不可变的心理内核
    core_traits.json       #   核心性格
    motivations.json       #   动机
    values.json            #   价值排序
    relationships.json     #   与他人的关系
  background/              # 不可变的来历
    origin.md / history.md / secrets.md
  character/               # 数值(运行时可写)
  short-term-memo/ · long-term-memo/   # 种子记忆(玩时累积)
  assets/portrait.png      # 立绘
```

关键区别:
- **persona / background 是「不可变内核」**:这个角色是谁,不会因为一局游戏改掉。
- **character / 记忆 / run_state 是「运行时可写」**:数值会变、记忆会累积,这是角色「活着」的部分。不要预先写满。

## 一步步

### 1. 在仓库根打开 AI 助手,描述这个角色(可直接抄)

> 用 soul-authoring 帮我做一个角色,放到 `my/souls/`,sid 用 `yanyan`。
> 角色:**盐砚**,一个在边境驿站守了二十年的老兵,沉默、记仇、对年轻人却出奇地软。
> 表面只想守着驿站终老,心底藏着一桩没替战死的兄弟了结的事。
> 给我完整的 persona(性格 / 动机 / 价值观 / 关系)、background(来历 / 历史 / 秘密)、
> 起手数值,和几条种子记忆。中文写内容,字段名英文。

助手会自动加载 `soul-authoring` skill,scaffold 整个 `my/souls/yanyan/` 目录。

### 2. 打磨「内核」三件事

角色好不好,看这三块,挑重点让助手深化:
- **`soul.md`(宪章)**:一句话能不能说清「他在压力下会怎么反应」?让助手
  「在 soul.md 里写清楚:盐砚被触到那桩心事时,会怎么回避,又会在什么情况下松口」。
- **`persona/values.json`(价值排序)**:两个价值冲突时他选哪个?这决定他的「人味」。
- **`background/secrets.md`(秘密)**:藏着的东西是角色的引擎。让它「把那桩没了结的事写具体」。

### 3. 放进角色库,单独聊聊

角色库在 `~/.worldlines/souls/`,网页和终端共用。把做好的角色放进去:

```bash
cp -R my/souls/yanyan ~/.worldlines/souls/yanyan
```

然后在终端里 `neonrp`,启动器「角色库」里选「💬 灵魂对话」,挑盐砚聊几轮。
看他**记不记事**、**守不守人设**(会不会突然变性子)。

### 4. 放进一个世界

两种做法:

- **请进一局正在玩的游戏**:在终端游戏里 `/cast yanyan`。只影响这一局。
- **写进你的模板**:在 `template.json` 的 `souls` 里加一行 link:

  ```json
  "souls": [
    {"sid": "chara", "role": "npc"},
    {"lib": "yanyan", "role": "npc"}
  ]
  ```

  模板里只存 link,开局时才把角色库里的盐砚复制进这一局;你改了角色库,下一局就拿到新的。
  也可以把角色文件夹放进模板(`souls/yanyan/`),写成 `{"sid": "yanyan", "path": "souls/yanyan", "role": "npc"}`,
  这样模板发给别人时角色跟着走。

然后照[教程 03](./03-game-world.md) 检查、试玩:

```bash
neonrp template lint my/<id>.template
neonrp tui --from my/<id>.template
```

### 5. (可选)不开界面,跑脚本

做研究、复现实验时,可以不进界面,直接对一局发话:

```bash
neonrp template build my/<id>.template /tmp/run-<id>
neonrp play --project /tmp/run-<id> "去驿站找盐砚"
neonrp play --project /tmp/run-<id> --json --trace "问他那桩旧事"   # 输出 JSON,并附上这一回合的编排记录
```

## 小抄

- **soul ≠ 角色卡。** soul 有持久内心状态、会自己更新;角色卡是静态人格描述。手里有酒馆卡,
  在终端游戏里 `/import <卡片文件>` 就能补全成一个 soul。
- **内核不可变,运行时可写。** persona / background 别让它在游戏里被改掉;character / 记忆 / run_state 才是活的部分。
- **多个角色进一个世界,先各自单独调好再合。** 范本是石津镇。

---

回到 **[教程总览](./README.md)**。做完想分享、想上 Hub,见 [docs.worldlines.gg](https://docs.worldlines.gg/docs/creators/publish)。
