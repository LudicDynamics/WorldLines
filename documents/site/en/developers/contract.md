---
title: "Interface contract"
description: "What a template exposes: variables, classes, ops, events, asset slots, views. Generated on demand, worldlines.contract/0.1."
---

<!-- section: what -->
## What a contract is

The protocol is *how to talk*; the interface contract is *what this world has to talk about*. The engine builds the template into a scratch folder, reads its registry and produces one JSON document. It is not stored as a file; it is generated on demand:

```bash
neonrp template contract stoneford-town            # JSON
neonrp template contract stoneford-town --ts       # generated TypeScript
neonrp template contract stoneford-town --gd       # generated GDScript
```

```text
GET /api/v1/local/templates/<id>/contract[?fmt=ts|gd]
```

**Not the play contract.** A play contract (`play_contract`, e.g. `open-adventure@1`) is a promise about the experience: turns, deaths, endings — see [Play contracts](/docs/creators/contracts); a run's play contract is at `GET /api/v1/play/engine/contract`. The interface contract on this page is a type list for client code.

<!-- section: shape -->
## Shape

Stoneford (excerpt):

```json
{
  "$schema": "worldlines.contract/0.1",
  "world": "stoneford-town",
  "template": {"base": "rpg", "mixins": ["economy"]},
  "vars":    [{"name": "player.gold", "type": "int", "min": 0, "at": "game/player/wallet.json"},
              {"name": "price.T001.grain", "type": "int", "min": 1, "max": 9999, "at": "game/towns/T001/market.json", "readonly": true}],
  "classes": [{"name": "caravan", "policy": "auto", "required": ["name"], "slots": ["icon"]}],
  "ops":     [{"op": "trade", "kind": "action", "fields": {"good": "any", "qty": "any"}, "owner": "economy"}],
  "events":  ["var.changed", "entity.created", "entry.entered", "flag.set", "trigger.fired", "ending.reached", "pending", "commit"],
  "beat_events": ["node.enter", "node.leave", "plan.beat", "resolve.beat", "dice", "tool", "state.changed", "run.settled", "…"],
  "triggers": [{"id": "P20.pass.guild", "when": {"text": "both"}}],
  "slots":   [{"id": "level.map", "kind": "image", "required": "publish", "ratio": "3:2", "hotspots": true, "dir": "assets/level/map/"}],
  "views":   [{"id": "alert", "widget": "gauge", "bind": ["town.alert"], "layout": {"area": "right", "order": 1, "range": [0, 5]}}],
  "panels":  [{"id": "formation", "tag": "formation", "format": "text", "schema": {"…": "…"}}],
  "transport": {"rpc": "…", "stream": "…"},
  "interaction": {"requests": ["…"], "switches": [], "exits": [], "panels": ["…"], "engine": ["…"]},
  "version": "0.1",
  "hash": "1a8b17c389cd"
}
```

| Key | Contents |
|---|---|
| `template` | the base rules pack and its mixins |
| `vars` | closed-schema variables: type, range, which file they live in, read-only or not |
| `classes` | open-schema classes: growth policy, required props, their asset slots |
| `ops` | the ops this run can land; `owner` is the pack or mixin that registered it |
| `events` | event types on the ledger / subscriptions |
| `beat_events` | beat events on the turn stream (see [Live event stream](/docs/developers/events)) |
| `slots` · `views` · `panels` | asset slots, views, panels (pack + mixins + the template's `ui`, merged) |
| `interaction` | the stop points, layer switches, exits, panels and engine-initiated points the pack declares |
| `transport` | route hints (the [Protocol](/docs/developers/protocol) page is authoritative) |

<!-- section: hash -->
## Hash

`hash` covers everything but `version`, so any change in content changes it. Generated clients carry it as the constant `CONTRACT_HASH`; use it to tell whether your generated code is stale, for example by comparing it with the `hash` from `GET …/contract` at build time. The engine does not check it on connect.
