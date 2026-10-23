"""Tests for the deterministic CoC 7e dice core (ADR-0027 roll_check)."""

import random

from neonrp.core.dice import (
    DiceResult,
    Outcome,
    format_dice_line,
    roll_check,
)


class _FixedRng(random.Random):
    """An RNG whose next randint result is pinned, for boundary testing."""

    def __init__(self, value: int) -> None:
        super().__init__()
        self._value = value

    def randint(self, a: int, b: int) -> int:  # noqa: ARG002 - signature parity
        return self._value


def _roll_with(value: int, target: int) -> DiceResult:
    return roll_check("Spot", target, rng=_FixedRng(value))


def test_seeded_roll_is_deterministic_and_replay_stable() -> None:
    # Same seed -> same roll across independent calls (M17 replay contract).
    first = roll_check("Persuade", 60, rng=random.Random(42))
    second = roll_check("Persuade", 60, rng=random.Random(42))
    assert first == second
    assert first.roll == second.roll
    assert first.outcome == second.outcome


def test_different_seeds_can_differ() -> None:
    a = roll_check("Dodge", 50, rng=random.Random(1))
    b = roll_check("Dodge", 50, rng=random.Random(999))
    # Not a strict guarantee for all seeds, but these two differ.
    assert (a.roll, a.outcome) != (b.roll, b.outcome)


def test_tier_boundaries_against_target_50() -> None:
    """BRP (10-14): critical ≤ 1/20 of the skill, special ≤ 1/5, success ≤ the skill, fumble 99 / 00 — rounded up."""
    target = 50
    assert _roll_with(1, target).outcome is Outcome.CRITICAL
    assert _roll_with(3, target).outcome is Outcome.CRITICAL   # ceil(50/20) = 3
    assert _roll_with(4, target).outcome is Outcome.SPECIAL
    assert _roll_with(10, target).outcome is Outcome.SPECIAL   # 50/5 = 10
    assert _roll_with(11, target).outcome is Outcome.SUCCESS
    assert _roll_with(50, target).outcome is Outcome.SUCCESS
    assert _roll_with(51, target).outcome is Outcome.FAIL      # > 50
    assert _roll_with(98, target).outcome is Outcome.FAIL
    assert _roll_with(99, target).outcome is Outcome.FUMBLE    # 99 / 00
    assert _roll_with(100, target).outcome is Outcome.FUMBLE
    assert _roll_with(4, 75).outcome is Outcome.CRITICAL       # the rulebook's own example: 1/20 of 75 = 3.75 → 4
    assert _roll_with(99, 99).outcome is Outcome.SUCCESS       # a skill of 99 only fumbles on 00


def test_passed_and_margin_adr_binary_view() -> None:
    success = _roll_with(30, 50)
    assert success.passed is True
    assert success.margin == 20  # target - roll
    fail = _roll_with(70, 50)
    assert fail.passed is False
    assert fail.margin == -20
    # Fumble counts as a failure even though it is a special roll.
    assert _roll_with(99, 50).passed is False


def test_low_target_does_not_underflow() -> None:
    # a tiny target still gives a roll of 1 its critical (the fractions are at least 1).
    assert _roll_with(1, 3).outcome is Outcome.CRITICAL
    assert _roll_with(2, 3).outcome is Outcome.SUCCESS


def test_format_dice_line_exact_shape_en() -> None:
    result = _roll_with(23, 50)
    line = format_dice_line(result, "en")
    assert line == "[Spot: 23 <= 50] → Success"


def test_format_dice_line_exact_shape_zh() -> None:
    result = roll_check("察觉", 50, rng=_FixedRng(8))
    line = format_dice_line(result, "zh")
    assert line == "[察觉: 8 <= 50] → 特殊成功"


def test_format_dice_line_failure_uses_gt_operator() -> None:
    result = roll_check("潜行", 40, rng=_FixedRng(77))
    assert format_dice_line(result, "zh") == "[潜行: 77 > 40] → 失败"
    assert format_dice_line(result, "en") == "[潜行: 77 > 40] → Failure"


def test_format_dice_line_all_tiers_localize_en_and_zh() -> None:
    expectations = {
        1: (Outcome.CRITICAL, "Critical Success", "大成功"),
        9: (Outcome.SPECIAL, "Special Success", "特殊成功"),
        45: (Outcome.SUCCESS, "Success", "成功"),
        80: (Outcome.FAIL, "Failure", "失败"),
        99: (Outcome.FUMBLE, "Fumble", "大失败"),
    }
    for roll_value, (tier, en_label, zh_label) in expectations.items():
        res = roll_check("Lore", 50, rng=_FixedRng(roll_value))
        assert res.outcome is tier
        assert format_dice_line(res, "en").endswith(f"→ {en_label}")
        assert format_dice_line(res, "zh").endswith(f"→ {zh_label}")


def test_default_rng_does_not_touch_global_state() -> None:
    # Pin global RNG, roll without an explicit rng, confirm global is unchanged.
    random.seed(12345)
    snapshot = random.getstate()
    roll_check("Climb", 55)
    assert random.getstate() == snapshot


def test_negative_target_rejected() -> None:
    try:
        roll_check("Bad", -1, rng=random.Random(0))
    except ValueError:
        return
    raise AssertionError("expected ValueError for negative target")


# --- D&D 5e ruleset (additive; coc must stay byte-identical) ---


