---
title: "Agents & Orchestration"
description: "Agent design in WorldLines — how the file-backed agent format + harness customization give you high-freedom game authoring."
---

<!-- section: philosophy -->
## Why file-backed agents

WorldLines' agent system is **radically file-backed**. Every agent — character, domain, referee — is a directory of plain files:

- `agent.json` — triggers, tags, priority, routing metadata
- `system.md` — the system prompt template (Markdown, human-readable)
- `skills/` — optional reusable prompt fragments / capability modules
- `tools.json` — optional extra tool definitions
- `policies.md` — optional hard rules (v0.2+)

No databases. No API-bound state. You can `git diff` an agent, fork one, copy/paste another. This is the same insight Claude Code applied to code — **the filesystem is the UI**.

<!-- section: harness-editing -->
## High-freedom harness editing

The harness — the loop that plans, retrieves context, calls tools, and applies diffs — is **defined by agent files**, not by engine code.

That means a game author can:

- Change the **narration voice** by rewriting a `system.md`
- Change the **retrieval scope** by editing an agent's `tools.json`
- Change the **decision style** by adding a `policies.md`
- Change the **dispatcher behavior** by tweaking triggers / tags / priority

A whole new subgenre (mystery / slipstream / otome / TRPG) can be expressed as a set of agent directory changes over the stoneford base, without touching a line of Python. This is the design space WorldLines is optimizing for.

<!-- section: anatomy -->
## Agent anatomy

A full agent directory looks like:

```
agents/elena/
├── agent.json        # triggers, tags, priority, routing
├── system.md         # system prompt template
├── skills/
│   └── innkeeper.md  # reusable prompt fragments
├── tools.json        # extra tool definitions (optional)
└── policies.md       # hard rules (v0.2+)
```

The stoneford starter ships with **6 agents**: `orchestrator`, `town-agent`, `dungeon-agent`, `combat-referee`, `world-builder`, `rules-referee`.

<!-- section: dispatch -->
## Dispatcher

The dispatcher picks an agent for each query using:

1. Explicit `--agent` flag
2. Regex trigger patterns from `agent.json`
3. Tag overlap with the current context
4. Priority tiebreak

Agents can be invoked directly via CLI:

```bash
neonrp agent run town-agent --query "describe the harbor"
neonrp agent list --json
neonrp agent show town-agent
```

<!-- section: harness-loop -->
## Harness — the orchestration loop

WorldLines' agent harness implements a **Plan → Diff → Apply loop** with:

- Bounded retrieval (minimal-context, hybrid fuzzy + vector)
- Deterministic tool ordering
- Per-turn budget (tokens / tool calls)
- Thinking channel separated from narration

The **orchestrator** agent is the top-level harness coordinator — it routes to domain / character agents via a `task()` tool, keeps the game state coherent, and owns the player-facing narration.

Router modes (`fast` / `orchestrator` / `multi-agent`) change *how* orchestration happens per turn — see [Router Modes](/docs/core-concepts/engine-modes).

<!-- section: skills -->
## Skills

**Skills** are reusable prompt fragments / capability modules an agent can `use`. Builtin skills ship with the engine; you can also define project-local skills in `skills/`.

List available:

```bash
/skills              # inside TUI
```
