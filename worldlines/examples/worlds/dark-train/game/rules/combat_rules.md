# Combat — Dark Train (BRP)

> Canonical reference for the `referee` (`check_type: "combat"`). The GM
> routes here whenever physical exchange is on the table. Combat in Dark
> Train is **rare**, **brief**, and **never about winning** — it's about
> how much of you the encounter takes.
>
> Rules base: *Basic Roleplaying: Universal Game Engine* (Chaosium, ORC
> License). Sections marked **This world's own rule** are Dark Train
> additions.

## Core stats touched

From `game/player/stats.json`:

- `HP = (CON + SIZ) ÷ 2`, rounded up (the passenger: 13)
- `Major wound = one hit of at least half max HP` (rounded up; the passenger: 7)
- `Damage modifier` from STR + SIZ: 13–16 → −1D4, 17–24 → none, 25–32 → +1D4
  (the passenger: 24 → none)
- `Brawl` — 25 (untrained adult)
- `Dodge` — DEX × 2 (the passenger: 24)
- `Firearm (Handgun)` — 20 unless a memory fragment raised it

## Round structure

One round = one exchange. Everyone acts in **DEX order, highest first**.
On their turn the passenger spends the round on **one** of:

1. **Attack** — Brawl / Melee Weapon / Firearm, d100 ≤ skill
2. **Dodge** — d100 ≤ Dodge against an incoming attack (one free
   defence per round; further dodges in the same round are Difficult)
3. **Move / interact** — open a door, grab the lantern, hand a fragment
   to an NPC. Usually no roll; if speed matters, an Agility roll (DEX × 5).
4. **First Aid** — d100 ≤ First Aid, restores `1D3` HP, **once** per
   wound.

## Attack and defence

The attacker rolls first. If the attack succeeds, the defender may
Dodge. Compare result levels (critical > special > success):

| Attack     | Defence result            | Outcome                                       |
|------------|---------------------------|-----------------------------------------------|
| success+   | equal or better level     | stopped; near miss, **no damage**             |
| success+   | lower level, or failed    | hit lands; roll damage                        |
| failure    | —                         | miss; on a defender's special/critical dodge, the defender gains position next round |
| fumble     | —                         | the GM invents the indignity (dropped weapon, fall, a hit on the wrong thing) |

Damage by attack level:

- **Success** — weapon damage + damage modifier.
- **Special** — bladed or pointed weapons roll weapon damage **twice**;
  blunt ones add the **maximum** damage modifier and knock the target
  back a step.
- **Critical** — **maximum** weapon damage plus a rolled damage
  modifier; any armour is ignored.

## Weapon damage

| Source                              | Damage                  | SAN rider on hit               |
|-------------------------------------|-------------------------|--------------------------------|
| Bare fist (untrained)               | 1D3 + dm (usually none) | —                              |
| Improvised: shard, bottle           | 1D4 + dm                | —                              |
| Carving knife (a nervous passenger) | 1D4 + 2                 | —                              |
| Folded straight razor               | 1D6                     | —                              |
| The Conductor's cane                | 1D8 + 1                 | +1D4 SAN on hit                |
| **Fog-thing (extending limb)**      | 2D6                     | +1D6 SAN automatic on contact  |
| Service revolver (rare find)        | 1D10                    | —                              |

**Improvised weapons** (lantern, length of pipe, jagged window glass)
deal +1 damage, and the attack takes −10% (you've never held this
thing). The GM decides which objects count.

## SAN riders in combat (this world's own rule)

Some attackers' presence is itself uncanny. When the attacker has
`uncanny: true` (set on the NPC in `npc/*.json`), a **hit** delivers HP
damage *plus* a sanity roll. The referee returns a `san_rider` field;
the GM routes it back as a `check_type: "san"` call.

Uncanny attacker behaviours that warrant the rider:

- Face slips out of focus mid-swing
- Bleeds something not red
- Doesn't react to a clear strike on it
- Speaks the passenger's forgotten name during the exchange
- Smells of the fog when nothing should

## Major wounds

A single hit dealing **half max HP or more** is a **major wound**:

1. If it takes the passenger to 0 HP: **no death** — *dispersal* (see
   "What 0 HP means" below).
2. If still standing, roll **Stamina** (CON × 5). Failure → unconscious
   for `1D10` minutes; the GM narrates what the world does in that gap.
3. Major wounds bleed: −1 HP each following round until a First Aid
   success. Track in `stats.json.status_effects[]`.

## What "0 HP" means (this world's own rule)

The passenger does **not die**. They wake in an **earlier carriage**,
with a gap in memory and one of:

- A flag in `player/flags.json`: `dispersed_in_carriage_N`
- One item lost from inventory (the GM's pick, narrative-driven)
- One skill ticked down −5% (the body knew; the body forgot)

This is **canon-driven mercy** — the Train doesn't kill, it
*rearranges*. Don't trivialise it. The cost is real and accumulates.

Re-traversal: the carriage where the passenger fell may have shifted
layout, NPCs may not remember meeting them, fragments may need to be
recovered again from a different position.

## Ending combat

Combat in Dark Train resolves in **1–3 exchanges almost always**:

- The NPC retreats / collapses / **becomes something else** (uncanny pivot)
- The passenger flees (Agility roll, DEX × 5, to break contact; failure = one more round)
- An object intervenes (a door slides shut, the Conductor arrives, the
  lights go out and when they're back nobody is here)

No loot drops. What the passenger carries away from a fight is a
**clue**, a **fragment**, or a **scar** — entries added to
`player/journal.md` or `lore/notes.md`. Bodies are not searched in the
ordinary sense; the Train doesn't leave bodies.

## Output contract (referee → world-agent)

```json
{
  "check_type": "combat",
  "round": 2,
  "actor": "player | npc_id",
  "action": "attack | dodge | move | first_aid",
  "skill_used": "Brawl",
  "skill_rating": 25,
  "roll": 18,
  "level": "success",
  "defence": {"npc": "nervous-woman", "skill": "Dodge", "rating": 25, "roll": 47, "level": "failure"},
  "damage": {"dice": "1D4", "rolled": 3, "modifier": "0", "total": 3},
  "hp_delta": {"player": 0, "nervous-woman": -3},
  "major_wound": false,
  "status_effects_added": [{"target": "nervous-woman", "effect": "bleeding", "duration": "until_first_aid"}],
  "san_rider": null,
  "ends_combat": false,
  "narrative_hint": "she steps in too fast and the bottle goes the wrong way; you see her wince before she hides it."
}
```

If `san_rider` is non-null:

```json
"san_rider": {"severity": "minor", "trigger": "her face didn't quite track with the swing"}
```

The GM passes that to the referee as a `san` call and weaves both
results into the same paragraph.

## A word on tone

Combat in Dark Train is **not action**. It's *intrusion of the physical
into a story that was supposed to be cerebral*. Treat each exchange like
one panel of a comic — read once, land hard, move on. Don't choreograph
multi-round duels; the Train doesn't let you.
