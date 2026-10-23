# Kagura Island

> Japanese-flavored suspense, time loop, Yith mythos, owner-directed soul runtime.

`kagura-island` is one of NeonRP's most complete soul-native templates to date. It keeps
the `orchestrator` router shell, but as long as `playthrough.json + souls/` exist in the root,
the runtime enters the M18 `world-agent -> active souls -> world-agent` wrapper flow.

## Template Layout

```text
kagura-island/
├── runtime_contract.json      # router shell; live soul wrapper still engages
├── playthrough.json           # copied into <game>/.neonrp/playthrough.json
├── agents/                    # world-agent + functional sub-agents
├── game/                      # world truth owned by world-agent
└── souls/                     # 8 full soul folders (M16 schema)
```

## Runtime Reading

- `world-agent` is the sovereign orchestrator.
- `active_souls` in `playthrough.json` define which soul instances think this turn.
- Souls are isolated actors. They do not share folders and do not directly own world
  state.
- Final player-facing narration still closes through `world-agent`.

This means Kagura is not a peer mesh. It is an owner-directed actor set with a single
world close boundary.

## Soul Layout

Every soul folder follows the committed M16 bundle shape:

- `soul.json` — machine identity envelope
- `soul.md` — prose-facing soul charter for authoring / alignment
- `persona/*.json` — structured traits, motivations, values, relationships
- `background/*.md` — history, origin, secrets
- `character/*.json` — visible profile, stats, inventory, status
- `rules/*.md` — roleplay guardrails for that soul
- `short-term-memo/` and `long-term-memo/` — memory stores
- `trajectory/` — action trail
- `agents/manifest.json` — internal specialist roster contract

Current engine path still resolves each soul as one consolidated runtime agent synthesized
from `agents/manifest.json + persona/`. The six specialist entries remain the soul-internal
contract, not six always-live runtime peers.

## Player Binding

The human player is already fixed at setup through `game/meta/roster.json` and
`playthrough.json`. In Kagura this is `kakaru` for the committed Dream 1 run.
The world-agent must not ask the player to choose a character again.

## What This Template Demonstrates

- Soul folders as first-class runtime assets
- World truth vs soul truth separation
- Owner-directed orchestration instead of peer democracy
- Off-stage soul continuity with explicit folder state
- A concrete `soul.md + persona/*.json` split for roleplay authoring
