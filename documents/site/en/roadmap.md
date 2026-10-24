---
title: "Roadmap"
description: "What has shipped, what we are working on, what comes next. No dates."
---

<!-- section: shipped -->
## Shipped: 1.0.x

The full record is in the [changelog](/docs/changelog). The main points:

- **Two local interfaces**: `worldlines` (local web UI) and `neonrp` (terminal launcher), installed from PyPI or GitHub, updating themselves at launch; online play at [worldlines.gg](https://worldlines.gg) and in the iOS app
- **Two-beat turns**: talk first, then resolve; a judge (Jev, or the run's own model) decides when the talk is settled
- **State written first, checked in the background**, and you are told what changed
- **Templates and play contracts**: four official contracts (mystery TRPG · open adventure · murder mystery · romance companion), checked before publishing
- **A separate character library**: worlds hold links to characters, and one character can join many worlds
- **Export / import**: templates and characters travel as one package; SillyTavern cards import directly
- **Two worlds built into the local edition**: Greyoak House and Stoneford; the other official worlds are on the Hub
- **Open source**: the NeonRP engine (Apache-2.0) and the WorldLines product (AGPL-3.0) are both on [GitHub](https://github.com/LudicDynamics/WorldLines)

<!-- section: now -->
## Working on now

- **Publishing**: uploaded worlds start as drafts and go up after review; uploads are checked for secrets, a cover, portraits, and titles and blurbs in four languages
- **Runs into replays**: export a run you played as a replay and share it on the Hub
- **More official worlds**, and making the two current ones steadier and more fun

<!-- section: next -->
## Next

- Choosing a library character as the protagonist you play when a run starts
- Undo and going back to a turn on the web, too
- Japanese and Korean versions of these docs

Desktop app: macOS on Apple silicon has the [NeonRP desktop app](https://worldlines.gg/downloads/NeonRP_aarch64.dmg), which installs the engine on first launch. It is not notarized: on first open, go to System Settings › Privacy & Security and click "Open Anyway". There is no installer yet for Windows or Intel Macs; use `pip install worldlines`.

<!-- section: protocol -->
## Open specs

The specs for worlds, characters, templates, play contracts and rule packs are public — see [Specs](/docs/developers/specs).
