---
title: "Live event stream"
description: "What a heavy front end wires up: send a line, take the streamed prose, take beat events, stop, settle."
---

<!-- section: loop -->
## One turn, there and back

> **Status: ships with 1.0**

```text
POST /cmd {"text": "I check the back garden"}   → the turn starts (409 while another line runs)
GET  /events                                    ← SSE: chunk … chunk → beat events … → positions → turn_done
POST /cancel                                    → the running turn stops after its current step
```

Connect `/events` first (one long-lived connection; `hello` means connected), then post `/cmd`.

<!-- section: stream -->
## Messages on `/events`

| kind | when | fields |
|---|---|---|
| `hello` | on connect | the run at a glance |
| `turn_start` | a line starts | `text` |
| `chunk` | prose arrives | `text`; every character a soul says carries `[[subagent:<name>]]`, untagged text is the host |
| `thinking` | the model's reasoning (when given) | `text` |
| `tool` | a tool was called during the turn | `name` |
| `soul_status` | a character's state changed | `statuses` |
| beat events | after the line lands, in order | see below |
| `positions` | after the beat events | who is where |
| `turn_done` | the line is over | `success` · `error` · `narration` |
| `rebound` | the engine switched to another run | this stream belongs to the old run: reconnect |

<!-- section: beats -->
## Beat events

| kind | what | main fields |
|---|---|---|
| `node.enter` / `node.leave` | into / out of an orchestration node (plan · resolve · combat layer …) | `node` |
| `plan.beat` | the planning beat: host lines, who was handed the mic, agreed checks | `script` · `mic` · `board` · `checks` |
| `resolve.beat` | the resolve beat: what advanced it, the prose, options | `text` · `options` · `rolled` |
| `dice` | every roll | `request` · `answer` |
| `tool` | any other tool call | `request` · `answer` · `async` |
| `state.changed` | what landed on the world | `applied` · `created` · `refused` |
| `run.settled` | the run reached its exit | the settlement (below) |

Catching up after a reconnect: `GET /api/v1/play/engine/beats?since=N` → `{events, next}`, same names and shapes as the stream.

<!-- section: reads -->
## Read any time

```
GET /api/v1/play/engine/settlement           the run's settlement (empty before the exit)
GET /api/v1/play/engine/entities?cls=status  one class's entities and props (e.g. your conditions)
GET /api/v1/play/engine/graph                the orchestration graph in force
GET /api/v1/play/engine/contract             the run's contract
GET /traces · /trace?i=N                     the full record of every line
```

The Front end bench's "Events" view shows these live, each with how to wire it in Godot / TS. Every field: the template folder's `spec/` and `neonrp spec http`.
