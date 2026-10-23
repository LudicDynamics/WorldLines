---
title: "Protagonists and NPCs"
description: "Only protagonists are independent; NPCs are driven by the world; promoting an NPC is an engine operation."
---

<!-- section: soul -->
## Protagonists (souls)

> **Status: ships with 1.0**

A protagonist has its own agent: personality, goals, commitments, memory; it decides and speaks for itself. A protagonist is a folder `souls/<sid>-<iid>/`: persona and rules in markdown, mood / trust / intention / location in `run_state`, portraits in `assets/`.

In Stoneford Elena follows you; Rowan, in Jadestone, sets out after 11:00 on his own goals — nobody scripts him.

<!-- section: npc -->
## NPCs

Helun at the guild and Mira at the inn are NPCs: no agent of their own; the world agent speaks for them and moves them by rule. An NPC is an instance of the open-schema class `npc`.

<!-- section: cast -->
## Promotion

`neonrp cast` puts a protagonist into any world. Promoting an NPC in a world is also a cast: it creates a protagonist folder, registers it in the cast, and from then on it decides for itself — an engine operation, not a field edit.
