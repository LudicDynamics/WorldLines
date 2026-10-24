---
title: "World lines"
description: "Every turn is a world commit; you can go back to any turn and branch a new line from there, keeping the old one."
---

<!-- section: dag -->
## The commit graph

Every run has a **commit graph**: each turn lands one world commit, recording its parent and a snapshot (content-addressed); each character's own commits live in her own folder. Commits are stored in `~/.worldlines/commits` by default.

- **In the game**: `/save` saves, `/load` loads a save or a snapshot of this run, `/undo` undoes the last step, `/undo list` lists this line's turns, `/undo <turn>` branches a new line from that turn. See [Save · branch · undo](/docs/players/saves).
- **On the web**: the run's commit graph is drawn on screen; "roll back to here" forks a new branch at that turn and keeps the current line.
- **On the command line**: `neonrp commit log · checkout · branch · gc · verify`.

Going back never deletes anything: it opens a new line from an old commit.

<!-- section: why -->
## Why it matters

The world grows things by itself (new places, caravans, rumors). The same opening can grow into two different worlds on two lines — a basic tool for simulating and testing a world's rules.
