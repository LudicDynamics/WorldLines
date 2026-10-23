# Sanity — Dark Train (BRP)

> Canonical reference for the `referee` (`check_type: "san"`). The GM
> (world-agent) routes here whenever something *uncanny* touches the
> passenger — it never resolves SAN itself. SAN loss, temporary
> insanity, lingering marks and dispersal all originate in this file.
>
> Rules base: the optional **Sanity** rule of *Basic Roleplaying:
> Universal Game Engine* (Chaosium, ORC License). Sections marked
> **This world's own rule** are Dark Train additions.

---

## Scale

- `SAN` starts at `POW × 5`. The passenger has POW 12 → **SAN 60**.
- SAN can never exceed **99**, and certain knowledge lowers that
  ceiling: `max_san = 99 − Forbidden Lore` (see below).
- `player/stats.json` carries `san.current`, `san.max` and
  `san.starting`. Total SAN lost so far (used by event preconditions
  `min_san_loss`) is `san.starting − san.current`.

### Thresholds (texture only)

| Current SAN (share of max) | State                                                          |
|----------------------------|----------------------------------------------------------------|
| 80–100%                    | clear-headed                                                   |
| 50–80%                     | unsettled — reflections lag a beat, the wheels' rhythm sticks  |
| 30–50%                     | **fraying** — hand tremor, perception skips, names won't come  |
| 10–30%                     | **brittle** — see below                                        |
| 0                          | **dispersal** — see "SAN 0" below                              |

These don't modify dice; they're texture for the GM to weave. The
mechanical bite comes from the sections below.

---

## Sanity roll (d100 vs current SAN)

When the referee is called with a trigger:

1. Roll `1d100` against **current SAN**.
2. **Success** (`roll ≤ current SAN`) → lose the **success** amount of
   the trigger (often 0 or 1). Even a success can cost something.
3. **Failure** (`roll > current SAN`) → lose the **failure** amount.
4. A roll of 99–00 is always a failure.

High SAN is a large target, easy to roll under. As SAN drops, the same
triggers cost more often.

**This world's own rule — brittle:** if `current SAN ≤ 10`, every
sanity roll is **Difficult** (target = current SAN × ½, round up).

---

## Trigger table

| Trigger                                              | Success loss | Failure loss  |
|------------------------------------------------------|--------------|---------------|
| Glimpse the void outside a window                    | 0            | 1D3           |
| Long stare into the void (≥ one turn)                | 1            | 1D6           |
| NPC's face skews briefly                             | 0            | 1D4           |
| Train stops shuddering (the rhythm goes silent)      | 1            | 1D6 + 1       |
| The child's bear answers a question                  | 1            | 1D4           |
| Reading text that reads you back                     | 1D3          | 2D6           |
| Direct contact with the Conductor's hand             | 1D4          | 2D6           |
| Witnessing a passenger dissolve into the fog         | 1D6          | 2D10          |
| Realising a passenger is repeating yesterday's words | 1            | 1D4           |
| Hearing your own forgotten name spoken               | 1D2          | 1D6 + 2       |
| **Reading the Conductor's logbook** (event-only)     | 1D6          | 1D10, and Forbidden Lore +1 |

Severity defaults when a trigger isn't listed: minor `0/1D3`, moderate
`1/1D6`, major `1D3/2D6`.

Triggers stack within a scene only if they're qualitatively distinct.
"Three windows in a row" is one trigger. Three different *kinds* of
uncanny in three minutes is three triggers.

---

## Temporary insanity

BRP: losing **half of your current SAN** within a short span (about
five minutes) drives you temporarily insane. On this train the span is
**one resolve / scene beat**: the referee records `san.beat_start` at
the first sanity roll of a beat (a beat = one GM turn; `san.beat_turn`
holds its `run_state.turn_count`) and adds every loss in that beat to
`san.beat_loss`. When `beat_loss ≥ beat_start ÷ 2` → temporary insanity.

It lasts until the end of the current scene. The referee rolls `1D8`
on this world's own table:

| 1D8 | Episode                                                                  |
|-----|--------------------------------------------------------------------------|
| 1   | **Counting the joins** — counts rail joints aloud and can't stop until the count "comes out right" |
| 2   | **Facing backward** — turns to face the rear of the Train and won't look forward |
| 3   | **The wrong ticket** — insists the torn ticket belongs to someone else and tries to return it |
| 4   | **Holding the strap** — grips a handrail or seat back; the hand won't open |
| 5   | **Borrowed name** — answers to a name that isn't theirs for the rest of the scene |
| 6   | **Window-pressed** — presses palm and forehead to the glass, breath fogging it |
| 7   | **Dead sleep** — falls asleep where they stand, between one word and the next |
| 8   | **Clear line** — sees the whole Train end to end for one moment, then cannot say what they saw |

Episodes appear in **prose**, never as a status icon. The GM writes the
symptom into the scene; the player still chooses their actions (some
may be narratively constrained — "your hand won't let go of the strap").

---

## This world's own rule — lingering marks

