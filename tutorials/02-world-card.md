# 02 · 做一张世界卡（World Card / Lorebook）

**目标:** 用 AI 助手做一张 SillyTavern 兼容的世界卡(世界书 / lorebook),
给角色或世界一套**按关键词触发**的设定库。
**用到的 skill:** `world-card-authoring`(自动触发)。
**产出:** `world/lorebook/<name>.json`(独立世界书),或写进角色卡的 `data.character_book`。

> 世界卡 = 一组 **lore 条目**,每条带 `keys`(触发关键词)。玩到相关词时,对应设定
> 才被注入上下文 —— 这样可以塞很多设定而不撑爆 prompt。

## 独立世界书 vs 内嵌世界书

| | 独立世界书 | 内嵌(character_book) |
|---|---|---|
| 位置 | `world/lorebook/<name>.json`,顶层 `entries` 数组 | 角色卡里的 `data.character_book` |
| 适合 | 一个世界共享、给多个角色用 | 跟着**单个角色**走的随身设定 |
| 怎么做 | 这篇 | [教程 01](./01-character-card.md) 第 4 步 |

## 一步步

### 1. 在仓库根打开 AI 助手,描述世界（可直接抄）

> 帮我做一张独立世界卡(lorebook),放进 `world/lorebook/`。
> 世界设定:架空的「雾港」,一座常年大雾、靠潮汐发电的海港城。
> 给我 6-8 条 lore,涵盖:城市本身、潮汐电塔、雾里会出现的「回声人」、
> 港口黑市、市政厅与灯塔教会的对立。每条配好触发关键词。中文写内容,字段名英文。

助手会:
- 自动加载 `world-card-authoring` skill;
- 产出 `entries` 数组,每条含 `keys`(关键词)、`content`(设定正文)、
  `comment`(给作者看的标题)、`insertion_order`、`enabled` 等酒馆字段。

### 2. 把握三件事,让世界书好用

- **关键词要「玩家真会打出来的词」** —— 让助手「检查每条的 keys,补上同义词和俗称」。
  例:回声人 → 也触发「雾里的人」「影子」。
- **每条只讲一件事** —— 条目太杂会一次注入一大坨。让它「把过长的条目拆成两条」。
- **排好优先级** —— 核心世界观 `insertion_order` 高,边角料低。

### 3. 加一条「常驻」条目（可选）

有些设定希望**每次都在场**(比如世界基调、铁律),不靠关键词触发:

> 加一条常驻条目(constant: true),一句话点明雾港的基调:「在雾港,看清的代价是被看清」。

### 4. 校验

> 校验 `world/lorebook/雾港.json`:每条有没有 keys、有没有空 content、有没有重复 keys。

## 产出长这样（节选）

```json
{
  "name": "雾港",
  "entries": [
    {
      "comment": "潮汐电塔",
      "keys": ["电塔", "潮汐", "发电", "塔"],
      "content": "雾港的电力全靠外海的三座潮汐电塔。涨潮供电,落潮全城点油灯……",
      "insertion_order": 20,
      "enabled": true,
      "constant": false
    },
    {
      "comment": "基调(常驻)",
      "keys": [],
      "content": "在雾港,看清的代价是被看清。",
      "insertion_order": 100,
      "enabled": true,
      "constant": true
    }
  ]
}
```

## 小抄

- **世界书是「按需注入」,不是「全量塞」** —— keys 没命中就不进上下文,所以可以做厚。
- 想要给玩家**叙事感**的长篇设定(不靠关键词),用 `game/lore/<topic>.md` 写散文 lore,
  那是世界内部用的,不走酒馆格式。
- 这张世界书可以挂到 [教程 01](./01-character-card.md) 的角色卡上,也可以喂给 SillyTavern。

---

下一篇:**[03 · 完整世界](./03-game-world.md)** —— 从零搭一个会呼吸的 orch 世界。
