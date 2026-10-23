# Orchestration templates

One folder per template, `<id>/orch.json` (`worldlines.orch-template/1`, see `neonrp/core/orch_templates.py`).
A template = one world orchestration + its parameters. How the characters present act (legacy · S-judge · S-direct ·
S-free) is a separate axis the world picks in `uses.soul` (the template's `soul.variant` is the default).
A world names one in its `template.json`: `"uses": {"template": "<id>", "version": "<x.y>", "soul": "<variant>"}`.

| id | world orchestration |
|---|---|
| `one_beat` | one beat (the Resolve) — the open engine's |

A private layer adds its own (`orchestrations/<id>/orch.json`); a world naming a template this engine lacks plays
`one_beat`, with the characters' orchestration it named.
