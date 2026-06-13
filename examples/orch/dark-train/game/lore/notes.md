# Dark Train — Event Notes

> Terse per-event log. The Keeper appends an entry after any
> turn that involved a state-changing event (item picked up,
> NPC dialogue advancing affection ≥ ±3, scripted event fired,
> SAN check failed, dispersal). Daily wheel-clatter ticks don't
> belong here.

Format:

```
## Tick N · Carriage X · <action>
- One factual sentence describing what happened
- Optional: state delta (flag set, fragment heard, SAN delta)
- Optional: hook for future ("the nervous woman remembered a name")
```

The Keeper writes this for itself, not for the player — but the
investigator's journal (`game/player/journal.md`) draws from the same
events, paraphrased to first-person.

---
