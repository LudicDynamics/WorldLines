# Soul-agent IO contracts (6 specialists)

| Agent | Role | Input | Output | Writes |
|---|---|---|---|---|
| soul-orchestrator | dispatcher | turn context, world cue | dispatch plan | run_state.json, trajectory/** |
| soul-mind | cognition | persona+memo+context | intent/appraisal | (none — read-only reasoner) |
| soul-memory | retention | events this turn | consolidated memory | short-term-memo/**, long-term-memo/** |
| soul-action | execution | chosen intent | RPG state delta | character/**, trajectory/**, run_state.json |
| soul-dialogue | speech | scene + interlocutor | spoken lines | short-term-memo/conversation_cache.json |
| soul-narrative | story-iface | turn outcome | story-facing summary | run_state.json |

Immutable post-creation: persona/, background/, rules/ (no writer).
