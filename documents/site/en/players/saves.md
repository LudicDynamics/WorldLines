---
title: "Save · branch · undo"
description: "Every run saves itself. Step back one move, or go back to a turn and start a new line from there."
---

<!-- section: auto -->
## Saved automatically

Every run is a folder in `~/.worldlines/plays/`, saved after every turn lands. There is nothing to save by hand: close it, open it again, and carry on.

<!-- section: web -->
## On the web

On the overview, click the world; its card lists your saves:

- **continue** a run where you left it;
- **start a new run** of the same world — the old one stays in your saves;
- **delete** a run (you are asked again).

Undo and going back to a turn are terminal-only for now. The web UI and the terminal share the same saves: a run you played on the web can be picked up in the terminal with `/load`.

<!-- section: cmds -->
## In the terminal

| Command | Does |
|---|---|
| `/open` | list the worlds and saves you can play; `/open <save>` continues it, `/open <world>` starts a new run |
| `/load` | pick a save to continue, or a snapshot from this run |
| `/save [name]` | store a snapshot in this run |
| `/undo` | step back one move |
| `/redo` | redo the move you just undid |
| `/undo list` | list the turns on this line |
| `/undo <turn>` | go back to that turn and start a new line from there; the old line is kept |

A new line never changes the old one; every turn of the old line is still there.

<!-- section: under -->
## Behind it: the commit graph

Every turn is a commit, and a run is a commit graph — see [World lines](/docs/concepts/worldlines). Outside the game: go into the run's folder and run `neonrp commit log`.
