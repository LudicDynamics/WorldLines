# Skills — Dark Train (BRP)

> Canonical reference for the `referee` (`check_type: "skill"`). The GM
> (world-agent) never rolls dice directly; whenever player intent has an
> uncertain outcome, it routes to the referee with the skill name and the
> difficulty.
>
> Rules base: **Basic Roleplaying: Universal Game Engine** (Chaosium,
> ORC License). Skill names and base values follow the engine's BRP pack.
> Sections marked **This world's own rule** are Dark Train additions.

## Check mechanic (d100 ≤ skill)

Roll `1d100`. The target is the passenger's skill rating, adjusted for
difficulty:

| Difficulty    | Target            | Use when                                               |
|---------------|-------------------|--------------------------------------------------------|
| **Easy**      | skill × 2         | calm, time to spare, the right tool in hand            |
| **Average**   | skill             | default                                                |
| **Difficult** | skill × ½ (round up) | hostile opposition, time pressure, poor light, cold hands |

Compare the roll to the (adjusted) target:

| Roll                              | Result       | Meaning on this train                                   |
|-----------------------------------|--------------|---------------------------------------------------------|
| ≤ target ÷ 20 (round up)          | **Critical** | the best possible outcome, and a little more            |
| ≤ target ÷ 5 (round up)           | **Special**  | clean and quick; an extra detail comes with it          |
| ≤ target                          | **Success**  | it works                                                |
| > target                          | **Failure**  | it doesn't — but the world still says something         |
| 99 or 00                          | **Fumble**   | "the thing breaks worse than it was" — the GM adds a complication |

A puzzle hook may ask for a **special** success (e.g. "Insight,
difficult, special needed"): only a special or critical opens it.

Situational modifiers: shift the difficulty one step (Average → Easy or
Difficult), or apply a flat ±10% / ±20% when a step is too much. Never
stack more than one step plus one flat modifier — if it is still
harder than that, the action is simply Difficult and the GM says why.

## This world's own rule — Try again at a price (付代价再试)

On an ordinary **failure** (not a fumble) the player may try **once
more** — but only by naming a concrete cost that the GM accepts before
the second roll:

- a noise that carries down the carriage
- a tool, item or piece of clothing that breaks or is lost
- an NPC's trust (affection −5 or a remembered slight)
- the next sanity loss is +1

The cost is paid whether the retry succeeds or not. A **fumble on the
retry closes that path** for this carriage: the latch jams for good, the
NPC stops answering that question, the page tears away.

## Starting ratings (a passenger who has just woken up)

You don't remember being trained for anything. Skills sit at their BRP
**base** value, with a few instincts the body kept (marked ★).

| Skill                  | BRP base | Passenger | Notes                                                      |
|------------------------|----------|-----------|------------------------------------------------------------|
| **Spot**               | 25       | 25        | Rises to 40 after the first carriage is cleared (eyes adapt) |
| **Listen**             | 25       | 25        | Key skill — the Train speaks in sounds first               |
| **Research**           | 25       | 25        | Reading damaged, partial or unfamiliar text                |
| **Insight**            | 5        | 20 ★      | Reading another passenger; failure → a wrong impression    |
| **Persuade**           | 15       | 15        | NPCs are not negotiating with a stranger                   |
| **Fast Talk**          | 5        | 15 ★      | One quick line to get past a moment                        |
| **Stealth**            | 10       | 20 ★      | Carriages are narrow; moving quietly matters               |
| **Hide**               | 10       | 10        | Very few places to hide                                    |
| **First Aid**          | 30       | 30        | You at least know which way wounds go                      |
| **Medicine**           | 5        | 5         | Locked behind a memory fragment                            |
| **Repair**             | 15       | 15        | Doors, latches, the emergency cord, dials                  |
| **Fine Manipulation**  | 5        | 5         | Small mechanisms, a lock without its key                   |
| **Climb**              | 40       | 40        | Healthy adult body                                         |
| **Dodge**              | DEX × 2  | 24        | Used in combat; see combat_rules.md                        |
| **Brawl**              | 25       | 25        | Untrained but functional                                   |
| **Firearm (Handgun)**  | 20       | 20        | Only if a weapon is ever found                             |
| **Knowledge (Occult)** | 5        | 5         | You don't remember reading about these things              |
| **Forbidden Lore**     | —        | 0         | This world's own skill; see sanity_rules.md                |

Characteristic rolls (BRP): **Idea** = INT × 5, **Stamina** = CON × 5,
**Agility** = DEX × 5, **Effort** = STR × 5. Use them when no skill fits.

## This world's own rule — Memory fragments (记忆碎片)

The passenger starts with no remembered training. When they recover a
**memory fragment** that points at a past life (a scrap of a medical
licence, a name tag, a hand that knows knots), the GM raises **one**
related skill by **1D6 + 5%**, once per fragment, and narrates it
("you knew this once; the gesture comes back before the name does").
A skill can only be raised this way by a fragment that clearly points
at it. Record each raise in `player/stats.json` and the fragment in
`player/journal.md`.

## When to call the referee

The GM routes to the referee whenever any of these is true:

- **Uncertainty**: the outcome is meaningful and not predetermined
- **Opposition**: another mind or system is resisting
- **Excess**: the action exceeds the passenger's apparent capability
- **Risk**: failure changes the world state (lock breaks, NPC notices)
- **Probability**: a random world reaction (door opens / fog thickens)

Opposed skills (per the BRP pack): Stealth vs Listen, Hide vs Spot,
Persuade / Fast Talk vs Insight. Both roll; the higher result level
wins; on a tie, the higher roll that still succeeded wins.

When **not** to call:

- A routine action with no failure state (walk down the aisle, sit, look out of the window)
- `check_type: "san"` — see sanity_rules.md
- `check_type: "combat"` — see combat_rules.md

## Output contract (referee → world-agent)

```json
{
  "ruling": "skill_check | impossible | meta_rejected",
  "skill": "Spot",
  "rating": 25,
  "difficulty": "easy | average | difficult",
  "target": 25,
  "needs": "success | special",
  "roll": 23,
  "level": "critical | special | success | failure | fumble",
  "retry": {"offered": true, "cost": null, "used": false},
  "consequences": {
    "on_success": "you find the ticket stub under the seat",
    "on_fail": "your hand brushes only dust"
  },
  "narrative_hint": "the cushion is cold; the stub is bent at one corner"
}
```

`narrative_hint` is one short sentence the GM may weave into prose
verbatim or paraphrase. Never the dice math itself — that surfaces only
in the HUD line.

## Failure is information

Failure on this train is rarely "nothing happened." Treat every failed
check as the world saying something specific:

- **Spot fail** → the thing is there, but you'll notice it later in a
  worse way (a broken cup on the next pass, or the NPC sees you looking).
- **Insight fail** → you formed an opinion. The GM just doesn't tell
  you it's the wrong one.
- **Persuade fail** → the NPC remembers being asked.

The passenger's compass is bent, not blank.
