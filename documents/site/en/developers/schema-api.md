---
title: "Register & subscribe (Python)"
description: "registry.register / load_registry; ledger events and sdk.on / events / history / enqueue."
---

<!-- section: register -->
## register(root, table, id, spec)

> **Status: ships with 1.0**

The **single write path** for the closed and open schema: writes one entry into `game/meta/<table>.json`, validates first, raises `RegisterError` on failure. `spec=None` removes an entry (for `actions` it writes a tombstone = the op is turned off); with `replace=False` an existing id is an error. The caller reloads with `load_registry(root)`.

```python
from neonrp.core.registry import register, load_registry, RegisterError

register(root, "classes", "faction", {
    "required": ["name"], "folder": "game/factions", "scope": "world",
    "props": {"power": {"type": "int", "min": 0, "max": 100}}, "mutable": ["power"]})
register(root, "entries", "F_bandits", {"class": "faction", "props": {"name": "One-Eyed Tiger bandits", "power": 46}})
reg = load_registry(root)   # template pack + world files + registered overlays
```

<!-- section: rules -->
## Validation per table

| Table | Rules |
|---|---|
| `variables` | `type` ∈ int / float / str / bool; `path` + `key` required |
| `entries` | `class` must be registered first; required and typed props checked against the class (`check_envelope`) |
| `classes` | `required` / `invariants` / `mutable` are lists; `scope` ∈ place / town / world; prop types ∈ int float str bool enum list, enum needs `values`; `rels` values name the allowed classes (several joined with a vertical bar, or `*`) and those classes must exist; `mutable` must be declared in props; template classes can't be given a folder |
| `actions` | `kind` ∈ action / update; `fields` is a list |
| `triggers` | validated as WHEN / IF / THEN / ELSE |

<!-- section: specs -->
## VarSpec and ClassSpec

```python
VarSpec(name, type, path, key, value=None, min=None, max=None, max_key=None,
        readonly=False, doc="")          # doc = the rule the model sees
ClassSpec(name, parent_class=None, required=[], invariants=[], render="",
          folder="", scope="place", tier=2, id_prefix="",
          props={}, mutable=[], rels={})
```

<!-- section: events -->
## Event types

Every landing appends a line to `game/meta/events.jsonl`: `{"seq", "turn", "ts", "type", "payload"}`. The types are closed:

| Type | Payload |
|---|---|
| `turn.started` · `turn.done` | turn start / end (done carries applied / refused / created / triggered counts) |
| `var.changed` | `var` · `from` · `to` · `by` |
| `flag.set` | `key` · `from` |
| `entry.entered` | `who` · `entry` |
| `entity.created` · `entity.patched` · `entity.promoted` | new instance / props changed / promoted to protagonist |
| `trigger.fired` | `id` · `why` · `emitted` |
| `tool.requested` · `tool.ran` | a rule requested a tool / the tool ran |
| `soul.settled` · `narration.landed` · `turn.ended` | protagonist settled / narration landed / an ending |

<!-- section: sub -->
## Subscribing: push and pull

```python
from neonrp.core import sdk

def on_gold(ev):
    if ev["payload"]["to"] < 3:
        sdk.enqueue(root, {"op": "flag", "key": "broke"}, by="my-hook")   # queue only, never write files

off = sdk.on("var.changed:player.gold", on_gold)     # push: called after landing, in seq order
sdk.events(root, since=120, type="var.changed")      # pull: events
sdk.history(root, "player.gold")                     # pull: [{turn, seq, var, from, to, by}]
off()
```

- Patterns: `*` · `<type>` · `<type>:<key>` · `<type>:*` (key = variable name / trigger id / instance id / who);
- callbacks run after the ledger is written; a failing callback never breaks the turn;
- `enqueue` writes `game/meta/op_queue.json`, drained into verify on the **next turn** — outside logic can still only propose;
- to subscribe from another process, use `neonrp schema watch <pattern>` (it reads the same events.jsonl).

> There are no HTTP register/subscribe endpoints yet (the web side only has the per-turn SSE stream) — see [Protocol](/docs/developers/protocol).
