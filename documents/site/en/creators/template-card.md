---
title: "Template card: card.yaml"
description: "World card + character cards in one. The author fills a short template; an agent builds the world from the rules."
---

<!-- section: pack -->
## Package layout

> **Status: in design · interfaces are provisional** — the settled 3.0 design; names and fields may still change before it ships.

```text
<id>.wlcard/
  card.yaml                 ← the only file the author must fill in
  manifest.json             ← template, fragments, mode knobs, cast
  rules/world.rules.yaml    ← world-card rules
  rules/souls/<sid>.rules.yaml
  world/  souls/  story/  assets/
```

**A card is not a new format — it is an index of folders.**

<!-- section: card -->
## card.yaml

```yaml
title: Fog Town · The Amnesiac Traveller
pitch: A river-port town in the fog. You have lost your memory; a healer meets you at the north gate.
lang: en
story: |
  Before dawn the fog lay on the post road like wet cloth…
core: |
  The Greyfog North. Stoneford is a river-port trading town where the fog never lifts…
leads:
  - name: Elena
    who: an amnesiac healer
    want: land her first real contract in Stoneford
  - name: Rowan
    who: an adventurer from Jadestone
    want: find the entrance of the legend at the edge of the world
play:
  ending: open        # open | closed
  freedom: sandbox    # sandbox | semi | linear
  time: rp+tick
template: rpg
mixins: [space, tick, economy, factions]
```

<!-- section: template -->
## Picking a template and fragments

`template` picks a kind of play (built-in templates, implemented: `rpg`, `werewolf`); `mixins` stacks system fragments (space · tick · economy · factions, in design). The engine reads `manifest.json["template"]` to decide which pack to use (implemented).

<!-- section: rules -->
## Two sets of rules

- **world-card rules**: which classes and variables exist, what may be added during play, how endings are judged;
- **character-card rules**: protagonists' personality numbers, possible goals, commitments, what they know and what they reveal.

Once the rules are frozen, open worlds, worlds with endings, sandboxes and semi-sandboxes are just knob combinations on the same thing.
