---
title: "Engine Modes — the Multi-Agent Simulation (+ lighter Fast / Orchestrator)"
description: "WorldLines is a multi-agent simulation: a world-agent wrapping a society of independent souls. Fast and Orchestrator are lighter modes for simpler, single-thread scenes."
---

<!-- section: comparison -->
## At a glance

| Mode             | What runs each turn                                         | Status              |
|------------------|------------------------------------------------------------|---------------------|
| **Multi-Agent**  | A world-agent wraps **active souls** — each an independent character-agent with its own mind | ✅ Shipped (v0.2.3, local) |
| **Orchestrator** | A world-agent re-routes to domain agents via `task()`       | ✅ Shipped           |
| **Fast**         | A single agent, minimal routing                             | ✅ Shipped           |

**Multi-Agent is the engine** — a world-agent wrapping a society of independent souls, each its own mind. This is the **village model**, and where every world is heading. **Orchestrator** (a world-agent routing to domain agents over data-driven NPCs) and **Fast** (a single agent) are lighter modes for simpler, single-thread scenes. All three write the same event-log format and the persisted state is identical — the difference is **what thinks each turn**.

**Multi-Agent runs locally** (TUI / CLI) today; hosted play offers the lighter Fast + Orchestrator. It's reproducible: any world with a `souls/` folder + `playthrough.json` engages it. See [worldlines/templates/stoneford-town.template](https://github.com/LudicDynamics/WorldLines/tree/main/worldlines/templates/stoneford-town.template) (Stoneford) and [worldlines/templates/pct-house.template](https://github.com/LudicDynamics/WorldLines/tree/main/worldlines/templates/pct-house.template) (Greyoak House, 2 souls).

<!-- section: fast -->
## Fast Mode

A **single agent** handles the turn end-to-end. No orchestrator, no delegation, no `task()` calls.

**Good for**:
- Cheapest per-turn LLM cost
- Quick iteration while authoring
- Narration-heavy scenes where routing isn't needed

**Limitations**:
- No sub-agent specialization — combat questions reach the same agent as narration
- State drift risk higher on complex scenes that cross domains

<!-- section: orchestrator -->
## Orchestrator Mode

The default for Stoneford. An **orchestrator** / narrator agent sits on top of domain agents (town / dungeon / combat-referee / world-builder / rules-referee) and **re-routes every turn** via a `task()` tool.

**Good for**:
- Scenes that span multiple domains (combat inside a town, ritual in a dungeon, etc.)
- Any moment where rule consistency matters
- Canonical play loop

**Cost**:
- Every turn pays orchestrator + at least one domain agent
- Latency bounded but higher than Fast

<!-- section: multi-agent -->
## Multi-Agent Mode — the village model ✅

**Shipped in v0.2.3 (local).** This is the **village**. Instead of one narrator playing every character, **each character is its own AI agent** — a "soul" with its own personality, memory, secrets, and goals. They think for themselves.

A **world-agent** hosts the scene like a game master: each turn it wakes the characters who are present, lets each one decide what to say and do, then weaves their moves into a single narration.

```
              world-agent  (the host / narrator)
                    │  wakes whoever is in the scene
          ┌─────────┼─────────┐
       Kagami     Hane      Shiro      ← each an independent soul:
      (own mind) (own mind) (own mind)    its own memory, agenda, voice
          └─────────┼─────────┘
                    ▼
              world-agent  → narrates the turn; the world remembers
```

**Why it matters**

- **Each character is real.** Elena isn't a line the narrator writes for her — she's an agent who decides for herself, and can surprise you.
- **They remember.** Souls keep their memory, relationships, and personal arc across turns, so the village evolves and characters bring up what you did earlier.
- **A soul is portable.** Because each one is self-contained, the same Elena can travel from Stoneford into Kagura Island and still be herself.

**Try it** (runs locally today):

```bash
neonrp template build worldlines/templates/pct-house.template /tmp/pct-house && neonrp play --project /tmp/pct-house   # Greyoak House
neonrp template build worldlines/templates/stoneford-town.template /tmp/stoneford-town && neonrp play --project /tmp/stoneford-town   # Stoneford
```

Any world that ships a `souls/` folder + a `playthrough.json` becomes a village automatically. Author your own characters with the `soul-authoring` workflow.

Hosted play (WebHub) currently covers Fast + Orchestrator; bringing the village online is a separate track.

<!-- section: switching -->
## Switching router modes

Router mode is per-turn, not per-project. Switch it in the TUI:

```
/router-mode fast
/router-mode orchestrator
/router-mode multi-agent
```

Or pass `--router-mode <mode>` to `neonrp run`. The session log records the router mode on every event so replay is always faithful.