When an episode of temporary insanity ends while **current SAN is below
half of max SAN**, it leaves a **lingering mark**. Roll `1D6`:

| 1D6 | Mark                                                                       |
|-----|----------------------------------------------------------------------------|
| 1   | **Dread of the connector** — the swaying space between carriages makes your knees go |
| 2   | **Dread of stopping** — any slowing of the Rhythm closes your throat       |
| 3   | **Dread of glass** — you stop looking at windows, and what is in them      |
| 4   | **The tally** — you must keep a count of something (doors, seats, breaths) |
| 5   | **The ledger habit** — you write down every name you hear, on anything     |
| 6   | **The other passenger** — you are sure someone is always one seat behind you, and sometimes there is |

Effect: sanity rolls caused by the mark's subject get **+10%** (you've
lived with it), but skill checks in scenes featuring that subject are
**one difficulty step harder**. Marks are permanent on this train.
Store them in `player/stats.json.afflictions[]` as
`{name, subject, gained_at_tick}`. Don't list them in the HUD; the
player discovers the symptom in play.

---

## SAN 0 — dispersal (this world's own rule)

The passenger doesn't die and doesn't go permanently insane. **Dispersal**:

1. The current scene ends mid-sentence.
2. The next turn opens in an **earlier carriage** — the GM picks by
   narrative geometry, not at random.
3. Memory gap: one item lost; one fragment retroactively unheard
   (remove from `player.fragments_heard[]`); one NPC no longer
   remembers meeting them (`state.met → false`).
4. Current SAN restored to `max_san ÷ 3` (round up). Max SAN drops by
   **2** permanently.

Dispersal is **not a game over**. It's the Train's way of editing. The
passenger may reach Carriage 1 having been dispersed twice; the truth
they find there will be different from the one a fresh passenger would
have found.

---

## This world's own rule — Forbidden Lore (禁知)

Forbidden Lore measures how much the passenger **understands what the
Train is**. It starts at **0** and goes up:

- Reading certain texts or documents (event-driven, +1 to +5)
- Surviving direct contact with the Conductor's hand (+1)
- Hearing your own forgotten name spoken back (+1)
- Reading the Conductor's logbook in Carriage 2 (+2 to +5)
- Reaching Carriage 1 (+1 to +10, depending on the ending)

Every point **lowers max SAN by 1** (`max_san = 99 − forbidden_lore`).
That ceiling cannot be recovered on this train.

Forbidden Lore can be **rolled** (`d100 ≤ forbidden_lore`) to recognise
a sign: "have I seen this kind of thing before?" A **success** means
the passenger *understands* what just happened — and understanding
costs **1D3 SAN** (no sanity roll; it is simply paid). A failure means
the sign stays unreadable, at no cost.

---

## Narrative integration — no numbers in prose

The GM **never writes "you lose 4 SAN"**. The HUD line shows the delta
(`SAN 56 (-3)`); the prose shows the *symptom*:

> Your reflection on the window lags a beat behind you.
> A name surfaces in your throat. Not yours. It sinks again.
> The wheels are off by a heartbeat. You hadn't noticed they had a heartbeat.

If you find yourself describing the trigger directly — "the void horror
radiates dread" — stop. Describe **what the passenger does** in the
trigger's presence. SAN loss is a description of how the passenger's
body is currently failing to be normal.

---

## Output contract (referee → world-agent)

```json
{
  "check_type": "san",
  "trigger": "long_stare_into_void",
  "severity": "minor | moderate | major",
  "difficulty": "average | difficult",
  "san_check": {"roll": 47, "target": 56, "result": "success"},
  "san_loss": {"success": "1", "failure": "1D6", "applied": 1},
  "san_delta": {"before": 56, "after": 55},
  "beat": {"start": 56, "loss": 1},
  "temporary_insanity": null,
  "lingering_mark": null,
  "forbidden_lore_delta": 0,
  "pending_dispersal": false,
  "narrative_hint": "the fog hasn't moved; you have to look back to be sure the train has."
}
```

When applicable:

```json
"temporary_insanity": {
  "triggered_by": "lost 24 of 47 SAN this beat",
  "roll": 4,
  "episode": "holding the strap: the hand on the seat back won't open",
  "lasts": "until end of scene"
}
```

```json
"lingering_mark": {
  "roll": 3,
  "name": "dread of glass",
  "subject": "windows and reflections",
  "modifier": "+10% to sanity rolls caused by reflections; one step harder skill checks in scenes featuring them"
}
```

The GM composes prose from `narrative_hint` plus any
`temporary_insanity.episode` text. Numbers go on the HUD line, never in
the body of the scene.

---

## When *not* to call for a sanity roll

- Routine progress, unsettling-but-not-uncanny ambience
- Fights with mundane attackers (no `uncanny` flag) — combat handles HP only
- The passenger reading a clue about *another person's* breakdown —
  it's information, not a trigger

When in doubt, ask: *is the world's physics being violated right now,
in a way the passenger is registering?* If yes → sanity roll. If no →
ordinary description.
