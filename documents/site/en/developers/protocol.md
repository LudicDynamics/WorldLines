---
title: "Protocol"
description: "The engine's two outward layers: worldlines.net/1 (JSON-RPC, for your own clients) and the HTTP routes. The same for every world."
---

<!-- section: host -->
## Host an engine

```bash
neonrp template build pct-house ./house       # a playable world folder
neonrp serve --project ./house --port 8788
# → {"url": "http://127.0.0.1:8788", "token": "…", "protocol": "worldlines.net/1"}
```

`neonrp serve` mounts only the engine API (no web UI), for front ends that bring their own interface: Godot, your own web page, a remote TUI (`neonrp tui --connect <url> --token <token>`). The local web app `worldlines` serves the HTTP routes below too.

The engine process is the one truth of the run: clients send intents, the engine rules on them and lands them.

<!-- section: rpc -->
## worldlines.net/1

JSON-RPC 2.0 over two endpoints, both with `Authorization: Bearer <token>`:

```text
POST /rpc           one request → one answer (turn.send answers when the turn is done)
GET  /rpc/events    SSE: the run's message bus, each event one JSON-RPC message; ?since=<seq> replays what you missed
```

| Method | What it does |
|---|---|
| `session.hello {protocol}` | handshake first; a wrong version answers -32003 |
| `turn.send {text, client?}` | send a line; returns the turn's result. -32002 while another line runs. Player seats only |
| `turn.cancel` | the running turn stops after its current step |
| `session.state` · `session.messages` · `session.clear` · `session.set_mode` | read state / messages, clear, switch mode |
| `session.whoami` | which seat this credential is |
| `room.invite` · `room.seats` · `room.pending` · `room.approve` · `room.deny` · `room.revoke` · `room.auto_approve` | multiplayer: invite, approve, revoke seats (host token only) |
| `session.join {invite}` · `session.join_status` | trade an invite for a seat credential |
| `reply {id, result}` | answer a request the host sent (`ask_user`) |

Notifications on `/rpc/events` are `{"method": "bus.message", "params": {topic, seq, payload}}`. A front end mostly listens to three topics: `engine/stream` (prose as it is written) · `engine/beat` (beat events, see [Live event stream](/docs/developers/events)) · `engine/event`. A seat credential sees only its own share.

Complete client implementations: `worldlines/examples/clients/ts/src/client.ts` (one file) and `worldlines/examples/clients/godot/addons/worldlines/client.gd`.

<!-- section: http -->
## HTTP routes

Reads and writes you can use without JSON-RPC:

```text
POST /cmd {"text": "…"}                          send a line (202; 409 while another line runs)
GET  /events                                     SSE: the turn stream (see Live event stream)
POST /cancel                                     stop the running turn
GET  /state                                      who is where (only characters the player knows)
POST /rollback {"commit": "<id>"}                branch off at that commit; the current line stays

GET  /api/v1/play/schema[/history|/events|/stream]   variables, classes, ops, triggers; changes; subscribe
POST /api/v1/play/engine/tick {"turns": 1..50}   the world runs a few steps on its own (no model; 409 mid-turn)
GET  /api/v1/play/engine/beats?since=N           catch up on beat events
GET  /api/v1/play/engine/beat-kinds              how this run's beats are shown (names, colours, hints)
GET  /api/v1/play/engine/commits                 the run's commit graph
GET  /api/v1/play/engine/contract                the run's play contract
GET  /api/v1/local/templates/<id>/contract[?fmt=ts|gd]   a template's interface contract / generated client
```

The full list is generated from the engine: `neonrp spec http`.

<!-- section: verbs -->
## Verbs at a glance

| You want to | Use |
|---|---|
| propose an action | send a line (`turn.send` / `POST /cmd`), or a structured action `POST /cmd {"action": "inspect" \| "pick", "target"}` / `{"action": "skill", "skill", "target"?}` |
| read a variable / its history | `GET /api/v1/play/schema` · `…/history?var=` · Python `load_registry` · `sdk.history` |
| subscribe to changes | `GET /api/v1/play/schema/stream?pattern=` · Python `sdk.on` · `neonrp schema watch` |
| register | Python `registry.register` · `neonrp schema register` · the edit session's `…/schema/register` |
| let the world run | `POST /api/v1/play/engine/tick` · Python `sdk.tick` |
| world lines | `GET …/engine/commits` · `POST /rollback` · `neonrp commit log / checkout / branch` |
