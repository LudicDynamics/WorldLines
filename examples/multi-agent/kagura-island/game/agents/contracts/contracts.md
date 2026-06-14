# World-agent runtime contracts — 神楽島

## world-agent (orchestrator, singleton)
- **Input:** player action text, current `game/meta/run_state.json`, `game/timeline/current.json`, soul roster from `.neonrp/playthrough.json`.
- **Output:** updated world state (time advance, location/flag changes, taboo/disappearance/loop adjudication). Under M18 the runtime additionally fans the turn out to every active soul instance and commits once.
- **Writes:** `game/timeline/*.json`, `game/locations/*.json`, `game/meta/run_state.json`, `game/lore/notes.md`.

## story-narrative (fallback functional sub-agent)
- **Input:** underspecified edge scenes the world-agent chooses not to resolve directly.
- **Output:** thin descriptive material for the world-agent to integrate.
- **Writes:** none by default; world-agent owns final world-facing persistence.

## souls (the cast — M16 soul instances, bound by playthrough.json)
Each character is a full M16 soul with its own 6 soul-* specialists
(orchestrator/mind/memory/action/dialogue/narrative). The M18 world-agent
registers each soul as a `CharacterAgent` and collects per-turn proposals;
per-folder write permissions are enforced from each soul's
`agents/manifest.json` write_globs (WORLD_SOUL_FOLDERS §2.2-2.3).

## control-plane allowance

The runtime may perform low-entropy, system-style continuity writes for off-stage
souls. This is not a second personality stream and does not grant the world-agent
permission to read or author soul-private thought.

## player binding

The player character is fixed by `game/meta/roster.json` plus `playthrough.json`.
The world-agent must not reopen player selection inside the scene.
