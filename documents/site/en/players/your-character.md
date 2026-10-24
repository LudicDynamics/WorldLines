---
title: "Your character"
description: "Characters live in your own library and can join many worlds; worlds and characters others share, and SillyTavern cards, are one import away."
---

<!-- section: library -->
## The character library

Your characters live in the library (`~/.worldlines/souls/`) and belong to no single world. One character can join many worlds:

- who they are can differ per world, but it is the same personality;
- what happens in a run belongs to that run; at the end, only what that kind of game promises to carry (memories, trust, affection) comes back to the character;
- a role and secret handed out in a murder mystery never follow the character into another world.

<!-- section: bring -->
## Bringing a character into a world

In the terminal game:

- `/cast` lists the characters you can bring in; `/cast <character>` brings one into this world;
- `/who <character>` shows where they are and what they remember;
- `/remove <character>` takes them out of this world (the library copy is untouched);
- `/reset <character>` makes them forget what happened in this world, back to how they arrived.

Not built yet: choosing a library character as **the protagonist you play** when a run starts. For now you play the role the world gives you (the investigator in Greyoak House, for example).

<!-- section: share -->
## Importing worlds and characters others share

Someone sends you a `.zip`:

- **web**: on the Template page, choose "Import…" and pick the file;
- **terminal**: `/import <file>`.

The world goes into your template store and the characters it carries into your library; one with the same name as yours but different content gets a new name, never overwriting yours.

To share your own: "Export" on the Template page. Works in the default zone (including official worlds) can be played but not exported. See [Export and import](/docs/creators/export-import).

<!-- section: tavern -->
## Importing a SillyTavern card

Got a SillyTavern character card (`.png` or `.json`)? In the terminal game:

```text
/import my-character.png
```

The engine reads the card and uses your current model to fill it out into a complete character in your library. When it is done it suggests `/cast <character>` to bring them into the current world.

Filling out the card calls the model, so an import takes a little while and uses a little of your model budget.
