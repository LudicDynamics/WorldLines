---
title: "Protocol"
description: "The generic kernel protocol: the same for every world, usable from any language."
---

<!-- section: verbs -->
## Verbs

> **Status: in design · interfaces are provisional** — the settled 3.0 design; names and fields may still change before it ships.

| Verb | Does | Existing Python counterpart |
|---|---|---|
| `propose(ops)` | propose; returns applied / refused (with reasons) / pending | `sdk.verify` + `sdk.apply` |
| `get(var)` · `history(var)` | read the closed schema | `load_registry` · `sdk.history` |
| `query(class, filter)` | query open-schema instances | `load_registry(...).entries` |
| `register(table, id, spec)` | register | `registry.register` |
| `subscribe(pattern)` | the change-event stream | `sdk.on` · `neonrp schema watch` |
| `say(text)` · `tick()` | present depending on the template's seams | — |
| `log` · `branch` · `checkout` | world lines | `neonrp commit` |

<!-- section: transport -->
## Transport

HTTP for request / response, WebSocket or SSE for the event stream, JSON bodies:

```text
POST /api/v1/worlds/stoneford-elena/propose
POST /api/v1/worlds/stoneford-elena/register/variables/price.T001.grain
GET  /api/v1/worlds/stoneford-elena/vars/price.T001.jade?history=1
GET  /api/v1/worlds/stoneford-elena/entities?class=faction
GET  /api/v1/worlds/stoneford-elena/events/stream?pattern=var.changed:*
```

> Today: these endpoints do not exist yet. The web side only has the per-turn SSE stream; `neonrp serve` is internal.
