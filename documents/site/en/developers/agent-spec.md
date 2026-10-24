---
title: "Where specs live"
description: "Specs sit in the folders agents work in: every template, the template store and the character library carry AGENTS.md · CLAUDE.md · spec/."
---

<!-- section: inside -->
## Inside the folders

Claude Code reads `CLAUDE.md`, Codex and most agents read `AGENTS.md`, and they all read the files next to them. So the specs go straight into every folder a creator (and their agent) edits:

| Folder | Specs it carries |
|---|---|
| each template `<id>.template/` | `template` · `world` · `soul` · `contract` (en / zh) · the `ops` of its play pack · `authoring` |
| the template store root | `template` · `world` · `soul` · `contract` · `authoring` |
| the character library `~/.worldlines/souls/` | `soul` · `template` · `contract` |

How agents use them: [For agents](/docs/agents/overview).

<!-- section: fresh -->
## When they are refreshed

- on `fork` and on import — an import gets this engine's specs, not the exporter's;
- `neonrp spec sync` refreshes everything (store + library + every template); `neonrp spec sync <template folder>…` only those;
- an `AGENTS.md` / `CLAUDE.md` you wrote yourself (no "generated" mark) is never overwritten;
- runs never get them; they are not part of a save.

Sources: written specs live in the engine's `documents/spec/` (world · soul · template · contract · pack · player); `ops` · `authoring` · `contracts` · `http` are generated from the code every time, so they never go stale.

<!-- section: tools -->
## For tools and scripts

The same text is available to scripts and your own tools: `neonrp spec [name] [--lang] [--pack]`, `GET /api/v1/spec/<name>`, `/llms.txt`. WorldLines' own authoring agent has no shell; it uses the built-in `read_spec` tool (offered in build mode only).
