---
name: combat
description: D20 combat flow, initiative, damage, and status effects.
---

# Combat Basics

Use a clear turn order and apply effects deterministically.

1. Roll initiative for all participants.
2. Resolve turns in initiative order.
3. Apply action effects to HP, status, and position.

# Damage and Defense

- Calculate attack result before narrating impact.
- Clamp HP at `0..max_hp`.
- If HP reaches `0`, add a clear downed/defeated state.

# Status Effects

- Keep status effects explicit in entity fields.
- Include duration when possible.
- Remove expired effects as part of turn resolution.

# Narrative Rule

Always narrate consequence after mechanical updates are known.
