---
title: "Terminal commands"
description: "Every slash command in the terminal game, and where the old ones went."
---

<!-- section: how -->
## How to use them

In the terminal game you reach with `neonrp`, type `/` in the input box to list commands with completion. Most commands without arguments open a picker, so you don't need to remember ids.

Besides the commands below, a world can bring its own, such as Greyoak House's skills `/Listen` and `/Spot`: they show up next to the engine's commands when you type `/`.

<!-- section: play -->
## Playing

| Command | Does |
|---|---|
| `/open [world or save]` | without arguments: list the worlds and saves you can play. With a save: continue it. With a world: start a new run |
| `/init [world]` | start a new run of a world; without arguments a picker, which can also create a blank world from scratch |
| `/load [save or snapshot]` | continue a save, or load a snapshot from this run; without arguments a picker |
| `/save [name]` | store a snapshot in this run |
| `/undo` | step back one move |
| `/undo list` | list the turns on this line |
| `/undo <turn>` | go back to that turn and start a new line; the old one is kept |
| `/redo` | redo the move you just undid |
| `/status [page]` | the status panel. Pages: `player` you · `agents` characters · `plan` planning board · `dice` rolls · `settlement` ending and settlement · `contract` play contract · `account` account and judge · `usage` usage · `room` networked table |
| `/lang [language]` | the language this run is narrated in: `zh` `en` `ja` `ko` |
| `/find <keyword>` | search this world's places, people and items |
| `/clear` | clear the conversation on screen |

<!-- section: characters -->
## Characters

| Command | Does |
|---|---|
| `/who [character]` | step into a character's view: where they are, what they remember, what they did in the last few turns; from there you can talk to them directly, or act for them |
| `/cast [character] [role]` | bring a library character into this world, as `npc` or `player`; without arguments, list who is available |
| `/create <name>` | create a new character in build mode, written by the agent |
| `/remove <character>` | take a character out of this world (the library copy is untouched) |
| `/reset <character>` | make a character forget their memories and history here; who they are stays the same |
| `/import <file>` | import a world package (`.zip`) or a SillyTavern card (`.png` / `.json`), recognised by its content |

<!-- section: build -->
## Building worlds

| Command | Does |
|---|---|
| `/mode [build or play]` | switch within the same world: build = let the agent change this world, play = play it |
| `/vault [build]` | project this world into an Obsidian vault and open it; `build` only writes it, without opening |
| `/dev [item]` | for creators and troubleshooting: `graph` orchestration graph · `dry-run` run one beat on trial · `beats` mark the beat skeleton in the prose · `template` templates · `validate` check the world · `mcp` · `bridge` · `debug` |

<!-- section: app -->
## Account, settings, updates

| Command | Does |
|---|---|
| `/login` | Worldlines account (optional): the Jev judge, the model relay, uploading worlds. `/login code` signs in without a browser · `/login status` shows the state · `/login out` signs out |
| `/settings` | models, keys, the Discord bridge and other settings |
| `/update` | check for updates. `/update apply` installs · `/update status` shows version and settings · `/update mode auto`, `prompt` or `notify` sets what happens at launch · `/update channel` changes the update channel |
| `/help` | list the commands |
| `/quit` · `/q` | quit |

<!-- section: input -->
## Marks in the input box

| Write | Does |
|---|---|
| `@name` | speak to a character; typing `@` completes the people present |
| `@dm` | ask the host to carry on: planning moves straight to resolve |
| 「定」 | the same — the talk is settled |
| `#` | inside a sentence, completes places and items |

<!-- section: removed -->
## Where the old commands went

Since 1.0 the commands have been cut down to the ones above. Typing an old one doesn't fail with "unknown command"; it tells you what to use now:

| Old command | Use now |
|---|---|
| `/branch` | `/undo list` · `/undo <turn>` |
| `/worlds` `/worldlines` `/continue` | `/open` |
| `/game` | `/open` · `/create` |
| `/sessions` | `/load` |
| `/models` `/auth` `/wl-model` `/locale` | `/settings` |
| `/load-world` | `/import` |
| `/export-world` | the command line: `neonrp export-world` |
| `/context` | `/find` |
| `/replay` | `/dev dry-run` |
| `/compact` | `/clear` |
| `/copy` | `F6` |
| `/run` `/agent` | just say it |
| `/index` | kept up to date by the engine |
| `/skills` | the agent uses them on its own |
| `/files` | git on the command line |

A few more are no longer listed but still work when typed: `/validate` (also `/dev validate`), `/mcp` (also `/dev mcp`), `/bridge` (also `/dev bridge`), `/debug` and `/verbose` (merged into `/dev debug`), `/stats` (now `/status usage`), `/config` (use `/settings` day to day).

The `--mcp` launch mode and the Claude Code preset were removed in 1.0.3.
