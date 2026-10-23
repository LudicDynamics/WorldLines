# Stoneford Elena — Stone Ford · Elena

> A hybrid template built on the real contract of `llm-rpg-starter`/`stoneford-orch`: the old world contract is preserved, and the new soul runtime is wired in.

`stoneford-elena` doesn't tear down and rewrite `stoneford-orch` wholesale; it layers `playthrough.json + souls/` and `soul.md` on top of the world-agent / town-agent / rules-referee contract that has actually run and proven out.

## What This Demo Is

- A testable second world
- A soul-native transitional template that keeps the `game/player/` compatibility layer
- A Stone Ford variant with an explicit heroine

## Runtime Shape

At runtime, this world behaves as:

`world-agent -> active souls -> world-agent`

while still retaining the Stone Ford domain-agent contract family under `agents/`.

## Source Of Truth

- `game/` remains world-agent-owned world state.
- `souls/elena-si-elena0001/` is Elena's soul truth.
- `game/player/*` is a compatibility projection for the current orchestrator-era
  Stone Ford contract. It is useful, but it is not the only truth source anymore.

If soul identity and `game/player/*` drift, treat the soul folder as the long-term
character source and `game/player/*` as the local world-facing projection that should be
reconciled.

## Included Souls

- `elena-si-elena0001` — heroine / player soul
- `rowan-si-rowan0001` — a young adventurer soul from Jadestone, chasing the deep-cave legend of the "world's edge"

## Why This Exists

Kagura proves the pure soul-native path. Stoneford Elena proves the migration path:
you can keep a proven world contract while gradually moving protagonist logic from
`game/player/` toward explicit soul bundles.
