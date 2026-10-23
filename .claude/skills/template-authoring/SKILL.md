---
name: template-authoring
description: Create or edit a WorldLines template (`<id>.template/` with template.json) — bind a world + souls + a play pack (rpg, rpg+economy+factions, pct, werewolf, monopoly …), give it a card, mode, prompts, plots/endings and asset slots, then lint, build and play-test it with neonrp. Use when the user wants a complete playable / publishable world package, not just a character or a world folder.
---

# Template authoring

A template is the unit a player picks and a creator publishes. It does not copy the world: it **binds** a world folder,
picks souls, picks a play pack, and adds the card, mode, prompts, plots and asset slots. Spec: `documents/spec/template.zh.md`
(English: `template.en.md`). World and soul folders have their own specs (`world.*.md`, `soul.*.md`); the play contract a
template promises is in `contract.*.md`, and what each play pack provides is in `pack.*.md`.

## 1. Pick the closest reference and copy it

| Want | Copy |
|---|---|
| story with endings, two companions | `worldlines/templates/stoneford-elena.template/` |
| sandbox with a living economy and factions | `worldlines/templates/stoneford-market.template/` or `stoneford-three-towns.template/` |
| a social deduction game | `worldlines/templates/werewolf-night-village.template/` |
| an investigation with clues and endings (sandbox TTRPG, BRP percentile rules) | `worldlines/templates/pct-house.template/` |

```bash
cp -R worldlines/templates/stoneford-three-towns.template my/<id>.template
```

Then edit `template.json`: set a new ASCII `id`, `version`, and the card (`title`, `pitch`, `lang`, `tags`, `cover`).

## 2. Bind the world

- Use a built-in world: `"world": {"builtin": "<world id>"}`; change its data without forking it through `world-overlay/`
  (files there replace the world's files of the same path, e.g. `world-overlay/game/world/economy.json`).
- Or ship your own world inside the template: `"world": {"path": "world"}` and put a full world folder (see the world spec) there.

## 3. Souls, pack, mode

- `souls`: fixed `{"sid": "...", "role": "npc"}` rows, or a pool to draw from (see spec).
- `pack`: `{"name": "rpg", "mixins": ["economy", "factions"], "engine": {"turn": {"mode": "v3"}}}` — packs: `rpg`, `pct`,
  `werewolf`, `monopoly`; mixins `economy`, `factions`. Keep the `engine` block the reference template has.
- `play_contract`: `"<id>@<version>"`, the experience the template promises (`open-adventure@1`, `mystery-trpg@1` …); lint
  checks it (see `contract.zh.md`).
- `mode`: `ending` = `open | single | multi`, `freedom` = `free | semi | guided`.

## 4. Prompts, plots, assets

- `prompts`: list of prompt files (`prompts/world.md`, …) layered over the pack's; named prompts for asset recipes go under `ui.prompts`.
- `plots`: plot folders with stages and endings (multi-ending templates) — the reveal is only shown after the ending.
- `ui.slots` declare which images are needed (level maps, soul portraits, place scenes, icons); `neonrp template slots` lists what is missing.

## 5. Check, build, play

```bash
neonrp template lint my/<id>.template            # fix every block; read every warn
neonrp template slots my/<id>.template
neonrp template build my/<id>.template /tmp/try-<id>
cd /tmp/try-<id> && neonrp tui --play            # first line: 开始游戏
```

Report to the user: each lint block you fixed and how, what is still a warn, and how the first two beats of the play test went
(did the opening appear, did the characters present act as written, did the turn land the state).

## Rules

- Content in the target language, natively; ids / keys / file names ASCII.
- Never edit engine code; never invent a field — if the spec does not list it, check the code location the spec cites.
- No secrets, personal paths or internal addresses in any file.
