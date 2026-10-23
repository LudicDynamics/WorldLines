---
title: "Soul Protocol"
description: "The shape of a distributable soul: a self-contained agent bundle with persona, memory, goals, and a set of agents that drive behavior. Uploaded to SoulHub."
---

<!-- section: what-is-a-soul -->
## What a soul is

A *soul* is the inner life of a player or NPC: who they are (persona), what they remember (memory), what they want (motivations), how they act (agents). It's deliberately **world-agnostic by default** — the same Elena should be droppable into many worlds. Soul authors pin to specific worlds via the `compatible_worlds` manifest field when behavior depends on world-specific lore.

**Naming.** `soul` is the preferred term going forward. `character` remains as a legacy alias in the schemas; both validate identically. `sid` is the soul id (mirrors `wid` for worlds).

<!-- section: bundle-layout -->
## Bundle layout

```
<sid>/
├── soul.json                          ← machine identity envelope (REQUIRED)
├── soul.md                            ← prose-facing soul charter (REQUIRED)
├── run_state.json                     ← per-run mutable state (REQUIRED)
│
├── persona/                           ← who they are (REQUIRED)
│   ├── core_traits.json
│   ├── values.json
│   ├── motivations.json
│   └── relationships.json
│
├── character/                         ← mechanical surface (REQUIRED)
│   ├── profile.json
│   ├── stats.json
│   ├── status.json
│   ├── equipment.json
│   ├── inventory.json
│   └── wallet.json
│
├── background/                        ← prose lore (optional)
│   ├── origin.md
│   ├── history.md
│   └── secrets.md
│
├── rules/                             ← per-soul constraints (optional)
│   ├── action_rules.md
│   ├── decision_rules.md
│   └── interaction_rules.md
│
├── long-term-memo/                    ← persistent memory
│   ├── emotional_memories.json
│   ├── important_events.md
│   └── learned_facts.json
│
├── short-term-memo/                   ← session memory
│   ├── current_context.json
│   ├── recent_events.json
│   └── conversation_cache.json
│
├── trajectory/                        ← first-person action log
│   └── action_log.md
│
└── agents/                            ← agent set (REQUIRED)
    ├── manifest.json
    └── contracts/<agent_id>.json
```

The soul instance also keeps its own `.commits/` version store (its per-turn commit chain — see [Folders & Versioning](/docs/protocol/folders)).

<!-- section: soul-md -->
## soul.json vs soul.md

Two root files, two jobs. `soul.json` is the **machine identity envelope** — `sid`, name, version, source/hash, agent template. It anchors the soul in the SoulHub registry and lets `list_souls()` discover the bundle fast.

`soul.md` is the **prose-facing soul charter** — the one-file natural-language overview of *how this soul should feel and behave* in roleplay:

- first-person identity and self-image
- voice, speaking style, emotional tone
- values, taboos, and non-negotiables
- what the soul tends to notice, hide, pursue, or avoid

It complements — never replaces — the structured files:

| File | Role |
|---|---|
| `soul.json` | machine identity / source / version anchor |
| `soul.md` | runtime-facing natural-language charter |
| `persona/*.json` | structured psychological kernel (tooling / validation) |
| `background/*.md` | factual lore and secrets |

Think of `soul.md` as NeonRP's roleplay adaptation of the broader "soul document" pattern: one file that tells the model how this being ought to *be*, while the surrounding files tell the engine what it *contains*. Both `soul.json` and `soul.md` are immutable after creation (only `soul-orchestrator` may touch `soul.json`, and only to rename).

<!-- section: six-agents -->
## The reference soul: 6 agents

The first sample soul ([Elena](https://hub.worldlines.gg/souls/elena), `elena@1.0`, hash `827ac36a11c1`) ships the 6-agent baseline:

| Agent | Responsibility |
|---|---|
| **orchestrator** | Triggered after each player turn. Sequences the other agents. |
| **mind** | Situational analysis + persona-aligned decision. |
| **action** | Executes movement, item use, NPC interaction, investigation, rest. |
| **memory** | Stores new perceptions; consolidates short-term → long-term. |
| **dialogue** | Generates utterances; voice / mood / disclosure-level filter. |
| **narrative** | Talks to the world's narrative agent — sends requests, observations, plot suggestions. |

Custom souls can swap any subset by shipping a different `agents/manifest.json`. The 6-agent set is the recommended baseline, not a constraint.

<!-- section: authoring-rules -->
## Authoring rules of thumb

- **`sid` is forever.** It's the public handle.
- **Sample text should be short.** The bundle ships the *shape* of the soul; an LLM rewrites the prose during onboarding when the player describes the soul they want. Keep `persona/values.json` to a few entries, not an essay.
- **Don't ship spoilers in `learned_facts.json` at publish time.** Those entries accumulate during play. Shipping them defeats the point of dropping the soul into fresh worlds.
- **Markdown for prose, JSON for structure.** Reach for Markdown only in `background/`, `rules/`, `*-memo/important_events.md`, and `trajectory/action_log.md`. Everything else stays JSON so editors can validate.

<!-- section: distribution -->
## Distribution

```
neonrp world upload my-soul --kind souls --slug elena --version 1.0
# → s3://worldlines-hub/souls/<hash>.zip + souls/index.json entry
neonrp world download elena --kind souls
```

Browse published souls at [hub.worldlines.gg/souls](https://hub.worldlines.gg/souls). The launcher consumer flow is in design — track [SOULHUB.md on GitHub](https://github.com/LudicDynamics).

<!-- section: see-also -->
## See also

- [World Protocol](/docs/protocol/world) — what the soul plays in
- [Agent Protocol](/docs/protocol/agent) — how souls actually decide and act
- Canonical spec on GitHub: [SOUL-PROTOCOL.md](https://github.com/LudicDynamics)
