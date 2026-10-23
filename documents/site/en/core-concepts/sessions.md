---
title: "Modes — Build · TUI · Web UI"
description: "Three ways to run a world: author it (Build), play it in the terminal (TUI), or play it in the browser (Web UI)."
---

<!-- section: modes -->
## Three modes: Build · TUI · Web UI

A world runs in one of three modes:

| Mode | What it is | Where |
|---|---|---|
| **Build** | Author the world — edit `game/` files directly, or have an AI agent do it (plan → diff → apply) | Launcher · CLI · any editor |
| **TUI** | Play in the terminal, Claude-Code-style — watch the thinking, tool-use, and narration | `neonrp tui` |
| **Web UI** | Play in the browser, watching every agent live | [WebHub](https://hub.worldlines.gg), or `neonrp web` locally |

**Pluggable media generation.** A world isn't limited to text. You can wire in generation APIs that the engine calls as the scene unfolds:

- an **image-generation API** — scene art, character portraits, key moments
- a **BGM-generation API** — adaptive background music that follows the mood

So the same agentic world can render as a full aud-visual experience, not just a transcript.

> Inside **Build** and play, the engine also tracks *how* agent proposals are applied — **direct**, **gated (sandbox)**, or **auto** — and composes with the [router mode](/docs/core-concepts/engine-modes) (fast / orchestrator / multi-agent). See the sections below.

<!-- section: build-mode -->
## Build Mode

Authoring mode. You edit files in `game/` directly (in any editor) — no agent turns are routed. Use for:

- Scaffolding a new town / NPC / quest
- Fixing data a play session surfaced
- Quick tests of how an agent would narrate a given state

Since *you* are the source of truth, there's no approval gate and no router mode.

<!-- section: sandbox-mode -->
## Sandbox Mode

Agent runs produce **proposals** that you review and **approve per turn**. The diff is shown before anything lands in `.neonrp/events.jsonl`.

Use `/autoapply on|off` inside the TUI to toggle the gate on the fly — `autoapply on` effectively turns sandbox into play for the session; `autoapply off` restores the gate.

**Good for**:
- Experimenting with new agents whose proposals you don't fully trust
- Authoring with AI assistance while retaining veto
- Debugging dispatcher / harness behavior — every proposal is visible

<!-- section: play-mode -->
## Play Mode

GM mode. Agents generate proposals and the engine **auto-applies** them. The transcript reads like a narrative — you don't see diffs unless something fails schema validation.

This is the mode a player spends most of their time in. The world changes as the story unfolds. Branch or snapshot before risky moves if you want to rewind later.

Router mode applies here: `/router-mode fast` for minimal routing, `/router-mode orchestrator` for cross-domain consistency, `/router-mode multi-agent` for sticky sub-agent delegation.

<!-- section: tui-layout -->
## TUI Layout

Single-pane conversational transcript on top, input line at bottom, status bar at top right. The `[AUTO]`/`[manual]` tag in the status bar reflects the current play mode.

```
┌─────────────────────────────────────────────────────────────────┐
│ project │ branch │ head │ turn │ [AUTO]/[manual] │ provider     │
├─────────────────────────────────────────────────────────────────┤
│   user     > look around                                        │
│   tool     read_context("harbor") -> 3 entities                 │
│   thinking …                                                    │
│   agent    The Shale rolls grey under dawn fog. …               │
├─────────────────────────────────────────────────────────────────┤
│ > _                                                             │
└─────────────────────────────────────────────────────────────────┘
```
