# 01 · 做一张角色卡（Character Card）

**目标:** 用 AI 助手做一张 SillyTavern 兼容的角色卡(V2/V3),可以导进酒馆、分享给别人,
也可以之后接进 WorldLines 世界。
**用到的 skill:** `character-card-authoring`(自动触发)。
**产出:** `cards/character/<id>.json`。

> 角色卡 = 一个**可移植的角色定义**(人格、开场白、示例对话、可选世界书)。
> 它跟 NeonRP 世界里原生的 `game/character/<id>.json` 是**两种不同格式** —— 这篇做的是
> 前者(酒馆格式)。要给某个世界加 NPC,看 [教程 03](./03-game-world.md)。

## 一步步

### 1. 在仓库根打开 AI 助手
```
cd WorldLines
claude          # 或你的 Codex / 其他助手
```

### 2. 描述你的角色（可以直接抄这个 prompt）

> 帮我做一张角色卡,导出酒馆格式。
> 名字叫**白蘅**,设定:民国时期苏州的女中医,表面温婉、心里有股不肯认输的劲;
> 说话用半文半白的口吻,偶尔夹一句吴语。喜欢:旧书、雨天、把脉时的安静;
> 怕的是:别人替她做决定。开场白让她在医馆里第一次见到玩家。
> 用中文写正文,字段名用英文。放进 `cards/character/`。

助手会:
- 自动加载 `character-card-authoring` skill;
- 产出 `chara_card_v2`(或 v3)结构的 JSON:`name` / `description` / `personality` /
  `scenario` / `first_mes` / `mes_example` / `creator_notes` / `tags` …;
- 中文写**内容**,英文保持**字段名**(WorldLines 约定:内容用目标语言,ID/字段名 ASCII)。

### 3. 让它细化你最在意的部分

角色卡的质量基本取决于三块,挑你在意的让助手打磨:
- **`first_mes`(开场白)** —— 决定第一印象。让它「给我 2 个不同基调的开场白挑」。
- **`mes_example`(示例对话)** —— 锁定声口。让它「补 2 段示例对话,体现她嘴硬心软」。
- **`personality` / `description`** —— 别写成설定罗列,让它「写成能直接喂给模型的紧凑人格描述」。

### 4.（可选）给角色挂一个世界书

如果这个角色需要随身带设定(门派、家世、黑话),让助手:

> 给白蘅加一个内嵌世界书(character_book),3-4 条:她的医馆、她师父、苏州城里的传闻。

这会写进角色卡的 `data.character_book`。要做**独立**的大世界书,看 [教程 02](./02-world-card.md)。

### 5. 校验

> 校验一下 `cards/character/白蘅.json` 符不符合 chara_card_v2 规范,有没有缺必填字段。

助手会按 skill 里的 schema 自查。你也可以把这张卡直接拖进 SillyTavern 验证导入。

## 产出长这样（节选）

```json
{
  "spec": "chara_card_v2",
  "spec_version": "2.0",
  "data": {
    "name": "白蘅",
    "description": "民国苏州,问松堂的年轻女医……",
    "personality": "温婉的表,倔强的里;替人拿主意时最自在,被人替她拿主意时最抗拒。",
    "first_mes": "「这位……是来看诊,还是来躲雨的?」她搁下手里的医书……",
    "mes_example": "<START>\n{{user}}: 你这医馆怎么不挂招牌?\n白蘅: 「招牌是给找不到路的人看的。你既进来了,便是不需要。」",
    "tags": ["民国", "中医", "女性", "中文"]
  }
}
```

## 小抄

- **内容用中文/目标语言,字段名英文。** 这是全仓库的约定。
- **一张卡只做一个角色。** 多角色 → 多张卡,或者直接去 [教程 03](./03-game-world.md) 搭世界。
- 想把这张酒馆卡**导进** NeonRP 变成可玩切片,那是另一个流程(`tavern-game-import`),不在这篇。

---

下一篇:**[02 · 世界卡](./02-world-card.md)** —— 给角色或世界做一份 lorebook。
