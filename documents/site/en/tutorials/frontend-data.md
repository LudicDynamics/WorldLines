---
title: "One template, many front ends"
description: "How a web, a Godot and a TypeScript front end each read the same template and the same run, and which interfaces and events your own front end needs."
---

<!-- section: picture -->
## How it fits

```text
template (template.json · world/ · souls · plots/ · pictures)
   │  a run starts: the template is built into a run
   ▼
engine process — the one truth of the run
   │  POST /rpc · GET /rpc/events · HTTP reads
   ├── standard web front end (what players see on the Hub and iOS; not open source)
   ├── Godot example   worldlines/examples/clients/godot
   ├── TS example      worldlines/examples/clients/ts
   └── your front end
```

A front end does not change the world. It sends a line or an action; the engine rules on it, lands it and pushes the prose, beat events and state back. Everything on screen comes from the engine's data and the template's pictures.

So a template is not written once per front end: front ends know the interfaces, not any particular world.

<!-- section: host -->
## Which engine to connect to

| Engine | How to start it | Token |
|---|---|---|
| local workbench | `worldlines` (default `http://127.0.0.1:8787`) | "Copy token" on the workbench's Frontend page; or `curl -s http://127.0.0.1:8787/api/v1/local/frontends/_/connect` (answers local requests only) |
| one world folder | `neonrp serve --project <folder> --port 8788` | printed at start: `{"url", "token", "protocol"}` |

For front-end work, the local workbench is the easier host: the test bench and your front end share the same run, so you debug on one side and watch the screen on the other. `neonrp serve` fits when you run one world without the workbench (see [Protocol](/docs/developers/protocol)).

<!-- section: five -->
## Six things a front end reads

| What | Where from |
|---|---|
| connection | `POST /rpc` with `session.hello {protocol: "worldlines.net/1"}`; every request carries `Authorization: Bearer <token>` |
| how beats look | `GET /api/v1/play/engine/beat-kinds`: each beat's name, tone, input hint, suggestions, dividers |
| prose and beat events | `GET /rpc/events` (SSE): `engine/stream` is the prose as it is written, `engine/beat` the beat events, `engine/event` turn start / end |
| state | `GET /state` (who is where) · `GET /api/v1/play/schema` (variables) · `GET /api/v1/play/engine/entities?cls=<class>` · `GET /api/v1/play/engine/views` · `GET /api/v1/play/engine/settlement` |
| pictures | this run's pictures by address (`/api/v1/play/place-image?addr=` and so on); CG, ending art and the like are named by slot id (see "Pictures" below) |
| types | `neonrp template contract <id> --ts` / `--gd`: typed variables, classes, ops, events and slots (see [Interface contract](/docs/developers/contract)) |

Say a line with `turn.send {text}`; it returns when the turn is over, and the prose arrives on `/rpc/events` meanwhile. Stop with `turn.cancel`. When the host asks something (`ask_user`), answer with `reply {id, result}`.

A front end knows no particular beat. The open engine has one resolve beat per turn; the PyPI release has planning and resolve beats. The same front-end code handles both, because names and styles come from `beat-kinds`.

<!-- section: events -->
## Beat events and the screen

| Event | What a front end can do |
|---|---|
| `node.enter` / `node.leave` | switch the beat's look (name and tone from `beat-kinds`) |
| `plan.beat` / `resolve.beat` | land a passage of prose; turn `options` into buttons |
| `dice` | roll on screen: `total` · `vs` · `level` |
| `state.changed` | refresh numbers; each entry in `applied` is `{var, from, to}`, `refused` lists changes that did not land |
| `place.discovered` | light up a new place on the map: `addr` · `name` |
| `party.join` / `party.leave` | a companion joins / leaves |
| `stage.changed` | a plot stage moved; with `cg`, play the cut-scene picture |
| `show` | show a template picture now: `slot` is the slot id |
| `audio.cue` | change music / ambience |
| `run.settled` | the run reached an exit: read `GET /api/v1/play/engine/settlement` for the ending |

