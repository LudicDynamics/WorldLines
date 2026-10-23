---
title: "SillyTavern 导入"
description: "把 SillyTavern(酒馆)的世界卡与角色卡导入 WorldLines。"
---

<!-- section: character-cards -->
## 角色卡

SillyTavern(酒馆)角色卡可以是 JSON 文件,也可以是带 tEXt 元数据的 PNG 图片。两者均支持。

```bash
neonrp import sillytavern-card card.png --id mira-ashford
neonrp import sillytavern-card card.json --id mira-ashford
```

该命令会解析卡片,映射到 WorldLines 的 `npc/` schema,并将实体写入 `game/npc/<id>.json`。

📸 **截图稍后补上** —— 带 PNG 预览的导入对话框。

<!-- section: world-cards -->
## 世界卡

SillyTavern 世界卡(lorebook)内容更丰富 —— 定义了区域、阵营与世界设定。导入方式:

```bash
neonrp import sillytavern-world world-card.json
```

实体会按需拆入 `game/lore/`、`game/towns/` 与 `game/world/`。

📸 **截图稍后补上** —— 导入后的 lorebook 前后对照 diff 视图。

<!-- section: caveats -->
## 注意事项

- SillyTavern 中无法 1:1 映射的字段会放进结果实体的 `_meta.silly_tavern` blob。信息不丢失,只是还未在 schema 中升为一等公民。
- v0.1 的导入是**单向**的。回写 SillyTavern 格式的往返导出计划在 v0.2 提供。
- 如果卡片引用了外部托管的图片,导入会记一条警告日志,但不会下载图片。
