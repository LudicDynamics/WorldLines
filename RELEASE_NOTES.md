# Release Notes

**Language:** [English](./RELEASE_NOTES.md) · [简体中文](./RELEASE_NOTES.zh.md) · [日本語](./RELEASE_NOTES.ja.md) · [한국어](./RELEASE_NOTES.ko.md)

> Status: Beta — v0.1.0 Public Preview

## v0.1.0 — 2026-04-17 (D-Day)

The first public preview of **WorldLines** (engine codename `neonrp`).

### What ships

**Engine core**
- Event-sourced state with append-only log + snapshots
- Branch / undo / redo
- Sandbox creation, switch, drop
- Replay verification for determinism
- Schema validation (`game_entity.schema.json`)
- Entity index with fuzzy + optional embedding (hybrid) retrieval

**Agents & harness**
- Plan → Diff → Apply pipeline
- Dispatcher with trigger / tag / priority routing
- Multi-turn agentic loop (`--agentic`)
- Builtin skills packaged with the engine
- Orchestrator-driven multi-agent coordination via `task()`

**LLM providers**
- OpenAI-compatible (OpenAI, GLM, LM Studio, Ollama)
- Stub provider with fixture files for tests

**TUI (M9+)**
- Claude-Code-style conversational layout
- `build` / `sandbox` / `play` modes
- Slash commands with Tab completion
- Session management (`/continue`, `/new`, `/sessions`)
- Live token counter, streaming transcript, thinking channel

**Import**
- SillyTavern character cards (JSON + PNG tEXt)

**Templates**
- `default` — minimal starter
- `isekai` — Japan isekai sketch
- `kagura-island` — mystery drama
- `tokyo-science-university` — modern mundane
- `dark-train` — slipstream short
- **`stoneford`** — the headline sample: 5 towns, 28+3 quests, 6 agents,
  d20 combat rules (see [templates/stoneford/](templates/stoneford/README.md))

### Known limitations

- Python 3.11+ only; Windows not officially supported (use WSL2).
- Embedding retrieval requires a local OpenAI-compatible embedding server.
- Large worlds (>2k entities) not yet performance-tuned.
- No web UI — terminal-only for v0.1.
- `replay verify` is strict: any LLM non-determinism without cached
  fixtures will flag divergence. Use temperature=0 or fixtures.
- Multiplayer / shared branches not supported. Single-author workflows
  only.
- Stoneford starter is English/CJK mixed; localization pipeline is
  preview-quality.
- License terms for engine are **preview / pending**. See
  [LICENSE](LICENSE).
- **Harness strictness**: NeonRP orchestration depends on complete
  context. Missing entity data may require manual harness tuning.
- **Beta API stability**: Engine core is in rapid iteration. Expect
  breaking changes in v0.2 and v0.3 as we balance determinism vs
  flexibility.

### Roadmap — next milestones

**v0.2 (late Q2 2026)**
- Open data-format spec ("WorldLines Data" standard)
- Per-agent policy language (hard constraints on ops)
- Graph-based NPC memory
- Web companion viewer (read-only)

**v0.3**
- Multi-branch diffing and merge tools
- Shared-world collaborative sandboxes
- First-class Anthropic provider
- Richer combat referee DSL

**v1.0**
- Stable engine API
- Published data-format 1.0
- Marketplace of community templates

See [task-thinking/gotomarket-releases-open-source-rethink-0326.md](../../task-thinking/gotomarket-releases-open-source-rethink-0326.md)
for the strategic narrative.

### Acknowledgements

Built solo in Tokyo by the founder of Ludic Dynamics. Special thanks to
early testers of the `llm-rpg-starter` predecessor.

---

*For bug reports and feature requests, open an issue on the public repo
(link pending D-Day).*
