---
title: "Growth policy"
description: "When the narration wants a new instance of a class during play, who decides: auto / approve / creator only / forbid."
---

<!-- section: policy -->
## Four policies

> **Status: ships with 1.0**

Every class carries a `policy`. It governs new instances the **narration** creates with `new`:

| Policy | Meaning |
|---|---|
| `auto` | lands at once (the default; every world that never set a policy) |
| `approve` | goes to the "pending" queue (`game/meta/pending.json`); it lands when you approve, or you reject it |
| `creator` | only the creator adds them (`neonrp schema register` or the workbench); the narration is refused |
| `forbid` | nobody adds more |

The world's own rules (a fragment's per-turn rule, op handlers) are not gated: the economy fragment sends caravans without asking you.

<!-- section: set -->
## How to set it

Give `policy` when registering a class, or change only the policy of an existing class:

```bash
neonrp schema register classes npc --spec '{"policy": "approve"}'
```

The creator op `set_policy {cls, policy}` writes the policy into the template, so every later run follows it. During play you can change it for that run:

```
GET  /api/v1/play/engine/approvals          {pending: [...], policies: {class: policy}}
POST /api/v1/play/engine/approvals/<id>     {approve: true|false}
POST /api/v1/play/engine/policy             {class, policy}
```

<!-- section: grow -->
## Walking somewhere that isn't there

When the player heads for a place the map doesn't have yet, the engine first grows that place next to where the player stands (`new_location`), then walks in; it is not simply refused. Another town's id, or a place under a town nobody knows, is still refused. The new place appears on the map and a `place.discovered` event is sent.

Ops that add instances during play: `new` (a new instance of a registered class; the class needs a `folder`), `new_location`, `new_npc`.
