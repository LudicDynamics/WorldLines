---
title: "Register & subscribe (Python)"
description: "registry.register / load_registry, the event ledger and sdk.on / events / history / enqueue, plus the matching HTTP routes."
---

<!-- section: register -->
## register(root, table, id, spec, *, replace=True)

The **only write path** for the closed and open schema: writes one entry to `game/meta/<table>.json`, validated first; on failure it raises `RegisterError`. `spec=None` deletes (for `actions` it writes a tombstone = the op is turned off); with `replace=False` an existing id is an error. The caller reloads with `load_registry(root)` afterwards.

```python
from neonrp.core.registry import register, load_registry, RegisterError

register(root, "classes", "faction", {
    "required": ["name"], "folder": "game/factions", "scope": "world", "policy": "approve",
    "props": {"power": {"type": "int", "min": 0, "max": 100}}, "mutable": ["power"]})
register(root, "entries", "F_bandits", {"class": "faction", "props": {"name": "One-Eyed Tiger's bandits", "power": 46}})
reg = load_registry(root)   # the rules pack (with mixins) + the world's files + the registered overlays
```

<!-- section: rules -->
## Validation per table

| Table | Rules |
|---|---|
| `variables` | `type` ∈ int / float / str / bool; needs `path` + `key` |
| `entries` | the `class` must be registered first; required and typed props are checked per class |
| `classes` | `required` / `invariants` / `mutable` are lists; `scope` ∈ place / town / world; `policy` ∈ auto / approve / creator / forbid; prop types ∈ int float str bool enum list, enum needs `values`; `rels` values are allowed class names (joined with a pipe, or `*`) and those classes must exist; `mutable` must be in props; a pack's own class cannot be given a folder |
| `actions` | `kind` ∈ action / update / tool / request / mode; `fields` is a list |
| `triggers` | checked as WHEN / IF / THEN / ELSE |

<!-- section: specs -->
## VarSpec and ClassSpec

```python
VarSpec(name, type, path, key, value=None, min=None, max=None, max_key=None,
        readonly=False, doc="",          # doc = the rule the model sees next to the value
        max_step=None,                   # the most one turn may move it
        monotonic=False, carry=None,     # never goes down; an HH:MM clock passing midnight bumps the `carry` variable
        about=None, rest=None)           # about one entity: shown to the model only when it is present or off `rest`
ClassSpec(name, parent_class=None, required=[], invariants=[], render="",
          folder="", scope="place", tier=2, id_prefix="",
          props={}, mutable=[], rels={}, title="", packed=False,
          policy="auto",                 # when the prose brings up a new instance: auto / approve / creator / forbid
          effect=False, person=False, clue=False)
```

An `effect` class is a state on someone that counts down and applies itself each turn; instances of a `person` class can own things; instances of a `clue` class count as clues.

`kind` of an action: `action` (lands something) · `update` (changes a variable / prop) · `tool` (a request the engine answers) · `request` (asks someone for a reply) · `mode` (switches to a mode layer and continues).

<!-- section: events -->
## Event types

When a turn lands, one line per event goes to `game/meta/events.jsonl`: `{"seq", "turn", "ts", "type", "payload"}`. The types are closed:

| Type | payload |
|---|---|
| `turn.started` · `turn.done` | turn start / end (done carries applied / refused / created / triggered counts) |
| `var.changed` | `var` · `from` · `to` · `by` |
| `flag.set` | `key` · `from` |
| `entry.entered` | `who` · `entry` |
| `entity.created` · `entity.patched` | new instance / changed props |
| `trigger.fired` | `id` · `why` · `emitted` |
| `tool.requested` · `tool.ran` | a rule asked for a tool / the tool ran |
| `soul.settled` · `narration.landed` · `turn.ended` | a character settled / the prose landed / an ending was reached |

`entity.promoted` is in the type list but is not emitted today. Steps the world takes on its own through `sdk.tick` or `POST /api/v1/play/engine/tick` are not written to the ledger.

<!-- section: sub -->
## Subscribe: push and pull

```python
from neonrp.core import sdk

def on_gold(ev):
    if ev["payload"]["to"] < 3:
        sdk.enqueue(root, {"op": "flag", "key": "broke"}, by="my-hook")   # may only queue, never write files

off = sdk.on("var.changed:player.gold", on_gold)     # push: called after landing, in seq order
sdk.events(root, since=120, type="var.changed")      # pull: events
sdk.history(root, "player.gold")                     # pull: [{turn, seq, var, from, to, by}]
off()
```

- Patterns: `*` · `<type>` · `<type>:<key>` · `<type>:*` (key = variable name / trigger id / instance id / who);
- callbacks run after the ledger is written, in the process that runs the turn; a failing callback never breaks the turn;
- `enqueue` writes `game/meta/op_queue.json`; the **next turn** takes it into verification — outside logic can only propose;
- to subscribe from another process, use `neonrp schema watch <pattern>` (it reads the same events.jsonl).

<!-- section: http -->
## HTTP

The same reads and subscriptions on a local engine (`worldlines` or `neonrp serve`):

```text
GET  /api/v1/play/schema                          pack name + the five tables (variables with their values)
GET  /api/v1/play/schema/history?var=player.gold  one variable's changes
GET  /api/v1/play/schema/events?since=0&type=…    landed events
GET  /api/v1/play/schema/stream?pattern=…&since=  SSE: each new matching event
```

The play side only reads: players propose, they don't register. Registration lives on the edit session the creation desk opens: `POST /api/v1/create/session/edit-local/schema/register {table, id, spec}` and `…/unregister {table, id}`, with the same reads (`/api/v1/create/session/edit-local/schema[/history|/events|/stream]`).
