---
title: "Live event stream"
description: "What a heavy front end wires up: send a line, take the streamed prose, take beat events, stop, settle."
---

<!-- section: loop -->
## One turn, there and back

```text
POST /cmd {"text": "I check the back garden"}   → 202, the turn starts (409 {"error": "busy"} while another line runs)
GET  /events                                    ← SSE: chunk … beat events … → positions → turn_done
POST /cancel                                    → the running turn stops after its current step
```

Connect `/events` first (one long-lived connection; `hello` means connected), then post `/cmd`. Over JSON-RPC the same content arrives on `/rpc/events` as `engine/stream` and `engine/beat` (see [Protocol](/docs/developers/protocol)).

**The two engines send different beats.** In the PyPI release a turn may have two beats: a planning beat first (`plan.beat`, the world does not move), then, once it is settled, a resolve beat (`resolve.beat`). The engine built from the open-source repo has only the resolve beat, so a turn sends only `resolve.beat` (the opening beat is sent as `plan.beat` with `opening: true` by both). One front end handles both: read beat names and styles from `GET /api/v1/play/engine/beat-kinds` instead of hard-coding them.

<!-- section: stream -->
## Messages on `/events`

| kind | When | Fields |
|---|---|---|
| `hello` | on connect | an overview of the run |
| `turn_start` | a line starts | `text` |
| `chunk` | prose arriving | `text`; every character a soul speaks carries `[[subagent:name]]`, the rest is the host |
| `tool` | a tool was called mid-turn | `name` |
| `dice.rolled` | the moment a die is rolled, before the prose lands | the same numbers as the beat's `dice` event (`total` · `vs` · `level` …); a page that played it may skip the later `dice` by `total`/`vs` |
| `soul_status` | a soul's status changed | `statuses` |
| beat events | as each beat lands, in order | see below |
| `trace` | a line ends | the turn record for that line (trimmed for the player's page) |
| `positions` | after the beat events | who is where |
| `turn_done` | a line ends | `success` · `error` · `route_decision` · `narration`; `billing` when quota ran out, `timeouts` when a beat ran out of time |
| `write_down.*` | after the turn | see "State corrections" below |
| `rebound` | the engine switched runs | this stream belongs to the old run: disconnect and reconnect |

The model's thinking (`thinking`) only appears on the test bench's `/events?debug=1`.

<!-- section: beats -->
## Beat events

Each beat is pushed as it lands: when a planning talk settles and switches to the resolve beat, `plan.beat` arrives first, then the resolve beat's prose starts streaming.

| kind | What it is | Main fields |
|---|---|---|
| `node.enter` / `node.leave` | entering / leaving a node of the orchestration graph (planning · resolve · a mode layer such as combat) | `node` |
| `plan.beat` | the planning beat (release) or the opening: the host's lines, who was asked, the plan board, the agreed checks | `text` · `script` · `mic` · `board` · `checks` · `opening` · `ended_by` (when it switched to resolve) · `cg` (opening) |
| `resolve.beat` | the resolve beat: prose, options | `text` · `options` · `rolled` · `panels` · `advanced_by`; a structured action carries `action` |
| `dice` | every die this beat rolled | `request` · `answer` · `total` · `vs` · `level` |
| `tool` | every other tool call | `request` · `answer` · `async` |
| `state.changed` | what landed in the world | `applied` · `created` · `refused` · gains and losses |
| `party.join` / `party.leave` | a soul came along / stayed behind | `sid` · `iid` · `name` · `why` |
| `stage.changed` | a plot's stage variable moved | `plot` · `var` · `from` · `to` · `cg?` |
| `show` | a template picture to put on screen now | `slot` · `cls` · `inst` · `label` |
| `soul.mind` | what a present soul made of this beat | `attitude` · `intent` · `follow` · `stay` … |
| `place.discovered` | the player learned of a place | `addr` · `name` · `parent` · `by` |
| `achievement.unlocked` · `reward.granted` · `milestone` | achievement / reward card / open-adventure milestone | `id` · `title` … |
| `audio.cue` | music / ambience changed | `music` · `ambient` · `mood` · `fade_ms` |
| `run.settled` | the run reached its exit | the settlement |

`plan.beat` / `resolve.beat` carry `mentions` (entities named in the text, with their spans). After a reconnect, catch up with `GET /api/v1/play/engine/beats?since=N` → `{events, next}`: the same names and shapes as the live stream.

<!-- section: writedown -->
## State corrections

The resolve beat writes the prose first, then writes the beat's results into the state. When the model provider can turn thinking off per request (deepseek, for example), the engine lands a fast non-thinking answer at once and runs a thinking answer in the background; when that comes back it replaces the fast answer's values variable by variable (anything changed by something else in between is left alone, and tool and engine rulings always win). It waits at most 90 seconds, and is cancelled if the player sends the next line first.

After the turn a front end may still receive: `write_down.pending` (a correction is under way) → `write_down.corrected` (with what changed, followed by a `state.changed` with `corrected: true`) or `write_down.same` / `.cut` / `.timeout` / `.failed`.

<!-- section: reads -->
## Read any time

```
GET /api/v1/play/engine/settlement           the run's settlement (empty before an exit)
GET /api/v1/play/engine/entities?cls=status  one class's instances and props (e.g. your conditions)
GET /api/v1/play/engine/graph                the orchestration graph in effect
GET /api/v1/play/engine/contract             the run's play contract (not the interface contract — see [Interface contract](/docs/developers/contract))
GET /api/v1/play/engine/audio                what is playing now
GET /traces · /trace?i=N                     the full record of each line
```

Every field: the `spec/` folder inside each template, and `neonrp spec http`.
