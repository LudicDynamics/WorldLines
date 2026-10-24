---
title: "Redefining the heavy front end"
description: "The AI engine underneath only has to be fast and free; everything you see belongs to the front end. Whatever front end you attach, that is your heavy front end. Our job is to keep the engine fast and solid."
---

<!-- section: split -->
## Two ways to split the work

Most AI chat products have a thin front end. The whole experience lives inside one text box, and whatever the model outputs is what ends up on screen.

We do it the other way around. The AI engine underneath handles state, turns, character agents and the ledger, and it has two goals only: be fast, and be free. Everything you see belongs to the front end, and the front end can be as heavy as it likes: maps, portraits, scenes, animation, voice, staging. What the engine hands the front end is structured state and events, not a block of text for you to parse.

<!-- section: promise -->
## What the engine promises

- **Fast.** A beat takes seconds. State is written first and checked again in the background; it is only corrected if the check disagrees. You never wait on it.
- **Solid.** The model proposes, and the engine verifies before anything is written. Rules stop made-up facts, the engine rolls the dice itself, and every timeout has a fallback.
- **Free.** An open schema: any entity, any property, any rule can enter a world without changing the engine first.

The interface is HTTP, an event stream and files. State is a file you can read, diff and replay, not something that lives inside the model's head.

<!-- section: any -->
## Any front end can plug in

One engine already drives the terminal, the local web UI, worldlines.gg, iOS, and a Godot example. One game can move between front ends, because the state lives in the engine, not in the front end.

You can build your own as well: one that leads with a map, one that leads with voice, one that feels like a game console. The interface is described in [Developer quickstart](/docs/developers/quickstart) and [Godot integration](/docs/developers/godot).

<!-- section: ours -->
## The engine is our job

Speed and stability are on us. We will keep making the engine faster, steadier and more exact in what it allows, and we will keep the interface open.

We are building a standard heavy front end ourselves, but it will not be the only one. The front end is open. The engine is our promise.
