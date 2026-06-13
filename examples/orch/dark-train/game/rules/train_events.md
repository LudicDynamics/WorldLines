# Train Events — Canonical Reference

> For train-event specialist. Defines the tick clock, event taxonomy,
> rolling rules, and the pacing philosophy.

## Pacing philosophy

Dark Train is not an action-per-second game. Most turns produce no
event — the train just rolls on. Events accumulate; by the time
`tick_count ≥ 20` the PC has witnessed roughly 3-5 ambient moments
and possibly 1 scripted beat. The point is weight, not density.

Err toward **quiet ticks**. A carriage where the AC vent hums and
nothing supernatural happens for a full minute IS atmospheric. Players
who feel "something's always happening" stop being afraid of what
might happen.

## Tick rules

- `tick_count` starts at 0, increments +1 per `task(train-event, ...)`.
- Ambient roll: `d100` vs current carriage's `ambient_rate` (default 35).
  Roll under = event fires. Roll over = quiet tick.
- Scripted events checked BEFORE ambient. If a scripted fires, skip
  ambient.
- Only ONE scripted event per call, even if multiple preconditions pass.
  Prioritize by: min_tick higher = fires first (the "latest-unlocked"
  wins, to avoid the player blasting through three scripted events
  back-to-back).

## Ambient event structure

Ambient events live inline on `location/carriage-*.json` via the
`ambient_events` field:

```json
"ambient_events": [
  "lights-flicker",
  "reflection-lags",
  "fog-thickens",
  "passenger-vanishes"
]
```

The actual event contents (beats, san_delta, etc.) are shared —
train-event knows them from this rules file and the patterns below.

### Ambient event patterns

| id                   | san_delta | fragment?                            | effect                               |
|---|---|---|---|
| `lights-flicker`     | -1        | no                                   | momentary dark; NPC posture shifts   |
| `reflection-lags`    | -1        | no                                   | PC's reflection beats late           |
| `passenger-vanishes` | -2        | no                                   | a named passenger absent on re-look  |
| `whisper-through-door` | -1      | yes (pick from `whisper_pool`)       | fragment added to player             |
| `fog-thickens`       | 0         | no                                   | carriage.fog_level +1 (cap 5)        |
| `wheels-go-quiet`    | -2        | no                                   | 1-2 second silence from the rails    |
| `passenger-mouths-words` | -2    | yes (pick from `whisper_pool`)       | NPC mouths something without voice   |
| `door-opens-itself`  | -1        | no                                   | a door down the carriage swings open |

### Whisper pool (used when fragment_added)

Short fragments that accumulate into `player.fragments_heard`. Pick one
at random per trigger, don't repeat if already in player's list:

- "The wheels sound wrong on the rails."
- "Seven forward. Count them."
- "You gave the ticket to someone."
- "The Conductor remembers your name."
- "Nothing out there is moving the right direction."
- "You agreed to this."
- "The rear carriage was never six."
- "Forget the name. Keep the ticket."

## Scripted events

Stored as `game/events/<id>.json`. Each one:

```json
{
  "id": "event-name",
  "kind": "scripted",
  "precondition": {
    "min_tick": 0,
    "requires_carriage": null,
    "requires_flags": [],
    "min_san_loss": 0,
    "min_fragments_heard": 0
  },
  "fired_at_tick": null,
  "san_cost": [1, 6],
  "needs_san_check": true,
  "fragment_added": null,
  "beats": [...]
}
```

Precondition evaluation: ALL fields must match for the event to be eligible.
Empty / zero / null means "no constraint". After firing, write
`fired_at_tick = <current_tick>` so the event won't fire again.

## SAN loss policy

- Ambient event: fixed small cost (usually -1, up to -2).
- Scripted event: range `[min, max]` → needs_san_check=true signals
  puzzle-agent to delegate to rules-referee for the proper SAN check
  (roll-under-SAN). puzzle-agent handles the re-delegation, you just
  return the range.
- Cap total per-call san loss from a single event: -10. Anything more
  and the PC should instead get a **scripted** event that encodes the
  larger-than-usual impact.

## Quiet tick behavior

When nothing fires, still return the payload. puzzle-agent uses the
quiet tick to produce one of:

- Rhythm beat: "The wheels clatter on."
- Pass-of-time marker: "Minutes of silence. The fog outside is
  unchanged."
- NPC idle: "The sleeping old man hasn't stirred."

Even "nothing happened" is a signal to the player — the Train is
always present. Silences count.
