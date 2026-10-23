---
title: "命令行参考"
description: "neonrp schema · neonrp commit · neonrp cast · neonrp serve。"
---

<!-- section: schema -->
## neonrp schema

> **状态:随 1.0 发布**

| 子命令 | 作用 |
|---|---|
| `register <table> <id> --spec <JSON 或 @file> [--no-replace]` | 校验后写入 `game/meta/<table>.json` |
| `unregister <table> <id>` | 删除;对 actions 是关掉 op |
| `list [table] [--class C]` | 引擎现在看到的表 |
| `get <var>` · `history <var> [--since-turn N]` | 读值 / 变化 |
| `events [--since SEQ] [--type T] [--limit N]` | 读事件 |
| `watch [pattern] [--since SEQ] [--timeout S] [--interval S]` | 进程外订阅 |

通用:`--world <路径>`(默认当前目录)、`--json`。表:`variables` `classes` `actions` `triggers` `entries`。

<!-- section: commit -->
## neonrp commit

> 已发布

每局的提交图:`commit` · `log` · `checkout <id>` · `branch <name>` · `gc [--keep-last N]` · `verify <id>` · `backfill`。默认存放 `~/.worldlines/commits`(`--commits-root` 可改),工作目录用 `--game-root`。

<!-- section: template -->
## neonrp template

> **状态:随 1.0 发布**

`list` · `lint` · `build` · `show` · `slots` · `contract` · `contracts` · `fork` · `set-contract`,以及打包带走 / 带回:

```bash
neonrp template export <id> [-o FILE]          # 模板包(带上它 link 的角色)
neonrp template export --soul <名字> [-o FILE]  # 角色包
neonrp template import <FILE> [--id NEW] [--store DIR]
```

见[导出与导入](/docs/creators/export-import)。

<!-- section: spec -->
## neonrp spec

> **状态:随 1.0 发布**

打印给 agent 读的规格:`neonrp spec` 列表 · `neonrp spec <名字> [--lang zh|en]` · `neonrp spec ops --pack pct` · `neonrp spec --llms`。见[给 agent 读的 spec](/docs/developers/agent-spec)。

<!-- section: other -->
## cast 与 serve

- `neonrp cast`(已发布):把主角投进一个世界;
- `neonrp serve`(**internal**):引擎面的 HTTP 服务,默认 `127.0.0.1:8788`,玩家请用 `worldlines`;它的接口不承诺稳定。
