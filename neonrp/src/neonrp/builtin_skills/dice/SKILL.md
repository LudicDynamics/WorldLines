---
name: dice
description: Deterministic BRP d100 skill checks. Call instead of inventing roll numbers.
---

# When To Use

Use this skill for ANY uncertain action that needs a dice ruling: spot hidden,
persuade, dodge, composure, climb, resist — anything a GM would call for a roll.

NEVER invent a roll number, a percentage, or a success tier in prose. The roll
is produced by deterministic, replayable Python (ADR-0027 `roll_check`). You
consume its result; you do not author it.

# How To Call

The mechanics core is `neonrp.core.dice`:

- `roll_check(skill_name, target, *, rng=None, ruleset="coc", modifier=0, advantage=False, disadvantage=False) -> DiceResult`
- `format_dice_line(result, locale="en") -> str`

`ruleset` selects the system:

- `"coc"` (default, project default) — BRP roll-under d100. `target` is the
  actor's effective skill value (0–100). `modifier`/`advantage`/`disadvantage`
  are ignored.
- `"5e"` (opt-in, for worlds that want SRD 5.2) — roll-over d20. `target` is the
  DC. `modifier` is the flat bonus added to the d20. `advantage` rolls twice
  and takes the higher; `disadvantage` takes the lower; both true cancel to a
  straight roll.

Pass an explicit seeded `random.Random` as `rng` only for replay/benchmark
contexts; otherwise omit it. Both rulesets are replay-stable under a fixed rng.

# Output Contract — Fixed Line, Never Prose

A check result is surfaced as exactly ONE structured line:

```
[<check_name>: <roll> <op> <target>] → <outcome>
```

BRP example: `[侦查: 23 <= 50] → 困难成功` (`<op>` is `<=` on pass, `>` on fail).

5e example: `[Stealth: 17+3=20 >= 15] → Success` /
`[潜行: 17+3=20 >= 15] → 成功` — shape is
`[<name>: <natural>+<modifier>=<total> <op> <target>] → <outcome>`, `<op>` is
`>=` on pass, `<` on fail.

The check name and outcome label are localized (en/zh/ja/ko); the
bracket/arrow skeleton is fixed. Do not paraphrase, embellish, or replace this
line with narrative numbers. You may narrate *consequences* after the line, but
the line itself is verbatim.

# Outcome Tiers

## BRP (roll-under), derived from `roll` vs `target`

- `critical` — natural 01
- `extreme`  — roll ≤ target ÷ 5
- `hard`     — roll ≤ target ÷ 2
- `success`  — roll ≤ target
- `fail`     — roll > target
- `fumble`   — natural 96–100 (counts as a failure)

## SRD 5.2 (roll-over), reuses `critical`/`success`/`fail`/`fumble`

- `critical` — natural 20 (die face, regardless of DC)
- `fumble`   — natural 1 (die face, counts as a failure)
- `success`  — total (natural + modifier) ≥ DC
- `fail`     — total < DC

(5e never produces `extreme`/`hard`.)

# Return Contract To The Calling Agent

`roll_check` returns a structured `DiceResult` (NOT prose):

- `skill_name: str`
- `roll: int` — coc: the d100; 5e: the natural d20 actually used
- `target: int` — coc: skill value; 5e: DC
- `outcome: Outcome`
- `passed: bool` — true for critical/extreme/hard/success
- `margin: int` — positive == made it for BOTH rulesets (coc: `target - roll`;
  5e: `total - DC`)
- `ruleset: "coc" | "5e"`
- `total: int` — coc: same as `roll`; 5e: `natural + modifier`
- `natural: int` — 5e: the raw d20 face used (0 for coc)
- `modifier: int` — 5e: flat bonus (0 for coc)
- `rolls: tuple[int, ...]` — every raw d20 rolled (2 entries under
  advantage/disadvantage so the agent can cite both), empty for coc

The agent / sub-agent MUST branch on `outcome` / `passed` / `margin` to choose
what happens next — gate options, change available actions, escalate danger,
award/deny info — AND can cite the concrete roll numbers (`roll`, `natural`,
`modifier`, `total`, `rolls`) when narrating. The tier is the decision input;
the rendered line is the player-facing receipt. Both come from the same
deterministic result so replay reproduces identically.
