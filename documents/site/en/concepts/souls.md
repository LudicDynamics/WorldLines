---
title: "Characters and NPCs"
description: "Three words: a character (soul) has its own agent; a world NPC is voiced by the world; the protagonist is the one you play."
---

<!-- section: terms -->
## Three words

| Word | What it is | In Stoneford |
|---|---|---|
| **Character (soul)** | Has its own agent: persona, goals, promises, memory; decides and speaks for itself | Elena, Rowan |
| **World NPC** | No agent of its own; the world speaks for it and moves it by the rules; an instance of the open-schema `npc` class | Kas at the gate, Heron at the guild, Mira at the inn |
| **Protagonist** | The person you play | The traveller stuck outside the north gate in the fog season |

<!-- section: soul -->
## Characters

In a run, a character is a folder `souls/<sid>-<iid>/`: persona and rules in markdown, mood / trust / intent / position in `run_state`, portraits in `assets/`. A character's feelings, thoughts and diary are settled by herself; the world does not write them.

In Stoneford, Elena meets you at the north gate; Rowan is chasing the northern legend of the "edge of the world" and acts on his own goals — nobody writes a script for either of them. A character who is not with you takes a beat where she is.

A character's place in a run (`role` in `playthrough.json`) is one of three: `npc` (lives in the world, with her own agent), `companion` (can be chosen as your companion), `player` (as your avatar).

<!-- section: library -->
## The character library and links

Characters live in the **character library** (`~/.worldlines/souls/<name>`). A template holds only a link; the character is copied into a run when it starts:

```json
"souls": [
  {"sid": "elena", "role": "npc"},
  {"sid": "mira", "lib": "mira", "role": "companion"}
]
```

- `{"sid": …}`: a character that comes with the world.
- `{"sid": …, "lib": "<name>"}`: linked to the library; made real at run start as `souls/<sid>-si-<sid>-<template id>/`.
- `{"sid": …, "path": "<path inside the template>"}`: a character shipped in the template folder, also copied only at run start.

So one character can appear in many worlds, with separate memories in each run. When a character's `soul.json` says `"assets": {"sprite": "portrait"}`, her standing sprite is her portrait — no second picture needed. How to write characters: [Characters and casting](/docs/creators/characters).

<!-- section: cast -->
## Putting a character into a world

`neonrp cast <character>` casts a character from the library into a world, as an `npc` by default; with `--as player` she becomes your avatar (the protagonist). In the game the same thing is `/cast [character] [npc|player]`. It is an engine operation: it creates the character folder and registers her in the run's cast, and from then on she decides for herself — not a field you flip. A world NPC is never "promoted" by this; to give Heron his own agent, write a character for him and cast it in.
