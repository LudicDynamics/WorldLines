# TUI Guide

**Language:** [English](./TUI_GUIDE.md) · [简体中文](./TUI_GUIDE.zh.md) · [日本語](./TUI_GUIDE.ja.md) · [한국어](./TUI_GUIDE.ko.md)

> Status: Beta — layout stable; keybindings configurable in v0.2

The WorldLines TUI is a Claude-Code-style conversational terminal for
playing and building worlds.

## Launch

```bash
neonrp tui                               # default
neonrp tui --branch experiment           # specific branch
neonrp tui --provider lmstudio           # override provider
neonrp tui --continue                    # resume last session
neonrp tui --new                         # force new session (default)
neonrp tui --import-card card.png        # import before first turn
neonrp tui --verbose                     # stream raw LLM traffic
```

Fresh `init`-only directories can enter build mode immediately. `game new`
is optional — it only adds the default world + play-agent scaffold.

## Layout

Single-pane conversational transcript on top, input line at bottom, status
bar at top right.

```
┌─────────────────────────────────────────────────────────────────┐
│ project │ branch │ head │ turn │ [AUTO]/[manual] │ provider     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Transcript                                                     │
│   user     > look around                                        │
│   tool     read_context("harbor") -> 3 entities                 │
│   thinking …                                                    │
│   agent    The Shale rolls grey under dawn fog. …               │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ > _                                                             │
├─────────────────────────────────────────────────────────────────┤
│ q Quit │ Ctrl+K Commands │ Esc Interrupt │ F6 Copy              │
└─────────────────────────────────────────────────────────────────┘
```

## Modes

Switch with `/mode <name>`:

| Mode      | Behavior                                                    |
|-----------|-------------------------------------------------------------|
| `build`   | Direct file edits + natural narration. For authoring.       |
| `sandbox` | Proposal pipeline. Every change requires approval.          |
| `play`    | GM mode. Auto-apply on. Full immersion.                     |

## Slash Commands

| Command                     | Purpose                                   |
|-----------------------------|-------------------------------------------|
| `/init`                     | Initialize project in current dir         |
| `/game new [--template T]`  | Scaffold starter world                    |
| `/mode <build\|sandbox\|play>` | Switch interaction mode                |
| `/save [name]`              | Snapshot                                  |
| `/load <name>`              | Restore snapshot                          |
| `/branch <name>`            | Create or switch branch                   |
| `/undo` / `/redo`           | Move head back/forward                    |
| `/run <query>`              | Explicit dispatcher run                   |
| `/files`                    | Show file navigator                       |
| `/skills`                   | List builtin + local skills               |
| `/agents`                   | List agents and their triggers            |
| `/import sillytavern-card`  | Import character card                     |
| `/sessions`                 | Session picker                            |
| `/continue` / `/new`        | Session selection                         |
| `/verbose on\|off\|status`  | Toggle verbose diagnostics                |
| `/clear`                    | Clear transcript (state untouched)        |
| `/help`                     | In-app help                               |

Tab completes commands; Enter submits.

## Keybindings

| Key        | Action                                         |
|------------|------------------------------------------------|
| `q`        | Quit                                           |
| `Ctrl+Q`   | Safe quit (immediate terminal return)          |
| `Esc`      | Interrupt in-flight LLM turn                   |
| `Ctrl+K`   | Command palette                                |
| `Ctrl+P`   | Command palette (alternative)                  |
| `Enter`    | Submit                                         |
| `F6`       | Copy full transcript                           |

## Streaming Output

Three streams are interleaved:

- **user** — your input
- **tool** — tool calls (`read_context`, `find`, file reads, …)
- **thinking** — collapsed by default; expand to see reasoning
- **agent** — final narration

A live token counter sits in the top-right status bar.

## Session Persistence

Sessions persist per branch. `--continue` restores the last session on the
current branch; `/sessions` opens the picker to jump across branches.

## Troubleshooting

| Symptom                       | Fix                                          |
|-------------------------------|----------------------------------------------|
| Garbled characters            | Use iTerm2 / Ghostty / Alacritty, UTF-8      |
| Colors wrong                  | Ensure `TERM` supports 256-color             |
| TUI freezes                   | Press `Esc` to interrupt current turn        |
| Agent output empty            | Launch with `--verbose` to inspect traffic   |
| "not initialized"             | Run `/init` or `neonrp init`                 |

## See also

- [CLI_REFERENCE.md](CLI_REFERENCE.md)
- [CONCEPTS.md](CONCEPTS.md)
- [QUICKSTART.md](QUICKSTART.md)
