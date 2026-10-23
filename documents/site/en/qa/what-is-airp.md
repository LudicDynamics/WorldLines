---
title: "What is AIRP?"
description: "AIRP = AI RolePlay. Why this category exists and why it needs its own engine."
---

<!-- section: definition -->
## AIRP, defined — our way

**AIRP** stands for **AI RolePlay** — but we mean something specific by it.

The usual AIRP treats an AI as a **role-play partner**: one character you chat with, who plays a part for you. The world is a backdrop; the AI is an object you talk to.

**Our AIRP is different.** We believe in a **real-time, running world** where *every* AI inside it genuinely **lives** — each one an agent with its own mind, memory, and goals, acting for itself, not performing for you. You don't role-play *with* one character; you step into a world that's already alive, full of characters who'd keep living whether you were there or not.

That shift — from "an AI that plays a role" to "a world where the AIs actually live" — is what the rest of these docs are about.

<!-- section: engine-needed -->
## Why an engine?

AIRP needs the same guarantees a game engine gives:

- Persistent state you can save, branch, and restore
- A rules system that prevents AI-driven corruption
- Deterministic replay for debugging
- Structured tools for authoring content

WorldLines is that engine for AIRP.
