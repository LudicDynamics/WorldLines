---
title: "Changelog"
description: "Release history. Full notes on [GitHub Releases](https://github.com/LudicDynamics/WorldLines/releases)."
---

<!-- section: dev10 -->
## 1.0.3 — Install from GitHub, play online at worldlines.gg (2026-10-24)

- **Where to get it** — the local edition (`worldlines` = local web UI · `neonrp` = terminal launcher) installs from [this repository](https://github.com/LudicDynamics/WorldLines) / PyPI; [worldlines.gg](https://worldlines.gg) is online play. Both commands update themselves at launch (`/update mode prompt` to be asked first)
- **Write-down fast, then corrected** — a turn's state lands with a fast pass; a thinking pass re-reads the prose in the background and corrects it a few seconds later, visible in the TUI and the web
- **No judge, still settles** — without Jev or an account, the run's own model decides when the planning talk is settled; `/login` turns Jev on
- **Characters away from you travel** — a cross-town move walks the road and arrives by world date, no teleporting
- **TUI** — tabbed `/status`, slash completion for skills · targets · people · places, a quick bar above the input, dice reasons; the `--mcp` mode is gone
- **Creation desk on iOS and locally** — submit to the default zone, revise and resubmit, several works per template; new product icon

- **Play layer** — planning and resolve beats in their own colors, dice cards, state-change chips, your conditions, an ending screen; prose streams in with the host and each character in their own blocks
- **Stop, never stuck** — a running turn can be stopped; the page reconnects after a new run instead of hanging on "the host is thinking"; scrolling up no longer snaps back to the bottom
- **Authoring writes back** — the orchestration graph, roads on the map and plot triggers are saved straight into the template
- **Play contracts** — four official ones (mystery TRPG · open adventure · murder mystery · romance companion); a template declares one, lint checks it, the run settles at its exit
- **A character library of its own** — worlds hold links to characters, made real only when a run starts; one character in many worlds, many characters in one world
- **Export / import** — templates and characters as one package, out and back in
- **Specs inside the folders** — every template, the template store and the library carry `AGENTS.md` · `CLAUDE.md` · `spec/`, ready for Claude Code and Codex
- **Fix** — starting two runs in the same second no longer deletes the one being played
- **Built-in rule packs** — besides `rpg` (d20, SRD 5.2 optional), new `pct` (sandbox tabletop, BRP percentile dice, built on `rpg`) and `monopoly`; see [Specs](/docs/developers/specs)
- **No waiting on a stalled model** — a stream watchdog resends when the first token or the gap between tokens takes too long; thresholds are environment variables, see [Model providers](/docs/players/providers)

<!-- section: v040 -->
## v0.4.0 — One engine, two products (2026-08)

- **Engine / shell split** — the web UI and desktop shell moved to the open-source [WorldLines repo](https://github.com/LudicDynamics/WorldLines) (AGPL-3.0); the engine narrows toward a razor-thin simulation core (`pip install worldlines` works exactly as before)
- **Agents decide who talks** — the world-agent hosts the scene: it engages only the characters who should react, asks one directly when it needs an answer, and characters raise their hand when the world should know something
- **Direct lines to the cast** — `@name` for one-on-one and `#` for the room, answered from the character's own memory, no world clock
- **Observation is its own surface** — the observe page opens a world as a three-pane channel glass: channels (◉ world / #here / @character), the live feed, and a presence rail
- **Presence heartbeat** — characters in the scene but not engaged still give one light reaction each turn
- **Dice & physics-checked movement** — `roll_check` (BRP d100 / SRD d20) lands in the trace; every move passes map validation
- **Two modes, period** — `orchestrator` and `multi-agent`; the old `fast` mode is retired, old saves migrate silently
- **Fixes** — wedged LLM streams now time out into a retry ladder; sessions self-heal on refresh; long generations no longer truncate

<!-- section: v036 -->
## v0.3.1–v0.3.6 — Desktop hardening & position consistency (2026-07)

- **Windows batch** — UTF-8 everywhere (Chinese worlds no longer crash), desktop-shell watchdog no longer kills the engine, self-update dead-loop ended
- **The player's position follows the story** — narration and engine state can no longer disagree about where you are
- **`worldlines` opens the TUI again** — the terminal UI is back as the command-line default
- **Downloaded multi-agent worlds run true multi-agent** — bundle layout migrated at run creation instead of silently downgrading to a single narrator

<!-- section: v0300 -->
## v0.2.10–v0.3.0 — LocalShell: the engine grows into a full local product (2026-07)

- **LocalShell** — `neonrp web` grows from a play page into the full local product: game facade / study (continue, world library) / creation gate / PrePlay confirm / in-play toolbar; the same build powers the desktop shells
- **Prep workbench** — studio + three canvases (world / characters / script): the AI drafts, you land results into real world files
- **Three engine guardrails** — broken LLM-written JSON healed or rejected at the write boundary; `neonrp validate` is now a playability health-check; a location judge (free inside a town, gated town transitions, teleports impossible)
- **Turn rollback** — fork from any past turn (git-style), the current line is preserved
- **Imports become full souls** — SillyTavern cards fleshed out into complete souls; creation interviews stream AI thinking live
- **Reliability** — CJK world names fixed end-to-end; Playwright e2e foundation + release gate (no green tests, no release)

<!-- section: v029 -->
## v0.2.4–v0.2.9 — Creation, worlds & living movement (2026-06)

- **Created worlds are real multi-agent worlds** — full init, per-character soul-agents, an owned-worlds library (`worlds/` vs `plays/` split, browse + delete)
- **Richer web play** — world + town maps (zoom · pinch · minimize), orchestration progress, soul-psyche panel, continue & replay
- **Authoring** — entity files can live in nested sub-folders (`game/<kind>/.../<id>.json`)
- **Living movement (trial-beta)** — the world-agent owns where every soul goes, so state and narration can no longer disagree; characters stop teleporting between towns
- **Reliability** — CJK / IME input fixed, install-aware auto-update, faster update detection, Windows runs in the same shell right after install

<!-- section: v023 -->
## v0.2.3 — Multi-Agent Village (2026-06)

- **Multi-agent mode** — the village model: a world-agent wraps a society of independent souls (`world-agent → active souls → world-agent`)
- Reproducible — any world with `souls/` + `playthrough.json` engages it
- New example worlds: **Kagura Island** (7 souls) · **Stoneford · Elena** (2 souls)
- Stoneford-worldlines consolidated into `examples/orch/stoneford`; four official + multi-agent worlds in one repo
- Runs locally (TUI / CLI); hosted play stays Fast + Orchestrator

<!-- section: v020 -->
## v0.2.0 — Hub Launch (2026-06)

- **WebHub** / Hosted play / WorldHub+SoulHub / Create Studio / Cover system / Continue & resume / Multi-language

<!-- section: v019 -->
## v0.1.9 — Engine (2026-04)

- 10-agent 4-layer orchestrator / Stoneford starter / Claude Code runtime / File-backed world state
