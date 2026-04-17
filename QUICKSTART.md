# Quickstart — 30 minutes to your first turn

**Language:** [English](./QUICKSTART.md) · [简体中文](./QUICKSTART.zh.md) · [日本語](./QUICKSTART.ja.md) · [한국어](./QUICKSTART.ko.md)

> Status: Beta — covers the default stoneford starter path

This guide assumes you've finished [INSTALL.md](INSTALL.md) and that
`neonrp --help` prints a command list.

## 1. Create a project (2 min)

```bash
mkdir my-world && cd my-world
neonrp init
```

This creates `.neonrp/` with `manifest.json` and a `config.json` template.
No world yet — just an empty project.

## 2. Scaffold the stoneford starter (3 min)

```bash
neonrp game new --template stoneford
```

You now have:

```
my-world/
├── .neonrp/
│   ├── manifest.json
│   └── config.json
├── agents/
│   ├── orchestrator/
│   ├── town-agent/
│   ├── dungeon-agent/
│   ├── combat-referee/
│   ├── world-builder/
│   └── rules-referee/
└── game/
    ├── meta/
    ├── player/
    ├── towns/
    ├── dungeons/
    ├── rules/
    ├── lore/
    └── world/
```

See [templates/stoneford/](templates/stoneford/README.md) for what the
sample world contains.

## 3. Configure a provider (5 min)

Edit `./.neonrp/config.json` and pick one of the blocks in
[INSTALL.md](INSTALL.md#llm-provider-configuration). Export the API key:

```bash
export GLM_API_KEY=sk-...
# or
export OPENAI_API_KEY=sk-...
```

Validate the world:

```bash
neonrp validate
neonrp index build
```

## 4. Launch the TUI (1 min)

```bash
neonrp tui
```

Top-right status bar shows project name, branch (`main`), head event (`0`),
and provider.

## 5. Your first turn (5 min)

In the input line, type:

```
look around
```

The orchestrator routes to `town-agent`, which reads Stoneford's town data
and narrates. You'll see:

1. A **thinking** stream (collapsed by default).
2. A **tool use** indicator as the agent reads files.
3. The **narrative** response.
4. A new **event** appended to the log (head advances `0 → 1`).

## 6. Save a checkpoint

In the TUI, type:

```
/save opening-scene
```

Or from a separate shell:

```bash
neonrp save opening-scene
```

## 7. Branch an experiment (5 min)

Try a risky choice — say, stealing from Old Reed:

```
/branch try-stealing
steal the coin pouch while Old Reed is turned away
```

WorldLines writes this to a new branch. The main branch is untouched.

## 8. Undo / rewind

```
/undo
```

The head event moves back one step. Type `/redo` to reapply.

## 9. Load a save

```bash
neonrp load opening-scene
```

Or restart the TUI with `--continue` to resume the previous session.

## 10. What next?

- Skim [CONCEPTS.md](CONCEPTS.md) to understand events, snapshots, sandboxes.
- Try `/mode build` and ask an agent to add a new NPC to Stoneford — observe
  the **plan → diff → apply** pipeline.
- Read `templates/stoneford/README.md` and edit a town's JSON directly.
- Read [CLI_REFERENCE.md](CLI_REFERENCE.md) for all subcommands.

## Troubleshooting

| Symptom                              | Fix                                                  |
|--------------------------------------|------------------------------------------------------|
| `neonrp: command not found`          | Re-run `uv tool install -e .`                        |
| TUI renders garbled characters       | Switch to iTerm2 / Ghostty / Alacritty; set UTF-8    |
| `provider not configured`            | Check `.neonrp/config.json` + env var                |
| `validate` reports schema errors     | Run `neonrp validate --json` for detail              |
| Agent hangs / empty output           | `neonrp tui --verbose` to see raw LLM traffic        |
