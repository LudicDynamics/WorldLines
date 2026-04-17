# CLI Reference

**Language:** [English](./CLI_REFERENCE.md) · [简体中文](./CLI_REFERENCE.zh.md) · [日本語](./CLI_REFERENCE.ja.md) · [한국어](./CLI_REFERENCE.ko.md)

> Status: Beta — commands stable for v0.1.0; flags may gain options

Complete reference for the `neonrp` command-line tool. Run `neonrp <cmd> --help`
for the authoritative, up-to-date flag list.

## Command Map

| Command     | Purpose                                        |
|-------------|------------------------------------------------|
| `init`      | Create `.neonrp/` in current dir               |
| `game`      | Scaffold starter worlds (templates)            |
| `run`       | Dispatch a query to an agent                   |
| `save`      | Snapshot current state                         |
| `load`      | Restore from snapshot                          |
| `branch`    | Create or switch branches                      |
| `undo`      | Move head back one event                       |
| `redo`      | Reapply undone event                           |
| `validate`  | Validate `game/` against schema                |
| `index`     | Build/update entity index                      |
| `find`      | Search entities                                |
| `context`   | Ranked relevance for a query                   |
| `agent`     | Agent lifecycle                                |
| `import`    | Import SillyTavern / external cards            |
| `sandbox`   | Sandbox management                             |
| `replay`    | Replay and determinism verification            |
| `tui`       | Launch the Terminal UI                         |

## Project lifecycle

```bash
neonrp init
neonrp game new --template stoneford    # or: default / isekai / kagura-island
neonrp validate
neonrp index build
```

## Play loop

```bash
neonrp run "look around"
neonrp save checkpoint-1
neonrp undo
neonrp redo
neonrp branch try-stealing
```

## Agents

```bash
neonrp agent list --json
neonrp agent new narrator
neonrp agent show town-agent
neonrp agent run town-agent --query "describe the harbor" --provider glm
neonrp agent run town-agent --query "add a merchant" --apply
neonrp agent logs --tail 10
```

### Agent run options

| Option         | Purpose                                           |
|----------------|---------------------------------------------------|
| `--query, -q`  | The instruction (required)                        |
| `--provider`   | Override config provider (glm/openai/lmstudio/ollama/stub) |
| `--fixture`    | Stub-provider proposal JSON file                  |
| `--apply`      | Apply after preview                               |
| `--agentic`    | Multi-turn agentic loop                           |
| `--json`       | Machine-readable output                           |

## Retrieval

```bash
neonrp find "harbor" --kind location --json
neonrp context "stoneford guild" --limit 5
```

## Import

```bash
neonrp import sillytavern-card card.png --id mira-ashford
neonrp import sillytavern-card card.json
```

## Sandbox

```bash
neonrp save pre-experiment
neonrp sandbox new try-rebellion --from pre-experiment --switch
neonrp sandbox list
neonrp sandbox switch main
neonrp sandbox drop try-rebellion --force
```

## Replay

```bash
neonrp replay verify --from pre-experiment
neonrp replay verify --from pre-experiment --to 12 --json
neonrp replay checkout --from pre-experiment --to 5 --to-branch rollback
```

## TUI

```bash
neonrp tui
neonrp tui --branch experiment
neonrp tui --provider lmstudio
neonrp tui --continue
neonrp tui --import-card card.png --import-id world-card
neonrp tui --verbose
```

## Exit Codes

| Code | Meaning                                           |
|------|---------------------------------------------------|
| 0    | Success                                           |
| 1    | General error (validation failed, not found, etc.)|
| 2    | System error (not initialized, adapter failure)   |

## Environment

| Variable            | Purpose                     |
|---------------------|-----------------------------|
| `OPENAI_API_KEY`    | OpenAI                      |
| `GLM_API_KEY`       | Zhipu GLM                   |
| `ANTHROPIC_API_KEY` | Anthropic                   |
| `NEONRP_E2E_LLM`    | Enable real-endpoint tests  |

A `.env` in project root is auto-loaded.

## See also

- [TUI_GUIDE.md](TUI_GUIDE.md)
- [CONCEPTS.md](CONCEPTS.md)
