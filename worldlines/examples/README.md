# Examples

Example content for WorldLines: worlds, characters and front-end clients. The worlds are open content
(text CC BY 4.0, images and audio CC BY-NC 4.0, see [`../CONTENT-LICENSE.md`](../CONTENT-LICENSE.md)); fork, mod and ship your own.

## Start with the two built-in templates

The local edition ships two worlds as **templates** — the unit a player picks and a creator publishes. They are the best
place to start, both for playing and for making your own:

| Template | What it is | Characters |
|---|---|---|
| [Greyoak House · The Closed Door](../templates/pct-house.template) | one night in an old house, percentile-dice mystery | Winnie (your client), Oswin (the butler) |
| [Stoneford · The Night the Fog Withdraws](../templates/stoneford-town.template) | an open town; two nights and a day to gather what you need to leave | Elena, Rowan, and the townsfolk |

Both play in two beats per turn: talk first, then resolve.

```bash
pip install worldlines                                        # Python 3.10+; brings the neonrp engine
neonrp tui --from worldlines/templates/pct-house.template     # a fresh run of the template, straight into play
worldlines                                                    # or pick it in the local web UI: http://127.0.0.1:8787/local
```

`--from` builds a new run in `~/.worldlines/plays/` and leaves the template folder untouched.
The other official worlds are on the Hub: browse and play them online at [worldlines.gg](https://worldlines.gg)
without signing in, or sign in with a Worldlines account to download them.

To make your own template, copy one of these two and follow the tutorials (Chinese):
[`worldlines/tutorials/`](../tutorials).

## Older example worlds

[`worlds/`](./worlds) holds example worlds in the older format (an orchestrator world-agent voicing data-driven NPCs,
from before templates). They are kept as material for themes, NPC data and writing style; new worlds should be made as templates.

| World | What it is |
|---|---|
| [Stoneford](./worlds/stoneford) | siege TRPG — a world-agent routing to town / dungeon / combat / story |
| [Goblin Ambush](./worlds/goblin-ambush) | three-layer dungeon — fight three boss goblins |
| [Worldline](./worlds/worldline) | time drift — text the past, watch timelines rewrite |
| [Sakura Hallway](./worlds/sakura-hallway) | a school love story |
| [Lamp of Souls](./worlds/otome-lamp) | 国风乙女 court romance — four princes, a soul lamp, eight endings |
| [Dark Train](./worlds/dark-train) | quiet cosmic horror on a train that never stops; percentile-dice puzzle |

To try one as it is, copy the folder somewhere (play writes into the folder) and run `neonrp tui --play` inside it.
These worlds were written for the older single-narrator turn, so they don't get the two-beat play the templates have.

## Characters and clients

- [`characters/`](./characters) — example characters.
- [`clients/`](./clients) — example front ends that talk to the engine (TypeScript, Godot, art assets).

## License

The engine (`neonrp/`) is Apache-2.0. The product code in `worldlines/` is AGPL-3.0. The world and character content here is
CC BY 4.0 for text and CC BY-NC 4.0 for images and audio — see [`../CONTENT-LICENSE.md`](../CONTENT-LICENSE.md).