class _SeqRng(random.Random):
    """An RNG that yields a fixed sequence of randint values, in order."""

    def __new__(cls, values: list[int]):
        # random.Random.__new__ treats the first arg as a seed; list seeds are
        # unhashable, so bypass that path and let __init__ own the sequence.
        return super().__new__(cls)

    def __init__(self, values: list[int]) -> None:
        super().__init__()
        self._values = tuple(values)
        self._i = 0

    def randint(self, a: int, b: int) -> int:  # noqa: ARG002 - signature parity
        v = self._values[self._i]
        self._i += 1
        return v


def test_5e_dc_pass_and_fail_with_modifier() -> None:
    # natural 14 + 3 = 17 >= DC 15 -> success
    win = roll_check("Stealth", 15, rng=_SeqRng([14]), ruleset="srd", modifier=3)
    assert win.outcome is Outcome.SUCCESS
    assert win.passed is True
    assert win.natural == 14
    assert win.modifier == 3
    assert win.total == 17
    assert win.margin == 2  # total - DC
    # natural 8 + 2 = 10 < DC 15 -> fail
    lose = roll_check("Stealth", 15, rng=_SeqRng([8]), ruleset="srd", modifier=2)
    assert lose.outcome is Outcome.FAIL
    assert lose.passed is False
    assert lose.total == 10
    assert lose.margin == -5


def test_5e_nat20_crit_and_nat1_fumble_override_dc() -> None:
    # Natural 20 is critical even against an impossibly high DC.
    crit = roll_check("Athletics", 999, rng=_SeqRng([20]), ruleset="srd")
    assert crit.outcome is Outcome.CRITICAL
    assert crit.passed is True
    # Natural 1 is a fumble even with a huge modifier clearing the DC.
    fumble = roll_check("Athletics", 5, rng=_SeqRng([1]), ruleset="srd", modifier=50)
    assert fumble.outcome is Outcome.FUMBLE
    assert fumble.passed is False


def test_5e_advantage_takes_higher_disadvantage_takes_lower() -> None:
    adv = roll_check("Perception", 12, rng=_SeqRng([7, 15]), ruleset="srd", advantage=True)
    assert adv.natural == 15
    assert adv.rolls == (7, 15)
    assert adv.outcome is Outcome.SUCCESS
    dis = roll_check("Perception", 12, rng=_SeqRng([7, 15]), ruleset="srd", disadvantage=True)
    assert dis.natural == 7
    assert dis.rolls == (7, 15)
    assert dis.outcome is Outcome.FAIL
    # Both flags cancel to a single straight roll (5e rule).
    both = roll_check("Perception", 12, rng=_SeqRng([9]), ruleset="srd",
                      advantage=True, disadvantage=True)
    assert both.rolls == (9,)
    assert both.natural == 9


def test_5e_format_dice_line_shape_en_and_zh() -> None:
    res = roll_check("Stealth", 15, rng=_SeqRng([17]), ruleset="srd", modifier=3)
    assert format_dice_line(res, "en") == "[Stealth: 17+3=20 >= 15] → Success"
    res_zh = roll_check("潜行", 15, rng=_SeqRng([17]), ruleset="srd", modifier=3)
    assert format_dice_line(res_zh, "zh") == "[潜行: 17+3=20 >= 15] → 成功"
    # Failing 5e roll uses the `<` operator.
    miss = roll_check("潜行", 20, rng=_SeqRng([5]), ruleset="srd", modifier=1)
    assert format_dice_line(miss, "zh") == "[潜行: 5+1=6 < 20] → 失败"
    assert format_dice_line(miss, "en") == "[潜行: 5+1=6 < 20] → Failure"


def test_5e_replay_stable_with_injected_rng() -> None:
    a = roll_check("Arcana", 14, rng=random.Random(7), ruleset="srd", modifier=2,
                   advantage=True)
    b = roll_check("Arcana", 14, rng=random.Random(7), ruleset="srd", modifier=2,
                   advantage=True)
    assert a == b
    assert a.rolls == b.rolls
    assert a.outcome is b.outcome


def test_coc_path_byte_identical_regression() -> None:
    # Same call as before the 5e addition must yield an identical CoC result:
    # default ruleset, no modifier, neutral additive fields, same RNG stream.
    r = roll_check("Spot", 50, rng=random.Random(42))
    assert r.ruleset == "brp"  # 10-14: open-rule names; the old "coc" / "5e" are still read
    assert r.modifier == 0
    assert r.natural == 0
    assert r.rolls == ()
    assert r.total == r.roll  # coc total is just the d100
    assert r.margin == r.target - r.roll  # roll-under sign convention unchanged
    # Exact construction parity with the original 4-field DiceResult.
    expected = DiceResult(
        skill_name="Spot",
        roll=r.roll,
        target=50,
        outcome=Outcome(r.outcome),
    )
    assert r == expected
    # percentile line shape (still <=/> operators, no +mod= segment).
    line = format_dice_line(r, "en")
    assert line.startswith("[Spot: ")
    assert "=" not in line.split("]")[0]


def test_the_old_ruleset_ids_still_read():
    """10-14: ``coc`` → ``brp``, ``5e`` → ``srd``."""
    assert roll_check("Stealth", 15, rng=_SeqRng([14]), ruleset="5e", modifier=3).ruleset == "srd"
    assert roll_check("Spot", 50, rng=_SeqRng([20]), ruleset="coc").ruleset == "brp"
