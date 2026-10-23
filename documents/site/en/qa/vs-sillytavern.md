---
title: "vs SillyTavern"
description: "Compatible with SillyTavern's format — but a different paradigm: agentic simulation, not prompt-by-prompt chat."
---

<!-- section: two-paradigms -->
## Two paradigms: prompting vs agents

**SillyTavern** is a power-user *frontend* that sends carefully crafted **prompts** to your chosen LLM. Characters, lorebooks, prompt macros — it's the best-in-class chat-facing tool for prompt-driven role-play.

**WorldLines is agentic.** Instead of one LLM answering a prompt, an orchestration system — the same kind that powers **Claude Code** and **Codex** — runs a world: agents that plan, call tools, read and write state, and act on their own. We don't prompt a character; we **simulate** one, and the world around it.

<!-- section: compatible -->
## We want to stay compatible

SillyTavern's character cards and world books are a great content format, and we want to meet people where they are. You can already import SillyTavern cards:

```bash
neonrp import sillytavern-card card.png --id mira-ashford
```

The direction: keep the SillyTavern format importable, while offering a **new way to play** on top of it — agentic simulation, not prompt-by-prompt chat.

<!-- section: agent-roleplay -->
## A new kind of role-play

Plenty of people already role-play *directly inside* **Claude Code** or **Codex**, letting an agentic system drive characters and scenes. That's already beyond what a prompt-based frontend was built for — a new paradigm we call **Agent Role Play**.

WorldLines is built for exactly this: simulating personas and worlds through agent orchestration. And we're investing in the **front-end polish** to make agentic role-play feel as good as it is powerful — the depth of a running simulation, without living in a raw terminal.

Pick WorldLines when you want a world that persists, branches, and is genuinely *simulated*. Reach for SillyTavern when you want maximum prompt flexibility and its established extension ecosystem — and import your cards either way.
