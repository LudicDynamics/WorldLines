"""WorldLines green worldline-field animation for the launcher.

Renders branching worldlines, orbiting elliptical rings, moving
particles, a central pulse-knot, and background dust into a
Braille (2×4 dots/char) field. Per-cell colour comes from a
five-step green brightness gradient — ``GHOST`` for faint dust,
``WHITE_GREEN`` (bold) for the hottest cells.

Playback advances at a random-walk velocity so the animation
drifts faster and slower over time. Output is a multi-line string
with Textual rich-markup colour runs; the launcher's ``Static``
widget renders it with ``markup=True``.
"""

from __future__ import annotations

import math
import random

COLS = 58
ROWS = 18
PLAYBACK_FPS = 16

TAU = math.tau

# Five-step green brightness ladder.
GHOST = "#002A1E"
DIM_GREEN = "#005F3A"
GREEN = "#00B960"
HOT_GREEN = "#18FF82"
WHITE_GREEN = "#B6FFDA"

# Variable playback speed for the main animation. The logical frame
# advances by `_velocity` per tick; velocity random-walks around 1.0
# with mean reversion so it drifts faster and slower over time.
_SPEED_JITTER = 0.65       # per-tick random kick to velocity
_SPEED_MEAN_REVERT = 0.03  # per-tick pull back toward 1.0
_SPEED_MIN = 0.10
_SPEED_MAX = 4.00


# Braille sub-cell bit positions (U+2800 base).
_BRAILLE_BITS = {
    (0, 0): 0x01,
    (0, 1): 0x02,
    (0, 2): 0x04,
    (0, 3): 0x40,
    (1, 0): 0x08,
    (1, 1): 0x10,
    (1, 2): 0x20,
    (1, 3): 0x80,
}


def _color_for(power: float) -> str:
    if power > 0.86:
        return f"bold {WHITE_GREEN}"
    if power > 0.68:
        return f"bold {HOT_GREEN}"
    if power > 0.46:
        return GREEN
    if power > 0.27:
        return DIM_GREEN
    return GHOST


def _worldline_point(line_id: int, line_count: int, t: float, frame: int) -> tuple[float, float]:
    """A branching timeline curve that pinches around a central event."""
    lane = (line_id - (line_count - 1) / 2.0) / max(1.0, (line_count - 1) / 2.0)
    phase = line_id * 0.713 + math.sin(line_id * 1.7) * 0.35
    s = 2.0 * t - 1.0
    spin = frame * 0.029

    x = 0.92 * s
    y = 0.58 * lane * math.tanh(2.5 * s)

    knot = math.exp(-4.2 * (s * s + y * y))
    y += 0.16 * math.sin(5.5 * s + phase + spin) * (0.20 + abs(s))
    x += 0.10 * math.sin(phase * 1.4 + spin * 1.6) * knot
    y += 0.22 * math.cos(phase - spin * 1.2) * knot

    x += 0.035 * math.sin(8.0 * s + phase + spin * 0.7) * (1.0 - 0.45 * abs(s))
    return x, y


class _BrailleField:
    """High-resolution dot canvas: 2 dots wide × 4 dots tall per cell."""

    def __init__(self, width: int, height: int) -> None:
        self.w = width
        self.h = height
        self.dw = width * 2
        self.dh = height * 4
        self.bits = [[0] * width for _ in range(height)]
        self.power = [[0.0] * width for _ in range(height)]

    def dot(self, dx: int, dy: int, power: float = 0.45) -> None:
        if not (0 <= dx < self.dw and 0 <= dy < self.dh):
            return
        cx, sx = divmod(dx, 2)
        cy, sy = divmod(dy, 4)
        self.bits[cy][cx] |= _BRAILLE_BITS[(sx, sy)]
        if power > self.power[cy][cx]:
            self.power[cy][cx] = power if power < 1.0 else 1.0

    def plot(self, x: float, y: float, power: float = 0.45) -> None:
        # x, y are normalized to [-1, 1]; y positive upward.
        dx = int((x + 1.0) * 0.5 * (self.dw - 1))
        dy = int((1.0 - (y + 1.0) * 0.5) * (self.dh - 1))
        self.dot(dx, dy, power)

    def splat(self, x: float, y: float, radius: int = 2, power: float = 1.0) -> None:
        dx0 = int((x + 1.0) * 0.5 * (self.dw - 1))
        dy0 = int((1.0 - (y + 1.0) * 0.5) * (self.dh - 1))
        for yy in range(dy0 - radius, dy0 + radius + 1):
            for xx in range(dx0 - radius, dx0 + radius + 1):
                d = math.hypot(xx - dx0, yy - dy0)
                if d <= radius:
                    self.dot(xx, yy, power * (1.0 - d / (radius + 0.001)) + 0.25)


