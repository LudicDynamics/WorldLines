---
title: "Your first run"
description: "The local edition ships two worlds: Greyoak House for a first run, Stoneford for an open town."
---

<!-- section: pick -->
## Which one

The local edition comes with two worlds, listed first on the web overview and in the terminal launcher:

| World | In one line | Good for |
|---|---|---|
| **Greyoak House · The Closed Door** | one night of mystery in an old house, percentile dice | a first run: it fits in one evening and has clear endings |
| **Stoneford · The Night the Fog Withdraws** | an open town; two nights and a day to gather what you need to leave | wandering around and dealing with many people |

In both, every turn has two beats: talk first, then resolve. See [How a turn works](/docs/players/how-to-play).

<!-- section: greyoak -->
## Greyoak House · The Closed Door

**Opening**: nine in the evening, Greyoak House at the blind end of Fog Lane. Three nights ago its master went in through this door and never came out. His niece Winnie has asked you to investigate. A single oil lamp lights the hall; Oswin the butler stands in its shadow with a ring of keys in his fist and no sign of handing them over. Upstairs the study door stands ajar; in the back garden a loose board knocks in the wind.

**Who you are**: the investigator she hired. Checks use percentile dice (d100), and the right panel has a "Nerve" (sanity) meter.

**Who is there**:

- **Winnie**: your client, the master's niece, stays at your side;
- **Oswin**: the old butler, tight-lipped, knows more than he says.

**Goal**: before the night is out, find out where the master went, then decide how it ends. The story moves through four stages (the visit → the diary → the key → the cellar) and has several endings, one of them the true ending.

**Try these first**:

```text
Go upstairs and look in the study
@Oswin What has happened these three days?
/Listen Make out what is knocking in the back garden
```

The last line is one of this world's own skill commands: type `/` to see every skill and its value.

<!-- section: stoneford -->
## Stoneford · The Night the Fog Withdraws

**Opening**: the fifth night of the fog season. You stop under the last lamp outside Stoneford's north gate. Cass the gatekeeper swings his spear across your path: no guild commission, not one step north. The town is packed with people who cannot leave. Cass lowers his voice: at midnight the day after tomorrow, the fog will withdraw from the north road for one night.

**Goal**: in the two nights and a day before the fog withdraws, gather the three things you need to leave by the north gate:

- **leave** to pass the north gate;
- a way to **find the path** in the fog;
- a way past the **post road**, which bandits have cut.

Each can be had in more than one way, and the townsfolk bring them up when the time is right. Once the fog withdraws, go out the north gate and look for the scouting party that never came back. There are several endings.

**Who is there**:

- **Elena**: a healer who doesn't remember her own past; she is with you at the north gate from the start;
- **Rowan**: an adventurer from Jadestone chasing the legend of the Edge of the World in the far north; when he isn't with you he still follows his own plans;
- the townsfolk: Heron the guild steward, Old Reed the general dealer, Mira the innkeeper, Cass at the gate and others, played by the world.

**Try these first**:

```text
Go into town and ask around at the inn
Check the commissions at the guild
Ask Cass where the north road leads once the fog lifts
```

If you ask for someone who isn't there, the world tells you they are not here. That is not an error: every character has their own place in the world.

<!-- section: more -->
## More worlds

The other official worlds are on the Hub:

- play online: [worldlines.gg](https://worldlines.gg), or "Hub ↗" in the web UI's top bar. You can browse without signing in and play any world online straight from there;
- play on your machine: sign in with a Worldlines account first (`/login` in the terminal), then get the world on the Hub. In a terminal you can also run `neonrp template fetch <world id>`. Downloaded worlds go to `~/.worldlines/official/`.

For a world package someone sent you, see "Import" in [Your character](/docs/players/your-character).
