# CoC 7e Sanity — Dark Train

> Canonical reference for `sanity-keeper`. The Keeper (world-agent)
> routes here whenever something *uncanny* touches the investigator —
> never resolves SAN themselves. SAN losses, temporary insanity,
> indefinite insanity, and the resulting phobias / manias all originate
> in this file.

---

## Scale

- `SAN` starts equal to `POW × 5`. For a passenger with POW 60, that's
  **SAN 60 / 60**.
- Maximum SAN drops as the investigator learns the Mythos:
  `max_san = 99 - Cthulhu Mythos`. Locked unreachable territory.
- The investigator carries `current_san` (this turn) and `max_san`
  (the ceiling that's still possible for them) in `player/stats.json`.

### Thresholds

| Current SAN range | State                                                          |
|-------------------|----------------------------------------------------------------|
| 80–100% of max    | clear-headed                                                   |
| 50–80%            | unsettled — reflections lag a beat, the wheels' rhythm sticks  |
| 30–50%            | **fraying** — hand tremor, perception skips, names won't come  |
| 10–30%            | **brittle** — every new contact +1 difficulty to the SAN check |
| 0                 | **dispersal** — see "SAN 0" below                              |

These don't directly modify dice; they're texture for the Keeper to
weave. The mechanical bite comes from the next two sections.

---

## SAN check (roll-under d100)

When `sanity-keeper` is called with a trigger:

1. Roll `1d100`.
2. **Pass** if `roll ≤ current_san`. Lose the **lower** number from
   the trigger's `(pass / fail)` damage range.
3. **Fail** if `roll > current_san`. Lose the **higher** number.

Note the inversion — high SAN is a *large target*, easy to roll under.
This is deliberate: as SAN drops, the same triggers cost more.

If `current_san ≤ 10`, every new contact gets an additional **+1
difficulty step**: instead of regular SAN check, treat as **Hard**
(roll ≤ `current_san / 2`).

---

## Trigger table

| Trigger                                              | Pass loss | Fail loss     |
|------------------------------------------------------|-----------|---------------|
| Glimpse the void outside a window                    | 0         | 1d3           |
| Long stare into the void (≥ one turn)                | 1         | 1d6           |
| NPC's face skews briefly                             | 0         | 1d4           |
| Train stops shuddering (the rhythm goes silent)      | 1         | 1d6 + 1       |
| The child's bear answers a question                  | 1         | 1d4           |
| Reading text that reads you back                     | 1d3       | 2d6           |
| Direct contact with the Conductor's hand             | 1d4       | 2d6           |
| Witnessing a passenger dissolve into the fog         | 1d6       | 2d10          |
| Realising a passenger is repeating yesterday's words | 1         | 1d4           |
| Hearing your own forgotten name spoken               | 1d2       | 1d6 + 2       |
| **Reading the Conductor's logbook** (event-only)     | 1d6       | 1d10 + Mythos +1 |

Triggers stack within a single scene only if they're qualitatively
distinct. "Three windows in a row" is one trigger. Three different
*kinds* of uncanny in three minutes is three triggers.

---

## Temporary insanity (5+ in a single check)

If a single SAN check **loses 5 or more points** (either rolled or
floored sum), the investigator must immediately make an `INT × 5`
roll. **Failure** → temporary insanity. Roll `1d10`, lasts `1d10`
rounds (Keeper may round to "until end of scene"):

| 1d10 | Symptom                                                        |
|------|----------------------------------------------------------------|
| 1    | Stupor — sits and stares, won't act voluntarily                |
| 2    | Flight — moves away from the trigger at any cost                |
| 3    | Hysterics — laughter or sobbing, can't speak coherently         |
| 4    | Compulsion — must touch / count / arrange something specific    |
| 5    | Identity slip — refers to themselves by a different name        |
| 6    | Aggression — attacks the nearest source of the trigger          |
| 7    | Catatonia — falls asleep where standing                         |
| 8    | Confabulation — invents a memory that fills the gap             |
| 9    | Sensory bleed — hears / sees the trigger keep happening          |
| 10   | Brief lucidity — sees the Train clearly for one moment, then forgets |

These manifest in **prose**, never as a status icon. The Keeper writes
the symptom into the scene; the player's selectable choices stay open
(though some may be greyed-out narratively — "your hands won't let go
of the railing").

---

## Indefinite insanity (1/5 of max in a session)

If the investigator loses **(1/5) × max_san or more SAN within a
single session / day in-fiction**, they enter **indefinite insanity**.

Mechanically: roll **1d10** to pick a **phobia** or **mania** from the
two tables below. It's permanent until therapy (which doesn't exist
on this train). Effect:

- **+10** to any SAN check directly triggered by the phobia / mania's
  subject (you've already come to terms with it; it costs less)
- **-1 step** to any skill check in a scene *featuring* the
  phobia / mania's subject (you're not your full self around it)

### Phobias (1d10)

1. **Achluophobia** — fear of darkness; the emergency lights are now
   your only company
2. **Hodophobia** — fear of travel; you stop moving forward
3. **Algophobia** — fear of pain; the next wound is twice the cost
4. **Catoptrophobia** — fear of reflections; you avoid windows
5. **Pyrophobia** — fear of fire; the lantern is a problem
6. **Phonophobia** — fear of sound; the wheels become unbearable
7. **Anthropophobia** — fear of other people; NPCs trigger flight
8. **Necrophobia** — fear of the dead; passengers asleep look like corpses
9. **Hypegiaphobia** — fear of responsibility; can't be the one to act
10. **Atelophobia** — fear of imperfection; obsessively re-checks every act

### Manias (1d10)

1. **Graphomania** — must write everything down; spends turns scribbling
2. **Trichotillomania** — pulls own hair when stressed
3. **Mythomania** — lies about facts you know are true
4. **Onomatomania** — must name everything; assigns names to objects
5. **Aboulomania** — pathological indecision; can't act without rolling a die
6. **Ergomania** — compulsive activity; can't rest, can't sleep
7. **Hypermnesia** — recalls every detail; including ones you didn't see
8. **Pseudomania** — invents false memories of past triumphs
9. **Eleutheromania** — must escape; tries every door regardless
10. **Demonomania** — convinced something specific is following you, and it is

The phobia / mania is stored as `player/stats.json.afflictions[]` and
narratively folded into prose by the Keeper from then on. Don't list
it in the HUD line; the symptom is the player's to discover in play.

---

## SAN 0 — dispersal

The investigator doesn't die. **Dispersal**:

1. The current scene ends mid-sentence.
2. Next turn opens in an **earlier carriage** — Keeper picks based on
   narrative geometry, not random.
3. Memory gap: one item lost; one fragment retroactively unheard
   (remove from `player.fragments_heard[]`); one NPC no longer
   remembers meeting them (state.met → false).
4. Current SAN restored to `(max_san / 3)`. Max SAN drops by
   `min(5, current_loss / 4)` — there's a ceiling that's permanently
   lower now.

Dispersal is **not a game over**. It's the Train's way of editing.
The investigator continues. They may reach Carriage 1 having been
dispersed twice; the truth they find there will be different than the
one a fresh investigator would have found.

---

## Cthulhu Mythos

Starts at **0**. Goes up:

- Reading certain texts / documents (event-driven, +1 to +5)
- Surviving direct contact with the Conductor's hand (+1)
- Hearing your own forgotten name spoken back (+1)
- Reading the Conductor's logbook in Carriage 2 (+2 to +5)
- Reaching Carriage 1 (+1 to +10, depending on the ending)

Every point of Cthulhu Mythos **lowers `max_san` by 1** — and that
ceiling is unreachable from then on, even if the investigator rests.

Cthulhu Mythos is also a skill — it can be rolled for **recognition**:
"have I seen this kind of thing before?" Success = the investigator
*understands* what just happened, which is usually worse than not
understanding.

---

## Narrative integration — no numbers in prose

The Keeper **never writes "you lose 4 SAN"**. The HUD line shows the
delta (`SAN 56 (-3)`); the prose shows the *symptom*:

> Your reflection on the window lags a beat behind you.
> A name surfaces in your throat. Not yours. It sinks again.
> The wheels are off by a heartbeat. You hadn't noticed they had a heartbeat.

If you find yourself describing the trigger directly — "the void
horror radiates dread" — stop. Describe **what the investigator does**
in the trigger's presence. SAN loss is a description of how the
investigator's body is currently failing to be normal.

---

## Output contract (sanity-keeper → world-agent)

```json
{
  "trigger": "long_stare_into_void",
  "severity": "minor | moderate | major",
  "san_check": {"roll": 47, "vs": 56, "result": "pass"},
  "san_loss": {"pass_loss": "1", "fail_loss": "1d6", "applied": 1},
  "san_delta": {"before": 56, "after": 55},
  "temporary_insanity": null,
  "indefinite_insanity": null,
  "cthulhu_mythos_delta": 0,
  "narrative_hint": "the fog hasn't moved; you have to look back to be sure the train has."
}
```

When applicable:

```json
"temporary_insanity": {
  "int_check": {"target": 60, "roll": 71, "result": "fail"},
  "symptom_roll": 4,
  "symptom": "compulsion: arranges the ticket fragments in a row by colour",
  "duration_rounds": "1d10",
  "duration_rolled": 6
}
```

```json
"indefinite_insanity": {
  "triggered_by": "lost 13 SAN in this scene (max 60, threshold 12)",
  "roll": 4,
  "result_table": "phobia",
  "affliction": "catoptrophobia",
  "modifier": "+10 to SAN checks triggered by reflections; -1 step on skill checks in scenes featuring reflections"
}
```

The Keeper composes prose from `narrative_hint` plus any
`temporary_insanity.symptom` text. Numbers go on the HUD line, never in
the body of the scene.

---

## When *not* to call sanity-keeper

- Routine progress, unsettling-but-not-uncanny ambient
- Fights with mundane attackers (no `uncanny` flag) — combat-referee
  handles HP only
- The investigator reading a clue about *another person's* breakdown —
  it's information, not a trigger

When in doubt, ask: *is the world's physics being violated right now,
in a way the investigator is registering?* If yes → SAN check. If no
→ ordinary description.
