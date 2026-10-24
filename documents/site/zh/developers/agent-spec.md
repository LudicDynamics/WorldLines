---
title: "spec 放在哪"
description: "spec 就在 agent 工作的文件夹里:每个模板、模板库、角色库都带 AGENTS.md · CLAUDE.md · spec/。"
---

<!-- section: inside -->
## 在文件夹里

Claude Code 读 `CLAUDE.md`,Codex 和多数 agent 读 `AGENTS.md`,它们都读身边的文件。所以 spec 直接放进创作者(和他的 agent)会改的每个文件夹:

| 文件夹 | 带的 spec |
|---|---|
| 每个模板 `<id>.template/` | `template` · `world` · `soul` · `contract`(中英)· 这个模板玩法包的 `ops` · `authoring` |
| 模板库根 | `template` · `world` · `soul` · `contract` · `authoring` |
| 角色库 `~/.worldlines/souls/` | `soul` · `template` · `contract` |

怎么用见[给 agent](/docs/agents/overview)。

<!-- section: fresh -->
## 什么时候更新

- 复制模板(`fork`)、导入包时自动写;导入时换成这台引擎的 spec,不沿用导出方的;
- `neonrp spec sync` 刷新全部(模板库 + 角色库 + 每个模板);`neonrp spec sync <模板文件夹>…` 只刷这几个;
- 你自己写的 `AGENTS.md` / `CLAUDE.md`(没有「generated」标记的)永远不覆盖;
- 开局不复制这些文件,不进存档。

源头:写的 spec 在引擎的 `documents/spec/`(world · soul · template · contract · pack · player);`ops` · `authoring` · `contracts` · `http` 每次从代码生成,不会过时。

<!-- section: tools -->
## 给工具和脚本

同样的文本,脚本和自己的工具也能取:`neonrp spec [名字] [--lang] [--pack]`、`GET /api/v1/spec/<名字>`、`/llms.txt`。WorldLines 自己的创作 agent 没有命令行,用内置工具 `read_spec`(只在创作模式出现)。
