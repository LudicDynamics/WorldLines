---
title: "Events, Snapshots & Branches"
description: "WorldLines stores every change as an append-only event. Snapshots and branches make rewind cheap."
---

<!-- section: events -->
## Events

Every change in the world is an **append-only event** written to `.neonrp/events.jsonl`:

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

Events are the **source of truth**. `game/` is a materialization of the event stream. You can always rebuild `game/` by replaying events from event 0.

<!-- section: snapshots -->
## Snapshots

A **snapshot** (aka save) is a full copy of `game/` at a given event, plus metadata. Snapshots live in `.neonrp/saves/<name>/`. They exist to make rewind fast — replaying 10,000 events is slow; loading a snapshot is a file copy.

```bash
neonrp save opening-scene
neonrp load opening-scene
```

<!-- section: branches -->
## Branches

A **branch** is a named head pointer on the event log. Like git, branching is cheap: you fork the current state and write divergent events.

```bash
neonrp branch try-stealing
```

Branches share unchanged entities via copy-on-write under `.neonrp/branches/`.

<!-- section: sandboxes -->
## Sandboxes

A **sandbox** is a branch created *from a snapshot* and marked ephemeral. Sandboxes let you run "what-if" experiments without polluting named branches.

```bash
neonrp sandbox new experiment --from opening-scene --switch
# ... play ...
neonrp sandbox drop experiment --force
```

<!-- section: replay -->
## Replay & Determinism

Given the same events and a seeded LLM (or a cached fixture), replaying should produce the same `game/` state. `replay verify` checks this:

```bash
neonrp replay verify --from opening-scene
```

This is how WorldLines keeps AI-driven state reproducible — a property you can't get from a chat UI.
