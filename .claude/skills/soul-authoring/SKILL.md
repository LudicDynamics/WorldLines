---
name: soul-authoring
description: Scaffold a WorldLines soul folder (角色灵魂包) — a self-contained character bundle that lives under souls/<sid>/ with persona kernel, RPG mechanics, behaviour rules, seeded memory, and the 6 soul-agent manifest. Use when creating a new soul / character that will inhabit a world. Multi-soul → one-world framework.
---

# Soul Folder Authoring

Use this skill when creating a WorldLines soul — a self-contained character
bundle that can be played standalone (talk mode) or dropped into a world
(multi-soul → one-world).

## Architecture

```
souls/<sid>-<ts>/
  soul.md                 ← prose charter (voice, values, pressure pattern)
  persona/                ← immutable psychological kernel
    core_traits.json
    motivations.json
    values.json
    relationships.json
  background/             ← immutable lore
    origin.md
    history.md
    secrets.md
  character/              ← RPG mechanics (runtime-writable)
    stats.json
    inventory.json
    equipment.json
    wallet.json
    status.json
    profile.json
  rules/                  ← decision guardrails (immutable)
    decision_rules.md
    interaction_rules.md
    action_rules.md
  short-term-memo/        ← session working memory
    current_context.json
    conversation_cache.json
    recent_events.json
  long-term-memo/         ← durable memory
    important_events.md
    learned_facts.json
    emotional_memories.json
  trajectory/             ← append-only action log
    action_log.md
  agents/                 ← 6 soul sub-agents
    manifest.json
```

## 6-Agent Set

| Agent | Role | Write Permission |
|---|---|---|
| `soul-orchestrator` | Dispatcher | `run_state.json`, `trajectory/**` |
| `soul-mind` | Cognition | (read-only) |
| `soul-memory` | Retention | `short-term-memo/**`, `long-term-memo/**` |
| `soul-action` | Execution | `character/**`, `trajectory/**` |
| `soul-dialogue` | Speech | `conversation_cache.json` |
| `soul-narrative` | Story interface | `run_state.json` |

## Workflow

1. Read the soul description (one-line premise, archetype, traits).
2. Derive a stable ASCII `sid` slug from the character name.
3. Author `soul.md` first — it constrains voice, values, and social posture.
4. Author `persona/` kernel consistent with the charter.
5. Author `background/` consistent with persona.
6. Author `character/` mechanics sized to the implied power level.
7. Author `rules/` guardrails for runtime agents.
8. Seed memory folders with a plausible starting state.
9. Write `agents/manifest.json` last.

## Immutable vs Mutable

- **Immutable** (author once): `soul.md`, `persona/`, `background/`, `rules/`
- **Mutable** (runtime updates): `character/`, `short-term-memo/`, `long-term-memo/`, `trajectory/`

Make immutable folders complete at authoring time. Mutable folders only need a sane initial state. Never pre-fill trajectory with fabricated history.

## Language

- `name`, prose, persona in the soul's native language (zh / ja / ko / en)
- `sid` and all IDs ASCII-only (use pinyin / romaji / semantic slug)

## Do Not

- Do not invent new top-level folders beyond the canonical structure
- Do not put world/location lore here — that belongs in `game/`
- Do not pre-fill `trajectory/` with fake action history
- Do not skip `soul.md`
