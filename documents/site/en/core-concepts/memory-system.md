---
title: "Plan → Diff → Apply"
description: "Agents don't edit files directly. They emit proposals. You review, then apply."
---

<!-- section: proposal -->
## The Proposal

When an agent writes to the world it does not edit files directly. It emits a **proposal**:

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

The engine shows a diff, validates it against the schema, and then applies it as a new event. You (or an auto-apply rule) approve the transition.

<!-- section: ops-schema -->
## Operation Kinds

Operations are a small, closed vocabulary:

- `upsert_text` — create or replace a file with text content
- `upsert_json` — create or replace a JSON entity
- `patch_json` — targeted field updates (by JSONPath)
- `delete` — remove a file
- `move` — rename / relocate

Every op is schema-validated before apply.

<!-- section: retrieval -->
## Retrieval — minimal context

The harness uses **bounded retrieval** to feed only the relevant entities into each agent turn:

- Hybrid fuzzy + vector search
- Per-query entity budget
- Entity kind filters (`--kind location`, `--kind npc`)

From the CLI:

```bash
neonrp find "harbor" --kind location --json
neonrp context "stoneford guild" --limit 5
```

This is what keeps turn latency bounded even as worlds grow to 10,000+ entities.

<!-- section: determinism -->
## Why this matters

Plan → Diff → Apply is what makes WorldLines **reviewable** and **reproducible**:

- You can audit every state change as a structured diff
- Agents can't silently corrupt world state
- `replay verify` can re-derive the same state from events
- Chat UIs offer none of these guarantees
