---
title: "Triggers: WHEN / IF / THEN / ELSE"
description: "The creator's rules over the closed schema. Evaluated deterministically — no LLM."
---

<!-- section: shape -->
## Shape

> **Status: ships with 1.0**

```json
{"when": {"var": "player.gold"},
 "if":   [{"var": "player.gold", "<": 3}],
 "then": [{"to": "narration", "text": "Your purse is nearly empty ({after} coins)."},
          {"to": "soul", "who": "Elena", "text": "The player is almost out of money", "important": true}],
 "else": [],
 "edge": true, "once": false, "cooldown": 0}
```

Put it in `game/meta/triggers.json` (`neonrp schema register triggers …`) or `manifest.json["triggers"]`. Evaluated after every apply.

<!-- section: when -->
## WHEN: what wakes it

| Form | Meaning |
|---|---|
| `{"var": "player.gold"}` | a variable changed |
| `{"entry": "T001/inn", "event": "enter", "who": "player"}` | an instance event: enter / leave / talk / patch / created |
| `{"entry": "F_bandits", "prop": "power"}` | an instance prop changed |
| `{"flag": "met_guard"}` | a flag was set |
| `{"text": "player"}` | text arrived this turn (player / narration / both) |
| `{"turn": true}` | poll every turn |

<!-- section: if -->
## IF and THEN / ELSE

**IF** (all must hold): variable comparisons, `delta<=` (change in this apply), flags, instance props, text keywords, `{"who": "player", "at": "T001/inn"}`, `{"any": [...]}`.

**THEN / ELSE** emit to: `narration` · `soul` · `flag` · `var` (set / add) · `tool` · `end` (an ending) · `log`.

`edge: true` = fire only when the condition turns from false to true; `once` / `cooldown` limit repeats. If a rule changes a variable, the remaining rules are re-evaluated in the same apply (at most 3 levels). Every firing is recorded in the ledger (`trigger.fired`) with its reason chain.
