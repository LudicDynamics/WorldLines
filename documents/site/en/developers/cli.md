---
title: "CLI reference"
description: "neonrp schema · neonrp commit · neonrp cast · neonrp serve."
---

<!-- section: schema -->
## neonrp schema

> **Status: ships with 1.0**

| Subcommand | Does |
|---|---|
| `register <table> <id> --spec <JSON or @file> [--no-replace]` | validate, then write into `game/meta/<table>.json` |
| `unregister <table> <id>` | remove; for actions, turn the op off |
| `list [table] [--class C]` | the table as the engine sees it now |
| `get <var>` · `history <var> [--since-turn N]` | read a value / its changes |
| `events [--since SEQ] [--type T] [--limit N]` | read events |
| `watch [pattern] [--since SEQ] [--timeout S] [--interval S]` | subscribe from another process |

Common options: `--world <path>` (default: cwd), `--json`. Tables: `variables` `classes` `actions` `triggers` `entries`.

<!-- section: commit -->
## neonrp commit

> Released

The per-playthrough commit graph: `commit` · `log` · `checkout <id>` · `branch <name>` · `gc [--keep-last N]` · `verify <id>` · `backfill`. Stored in `~/.worldlines/commits` by default (change with `--commits-root`); the working tree is `--game-root`.

<!-- section: template -->
## neonrp template

> **Status: ships with 1.0**

`list` · `lint` · `build` · `show` · `slots` · `contract` · `contracts` · `fork` · `set-contract`, plus taking things out and back in:

```bash
neonrp template export <id> [-o FILE]          # a template package (with the characters it links)
neonrp template export --soul <name> [-o FILE] # a soul package
neonrp template import <FILE> [--id NEW] [--store DIR]
```

See [Export and import](/docs/creators/export-import).

<!-- section: spec -->
## neonrp spec

> **Status: ships with 1.0**

Prints the specs agents read: `neonrp spec` lists them · `neonrp spec <name> [--lang zh|en]` · `neonrp spec ops --pack pct` · `neonrp spec --llms`. See [Specs for agents](/docs/developers/agent-spec).

<!-- section: other -->
## cast and serve

- `neonrp cast` (released): put a protagonist into a world;
- `neonrp serve` (**internal**): the engine-side HTTP service, `127.0.0.1:8788` by default; players should use `worldlines`. Its interface is not promised to be stable.
