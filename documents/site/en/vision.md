---
title: "Vision"
description: "A world simulation where every character living in it truly comes alive."
---

<!-- section: harness -->
## Three parties, and a judge

Every run in WorldLines has three parties, each with a mind of its own:

- **The world**, played by the host. It owns places, time, prices and rules; it decides whether something can work and whether to roll, and writes the result into the world;
- **The player**: you. What you say is an **attempt**, not a fact;
- **The characters**: the people who live in the world. Each has their own goals, memories and limits; they agree, refuse, and follow their own plans when you are not around.

There is also a **judge** with one job: deciding whether the talk is settled and the turn should move from planning to resolve. With a Worldlines account, Jev judges; otherwise the run's own model does.

The three parties are kept apart: what you say on a character's behalf doesn't count, and a character can't rewrite the world's rules.

<!-- section: emergent -->
## Orchestration → a living world

On top of the three parties, the **orchestration** a template brings (today: two beats, talk first and then resolve) runs the whole world simulation and lets drama *emerge*. Story isn't scripted; it surfaces from the friction between you and the characters as they pursue their own goals. The orchestration keeps the world coherent; the characters make it alive and unpredictable.

<!-- section: social-experiments -->
## Beyond SNS: worlds for social experiments

Multi-agent simulation isn't only for social networks. We want WorldLines to host **social experiments in worlds beyond social networks**: towns, courts, expeditions, fantasy societies, where many characters act under real constraints and you can watch what emerges.

<!-- section: core -->
## The core: make the characters come alive

But the heart of it is simple. Above every benchmark and experiment, our central goal keeps coming back to one thing: making **every character genuinely come alive** inside the simulation — to remember, to want, to change, to surprise you. A world is only as alive as the people living in it.

<!-- section: use-cases -->
## What we built this engine for

- interactive-experience creation
- multi-agent society experiments (beyond social networks)
- agent research
- personality-model and world-model benchmarks

The engine makes these possible by giving creators **constraints, not scripts**.

<!-- section: different -->
## How it differs from other tools

**Character chat, like Character AI**: you get one character to chat with; the world is a backdrop. WorldLines puts the world first: characters live in a place with locations, time, rules and other people, what you do has consequences, and the consequences stay. The same character can carry their memories into different worlds.

**SillyTavern**: a power-user front end that sends carefully tuned prompts to the model you choose, the best of its kind for prompt-driven chat. WorldLines takes another route: an agent orchestration runs a world, the model proposes, and the engine checks before it writes. The two don't conflict: SillyTavern cards import directly (see [Your character](/docs/players/your-character)).

**General orchestration frameworks, like LangGraph**: nodes, edges, state and checkpoints to build any workflow. WorldLines is built for one thing: playable worlds. Its building blocks are worlds, characters, two-beat turns, templates and play contracts, not a general graph you design yourself.

**Social-network simulators**: many agents posting, following and influencing each other. WorldLines aims at tabletop-style role-play: a place you walk into and play, where every character is themselves, with memories and a will.

Why an engine and not just prompts: a world has to be saved, branched and replayed; rules have to stop the model making things up; state has to be files you can read and compare. That is a game engine's job.

<!-- section: community -->
## Community

Questions, bug reports, worlds to show off: come to [Discord](https://discord.gg/HJYWbdqWrE).
