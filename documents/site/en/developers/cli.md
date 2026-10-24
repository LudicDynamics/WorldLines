---
title: "CLI reference"
description: "The neonrp commands developers use most: template · schema · engine · commit · spec · serve · cast."
---

<!-- section: template -->
## neonrp template

| Subcommand | What it does |
|---|---|
| `list` | templates it can find: id, rules pack, ending mode, play contract, title, location |
| `lint <template> [--json] [--i18n-deep]` | check it; exit code 1 when anything blocks |
| `build <template> <dest> [--lang] [--force]` | build a playable world folder (refused when lint blocks, unless `--force`) |
| `show [--world <run>]` | which template a run was built from, and its stage |
| `contract <template> [--ts\|--gd]` | the interface contract as JSON, or generated TS / GDScript, see [Code generation](/docs/developers/codegen) |
| `slots <template>` | asset slots: which are filled, which are missing |
| `contracts` | the official play contracts, and which templates use each |
| `fork <template> <new id> [--title] [--store DIR]` | copy one into your template folder to edit it |
| `set-contract <template> <contract> [--clear]` | declare the play contract and re-lint |
| `export` · `import` | take it out / bring it back (below) |
| `publish <template> --official` | publish to the Default Zone as the official account (official account only; authors publish to the Free Zone from the creation desk) |
| `fetch <world id>` | get / update a Default Zone world into `~/.worldlines/official` with your Worldlines account |

`fork` / `import` need to know where to write: `--store DIR`, or the `NEONRP_TEMPLATE_WRITE_DIR` environment variable. The local web app `worldlines` uses `~/.worldlines/templates`.

```bash
neonrp template fork pct-house my-house --store ~/.worldlines/templates
neonrp template export ~/.worldlines/templates/my-house.template -o my-house.zip   # a template package (with the library souls it links)
neonrp template export --soul <name> -o soul.zip                                   # a soul package
neonrp template import my-house.zip --id my-house-2 --store ~/.worldlines/templates
```

Default Zone works (both bundled templates and the other official worlds) can be played, not exported: `fork` first and export your copy. Export leaves out the template's `frontends/` folder. See [Export & import](/docs/creators/export-import).

<!-- section: schema -->
## neonrp schema

| Subcommand | What it does |
|---|---|
| `register <table> <id> --spec <JSON or @file> [--no-replace]` | validate, then write to `game/meta/<table>.json` |
| `unregister <table> <id>` | remove; for actions this turns the op off |
| `list [table] [--class C]` | the tables as the engine sees them now |
| `get <var>` · `history <var> [--since-turn N]` | read a value / its changes |
| `events [--since SEQ] [--type T] [--limit N]` | read events |
| `watch [pattern] [--since SEQ] [--timeout S] [--interval S]` | subscribe from another process |

Common: `--world <path>` (default: the current folder), `--json`. Tables: `variables` `classes` `actions` `triggers` `entries`. See [Register & subscribe](/docs/developers/schema-api).

<!-- section: engine -->
## neonrp engine

In a world folder: `explain` (each setting in effect and the layer it comes from) · `tick -n N` (the world runs N steps on its own, no model call) · `graph` (the orchestration graph in effect) · `hooks` (what an orchestration editor can pick from) · `graph-test` (run a few lines through the graph on a stub model) · `mode`.

<!-- section: commit -->
## neonrp commit

Each run's commit graph: `commit` · `log` · `checkout <id>` · `branch <name>` · `gc [--keep-last N]` · `verify <id>` · `backfill`. Stored in `~/.worldlines/commits` by default (`--commits-root` to change it); the working tree is `--game-root` (default: the current folder).

<!-- section: spec -->
## neonrp spec

Print the specs agents read: `neonrp spec` lists them · `neonrp spec <name> [--lang zh|en]` · `neonrp spec ops --pack pct` · `neonrp spec --llms` · `neonrp spec sync [template folder…]` (refreshes `AGENTS.md` / `CLAUDE.md` / `spec/` in templates, the template store and the character library). See [Where specs live](/docs/developers/agent-spec).

<!-- section: other -->
## serve and cast

- `neonrp serve --project <run> [--port 8788]`: a server with only the engine API; prints the url and a token. Front ends with their own interface (Godot, your own web page, `neonrp tui --connect`) connect to it. Routes: [Protocol](/docs/developers/protocol). Its `--help` still says internal; players should use `worldlines`.
- `neonrp cast <soul> [--into <world>] [--as npc|player]`: put a soul (a sid or a soul folder) into a world, as an NPC by default; `--as player` makes it the player's avatar.
