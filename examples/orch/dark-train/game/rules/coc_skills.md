# CoC 7e Skills — Dark Train

> Canonical reference for `rules-referee`. The Keeper (world-agent)
> never rolls dice directly; whenever player intent has uncertain
> outcome, route to rules-referee with the relevant skill name and
> situational modifier.

## Check mechanic (1d100 vs skill)

Roll `1d100` low. Compare to the investigator's skill rating:

| Roll ≤             | Result            | Use when                                                  |
|--------------------|-------------------|-----------------------------------------------------------|
| skill              | **Regular Success** | default                                                  |
| skill / 2          | **Hard Success**    | hostile opposition, time pressure, partial visibility    |
| skill / 5          | **Extreme Success** | the only thing that opens a door / saves a life          |
| 01                 | **Critical**        | always, regardless of skill                              |
| ≥ 96 (or > skill)  | **Failure**         |                                                          |
| 100 (or 96-100 if skill < 50) | **Fumble** | "the thing breaks worse than it was" — Keeper invents a complication |

Push rolls: on a normal failure, the player may **try once more** by
risking concrete cost (broken tool, loud noise, NPC hostility, +1 SAN
loss next trigger). Fumble on a push is dire — the option closes
permanently or the cost lands hard.

## Default skill ratings (a passenger who has just woken up)

You don't remember being trained for anything. Treat all skills at
their **base** value unless background or memory recovery raised it.

| Skill              | Base | Notes                                                       |
|--------------------|------|-------------------------------------------------------------|
| **Spot Hidden**    | 25   | Bumps to 40 after first carriage cleared (eyes adapt)      |
| **Listen**         | 25   | Critical — the Train speaks in sounds first                 |
| **Library Use**    | 20   | For reading damaged / partial / unfamiliar text             |
| **Psychology**     | 20   | Reading another passenger; failure → wrong inference        |
| **Persuade**       | 15   | NPCs are not negotiating with a stranger                    |
| **Intimidate**     | 15   | Most passengers are already past being intimidated          |
| **Charm**          | 15   | One-shot — a single graceful gesture                        |
| **Stealth**        | 20   | Carriages are narrow; very few places to hide               |
| **First Aid**      | 30   | You at least know which way wounds go                       |
| **Mechanical Repair** | 15 | Doors / latches / emergency cord                          |
| **Climb**          | 40   | Healthy adult body                                          |
| **Dodge**          | DEX/2 | Used in combat; see combat_rules.md                        |
| **Brawl (Fighting)** | 25 | Untrained but functional                                   |
| **Occult**         | 5    | You don't remember reading about these things               |
| **Cthulhu Mythos** | 0    | Starts at 0. Goes UP with exposure. Max SAN drops with it. |

Background-specific bumps are unlocked by **memory recovery** — when
the investigator picks up a `fragment` that points at a profession
(scrap of medical license, a name tag, a hand that knows knots), the
Keeper raises the relevant skill **once** by +20, narratively
("you knew this once, the gesture comes back before the name does").

## Situational modifiers

The Keeper tells rules-referee the modifier when calling. Modifiers
shift the **difficulty level**, not the rating:

| Situation                                          | Effect                              |
|----------------------------------------------------|-------------------------------------|
| Right tool / preparation / ally helping            | Bonus die (roll 2 tens, keep lower) |
| Distraction / wounded / dim light / cold hands     | Penalty die (roll 2 tens, keep higher) |
| Multiple penalties stack                           | Up to 2 penalty dice (third just refuse the check) |
| Bonus + penalty cancel                             | Plain roll                          |

For "this is harder than usual" frame it as forcing a **Hard Success**
threshold instead of stacking modifiers — cleaner for the Keeper to
narrate.

## When to call rules-referee

The Keeper routes to rules-referee whenever any of these is true:

- **Uncertainty**: outcome is meaningful and not predetermined
- **Opposition**: another mind / system is resisting
- **Excess**: action exceeds investigator's apparent capability
- **Risk**: failure changes the world state (lock breaks, NPC notices)
- **Probability**: random world reaction (door opens / fog thickens)

When **not** to call:

- Routine action with no failure state (walk down aisle, sit, look out window)
- The mechanic is **SAN** — that goes to `sanity-keeper`, not rules-referee
- The mechanic is **combat** — that goes to `combat-referee`

## Output contract (rules-referee → world-agent)

```json
{
  "ruling": "skill_check | impossible | meta_rejected",
  "skill": "Spot Hidden",
  "rating": 25,
  "difficulty": "regular | hard | extreme",
  "roll": 23,
  "vs": 25,
  "result": "regular_success",
  "fumble": false,
  "consequences": {
    "on_success": "you find the ticket stub under the seat",
    "on_fail": "your hand brushes only dust"
  },
  "narrative_hint": "the cushion is cold; the stub is bent at one corner"
}
```

`narrative_hint` is one short sentence the Keeper may weave into prose
verbatim or paraphrase. Never the dice math itself — that surfaces
only in the HUD line.

## Failure is information

CoC failure is rarely "nothing happened." Treat every failed check as
the world saying something specific:

- **Spot Hidden fail** → the thing is there, but you'll notice it
  later in a worse way (broken cup on next pass, or the NPC sees you
  looking).
- **Psychology fail** → you formed an opinion. The Keeper just doesn't
  tell you it's the wrong one.
- **Persuade fail** → the NPC remembers being asked.

This is the texture of the Mythos: the investigator's compass is bent,
not blank.