Every field: [Live event stream](/docs/developers/events). After a drop, `GET /rpc/events?since=<seq>` replays what was missed.

<!-- section: slots -->
## Pictures: this run's, by address

This run's pictures, by address:

```text
GET /api/v1/play/place-image?addr=T001/hall      a place's scene; the address is player_location from /state
GET /api/v1/play/portrait?id=chara               a character's portrait; id=player is the player's
GET /api/v1/play/sprite?id=chara                 a transparent standing sprite
GET /api/v1/play/map/image?level=T001            a level map; GET /api/v1/play/map has the places and roads
```

A missing picture answers 404; draw a placeholder. These pictures are copied from the template into the run when it starts: when the template's pictures change, a new run picks them up.

Every picture in a template has a slot id. CG, ending art, the cover and item icons have no address route. The engine names them by slot id:

| Slot id | What |
|---|---|
| `card:cover` | the template cover |
| `level.map:<level>` | a level map, e.g. `level.map:T001` |
| `place.scene:<address>` | a place's scene, e.g. `place.scene:T001/hall` |
| `soul.portrait:<character>` · `soul.sprite:<character>` | portrait · transparent standing sprite |
| `item.icon:<id>` | an item icon |
| `player.portrait:player` | the player's portrait |
| `opening.cg:<n>` · `stage.cg:<plot>.<n>` | opening CG · plot-stage CG |
| `plot:<plot folder>:ending:<ending>` | ending art |

The `slot` of a `show` event and the `cg.slot` of `stage.changed` are slot ids; the ending is `exit` in `GET /api/v1/play/engine/settlement`. The two example front ends keep these pictures in their own art pack (`art.json`, keyed by ending id and place address) and take them from it when the event arrives. Slot kinds (ratio, whether required) are under `slots` in `neonrp template contract <id>`; to see which slots are filled: `neonrp template slots <id>`.

<!-- section: switch -->
## When the run changes

On the local workbench, when the test bench opens another run or Play overview starts a new one, the engine moves to the new run:

- `/rpc/events` stays open; the events after that belong to the new run;
- `GET /events` sends one `rebound`;
- on it, read the template id, `beat-kinds` and pictures again, then redraw.

The standard web front end on the test bench reloads the whole page when the run changes, so its pictures switch to the new template. The two examples read once, at connect: reconnect after the run changes (reload the TS page, restart the Godot game).

<!-- section: three -->
## What each front end reads

| | Standard web front end | Godot example | TS example |
|---|---|---|---|
| where | Hub, iOS | open-source repo, `worldlines/examples/clients/godot` | open-source repo, `worldlines/examples/clients/ts` |
| protocol | the same interfaces | `addons/worldlines/client.gd` (one node) | `src/client.ts` (one file) |
| how beats look | `beat-kinds` | `beat-kinds` | `beat-kinds` |
| pictures | the template's slots | its own art pack `art.json`, placeholders for pictures not drawn | as Godot, the same art pack |

The standard web front end is not open source; the interfaces on this page are the ones it uses. The test bench in the PyPI release has a "Standard frontend" tab in the right column, to watch the same run side by side.

How to run and change the two examples: [Godot and TS front ends](/docs/tutorials/frontend-examples).

<!-- section: own -->
## Put a front end inside the template

A world can carry its own front ends: `<template>/frontends/<name>/frontend.json`.

```json
{"schema": "worldlines.frontend/1", "kind": "web-ts", "title": "My front end", "entry": "index.html",
 "events": ["node.enter", "resolve.beat", "dice", "state.changed", "run.settled"], "targets": ["local"]}
```

| Field | Meaning |
|---|---|
| `kind` | `web-ts` · `godot` · `chat` |
| `entry` | the entry file, e.g. `index.html` / `project.godot` |
| `events` | the events it uses; the engine checks them against the known ones |
| `targets` | only `local` for now |

On the workbench's Frontend page, click "+ New", or "Copy into this world" on a built-in front end. Copy a built-in template into your own first. `frontends/` stays on your machine and is not exported.
