---
title: "CLI Reference"
description: "Essential `neonrp` commands. Run `worldlines <cmd> --help` for the authoritative flag list."
---

<!-- section: overview -->
## Command overview

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
| `agent`     | Agent lifecycle (new / list / show / run / apply / logs / context / path) |
| `import`    | Import SillyTavern / external cards            |
| `sandbox`   | Sandbox management                             |
| `replay`    | Replay and determinism verification            |
| `tui`       | Launch the Terminal UI                         |

<!-- section: project -->
## Project lifecycle

```bash
worldlines init                           # create .neonrp/
neonrp game new --template stoneford-orch  # templates: default / kagura-island / soul-talk / stoneford-elena / stoneford-orch
neonrp validate                       # schema-check game/
neonrp index build                    # rebuild retrieval index
```

<!-- section: play-loop -->
## Play loop

```bash
neonrp run "look around"
neonrp save checkpoint-1
neonrp load checkpoint-1
neonrp undo
neonrp redo
neonrp branch try-stealing
```

<!-- section: agents -->
## Agents

```bash
neonrp agent list --json
neonrp agent new narrator
neonrp agent show town-agent
neonrp agent path town-agent                            # print agent dir
neonrp agent run town-agent --query "describe the harbor" --provider glm
neonrp agent run town-agent --query "add a merchant" --apply
neonrp agent apply town-agent --proposal proposal.json --dry-run
neonrp agent context town-agent --query "harbor" --limit 8
neonrp agent logs --tail 10
```

### `agent run` options

| Option         | Purpose                                           |
|----------------|---------------------------------------------------|
| `--query`, `-q` | The instruction (required)                        |
| `--provider`   | Override config provider (glm / openai / lmstudio / ollama / stub) |
| `--fixture`    | Stub-provider proposal JSON file                  |
| `--apply`      | Apply after preview                               |
| `--json`       | Machine-readable output                           |

<!-- section: retrieval -->
## Retrieval

```bash
neonrp find "harbor" --kind location --json
neonrp context "stoneford guild" --limit 5
```

`find` does entity search; `context` returns ranked relevant entities for a query (hybrid fuzzy + vector when embedding is configured).

<!-- section: import -->
## Import

```bash
neonrp import sillytavern-card card.png --id mira-ashford
neonrp import sillytavern-card card.json
```

Imports SillyTavern character cards (JSON or PNG-with-tEXt). See [SillyTavern Import guide](/docs/guides/sillytavern-import).

<!-- section: sandbox-replay -->
## Sandbox & Replay

```bash
neonrp save pre-experiment
neonrp sandbox new try-rebellion --from pre-experiment --switch
neonrp sandbox list
neonrp sandbox switch main
neonrp sandbox drop try-rebellion --force

neonrp replay verify --from pre-experiment
neonrp replay verify --from pre-experiment --to 12 --json
neonrp replay checkout --from pre-experiment --to 5 --to-branch rollback
```

<!-- section: tui -->
## TUI — launch flags

```bash
neonrp tui                               # default
neonrp tui --branch experiment           # specific branch
neonrp tui --provider lmstudio           # override provider
neonrp tui --continue                    # resume last session
neonrp tui --new                         # force new session
neonrp tui --import-card card.png --import-id world-card
neonrp tui --verbose                     # stream raw LLM traffic
```

<!-- section: slash-commands -->
## TUI — slash commands

Inside the TUI, `/<cmd>` triggers an action. The full list:

### Session & history

| Command      | Purpose                                                 |
|--------------|---------------------------------------------------------|
| `/new`        | Start a brand new conversation session                  |
| `/continue`   | Resume previous conversation for current branch         |
| `/sessions`   | List saved per-branch sessions                          |
| `/clear`      | Clear conversation history                              |
| `/copy`       | Copy conversation to clipboard                          |
| `/compact`    | Compact conversation history                            |
| `/stats`      | Show conversation statistics                            |
| `/files`      | List recently modified files                            |

### World & state