class WorldLinesAnimation:
    """Stateful worldline-field renderer with variable playback speed.

    Each ``tick()`` advances one frame and returns the rendered grid
    as a ``\\n``-joined string with Textual rich-markup colour runs.
    The logical frame advances by a random-walk velocity per tick, so
    the field's rotations, oscillations, and dust resamplings speed
    up and slow down over time.
    """

    def __init__(self, seed: int | None = None) -> None:
        # Capture or pick a per-instance seed so reset() returns to
        # the same playback. Default-constructed instances get a
        # fresh seed each time — different launches look different.
        if seed is None:
            seed = random.randint(0, 2 ** 31 - 1)
        self._seed = seed
        self._rng = random.Random(seed)
        # Total tick count, including intro.
        self._frame = 0
        # Float "logical" frame for the main animation; advances by
        # the current velocity each tick so the field's rotations,
        # oscillations, and dust resamplings speed up and slow down.
        self._main_frame = 0.0
        self._velocity = 3.0

    def reset(self) -> None:
        self._frame = 0
        self._main_frame = 0.0
        self._velocity = 3.0
        self._rng = random.Random(self._seed)

    @property
    def step(self) -> int:
        return self._frame

    def tick(self) -> str:
        rendered = self._render_frame(self._main_frame)
        # Random-walk velocity around 1.0 so playback speed gently
        # drifts faster and slower over time.
        self._velocity += (self._rng.random() - 0.5) * _SPEED_JITTER
        self._velocity += (1.0 - self._velocity) * _SPEED_MEAN_REVERT
        if self._velocity < _SPEED_MIN:
            self._velocity = _SPEED_MIN
        elif self._velocity > _SPEED_MAX:
            self._velocity = _SPEED_MAX
        self._main_frame += self._velocity
        self._frame += 1
        return rendered

    # ------------------------------------------------------------------
    # Frame composition
    # ------------------------------------------------------------------

    @staticmethod
    def _render_frame(frame: float) -> str:
        field = _BrailleField(COLS, ROWS)
        line_count = 17
        iframe = int(frame)  # integer-sensitive ops (dust seed, gaps)

        # 1. Branching worldlines — the main visual.
        for i in range(line_count):
            for j in range(150):
                t = j / 149.0
                x, y = _worldline_point(i, line_count, t, frame)
                shimmer = 0.30 + 0.24 * math.sin(j * 0.17 + frame * 0.08 + i)
                field.plot(x, y, shimmer)

        # 2. Orbiting elliptical rings — less literal globe, more
        # "worldline field". Tiny gaps every nth dot for the
        # particle-renderer flavour.
        for ring in range(7):
            tilt = 0.35 + 0.12 * ring
            phase = ring * 0.91
            rot = frame * (0.014 + ring * 0.0015)
            for j in range(130):
                if (j + ring * 3 + iframe // 3) % 9 == 0:
                    continue
                theta = TAU * j / 130.0
                r = 0.42 + ring * 0.055
                x = r * math.cos(theta + rot + phase)
                y = r * math.sin(theta + phase) * tilt
                a = phase * 0.55
                xr = x * math.cos(a) - y * math.sin(a)
                yr = x * math.sin(a) + y * math.cos(a)
                field.plot(xr, yr, 0.22 + 0.08 * math.sin(theta * 3 + frame * 0.05))

        # 3. Moving particles riding the worldlines.
        for k in range(16):
            line = (k * 5 + 3) % line_count
            speed = 0.006 + (k % 5) * 0.0012
            t = (frame * speed + k * 0.071) % 1.0
            x, y = _worldline_point(line, line_count, t, frame)
            field.splat(x, y, radius=1 + (k % 3 == 0), power=0.92)

        # 4. Central pulse: memory / consequence / branch nexus.
        pulse = 0.5 + 0.5 * math.sin(frame * 0.16)
        field.splat(0.0, 0.0, radius=2 + int(pulse > 0.72), power=1.0)

        # 5. Sparse background digital dust. Re-seeded every 3 frames
        # so the dust resamples slowly instead of strobing.
        rng = random.Random(12345 + iframe // 3)
        for _ in range(max(10, COLS // 2)):
            x = rng.uniform(-1.0, 1.0)
            y = rng.uniform(-0.86, 0.86)
            if rng.random() < 0.70:
                field.plot(x, y, 0.12)

        return _render_markup(field)


def _render_markup(field: _BrailleField) -> str:
    """Emit one frame as a Textual-markup string. Colour runs collapse
    consecutive same-coloured cells into one ``[color]…[/]`` segment so
    the per-frame markup stays compact."""
    rows: list[str] = []
    for y in range(field.h):
        line: list[str] = []
        last_color: str | None = None
        for x in range(field.w):
            bits = field.bits[y][x]
            if bits == 0:
                if last_color is not None:
                    line.append("[/]")
                    last_color = None
                line.append(" ")
                continue
            color = _color_for(field.power[y][x])
            if color != last_color:
                if last_color is not None:
                    line.append("[/]")
                line.append(f"[{color}]")
                last_color = color
            line.append(chr(0x2800 + bits))
        if last_color is not None:
            line.append("[/]")
        rows.append("".join(line))
    return "\n".join(rows)
