---
title: "For agents"
description: "Claude Code, Codex or WorldLines' own authoring agent: open the folder, read AGENTS.md and spec/ first, run lint when done."
---

<!-- section: who -->
## Who this is for

> **Status: ships with 1.0**

For agents working on a creator's behalf: coding agents that work in folders (Claude Code, Codex …) and WorldLines' own authoring agent. People can read it too — it is the manual for authoring with files.

<!-- section: folders -->
## Three kinds of folder, each with its own instructions

| Folder | Holds | Read first |
|---|---|---|
| a template `<id>.template/` | the world, the cast, plots, assets, contract, orchestration | `AGENTS.md` (Claude reads `CLAUDE.md`, the same text) → the matching file in `spec/` |
| the template store (all your templates) | many `<id>.template/` | `AGENTS.md` → the template you are changing |
| the character library `~/.worldlines/souls/` | one character per folder | `AGENTS.md` → `spec/soul.md` |

A template's `spec/` holds `template` · `world` · `soul` · `contract` (each in en and zh), the `ops` of its play pack (what the model may write each turn) and `authoring` (the authoring ops the engine offers). They are generated for the engine version in use — **read them in the folder, not from somewhere else**. For a person who wants to read them through first, the same specs (plus the RPG Pack spec) are on the [Specs](/docs/developers/specs) page, and `neonrp spec` prints them once the engine is installed.

<!-- section: rules -->
## Rules

1. **Read the spec before writing**: `template.json` → `spec/template.md`; `world/` → `spec/world.md`; a character → `spec/soul.md`.
2. **Characters are links**: a cast row is `{"lib": "<library name>"}`; never copy a library character into a template; what differs in this world goes in `prompts/souls/<sid>/` or `world-overlay/`.
3. **Built-in templates are read-only**: `neonrp template fork <id> <new-id>` and work on the copy.
4. **World words stay in data**: place names, statuses, factions belong in the template's data, never in engine code.
5. **Do not hand-edit generated files**: `AGENTS.md` / `CLAUDE.md` / `spec/` carry a "generated" mark and are overwritten; an `AGENTS.md` you write yourself never is.

<!-- section: check -->
## Check your work

```bash
neonrp template lint .            # in the template folder: 0 block = playable and publishable
neonrp template build . /tmp/try  # build a real run
(cd world && neonrp validate)       # the world alone
```

What each lint code means: `spec/template.md` §7; the contract's checks: `spec/contract.md` §4.

Step-by-step tasks: [Recipes](/docs/agents/recipes).
