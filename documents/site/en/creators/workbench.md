---
title: "Workbenches"
description: "Six benches, one job each; what you change on screen is written straight back into the template."
---

<!-- section: map -->
## Six benches

> **Status: ships with 1.0**

| Bench | Owns | You do here |
|---|---|---|
| **Overview** | every world and save | start a run, continue one, see what is still missing before publishing |
| **Orchestration** | how a run moves (a state-machine graph) | pick the orchestration (`uses`, e.g. two beats / two beats at quick pace); see nodes and edges; add an edge, change a trigger; write back to the template |
| **World · Characters** | the content | world: map · plots · schema · data; characters: cards · relations · schema · data · persona dials |
| **Template** | assembly, the unit you publish | play pack and mixins, asset slots (upload / generate), contract, lint; copy, export, import; publish to the Free Zone, apply for the Default Zone (official accounts: publish as official) |
| **Test bench** | actually playing a run | see [The play screen](/docs/players/play-screen) |
| **Front end** | for heavy-front-end developers | play · live event stream · canvas · contract files (TS / Godot) |

World · Characters is **editing only**: it changes the template, not a run; playing happens on the test bench. Built-in templates are read-only — "Make a copy" on the Template page first. Default Zone works (the built-in templates among them) cannot be exported; your copy can. For publishing see [Publish to the Hub](/docs/creators/publish).

<!-- section: writeback -->
## Saved straight back

Three graphical editors write the template's files; the next run follows them:

- **The orchestration graph** — edges you add and triggers you change are stored as a patch on the default graph (`orchestration.json`). Nodes / edges the engine cannot run are marked red with the reason; only a warning, the run still plays. Only the local orchestration bench edits the graph; the web Hub and iOS desks let you pick one of a few orchestrations and show it read-only.
- **Roads on the map** — in road mode, click two places to build a road, click a road to remove it; a road joins two different places on the same level (across levels, use a port).
- **Plot triggers** — a `WHEN / IF / THEN` form; an unfinished one stays a draft and is not written. See [Triggers](/docs/creators/triggers).

<!-- section: cast -->
## Casting

Characters live in the library; templates hold links. See [Character library and casting](/docs/creators/characters).

<!-- section: agent -->
## Let an agent do it

Every template folder has `AGENTS.md`, `CLAUDE.md` and `spec/`: open it in Claude Code or Codex and edit directly — they read those first. See [For agents](/docs/agents/overview).
