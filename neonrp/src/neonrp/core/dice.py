"""Deterministic check core (ADR-0027 minimum `roll_check`).

This module is the Python-internal mechanics primitive. It does not write
files, does not narrate prose, and is seedable so M17 replay can reproduce a
roll exactly. ADR-0027's JSON example uses a d20 vocabulary
(`critical_success`/`critical_failure`/`success`/`failure`); the default ruleset
here is a percentile roll-under d100 (``"brp"``: Basic Roleplaying, Chaosium, ORC
License) while keeping the ADR's binding principles (deterministic, replayable,
structured, no file mutation, game terminology). `passed` + `margin` remain
available so callers that only care about the ADR's binary contract still work.

A second ruleset (``"srd"``: the d20 roll-over of the System Reference Document 5.2,
CC-BY-4.0) is available opt-in via the `ruleset` param; it is purely additive
(extra kwargs, extra `DiceResult` fields with defaults, a separate classifier).
The old ids ``"coc"`` / ``"5e"`` are still read (10-14: open rules only by name).
The percentile ladder below still has the
hard / extreme tiers of before; aligning it to BRP's special / critical is still to do.
"""

from __future__ import annotations

import random
import re as _re
from dataclasses import dataclass
from enum import Enum
from typing import Final, Literal

Ruleset = Literal["brp", "srd", "coc", "5e"]
_RULESET_ALIAS: Final[dict[str, str]] = {"coc": "brp", "5e": "srd"}  # ids before 10-14, still read


def canonical_ruleset(name: object) -> str:
    """``brp`` / ``srd`` for any id we have used (the old ``coc`` / ``5e`` included); anything else → ``brp``."""
    n = str(name or "").strip().lower()
    n = _RULESET_ALIAS.get(n, n)
    return n if n in ("brp", "srd") else "brp"

# percentile roll-under ladder. Order matters: lower index == better outcome.
# Membership in this enum is the single source of truth for valid tiers; the
# i18n layer mirrors these member values as message-key suffixes.
class Outcome(str, Enum):
    """Success tiers, best to worst.

    brp uses the full ladder (Basic Roleplaying: critical ≤ 1/20 of the skill, special ≤ 1/5, success ≤ the skill,
    fumble 99 / 00); srd d20 reuses only CRITICAL/SUCCESS/FAIL/FUMBLE (SPECIAL is never produced by the srd classifier).
    """

    CRITICAL = "critical"          # brp: roll <= ceil(target / 20) | srd: natural 20
    SPECIAL = "special"            # brp only: roll <= ceil(target / 5)
    SUCCESS = "success"            # brp: roll <= target | srd: total >= DC
    FAIL = "fail"                  # brp: roll > target | srd: total < DC
    FUMBLE = "fumble"              # brp: 99 / 00 | srd: natural 1


# brp: a roll of 99 or 00 fumbles; a skill of 99 or more only fumbles on 00 (it would succeed on 99 otherwise).
_FUMBLE_FLOOR: Final[int] = 99
_DICE_FACES: Final[int] = 100

# srd d20 roll-over constants.
_D20_FACES: Final[int] = 20
_D20_CRIT: Final[int] = 20
_D20_FUMBLE: Final[int] = 1


@dataclass(frozen=True, slots=True)
class DiceResult:
    """Structured result handed back to the calling agent.

    Frozen + slotted so it is cheap, hashable-adjacent, and cannot be mutated
    by a consumer mid-turn (replay/audit safety).
    """

    skill_name: str
    roll: int
    target: int
    outcome: Outcome
    # Additive fields (defaults keep the brp result shape/values unchanged).
    ruleset: Ruleset = "brp"
    # srd roll-over breakdown. For brp these stay neutral and are unused:
    #   natural   = the natural d20 face actually used (after adv/disadv pick)
    #   modifier  = flat bonus added to natural for the total
    #   rolls     = every raw d20 rolled this check (1 normal, 2 for adv/disadv)
    natural: int = 0
    modifier: int = 0
    rolls: tuple[int, ...] = ()

    @property
    def passed(self) -> bool:
        """ADR-0027 binary view: did the actor meet the difficulty?"""
        return self.outcome in (
            Outcome.CRITICAL,
            Outcome.SPECIAL,
            Outcome.SUCCESS,
        )

    @property
    def margin(self) -> int:
        """ADR-0027 `margin`.

        brp (roll-under): target - roll (positive == made it).
        srd (roll-over): total - target (positive == made it).
        Sign convention is kept "positive == success" for both rulesets so a
        consumer can branch on margin without knowing the ruleset.
        """
        if self.ruleset == "srd":
            return self.total - self.target
        return self.target - self.roll

    @property
    def total(self) -> int:
        """Effective check total the comparison used.

        srd: natural d20 + modifier. brp: just the d100 roll (no modifier),
        so this stays equal to `roll` and the brp contract is unchanged.
        """
        if self.ruleset == "srd":
            return self.natural + self.modifier
        return self.roll


