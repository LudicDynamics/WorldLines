# CoC 7e Combat — Dark Train

> Canonical reference for `combat-referee`. The Keeper routes to it
> whenever physical exchange is on the table. Combat in Dark Train is
> **rare**, **brief**, and **never about winning** — it's about how much
> of you the encounter takes.

## Core stats touched

From `game/player/stats.json`:

- `HP = (CON + SIZ) / 10` rounded down (typical 10-15 for a passenger)
- `Major wound threshold = HP / 2` — single hit at or above this triggers
  a CON × 5 roll to avoid passing out
- `Damage bonus / build` — usually `+0 / 0` for a passenger
- `Fighting (Brawl)` — default 25 (untrained adult)
- `Dodge` — default DEX / 2
- `Firearms (Handgun)` — usually 20 unless background restored it

## Round structure

One round = one exchange. CoC has no initiative grid — turn order by
**DEX descending**. Multiple aggressors act in DEX order. The
investigator can spend the round on **one** of:

1. **Attack** — Fighting / Firearms d100 ≤ skill
2. **Dodge** — Dodge d100 vs incoming attack's roll
3. **Fight back** — Fighting d100 vs incoming attack's roll (opposed)
4. **Move / interact** — open a door, grab the lantern, hand a fragment
   to an NPC. No roll usually; if speed-critical, DEX × 5.
5. **First aid** — First Aid d100 ≤ skill, restores `1d3` HP, **once**
   per wound per scene.

## Opposed roll (the heart of CoC combat)

Attacker rolls Fighting. Defender rolls Dodge or Fighting (fight back).
Compare **levels of success**:

| Attacker | Defender    | Outcome                                            |
|----------|-------------|----------------------------------------------------|
| Higher level | lower    | hit lands; roll weapon damage                     |
| Same level   | same     | defender keeps footing; near miss; **no damage**  |
| Lower    | higher      | defender turns it on them (fight back: deal damage back; dodge: positional advantage next round) |
| Both fumble | —        | both ridiculous; Keeper invents the indignity     |

If attacker scored **Extreme** and defender only **Regular**, attacker
adds **+1 damage die** (impale-equivalent for cosmic situations: hit
landed on a name, not a body).

## Weapon damage

| Source                              | Damage                  | SAN rider on hit               |
|-------------------------------------|-------------------------|--------------------------------|
| Bare fist (untrained)               | 1d3 + db (usually 0)    | —                              |
| Improvised: shard, bottle           | 1d4 + db                | —                              |
| Carving knife (a nervous passenger) | 1d4 + 2                 | —                              |
| Folded straight razor               | 1d6                     | —                              |
| The Conductor's cane                | 1d8 + 1                 | +1d4 SAN on hit                |
| **Fog-thing (extending limb)**      | 2d6                     | +1d6 SAN automatic on contact  |
| Service revolver (rare find)        | 1d10                    | —                              |

**Improvised weapons** (lantern, length of pipe, jagged window glass)
grant +1 damage and a -10 to Fighting skill (you've never held this
thing). The Keeper's call which counts.

## SAN riders in combat

Some attackers' presence is itself uncanny. When `combat-referee`
detects an `attacker.uncanny == true` flag (set on the NPC in
`npc/*.json`), the **hit** delivers HP damage *plus* an embedded
sanity check. combat-referee returns a `san_rider` field; the Keeper
routes that to `sanity-keeper`.

Common uncanny attacker behaviours that warrant the rider:

- Face slips out of focus mid-swing
- Bleeds something not red
- Doesn't react to a clear strike on it
- Speaks the investigator's forgotten name during the exchange
- Smells of the fog when nothing should

## Major wounds

A single attack dealing ≥ HP/2 damage in one hit is a **major wound**:

1. Investigator drops to 0 if the damage takes them there. **No
   death** — instead, *dispersal* (see "what 0 HP means" below).
2. If still standing, roll `CON × 5 d100`. Fail → unconscious for
   `1d10` minutes; the Keeper narrates what the world does in that gap.
3. Major wounds bleed: -1 HP each subsequent round until a First Aid
   success. Track in `stats.json.status_effects[]`.

## What "0 HP" means

The investigator does **not die**. They wake in an **earlier
carriage**, with a gap in memory and one of:

- A flag in `player/flags.json`: `dispersed_in_carriage_N`
- One item lost from inventory (Keeper's pick, narrative-driven)
- One skill ticked down -5 (the body knew; the body forgot)

This is **canon-driven mercy** — the Train doesn't kill, it
*rearranges*. Don't trivialise it. The cost is real and accumulates.

Re-traversal: the carriage where the investigator fell may have
shifted layout, NPCs may not remember meeting them, fragments may
need to be recovered again from a different position.

## Ending combat

Combat in Dark Train resolves in **1-3 exchanges almost always**:

- NPC retreats / collapses / **becomes something else** (uncanny pivot)
- Investigator flees (DEX × 5 to break contact; failure = one more round)
- Object intervenes (door slides shut, the Conductor arrives, the lights
  go out and when they're back nobody is here)

No loot drops. What the investigator carries away from a fight is a
**clue**, a **fragment**, or a **scar** — entries added to
`player/journal.md` or `lore/notes.md`. Bodies are not searched in the
ordinary sense; the Train doesn't leave bodies.

## Output contract (combat-referee → world-agent)

```json
{
  "round": 2,
  "actor": "player | npc_id",
  "action": "attack | dodge | fight_back | move | first_aid",
  "skill_used": "Fighting",
  "skill_rating": 25,
  "roll": 18,
  "level": "regular",
  "opposed_by": {"npc": "nervous-woman", "skill": "Dodge", "rating": 35, "roll": 47, "level": "fail"},
  "damage": {"dice": "1d4", "rolled": 3, "bonus": 0, "total": 3},
  "hp_delta": {"player": 0, "nervous-woman": -3},
  "status_effects_added": [{"target": "nervous-woman", "effect": "bleeding", "duration": "until_first_aid"}],
  "san_rider": null,
  "ends_combat": false,
  "narrative_hint": "she steps in too fast and the bottle goes wrong way; you see her wince before she hides it."
}
```

If `san_rider` is non-null:

```json
"san_rider": {"severity": "minor", "trigger": "her face didn't quite track with the swing", "vs_san_check": true}
```

The Keeper passes that to `sanity-keeper` and weaves both results into
the same paragraph.

## A word on tone

Combat in Dark Train is **not action**. It's *intrusion of the
physical into a story that was supposed to be cerebral*. Treat each
exchange like one panel of a comic — read once, land hard, move on.
Don't choreograph multi-round duels; the Train doesn't let you.
