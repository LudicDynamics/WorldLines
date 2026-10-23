---
title: "Agent Protocol"
description: "What an agent is, what it can read and write, and how a set of agents coordinates inside a world or a soul."
---

<!-- section: what-is-an-agent -->
## What an agent is

An *agent* is a single LLM-driven decision unit with explicit permissions, a defined role, and a contract that says what it does when called. Agents are not standalone — they live inside either a world bundle (`agents/` under a world) or a soul bundle (`agents/` under a soul), where a manifest declares the set and the routing rules between them.

This protocol is the **contract layer**. It says nothing about *which* agents you should ship — that's the world author's or soul author's choice. NeonRP ships two canonical sets:

- **World side** (`game/agents/manifest.json`) — the 10-agent, 4-layer roster the runtime calls the *world-agent team*: `orchestrator` (L1 router) · `town-agent` `dungeon-agent` `combat-referee` `rules-referee` `world-builder` (L2 domain) · `npc-mind` `story-narrative` (L3 perspective) · `clock-keeper` `world-evolution` (L4 world-time).
- **Soul side** (`soul/agents/manifest.json`) — the 6 specialists: `soul-orchestrator` (dispatcher) · `soul-mind` (cognition) · `soul-memory` (retention) · `soul-action` (execution) · `soul-dialogue` (speech) · `soul-narrative` (story interface).

Custom worlds and souls swap these freely. The protocol just ensures every agent declares what it touches.

<!-- section: the-contract -->
## The contract

Every agent declares an `agent-contract@0.1.0`-shaped JSON file (or Claude-Code-style `.md` with frontmatter). The minimum:

```json
{
  "schema_version": "0.1.0",
  "agent_id": "soul-mind",
  "name": "Soul Mind Agent",
  "role": "character-agent",
  "system_prompt": "...",
  "permissions": {
    "read_globs":  ["persona/**", "*-memo/**", "run_state.json"],
    "write_globs": [],
    "deny_globs":  ["**/secrets.md"]
  },
  "routing": { "scope": "any", "trigger_condition": "decision_required" },
  "max_turns": 20
}
```

Key invariants:

- **Deny-first permissions.** No globs = no access. Every read/write must be explicit.
- **`deny_globs` beats `write_globs`.** Use it to carve holes inside otherwise-permitted areas.
- **Role labels are open.** Use a canonical string (orchestrator, world-agent, character-agent, rule-agent, town-agent, dungeon-agent, combat-referee, facility-agent, notary, narrative) when applicable, or `custom` otherwise.

<!-- section: the-manifest -->
## The manifest: how a set coordinates

`agents/manifest.json` lists the set and declares routing rules:

```json
{
  "schema_version": "0.1.0",
  "agents": [
    { "id": "soul-orchestrator", "role": "orchestrator", "agent_path": "contracts/orchestrator.json" },
    { "id": "soul-mind", "role": "character-agent", "agent_path": "contracts/mind.json" }
  ],
  "routing_rules": {
    "after_player_turn": {
      "agents": ["soul-orchestrator", "soul-mind", "soul-action", "soul-memory", "soul-narrative"]
    },
    "conversation": {
      "agents": ["soul-dialogue", "soul-mind", "soul-memory"]
    }
  }
}
```

Routing rules support three shapes:

- **`agents`** — sequential pipeline triggered by the rule
- **`facilities`** — per-facility-type sub-agent map (towns dispatch to `shop_*`, `inn`, `guild`, …)
- **`transitions`** — state-change → next-rule pointer (e.g. world scope → enter_town → town scope)

<!-- section: three-layers -->
## Owner-directed runtime (M18)

The topology is **owner-directed**, not a peer mesh. A singleton **world-agent** owns `game/`, the turn loop, and the commit transaction. At turn start it fans out to N **character-agents** — one per active soul — each running its own LLM instance and writing only inside its own `souls/<sid>/` tree under the per-soul permission globs. Every world-level closure returns to the world-agent.

```
            world-agent  (singleton: owns game/, turn loop, commit)
                 │  fan-out at turn start
     ┌───────────┼───────────┐
     ▼           ▼           ▼
 character-   character-   character-
  agent       agent        agent
 (Elena)     (Conductor)  (Passenger)
  own LLM     own LLM      own LLM
     └───── proposals ─────┘
                 ▼
        apply pipeline (per-soul globs) → one M17 commit
```

The contract layer is what makes it safe — a soul's `soul-action` can write outside its tree only if its `write_globs` say so. See [Folders & Versioning](/docs/protocol/folders) for the commit boundary.

<!-- section: see-also -->
## See also

- [World Protocol](/docs/protocol/world) — what the world-side agent set runs against
- [Soul Protocol](/docs/protocol/soul) — what the soul-side agent set runs against
- Canonical spec on GitHub: [AGENT-PROTOCOL.md](https://github.com/LudicDynamics)