def _classify(roll: int, target: int) -> Outcome:
    """Map a raw d100 roll against a target to a percentile tier.

    Fractions round up and are at least 1 (BRP: 1/20 of 75% is 3.75 → 4). A fumble is checked before the success
    ladder; a critical is always a success.
    """
    if roll >= _FUMBLE_FLOOR and (roll >= _DICE_FACES or target < _FUMBLE_FLOOR):
        return Outcome.FUMBLE
    if roll <= max(1, -(-target // 20)):
        return Outcome.CRITICAL
    if roll <= max(1, -(-target // 5)):
        return Outcome.SPECIAL
    if roll <= target:
        return Outcome.SUCCESS
    return Outcome.FAIL


def _classify_5e(natural: int, total: int, target: int) -> Outcome:
    """Map a srd d20 result to a tier.

    Natural 20/1 override the DC comparison (srd crit/fumble are about the die
    face, not the total). Otherwise it is a flat roll-over: total >= DC.
    """
    if natural == _D20_CRIT:
        return Outcome.CRITICAL
    if natural == _D20_FUMBLE:
        return Outcome.FUMBLE
    if total >= target:
        return Outcome.SUCCESS
    return Outcome.FAIL


def roll_check(
    skill_name: str,
    target: int,
    *,
    rng: random.Random | None = None,
    ruleset: Ruleset = "brp",
    modifier: int = 0,
    advantage: bool = False,
    disadvantage: bool = False,
) -> DiceResult:
    """Resolve a single skill check.

    `ruleset` selects the system: `"brp"` (default, percentile roll-under d100) or
    `"srd"` (d20 roll-over); `"coc"` / `"5e"` are read as those two.
    `modifier`/`advantage`/`disadvantage` apply only to srd; for brp they are
    inert (brp never reads them).

    `rng` is injectable so replay/tests can pin the exact roll. When omitted we
    use a fresh module-local `random.Random()` rather than the global RNG, so a
    caller that forgets to seed still cannot perturb global randomness (ADR-0027
    "no dependency on global randomness").
    """
    if target < 0:
        raise ValueError(f"target must be non-negative, got {target}")
    generator = rng if rng is not None else random.Random()
    ruleset = canonical_ruleset(ruleset)  # type: ignore[assignment]

    if ruleset == "srd":
        if advantage and disadvantage:
            # srd rule: advantage and disadvantage cancel to a single straight
            # roll rather than stacking.
            advantage = disadvantage = False
        # Always draw two dice when adv/disadv so the RNG stream advances
        # identically regardless of which die is selected (replay stability).
        d1 = generator.randint(1, _D20_FACES)
        if advantage or disadvantage:
            d2 = generator.randint(1, _D20_FACES)
            rolls = (d1, d2)
            natural = max(d1, d2) if advantage else min(d1, d2)
        else:
            rolls = (d1,)
            natural = d1
        total = natural + modifier
        return DiceResult(
            skill_name=skill_name,
            roll=natural,
            target=target,
            outcome=_classify_5e(natural, total, target),
            ruleset="srd",
            natural=natural,
            modifier=modifier,
            rolls=rolls,
        )

    roll = generator.randint(1, _DICE_FACES)
    return DiceResult(
        skill_name=skill_name,
        roll=roll,
        target=target,
        outcome=_classify(roll, target),
    )


def format_dice_line(result: DiceResult, locale: str = "en") -> str:
    """Render a result as the single fixed structured line — never prose.

    brp shape (unchanged): ``[<name>: <roll> <op> <target>] → <outcome>`` with
    roll-under operators ``<=`` (pass) / ``>`` (fail).

    srd shape: ``[<name>: <natural>+<mod>=<total> <op> <target>] → <outcome>``
    with roll-over operators ``>=`` (pass) / ``<`` (fail), e.g.
    ``[Stealth: 17+3=20 >= 15] → Success``.

    Only the skill name and outcome label vary by locale; the bracket/arrow
    skeleton is constant so downstream parsing and benchmark diffs stay stable
    across languages.

    Imported lazily so `core.dice` has no hard import-time dependency on the TUI
    layer (keeps the mechanics core usable in headless/replay contexts).
    """
    from neonrp.tui.i18n import get_message

    outcome_label = get_message(locale, f"dice.outcome.{result.outcome.value}")

    if result.ruleset == "srd":
        op = ">=" if result.passed else "<"
        template = get_message(locale, "dice.line.5e")
        return template.format(
            name=result.skill_name,
            natural=result.natural,
            modifier=result.modifier,
            total=result.total,
            op=op,
            target=result.target,
            outcome=outcome_label,
        )

    op = "<=" if result.passed else ">"
    template = get_message(locale, "dice.line")
    return template.format(
        name=result.skill_name,
        roll=result.roll,
        op=op,
        target=result.target,
        outcome=outcome_label,
    )


# ── one dice entry for the engine (every roll goes through here — the random number, and the event a
#    frontend can animate / play a sound for). Still pure: callers send the event (``ledger.dice_rolled``). ──

_EXPR = _re.compile(r"^\s*(\d*)d(\d+)\s*([+-]\s*\d+)?\s*$", _re.IGNORECASE)


def roll_expr(expr: str, *, rng: random.Random, max_dice: int = 20) -> dict | None:
    """``NdM+K`` → {"expr": "2d6+1", "rolls": [..], "modifier": K, "total": sum+K}; None if it is not a dice expression."""
    m = _EXPR.match(str(expr or ""))
    if not m:
        return None
    n, sides = int(m.group(1) or 1), int(m.group(2))
    mod = int((m.group(3) or "0").replace(" ", ""))
    rolls = [rng.randint(1, sides) for _ in range(max(1, min(n, max_dice)))]
    return {"expr": f"{n}d{sides}{m.group(3).replace(' ', '') if m.group(3) else ''}", "rolls": rolls, "modifier": mod, "total": sum(rolls) + mod}


# The random-number backend behind the [dice] tool (the tool dispatches to a py — later possibly a ts —
# implementation). A backend maps a seed to a generator with ``randint``; seeded, so a replay rolls the same faces.
_BACKEND = None


def set_backend(fn) -> None:  # noqa: ANN001 — fn(seed: str) -> object with randint(a, b); None = Python's Random
    global _BACKEND
    _BACKEND = fn


def rng_for(seed: str) -> random.Random:
    return _BACKEND(seed) if _BACKEND is not None else random.Random(seed)



# ── the prose never claims a tier the dice did not give (niko 10-17: the narration said 大成功, the engine rolled 64) ──

def tier_guard(text: str, levels: list[str], words: dict, names: dict) -> tuple[str, list[dict]]:
    """``text`` with every tier word the beat's rolls did not reach put back to what was rolled. ``levels``: the tiers
    rolled this beat, the player's own first (``crit`` / ``success`` / ``fail`` / ``fumble``); ``words``: {tier: [the
    words that claim it]} (the pack's strings — the engine holds no words); ``names``: {tier: its word}. No roll this
    beat → nothing to contradict, the text stays. Returns (text, [{"word", "tier", "as"}])."""
    levels = [str(x) for x in levels or [] if x]
    if not text or not levels or not isinstance(words, dict):
        return text, []
    fixed: list[dict] = []
    for tier, ws in words.items():
        if tier in levels or not isinstance(ws, list):
            continue
        actual = levels[0]
        to = str(names.get(actual) or "")
        if not to:
            continue
        for w in sorted((str(x) for x in ws if x), key=len, reverse=True):
            latin = w.isascii()
            pat = _re.compile(rf"\b{_re.escape(w)}\b" if latin else _re.escape(w), _re.IGNORECASE if latin else 0)
            text, n = pat.subn(to, text)
            if n:
                fixed.append({"word": w, "tier": tier, "as": actual, "n": n})
    return text, fixed
