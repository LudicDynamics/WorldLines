# Fluttering-Heart System (minimal)

This world has no combat, no dice. The only "number" is **affection**, the only "timer" is
**the speed of falling petals**.

## Affection (affection 0–100, one per character)
Every meaningful line the player says, every choice to draw near or pull away, shifts the target character's affection.
The ruling goes to `@heart`, which returns a delta (change), and world-agent writes the new value back to
`game/npc/<id>.json`.

| Band | Level (affection_level) | Behavior |
|---|---|---|
| 0–19 | Stranger | Polite, keeping distance |
| 20–39 | Noticing | Starts bringing up topics, remembers the little things you said |
| 40–59 | Fluttering | Minds your reactions, may blush or avoid your gaze |
| 60–79 | Fond | Willing to tell the thing they've been hiding (the sketchbook / the novel / that line) |
| 80–99 | On the Verge | Brings the words to their lips, but just barely doesn't say them |
| 100 | Confession | Just speak your true feelings in the old school hallway, and the wish comes true |

## Falling Petals (petals_remaining 100 → 0)
`run_state.petals_remaining` is the deadline of this story. Each time a day / a major scene advances,
world-agent reduces it (about −15~25 per day). **If "Confession" isn't reached and spoken before the petals
all fall (hit zero), this fluttering heart stops at the place of almost** — and that is precisely the keynote of this world.

## Memory and Echo
Each character has a `memory` array. The weighty things the player said and did, world-agent appends
(one line + which day). The character will bring them up much later, on their own: "That line you said on the slope that day……"
— **what was said comes back**.

## Timeline (timeline)
Each time you enter the story you may land on a different timeline node (`first-meeting` / `after-school` /
`almost-spring-end` …). The same slope, a different moment, and the people you meet and the words you can say are different.

## Notes for world-agent
- Every weighty player word or action → call `@heart` to rule → write the new affection + that line back to the npc file,
  and update run_state (day / petals remaining / focus character).
- Advance only **one beat** at a time (one line of dialogue / one moment), then stop, `AskUserQuestion` with choices.
- The keynote is yours to hold: warm, with unsaid space, a touch of regret; never fast-forward "the speed of falling petals".
