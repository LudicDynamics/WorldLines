---
title: "命令行参考"
description: "开发者常用的 neonrp 命令:template · schema · engine · commit · spec · serve · cast。"
---

<!-- section: template -->
## neonrp template

| 子命令 | 作用 |
|---|---|
| `list` | 能找到的模板:id、规则包、结局模式、玩法合约、标题、位置 |
| `lint <模板> [--json] [--i18n-deep]` | 检查;有 block 时退出码 1 |
| `build <模板> <目标文件夹> [--lang] [--force]` | 搭成一个可玩的世界文件夹(lint 有 block 时拒绝,除非 `--force`) |
| `show [--world <局>]` | 一局是从哪个模板搭的、到了哪个阶段 |
| `contract <模板> [--ts\|--gd]` | 接口契约 JSON,或生成的 TS / GDScript,见[代码生成](/docs/developers/codegen) |
| `slots <模板>` | 素材槽:哪些已有、哪些缺 |
| `contracts` | 官方玩法合约,以及每个合约被哪些模板用 |
| `fork <模板> <新 id> [--title] [--store DIR]` | 复制一份到你的模板文件夹再改 |
| `set-contract <模板> <合约> [--clear]` | 声明玩法合约并重跑 lint |
| `export` · `import` | 打包带走 / 带回(见下) |
| `publish <模板> --official` | 以官方账号发到默认区(只有官方账号能用;普通作者在创作台发布到自由区) |
| `fetch <世界 id>` | 用 Worldlines 账号拉取 / 更新一个默认区世界到 `~/.worldlines/official` |

`fork` / `import` 要知道写到哪:`--store DIR`,或环境变量 `NEONRP_TEMPLATE_WRITE_DIR`。本机网页 `worldlines` 用的是 `~/.worldlines/templates`。

```bash
neonrp template fork pct-house my-house --store ~/.worldlines/templates
neonrp template export ~/.worldlines/templates/my-house.template -o my-house.zip   # 模板包(带上它 link 的角色)
neonrp template export --soul <名字> -o soul.zip                                   # 角色包
neonrp template import my-house.zip --id my-house-2 --store ~/.worldlines/templates
```

默认区的作品(两个内置模板和其他官方世界都是)只能玩,不能导出:先 `fork`,导出你的副本。导出会跳过模板里的 `frontends/` 文件夹。见[导出与导入](/docs/creators/export-import)。

<!-- section: schema -->
## neonrp schema

| 子命令 | 作用 |
|---|---|
| `register <table> <id> --spec <JSON 或 @file> [--no-replace]` | 校验后写入 `game/meta/<table>.json` |
| `unregister <table> <id>` | 删除;对 actions 是关掉 op |
| `list [table] [--class C]` | 引擎现在看到的表 |
| `get <var>` · `history <var> [--since-turn N]` | 读值 / 变化 |
| `events [--since SEQ] [--type T] [--limit N]` | 读事件 |
| `watch [pattern] [--since SEQ] [--timeout S] [--interval S]` | 进程外订阅 |

通用:`--world <路径>`(默认当前目录)、`--json`。表:`variables` `classes` `actions` `triggers` `entries`。见[注册与订阅](/docs/developers/schema-api)。

<!-- section: engine -->
## neonrp engine

在世界文件夹里:`explain`(每个生效的设置和它来自哪一层)· `tick -n N`(世界自己走 N 拍,不调模型)· `graph`(生效的编排图)· `hooks`(编排编辑器能选的东西)· `graph-test`(用占位模型把几句话走一遍编排图)· `mode`。

<!-- section: commit -->
## neonrp commit

每局的提交图:`commit` · `log` · `checkout <id>` · `branch <name>` · `gc [--keep-last N]` · `verify <id>` · `backfill`。默认存放 `~/.worldlines/commits`(`--commits-root` 可改),工作目录用 `--game-root`(默认当前目录)。

<!-- section: spec -->
## neonrp spec

打印给 agent 读的规格:`neonrp spec` 列表 · `neonrp spec <名字> [--lang zh|en]` · `neonrp spec ops --pack pct` · `neonrp spec --llms` · `neonrp spec sync [模板文件夹…]`(把 `AGENTS.md` / `CLAUDE.md` / `spec/` 刷新进模板、模板库和角色库)。见[spec 放在哪](/docs/developers/agent-spec)。

<!-- section: other -->
## serve 与 cast

- `neonrp serve --project <局> [--port 8788]`:只挂引擎接口的服务,打印 url 和 token;自带界面的前端(Godot、自己的网页、`neonrp tui --connect`)连它。接口见[协议](/docs/developers/protocol)。它的 `--help` 仍标着 internal;玩家请用 `worldlines`。
- `neonrp cast <角色> [--into <世界>] [--as npc|player]`:把一个角色(sid 或角色文件夹)放进一个世界,默认当 NPC;`--as player` 当玩家的分身。
