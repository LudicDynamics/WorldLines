# Narrative Rules — Dark Train

> Canonical style / formatting reference for puzzle-agent. When the
> three specialists return beats, puzzle-agent composes the final
> player-facing prose **by these rules**, not by general LLM instinct.

---

## HUD line (first line of every turn)

Every turn begins with a single-line status bar. This is the only
place mechanical numbers surface in prose — the body of the narrative
never mentions HP, SAN, tick_count, or dice. Format:

```
── Carriage 6 · HP 100 · SAN 80 · tick 0 ──
```

Fields in order:

1. **Current carriage** — pulled from `player.location`, localized.
   Use the short label (`Carriage 6`, `Connector Passage`, etc.).
2. **HP** — from `player.hp`. Drop the `/max` when HP equals max. Show
   the delta in parentheses when it changed this turn: `HP 94 (-6)`.
3. **SAN** — from `player.san`. Same delta convention: `SAN 77 (-3)`.
4. **tick** — from `player.tick_count`. Only shows when > 0 (skip on
   the opening turn).
5. **fragments** — from `len(player.fragments_heard)`. Only show when
   ≥ 1, as ` · fragments 2`.

Color / emphasis:
- Drop `── … ──` framing in plain-text / non-styled rendering.
- Keep the `·` separator. One space on each side.

### Examples

Opening turn, pristine state:
```
── Carriage 6 · HP 100 · SAN 80 ──
```

After a fight that cost HP:
```
── Carriage 3 · HP 87 (-6) · SAN 74 (-1) · tick 8 ──
```

Post-scripted event, fragment earned:
```
── Carriage 4 · HP 100 · SAN 72 (-3) · tick 12 · fragments 3 ──
```

When PC is fraying (SAN ≤ 40):
```
── Carriage 2 · HP 68 · SAN 34 (-2) · tick 19 · fragments 5 ──
```

---

## Length

- **1–3 paragraphs**, rarely 4. Max 5 only for major scripted events
  (train-stops-shuddering, conductor-first-contact).
- A "paragraph" is 2–5 sentences. Not a single run-on.
- Silence is a legitimate beat. One line of "The wheels clatter on."
  is a valid turn if the player did nothing meaningful.

## Voice

- **Second person** as default: "You see the door."
- **Third person** only for dissociation moments — when the PC's sense
  of self has just cracked: "The passenger touches the window. She is
  surprised the glass is warm." Used sparingly: once a session, maybe.
- Past tense occasionally for memory fragments ("You were here before.
  You remember now. You remember nothing else.") — italicize if the
  renderer supports it.

## Sensory priority

Dark Train is a horror of unreliable perception. Rank senses so the PC
(and reader) has to work:

1. **Sound** — wheels, breath, clicks, voices through doors. Primary.
2. **Touch** — temperature shifts, cold seat leather, the shape of
   something in a pocket.
3. **Sight** — limited by fog and emergency lighting. Distant things
   are shapes, not objects.
4. **Smell** — ozone, wet metal, something faintly rotten. Use
   sparingly — three smell-mentions per session is already too many.
5. **Taste** — almost never. Reserve for a single uncanny moment.

Lead with sound or touch. Resist the urge to describe everything
visually.

## Dialogue

- NPCs speak **short, broken, weighted**. Full sentences are a luxury.
- Never exceed 2 consecutive lines of dialogue from one NPC.
- NPCs don't explain themselves. They withhold, then release a
  fragment. They contradict each other. They don't remember meeting
  you.
- **No dialogue tags beyond `said`**. Not "whispered", "muttered",
  "hissed" — just `said`, or action beats that imply tone.

  ✓ "She looked at her hands. 'He's not there anymore,' she said."
  ✗ "'He's not there anymore,' she whispered fearfully."

## Forbidden words / tropes

Avoid the following — they're cosmic-horror clichés that flatten the
specific texture of Dark Train:

- `unspeakable`, `indescribable`, `maddening`, `eldritch`
- `tentacles`, `slime`, `monstrous geometry`
- Exclamation marks (the Train doesn't shout)
- The word "you feel" as a crutch for "you notice that" —
  feelings are what the PC can describe, not what the LLM editorializes
- `darkness` as a noun alone — describe WHAT the dark is doing (it
  thickens, it holds, it presses)
- `suddenly` — horror is not sudden on this train. It is slow and
  then always-there.

Allowed but handle with care:
- `fog`, `void` — canonical Train elements; use them precisely
- `cold` — overused; alternate with "the air has dropped", "the heat
  has left the seat"

## Codex — canonical phrasings for recurring elements

| Element | Canonical framing |
|---|---|
| **The Train** | singular, definite, treat it like a proper noun; "the Train has been moving for a long time"; never explain its mechanism |
| **The Fog** | grey, motionless, ideational; "the fog outside is not passing, it is hanging"; never say "mist" or "clouds" |
| **The Rhythm** | the sound of wheels on rails; when it changes, that is an event; "the rhythm is off by a heartbeat" |
| **The Void** | what is beyond the fog — described only through what the PC's mind does in its presence (pressure behind the eyes, certainty of something you can't name) |
| **The Conductor** | tall, uniform, cap, unchanging silhouette; never described in full face; his presence is positional, not visual |
| **Fragments** | when a fragment is heard, let it appear *inside* the prose as recalled thought — not always in direct quotes. e.g., the phrase `The wheels sound wrong on the rails` becomes a sentence the PC half-remembers while listening |
| **Sanity drop** | never say "you lose sanity"; instead show the symptom — a reflection lagging, a certainty that decays, a name that briefly surfaces and sinks |

## Pacing over a session

- **Ticks 0–5** — slow. Let the player explore carriage-6 without
  uncanny pressure. The Train establishes itself as mundane.
- **Ticks 5–15** — pressure builds. Ambient events begin. First
  scripted event fires (`conductor-first-contact` is a good candidate).
- **Ticks 15–30** — reveals. Scripted events can daisy-chain. The PC
  begins to accumulate fragments that make the Train's pattern legible.
- **Ticks 30+** — payoff. By now SAN is drained enough that the
  boundary between "what the PC sees" and "what the Train shows them"
  is porous. Save the highest-impact scripted events (like
  `the-message-on-the-window`) for here.

## End of turn

Close cleanly. The **last sentence** of the prose should land, not
trail. Compare:

✗ "And so you sit there, wondering what to do next, as the train goes on..."
✓ "The nervous woman's hands go still. She is watching the door."

Don't end with "what do you do?" — that's what `ask_user` is for.

## When the player does nothing / quiet tick

When `train-event` returns a quiet tick and the player hasn't done
anything consequential, the turn is allowed to be very short:

```
── Carriage 5 · HP 100 · SAN 78 · tick 9 ──

The wheels clatter on. Nothing stirs. The fog is the same fog.

What do you do next?
```

This is a legitimate beat. Don't feel obligated to manufacture drama.

---

## Summary — every turn, in order

1. HUD line.
2. One blank line.
3. Narrative body (1–3 paragraphs).
4. One blank line.
5. `ask_user` options OR a single open-ended line.

That's it. Reliable cadence matters more than novelty on any single turn.
