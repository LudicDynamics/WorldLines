---
title: "Building Character Agents"
description: "A first-class flow for building character-specific AI agents is on the roadmap. This page previews the intended shape."
---

<!-- section: shipping -->
## ✓ Shipping in v0.2.0

Multi-agent character NPCs and soul-agents are **live** in v0.2.0. Characters are authored as soul bundles (persona, character, agents, memo) and can be played via [Soul Talk](https://hub.worldlines.gg/play/souls/elena) on the WebHub or loaded locally via the CLI.

For world-NPCs, the engine supports per-NPC agent directories under `agents/` (see the [CLI `agent new`](/docs/guides/world-editor#agents) command). The orchestrator dispatches to these agents per-context — combat-referee, dungeon-agent, town-agent, etc.

<!-- section: agent-structure -->
## Agent directory structure

Create `agents/my-agent/` with:

```
agents/my-agent/
├── agent.json        # triggers, tags, priority
├── system.md         # system prompt template
├── skills/           # optional: skill fragments
└── tools.json        # optional: extra tool definitions
```

Scaffold with the CLI:

```bash
neonrp agent new my-agent
```

<!-- section: agent-json -->
## agent.json

```json
{
  "id": "harbormaster",
  "triggers": ["harbor", "dock", "ship"],
  "tags": ["location:harbor", "npc:official"],
  "priority": 50,
  "routing": {
    "invoke": "on_match",
    "fallback_to": "town-agent"
  }
}
```

The dispatcher picks this agent when the query matches triggers or tags, subject to priority.

<!-- section: test-agent -->
## Test the agent

```bash
neonrp agent run harbormaster --query "who is in charge of the harbor?"
neonrp agent run harbormaster --query "register a ship" --apply
```

Add `--json` for machine-readable output. Add `--fixture file.json` to stub the LLM response during tests.