| Command                                | Purpose                                         |
|----------------------------------------|-------------------------------------------------|
| `/init`                                | Initialize project in current directory         |
| `/game new`                            | Scaffold a new world from a template            |
| `/worlds`                              | Browse worlds in `~/.worldlines/games/`         |
| `/worldlines`                          | Guided world picker (model + world + launch)   |
| `/save [name]`                         | Snapshot state                                  |
| `/load [name]`                         | Restore from snapshot                           |
| `/branch [name\|list]`                 | Create / switch / list branches                 |
| `/undo` · `/redo`                       | Move head back / forward                        |
| `/sandbox [new\|list\|switch\|drop]`     | Manage sandboxes                                |
| `/validate`                            | Validate `game/` against schema                 |
| `/index [build\|update]`                | Rebuild/update the retrieval index              |
| `/find <keyword>`                      | Search entities                                 |
| `/context <query>`                     | Ranked relevance for a query                    |
| `/export-world [output.zip]`           | Zip `game/` + `.neonrp/` to a .zip              |
| `/load-world <zip>`                    | Restore exported zip into `~/.worldlines/games/` |
| `/import sillytavern-card <file>`      | Import a SillyTavern character card             |
| `/replay [verify\|checkout]`            | Replay verification                             |

### Modes & routing

| Command                                         | Purpose                                           |
|-------------------------------------------------|---------------------------------------------------|
| `/mode [build\|sandbox\|play]`                   | Switch play mode                                  |
| `/router-mode [fast\|orchestrator\|multi-agent]` | Switch router execution mode                      |
| `/autoapply [on\|off\|status]`                    | Toggle sandbox auto-apply                         |
| `/verbose [on\|off\|status]`                      | Toggle verbose debug mode                         |
| `/debug`                                        | Toggle MCP debug mode                             |

### Agents & runs

| Command                                                                       | Purpose                                              |
|-------------------------------------------------------------------------------|------------------------------------------------------|
| `/run <query>`                                                                | Run agent query explicitly                           |
| `/agent [list\|show <name>\|run <name>\|new <name>]`                            | Agent lifecycle                                      |
| `/apply`                                                                      | Apply pending proposal in sandbox mode               |
| `/skills`                                                                     | List available skills                                |

### Providers & settings

| Command                                                             | Purpose                                            |
|---------------------------------------------------------------------|----------------------------------------------------|
| `/models [name\|list\|set <name>\|show <name>]`                      | Quick model switch                                 |
| `/auth [list\|add\|set\|rm\|show]`                                   | Manage named model configs                         |
| `/wl-model [preset]`                                               | Switch WorldLines model preset (glm / opus)       |
| `/config [show\|set <key> <value>]`                                 | Show / set configuration                           |
| `/settings`                                                         | Open unified model / api key / discord settings   |
| `/locale [auto\|en\|zh\|ja\|ko]`                                    | Switch UI language                                 |
| `/mcp [status\|restart <server>]`                                   | MCP server management                              |
| `/bridge [status\|start <name>\|stop <name>]`                        | Manage Discord / Telegram bridges at runtime      |
| `/update [check\|apply\|status\|channel <name>]`                     | Check / apply worldlines updates                       |

### Meta

| Command        | Purpose                                   |
|----------------|-------------------------------------------|
| `/help`        | Show help                                 |
| `/quit` · `/q`  | Exit TUI                                  |

<!-- section: exit-codes -->
## Exit codes

| Code | Meaning                                           |
|------|---------------------------------------------------|
| 0    | Success                                           |
| 1    | General error (validation failed, not found, etc.) |
| 2    | System error (not initialized, adapter failure)   |

<!-- section: env -->
## Environment variables

| Variable            | Purpose                     |
|---------------------|-----------------------------|
| `OPENAI_API_KEY`    | OpenAI                      |
| `GLM_API_KEY`       | Zhipu GLM                   |
| `ANTHROPIC_API_KEY` | Anthropic                   |
| `NEONRP_E2E_LLM`    | Enable real-endpoint tests  |

A `.env` in project root is auto-loaded.
