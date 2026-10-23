---
title: "Folders & Versioning"
description: "The on-disk shape of a world (game/), a soul (soul/), and how the three version axes — creator, instance, commit — relate. One folder layout, two consumers: the engine writes it, the web renderer walks it."
---

<!-- section: shared-contract -->
## The shared contract

This is the canonical reference for the on-disk shape of a **world** (`game/`), a **soul** (`soul/`), and how the three version axes relate.

It synthesises the design-locked SoulHub (M16) and commit-versioning (M17) work; the world `game/` half documents what already exists on disk today. One folder layout, two consumers: the engine writes these folders, the web renderer walks them.

<!-- section: world-folder -->
## The world folder — game/

A world bundle is a `game/` directory. Creator-authored, versioned by the world author, distributed via WorldHub. Actual current layout:

```
game/
├── agents/                 # the world's agent roster (creator-versioned template)
│   ├── manifest.json       # which sub-agents this world ships (world-agent + domain agents)
│   └── contracts/          # per-agent IO contracts
├── meta/
│   ├── run_state.json      # live position / time / turn_count (per playthrough)
│   ├── active-agent.json   # which sub-agent currently holds the write lock
│   ├── game-start.json     # opening scene / handoff
│   ├── flag_aliases.json   # readable names for story flags
│   └── schedule.json       # timed / scheduled world events
├── lore/
│   ├── story.md            # main storyline (append-only narrative)
│   └── notes.md            # rumours / world observations
├── world/
│   ├── world_map.json      # node graph
│   ├── regions.json
│   └── factions.json
├── towns/<Txxx>/           # town location nodes
├── dungeons/<Dxxx>/        # dungeon location nodes
├── rules/                  # rule schema (dice, checks, combat)
└── player/                 # legacy player state — migrates into a soul
```

- `game/agents/manifest.json` is the **creator-versioned template** for the world's sub-agent team. At playthrough creation it is *seeded* into `playthrough.json`; the running engine reads `playthrough.json`, never the bundle manifest directly.
- `game/player/` is the **old** single-player-state model. Under M16 it is superseded by a soul folder; existing games auto-migrate.

<!-- section: soul-folder -->
## The soul folder — soul/

A soul bundle is a self-contained character. Can be the player avatar or an NPC. Distributed via SoulHub. Design-locked shape (M16, option B — NeonRP-native, not legacy-compatible):

```
souls/<sid>-<instance_id>/
├── soul.json               # machine identity envelope (NeonRP-specific)
├── soul.md                 # prose-facing soul charter (voice / values / taboos)
├── run_state.json          # live position/status (soul-orchestrator/action write)
├── agents/
│   ├── manifest.json       # the soul's 6-agent roster + per-agent write globs
│   └── contracts.md        # input/output schema per agent
├── persona/                # immutable psychological kernel
│   └── core_traits.json  motivations.json  values.json  relationships.json
├── background/             # immutable lore: origin.md  history.md  secrets.md
├── character/              # RPG mechanics (soul-action only)
│   └── stats.json  inventory.json  equipment.json  wallet.json  status.json  profile.json
├── rules/                  # decision/behaviour guardrails (read-only)
├── short-term-memo/        # session working memory
├── long-term-memo/         # durable memory (soul-memory writes)
├── trajectory/             # append-only autonomous-action log
└── .commits/               # the soul instance's own commit chain (M17)
```

**`soul.json` — machine identity envelope:**

```json
{
  "schema_version": 1,
  "sid": "elena",
  "name": "Elena Voss",
  "name_local": "艾莲娜",
  "version": "1.0",
  "source": {"kind": "soulhub|builtin|local-create", "hash": "...", "version": "1.0"},
  "agent_template": "heroine-classic|minimal",
  "tags": ["companion", "mage"]
}
```

**`soul.md` — prose-facing soul charter.** New first-class root file alongside `soul.json`. The one-file natural-language overview of *how this soul should feel and behave* in roleplay: first-person identity and self-image, voice and emotional tone, values / taboos / non-negotiables, what the soul tends to notice, hide, pursue, or avoid. It complements — never replaces — the structured files: `soul.json` = machine identity / version anchor · `soul.md` = runtime-facing natural-language charter · `persona/*.json` = structured psychological kernel · `background/*.md` = factual lore. NeonRP's roleplay adaptation of the broader "soul document" pattern — explicitly roleplay-facing, not a generic assistant constitution.

