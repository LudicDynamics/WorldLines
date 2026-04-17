# Core Concepts

**Language:** [English](./CONCEPTS.md) · [简体中文](./CONCEPTS.zh.md) · [日本語](./CONCEPTS.ja.md) · [한국어](./CONCEPTS.ko.md)

> Status: Beta — conceptual model stable; internals may shift

WorldLines is designed around a small set of primitives. Understand these
and the rest of the engine follows.

## Events

Every change in the world is an **append-only event** written to
`.neonrp/events.jsonl`. An event looks like:

```json
{
  "id": 42,
  "ts": "2026-04-17T10:03:11Z",
  "branch": "main",
  "agent_id": "town-agent",
  "kind": "proposal_applied",
  "ops": [
    {"op": "upsert_text", "path": "player/journal.json", "content": "..."}
  ]
}
```

Events are the source of truth. `game/` is a *materialization* of the event
stream. You can always rebuild `game/` by replaying events from event 0.

## Snapshots

A **snapshot** (aka save) is a full copy of `game/` at a given event, plus
metadata. Snapshots live in `.neonrp/saves/<name>/`. They exist to make
rewind fast — replaying 10,000 events is slow; loading a snapshot is a file
copy.

```bash
neonrp save opening-scene
neonrp load opening-scene
```

## Branches

A **branch** is a named head pointer on the event log. Like git, branching
is cheap: you fork the current state and write divergent events.

```bash
neonrp branch try-stealing
```

Branches share unchanged entities via copy-on-write under `.neonrp/branches/`.

## Undo / Redo

`undo` / `redo` walk the head pointer back and forward, restoring from the
nearest snapshot then replaying forward. Your event log is never destroyed.

## Sandboxes

A **sandbox** is a branch created *from a snapshot* and marked ephemeral.
Sandboxes let you run "what-if" experiments without polluting named
branches. You can drop them cleanly.

```bash
neonrp sandbox new experiment --from opening-scene --switch
# ... play ...
neonrp sandbox drop experiment --force
```

## Replay & Determinism

Given the same events and a seeded LLM (or a cached fixture), replaying
should produce the same `game/` state. `replay verify` checks this:

```bash
neonrp replay verify --from opening-scene
```

This is how WorldLines keeps AI-driven state reproducible — a property you
can't get from a chat UI.

## Agents

An **agent** is a directory under `agents/<agent-id>/` containing:

- `agent.json` — triggers, tags, priority, routing metadata
- `system.md` — the system prompt template
- (optional) `skills/`, `tools.json`, `policies.md`

The **dispatcher** picks an agent for each query using:

1. Explicit `--agent` flag
2. Regex trigger patterns
3. Tag overlap
4. Priority tiebreak

The stoneford starter ships with 6 agents (see [templates/stoneford](templates/stoneford/README.md)).

## Skills

**Skills** are reusable prompt fragments / capability modules an agent can
`use`. Builtin skills (packaged with the engine) appear automatically; you
can also define project-local skills in `skills/`.

## Plan → Diff → Apply

When an agent writes to the world it does not edit files directly. It emits
a **proposal**:

```json
{
  "run_id": "20260417-100311",
  "agent_id": "town-agent",
  "rationale": "Player examined the harbor; adding observed detail.",
  "ops": [
    {"op": "upsert_text", "path": "towns/stoneford.json", "content": "..."}
  ]
}
```

The engine shows a diff, validates it against the schema, and then applies
it as a new event. You (or an auto-apply rule) approve the transition.

## Harness — Orchestration Loop

WorldLines' agent harness implements a Plan–Diff–Apply loop with:

- Bounded retrieval (minimal-context, hybrid fuzzy+vector)
- Deterministic tool ordering
- Per-turn budget (tokens / tool calls)
- Thinking channel separated from narration

The **orchestrator** agent is the top-level harness coordinator — it routes
to domain agents via a `task()` tool, keeps the game state coherent, and
owns the player-facing narration.

## Build / Sandbox / Play Modes

The TUI exposes three modes:

- **build** — direct file edits with narrative responses. Use when
  authoring worlds.
- **sandbox** — proposal pipeline with manual approve. Safest.
- **play** — GM mode, auto-apply on, full immersion.

Switch via `/mode <name>` inside the TUI.

## Further Reading

- [CLI_REFERENCE.md](CLI_REFERENCE.md) — surface-level commands
- [TUI_GUIDE.md](TUI_GUIDE.md) — interactive workflows
- [templates/stoneford/](templates/stoneford/README.md) — the sample world
