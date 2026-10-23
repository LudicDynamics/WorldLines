"""Tests for the Braille worldline-field launcher animation.

Each ``tick()`` returns a ``\\n``-joined string of ``ROWS`` lines.
Lines contain Textual rich-markup colour runs; after stripping
markup, each row must be exactly ``COLS`` cells of either a Braille
glyph (U+2800 .. U+28FF) or a literal space.
"""

from __future__ import annotations

import re

from neonrp.tui.intro_animation import (
    COLS,
    PLAYBACK_FPS,
    ROWS,
    WorldLinesAnimation,
)


_MARKUP_RE = re.compile(r"\[/?[^\]]*\]")


def _strip(line: str) -> str:
    return _MARKUP_RE.sub("", line)


def _frame_lines(frame: str) -> list[str]:
    return frame.split("\n")


def test_tick_returns_string_with_correct_dimensions() -> None:
    anim = WorldLinesAnimation()
    frame = anim.tick()
    lines = _frame_lines(frame)
    assert len(lines) == ROWS
    for line in lines:
        assert len(_strip(line)) == COLS


def test_only_uses_braille_and_space() -> None:
    anim = WorldLinesAnimation()
    for _ in range(40):
        frame = anim.tick()
    plain = "".join(_strip(line) for line in _frame_lines(frame))
    for ch in plain:
        assert ch == " " or 0x2800 <= ord(ch) <= 0x28FF, (
            f"unexpected glyph in frame: {ch!r}"
        )


def test_frame_is_deterministic_per_frame_index() -> None:
    # Variable-speed playback uses a per-instance RNG, so two
    # instances must share a seed to be byte-for-byte identical
    # past the intro.
    a = WorldLinesAnimation(seed=42)
    b = WorldLinesAnimation(seed=42)
    for _ in range(30):
        assert a.tick() == b.tick()


def test_reset_returns_to_initial_frame() -> None:
    a = WorldLinesAnimation()
    first = a.tick()
    for _ in range(30):
        a.tick()
    a.reset()
    assert a.tick() == first


def test_step_counter_advances() -> None:
    a = WorldLinesAnimation()
    assert a.step == 0
    a.tick()
    assert a.step == 1
    a.tick()
    a.tick()
    assert a.step == 3


def test_playback_fps_is_reasonable() -> None:
    """Render budget sanity — too slow and the launcher feels juddery."""
    assert 4 <= PLAYBACK_FPS <= 30


def test_markup_runs_are_balanced() -> None:
    """Every opening ``[color]`` tag must have a matching ``[/]``."""
    anim = WorldLinesAnimation()
    for _ in range(20):
        frame = anim.tick()
        for line in _frame_lines(frame):
            opens = len(re.findall(r"\[(?!/)[^\]]+\]", line))
            closes = len(re.findall(r"\[/\]", line))
            assert opens == closes, f"unbalanced markup in line: {line!r}"


def test_frames_evolve_over_time() -> None:
    """Successive frames must differ — the worldline field is animated."""
    a = WorldLinesAnimation()
    first = a.tick()
    later = None
    for _ in range(10):
        later = a.tick()
    assert later is not None
    assert later != first


def test_frame_contains_braille_glyphs() -> None:
    """A rendered frame should have substantive content, not just spaces."""
    a = WorldLinesAnimation()
    for _ in range(5):
        frame = a.tick()
    plain = "".join(_strip(line) for line in _frame_lines(frame))
    braille_count = sum(1 for ch in plain if 0x2800 <= ord(ch) <= 0x28FF)
    assert braille_count > 50, f"only {braille_count} braille glyphs — frame looks empty"