**Soul agent roster.** `soul/agents/manifest.json` lists the 6 specialists: `soul-orchestrator` (dispatcher) + `soul-mind` (cognition) + `soul-memory` (retention) + `soul-action` (execution) + `soul-dialogue` (speech) + `soul-narrative` (story interface). Each carries a `write_globs` whitelist; the apply pipeline rejects writes outside it.

**Write-permission contract:**

| Path | Writer |
|---|---|
| `persona/` `background/` `rules/` | none (immutable post-creation) |
| `soul.md` | none (immutable post-creation) |
| `soul.json` | `soul-orchestrator` — on rename only |
| `character/` | `soul-action` |
| `short-term-memo/` | `soul-memory`, `soul-dialogue` |
| `long-term-memo/` | `soul-memory` |
| `trajectory/` | `soul-action`, `soul-orchestrator` (append-only) |
| `run_state.json` | `soul-orchestrator`, `soul-action` |
| `agents/manifest.json` | never (versioned with the soul bundle) |

**Migration.** Existing `~/.worldlines/players/` profiles auto-import to `~/.worldlines/souls/` on first launch after M16: a minimal `soul.json` + persona stub is synthesised; `game/player/*` content maps into `soul/character/*`.

<!-- section: version-axes -->
## Version management — three identity axes

Both worlds and souls share one model. Three orthogonal axes (M17):

- **Creator axis — `slug + version_hash`.** The published, authored version. Immutable. `wid`/`sid` + `version_hash`. One per slug+version in the WorldHub/SoulHub registry. *(The only versioning that existed before M17.)*
- **Instance axis — `instance_id`.** A fork into one playthrough. When a soul enters a world it is forked → a new soul **instance** with its own `instance_id` (UUID at fork) and its own independent per-turn commit chain. The world being played is likewise an instance. The two chains never embed each other's hashes. `(wid|sid, instance_id)` is globally unique — **no timestamp in identity**.
- **Commit axis — `commit_hash`.** Per-turn state snapshot of one instance. Content-hashed → the hash IS the identity, not metadata. World instance and soul instance each have their own commit DAG (branchable, no merge in v1). A commit bundles folder blob(s) + every agent's conversation snapshot + a `determinism` block (rng seed, rolls, llm-calls hash) — a complete, portable, deterministic execution context.

**Full address + binding:**

| Asset | Address |
|---|---|
| World | `(wid, instance_id, version_hash, commit_hash)` |
| Soul  | `(sid, instance_id, version_hash, commit_hash)` |

The world↔soul relationship and the live agent team are authoritative **only** in the session-layer playthrough manifest at `~/.worldlines/games/<wid>-<world_instance_id>/.neonrp/playthrough.json`. It carries the world instance ref + `world_agent_team` (seeded from `game/agents/manifest.json@<version_hash>`) + the list of soul instances. A world commit additionally carries a *read-only* `soul_scene_index`; souls never point back at worlds.

**Timestamp rule.** Timestamps are never part of identity. `instance_id` is unique; `commit_hash` pins the state. `archived_at` appears only when a commit is packaged for upload/export — a human-facing label for sorting, never a key. **Hash locates; timestamp only labels.**

<!-- section: on-disk-map -->
## On-disk map

```
~/.worldlines/
├── games/<wid>-<world_instance_id>/
│   ├── .neonrp/
│   │   ├── playthrough.json     # the binding
│   │   ├── HEAD                 # current world commit_id
│   │   └── sessions/<branch>.jsonl
│   ├── game/                    # world working tree
│   └── souls/<sid>-<soul_instance_id>/   # soul working trees
├── souls/<sid>-<ts>/            # downloaded/created soul library (pre-fork)
│   └── .commits/<soul_commit_id>.json + blobs/
└── commits/
    ├── worlds/<world_commit_id>.json
    ├── refs/<wid>/{HEAD,branches/*,tags/*}
    └── blobs/<hash>.{tar,jsonl}.zst
```

<!-- section: sandbox-replay -->
## Relationship to sandbox / replay

This model is a **superset** of the M4 sandbox/replay design: `sandbox` = fork a commit onto a branch; `save` = a degenerate single-agent commit; `replay verify` = cross-machine commit-hash comparison. The engine's stable tree-hash is reused verbatim for folder hashing. M4's reserved seed/rolls interface is filled by the commit `determinism` block.

See also: [World Protocol](/docs/protocol/world) · [Soul Protocol](/docs/protocol/soul) · [Agent Protocol](/docs/protocol/agent).
