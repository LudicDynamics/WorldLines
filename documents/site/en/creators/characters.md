---
title: "Character library and casting"
description: "Characters belong to no world: they live in the library, templates hold links, and a run makes them real."
---

<!-- section: library -->
## The character library

> **Status: ships with 1.0**

A character (soul) lives in the library `~/.worldlines/souls/<name>/`: personality, memories, looks and portrait are there, and it belongs to no world.

- One character can join many worlds; one world can cast many characters.
- A world does not hold a copy of the character — it holds a **link**.
- Only when a run starts (a template becomes a run) is the character copied in; from then on its memories and state in that run belong to that run.
- Change the character in the library and the next run gets the new one.

<!-- section: cast -->
## Casting: the template's cast list

> **Status: ships with 1.0**

Each row of a template's `souls` is one cast member:

```json
"souls": [
  {"sid": "chara", "role": "npc"},
  {"sid": "mira", "lib": "mira", "role": "companion"},
  {"sid": "guide", "path": "souls/guide"},
  {"pool": [{"sid": "a", "lib": "a"}, {"sid": "b", "lib": "b"}, {"sid": "c"}], "pick": 2}
]
```

| Row | What it is |
|---|---|
| `{"sid": …}` | a character native to the world (Greyoak House's butler, Stoneford's Elena …) |
| `{"sid": …, "lib": …}` | a character from the library — a link. When you write `template.json` by hand, `sid` is required: without it Lint reports `ref.soul` and the run skips the row |
| `{"sid": …, "path": …}` | a character kept inside the template folder |
| `{"pool": [...], "pick": N}` | a pool; each run draws N (werewolf, random line-ups) |
| `role` | `npc` a world NPC (default) · `companion` · `player` the lead, played by the player (at most one) |

Stoneford's cast is two world-native characters: `{"sid": "elena", "role": "npc"}`, `{"sid": "rowan", "role": "npc"}`.

Authoring writes the whole list with the `set_cast` op: a `{"lib": …}` row without `sid` gets it from the character's `soul.json`; a broken link, a character cast twice, an unknown role or two players refuse the batch and nothing is written.

<!-- section: switches -->
## A character's own switches

Written in the character's `soul.json`:

| Field | Meaning |
|---|---|
| `standalone: true` | can be chatted with on its own without being gained first |
| `takeable` (default `true`) · `take_when` | when the condition holds the player takes it home with its full memory. `take_when` is `companion_at_ending` (default: it is at the player's side when an ending lands) or `ending:<ending id>`. Free Zone runs let nobody be taken |
| `assets: {"sprite": "portrait"}` | the sprite is the portrait (when the portrait is already full-body); no second picture is stored |

<!-- section: per-world -->
## The same character, different in every world

> **Status: ships with 1.0**

The same character is "the client's friend" in Greyoak House and "a traveller who lost her memory" in Stoneford — those differences live in the **template**; the library character is never changed:

- `prompts/souls/<sid>/`: may override only `soul.md`, `persona/`, `rules/`, `agents/` (the personality and voice layer);
- `world-overlay/`: a different portrait for this world.

Which worlds a character is in: `GET /api/v1/local/souls/<name>/bindings`.

<!-- section: protocol -->
## The soul protocol: what a contract asks of characters

> **Status: not built yet** — what follows is the settled direction.

Different games ask different things of a character: a mystery TRPG needs an investigator sheet, a murder mystery hands everyone a role and a secret. Contracts will get a `souls` section:

- **in** — the sheet it needs, whether a player is required, required assets; a character without the sheet gets one from the converter at the start of the run, stored per contract in `character/sheets/<contract>.json`;
- **during** — roles and secrets the world hands out live in that run only and never follow the character elsewhere;
- **out** — only what the contract lists (memories, trust, affection) is written back to the library.

The player comes from the library too: pick one, or create one.

Details: the `contract` spec · `neonrp spec contract`.
