#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import shutil
import sys
import time
from dataclasses import dataclass
from typing import List, Sequence, Tuple

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
except ImportError as e:  # pragma: no cover - exercised only without Pillow
    # Must be ImportError (an Exception), NOT SystemExit (a BaseException):
    # callers like image_render.build_matrix_renderer wrap this import in
    # `except Exception` to degrade gracefully. A SystemExit slips past that
    # and crashes the whole app at startup when Pillow is absent.
    raise ImportError(
        "Pillow is required for matrix silhouette rendering (pip install pillow)"
    ) from e

RGB = Tuple[int, int, int]
Cell = Tuple[int, int, str, RGB, float]

RESET = "\x1b[0m"
HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"
ALT_ON = "\x1b[?1049h"
ALT_OFF = "\x1b[?1049l"
CLEAR = "\x1b[2J\x1b[H"

PALETTES = {
    "green": {
        "bg": (0, 4, 1),
        "low": (4, 28, 7),
        "mid": (16, 104, 28),
        "high": (92, 235, 110),
        "glow": (196, 255, 190),
    },
    "ice": {
        "bg": (1, 4, 7),
        "low": (7, 28, 44),
        "mid": (28, 115, 155),
        "high": (120, 228, 255),
        "glow": (220, 250, 255),
    },
    "purple": {
        "bg": (4, 2, 7),
        "low": (30, 10, 44),
        "mid": (98, 44, 150),
        "high": (195, 110, 255),
        "glow": (245, 220, 255),
    },
}

RAIN_GLYPHS = "01iIl|![]{}()<>/\\"
RING_GLYPHS = " .·:°*+oxO0◎◌◍"
EDGE_GLYPHS = "  ..,:;i1tfLCG08@"
GROUND_GLYPHS = "  ..,:;'`"
INTERIOR_GLYPHS = "   ..011"
BRAILLE_DOTS = (0x01, 0x02, 0x04, 0x40, 0x08, 0x10, 0x20, 0x80)



def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def smoothstep(a: float, b: float, x: float) -> float:
    if a == b:
        return 1.0 if x >= b else 0.0
    t = clamp((x - a) / (b - a))
    return t * t * (3.0 - 2.0 * t)


def mix(c1: RGB, c2: RGB, t: float) -> RGB:
    t = clamp(t)
    return (
        int(lerp(c1[0], c2[0], t)),
        int(lerp(c1[1], c2[1], t)),
        int(lerp(c1[2], c2[2], t)),
    )


def rgb_fg(rgb: RGB) -> str:
    return f"\x1b[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m"


def terminal_size(fallback=(100, 32)) -> Tuple[int, int]:
    s = shutil.get_terminal_size(fallback=fallback)
    return s.columns, s.lines


def fract(x: float) -> float:
    return x - math.floor(x)


def hash1(x: float) -> float:
    return fract(math.sin(x * 127.1 + 311.7) * 43758.5453123)


def hash2(x: float, y: float) -> float:
    return fract(math.sin(x * 127.1 + y * 311.7 + 74.7) * 43758.5453123)


def choose_by_intensity(glyphs: str, v: float) -> str:
    if not glyphs:
        return " "
    i = int(clamp(v) * (len(glyphs) - 1) + 1e-9)
    return glyphs[i]


@dataclass
class RenderOptions:
    palette: str = "green"
    char_aspect: float = 0.50
    contrast: float = 1.9
    brightness: float = 0.95
    sharpen: float = 1.2
    gamma: float = 0.9
    black_point: float = 0.58
    silhouette_softness: float = 0.10
    edge_boost: float = 2.1
    glow_boost: float = 1.2
    texture_amount: float = 0.22
    interior_noise: float = 0.07
    rain_density: float = 0.16
    rain_speed: float = 1.0
    ring_strength: float = 0.95
    ring_count: int = 5
    ground_glow: float = 0.75
    vignette: float = 0.18
    shimmer: float = 0.08
    scanline: float = 0.10
    dither: float = 0.04
    enable_rain: bool = True
    enable_rings: bool = True
    enable_ground: bool = True


class MatrixSilhouetteRenderer:
    """Style renderer for black-field silhouette + matrix-rain + arcane rings."""

    def __init__(self, image: Image.Image, options: RenderOptions | None = None):
        self.src = image.convert("RGB")
        self.options = options or RenderOptions()
        if self.options.palette not in PALETTES:
            raise ValueError(f"Unknown palette: {self.options.palette}")

    @classmethod
    def from_path(cls, path: str, options: RenderOptions | None = None):
        return cls(Image.open(path), options)

    def _fit_crop(self, width: int, height: int) -> Image.Image:
        target_px_w = max(1, width)
        target_px_h = max(1, int(height / max(0.05, self.options.char_aspect)))

        img = self.src.copy()
        sw, sh = img.size
        src_ratio = sw / sh
        dst_ratio = target_px_w / target_px_h
        if src_ratio > dst_ratio:
            new_w = int(sh * dst_ratio)
            x0 = (sw - new_w) // 2
            img = img.crop((x0, 0, x0 + new_w, sh))
        else:
            new_h = int(sw / dst_ratio)
            y0 = (sh - new_h) // 2
            img = img.crop((0, y0, sw, y0 + new_h))
        return img.resize((target_px_w, target_px_h), Image.Resampling.LANCZOS)

    def _resized_fields(self, width: int, height: int):
        # Everything here is independent of ``t``: the same six fields feed
        # every animation frame at a given size, yet they used to be
        # recomputed per frame — six PIL filters + six resizes at ~7 fps.
        # One-slot cache keyed by size (the panel only ever asks for the
        # size it currently is; a resize simply replaces the slot).
        cache = getattr(self, "_fields_cache", None)
        if cache is not None and cache[0] == (width, height):
            return cache[1]
        fields = self._compute_resized_fields(width, height)
        self._fields_cache = ((width, height), fields)
        return fields

    def _compute_resized_fields(self, width: int, height: int):
        img = self._fit_crop(width, height)
        img = ImageEnhance.Contrast(img).enhance(self.options.contrast)
        img = ImageEnhance.Brightness(img).enhance(self.options.brightness)
        if self.options.sharpen > 1.0:
            img = ImageEnhance.Sharpness(img).enhance(self.options.sharpen)

        gray = ImageOps.grayscale(img)
        edge = gray.filter(ImageFilter.FIND_EDGES)
        edge = ImageEnhance.Contrast(edge).enhance(2.8)
        blur = gray.filter(ImageFilter.GaussianBlur(radius=2.2))
        glow = blur.filter(ImageFilter.GaussianBlur(radius=4.5))
        local = gray.filter(ImageFilter.GaussianBlur(radius=1.0))
        edge_dilated = edge.filter(ImageFilter.MaxFilter(size=5))

        rgb = img.resize((width, height), Image.Resampling.BILINEAR)
        gray = gray.resize((width, height), Image.Resampling.BILINEAR)
        edge = edge.resize((width, height), Image.Resampling.BILINEAR)
        edge_dilated = edge_dilated.resize((width, height), Image.Resampling.BILINEAR)
        glow = glow.resize((width, height), Image.Resampling.BILINEAR)
        local = local.resize((width, height), Image.Resampling.BILINEAR)
        return rgb, gray, edge, edge_dilated, glow, local

    def _palette_color(self, b: float, tint: float = 0.0) -> RGB:
        pal = PALETTES[self.options.palette]
        b = clamp(b)
        if b < 0.18:
            c = mix(pal["bg"], pal["low"], b / 0.18)
        elif b < 0.62:
            c = mix(pal["low"], pal["mid"], (b - 0.18) / 0.44)
        else:
            c = mix(pal["mid"], pal["glow"], (b - 0.62) / 0.38)
        if tint:
            c = mix(c, pal["glow"], tint)
        return c

    def _ring_intensity(self, x: int, y: int, width: int, height: int, t: float) -> Tuple[float, float]:
        if not self.options.enable_rings or self.options.ring_strength <= 0.0:
            return 0.0, 0.0
        cx = width * 0.52
        cy = height * 0.46
        dx = x - cx
        dy = y - cy
        r = math.hypot(dx, dy)
        ang = math.atan2(dy, dx)
        base = min(width, height)
        radii = [base * k for k in (0.14, 0.19, 0.24, 0.30, 0.36, 0.43)[: max(1, self.options.ring_count)]]

        best = 0.0
        rune = 0.0
        rot = t * 0.18
        for i, rr in enumerate(radii):
            line = 1.0 - smoothstep(0.0, 1.7, abs(r - rr))
            if line <= 0.0:
                continue
            segs = 12 + i * 4
            a = (ang + rot * (1 if i % 2 == 0 else -1)) * segs / (2 * math.pi)
            frac = fract(a)
            dash = 1.0 if frac < 0.18 or 0.42 < frac < 0.58 or 0.82 < frac else 0.0
            marker = 1.0 if abs(frac - 0.5) < 0.03 else 0.0
            best = max(best, line * (0.40 + 0.60 * dash))
            rune = max(rune, line * (0.25 + 0.75 * marker))

        cross = 0.0
        if abs(dx) < 1.0 and r < base * 0.38:
            cross = 0.65
        if abs(dy) < 1.0 and r < base * 0.38:
            cross = max(cross, 0.65)
        return clamp((best + cross) * self.options.ring_strength), clamp(rune * self.options.ring_strength)

    def _rain_intensity(self, x: int, y: int, width: int, height: int, t: float) -> float:
        if not self.options.enable_rain or self.options.rain_density <= 0.0:
            return 0.0
        col_seed = hash1(x * 0.717 + 9.1)
        if col_seed > self.options.rain_density:
            return 0.0
        speed = self.options.rain_speed * (0.35 + col_seed * 2.0)
        phase = fract(col_seed * 13.0 + t * speed * 0.17)
        head = phase * (height + 12) - 6
        tail = 4 + int(col_seed * 14)
        dist = head - y
        if dist < 0 or dist > tail:
            return 0.0
        trail = 1.0 - dist / max(1, tail)
        flicker = 0.55 + 0.45 * math.sin(t * 6.0 + x * 0.13 + y * 0.07)
        return clamp(trail * flicker)

    def _ground_intensity(self, x: int, y: int, width: int, height: int, t: float, glow_val: float) -> float:
        if not self.options.enable_ground or self.options.ground_glow <= 0.0:
            return 0.0
        ny = y / max(1, height - 1)
        band = smoothstep(0.70, 0.96, ny)
        wave = 0.5 + 0.5 * math.sin(x * 0.12 + t * 0.6)
        scan = 0.5 + 0.5 * math.sin(y * 3.0 + t * 1.3)
        return clamp(band * (0.25 + 0.55 * glow_val + 0.20 * wave) * (0.65 + 0.35 * scan) * self.options.ground_glow)

    def _noise(self, x: int, y: int, t: float) -> float:
        return hash2(x * 1.17 + int(t * 7.0), y * 1.91 + int(t * 13.0))

    def cells(self, width: int, height: int, t: float = 0.0) -> List[Cell]:
        width = max(2, int(width))
        height = max(2, int(height))
        rgb, gray, edge, edge_d, glow, local = self._resized_fields(width, height)
        gp = gray.load()
        ep = edge.load()
        edp = edge_d.load()
        glp = glow.load()
        lp = local.load()
        rp = rgb.load()

        out: List[Cell] = []
        for y in range(height):
            for x in range(width):
                g = gp[x, y] / 255.0
                e = ep[x, y] / 255.0
                ed = edp[x, y] / 255.0
                gl = glp[x, y] / 255.0
                loc = lp[x, y] / 255.0
                src_rgb = rp[x, y]

                darkness = 1.0 - g
                structure = max(e, abs(g - loc) * 2.2, ed * 0.55)
                silhouette = smoothstep(
                    self.options.black_point - self.options.silhouette_softness,
                    self.options.black_point + self.options.silhouette_softness,
                    darkness,
                )
                silhouette *= smoothstep(0.05, 0.20, structure + gl * 0.35)
                silhouette = clamp(silhouette)

                edge_glow = clamp(e * self.options.edge_boost + gl * self.options.glow_boost * 0.34)
                edge_glow *= (0.45 + 0.55 * (1.0 - silhouette * 0.5))

                ring_i, rune_i = self._ring_intensity(x, y, width, height, t)
                rain_i = self._rain_intensity(x, y, width, height, t)
                ground_i = self._ground_intensity(x, y, width, height, t, gl)

                # sparse background texture, kept subtle
                noise = self._noise(x, y, t)
                tex = clamp((g * 0.35 + structure * 0.12) * self.options.texture_amount)
                if noise > 0.90:
                    tex += 0.06
                tex = clamp(tex)

                # interior silhouette should stay mostly black with very rare faint dots
                interior = silhouette * (1.0 - smoothstep(0.10, 0.55, edge_glow + ring_i * 0.5))
                interior_noise = interior * self.options.interior_noise * (0.2 + 0.8 * noise)

                # scanline + shimmer
                scan_mul = 1.0 - self.options.scanline * (0.5 + 0.5 * math.sin(y * 1.0 + t * 7.0))
                shimmer = 1.0 + self.options.shimmer * math.sin(x * 0.21 + y * 0.13 + t * 1.7)

                comp = clamp(
                    edge_glow * 0.95
                    + ring_i * 0.70
                    + rune_i * 0.85
                    + rain_i * 0.72
                    + ground_i * 0.65
                    + tex * 0.55
                    + interior_noise
                )
                comp *= scan_mul
                comp *= shimmer

                nx = (x + 0.5) / width - 0.5
                ny = (y + 0.5) / height - 0.5
                vignette = 1.0 - self.options.vignette * min(1.0, math.sqrt(nx * nx + ny * ny) / 0.7071)
                comp = clamp(pow(comp * vignette, self.options.gamma))
                comp = clamp(comp + (noise - 0.5) * self.options.dither)

                # Determine character/layer.
                if interior > 0.58 and edge_glow < 0.25 and ring_i < 0.35:
                    if noise < 0.92:
                        ch = " "
                        bright = 0.0
                    else:
                        bright = interior_noise * 0.7
                        ch = choose_by_intensity(INTERIOR_GLYPHS, bright * 3.0)
                else:
                    layers = {
                        "rune": rune_i,
                        "edge": edge_glow,
                        "ring": ring_i,
                        "rain": rain_i,
                        "ground": ground_i,
                        "tex": tex,
                    }
                    dominant = max(layers, key=layers.get)
                    if dominant == "rain":
                        ch = RAIN_GLYPHS[int(hash2(x, y + int(t * 20)) * len(RAIN_GLYPHS)) % len(RAIN_GLYPHS)]
                    elif dominant == "rune":
                        ch = choose_by_intensity(" .:+*◎◌◍", rune_i)
                    elif dominant == "ring":
                        ch = choose_by_intensity(RING_GLYPHS, ring_i)
                    elif dominant == "ground":
                        ch = choose_by_intensity(GROUND_GLYPHS, ground_i)
                    else:
                        ch = choose_by_intensity(EDGE_GLYPHS, max(edge_glow, tex))
                    bright = comp
                    if bright < 0.05:
                        ch = " "

                # slight source-driven tint but still monochrome-ish.
                src_lum = (0.2126 * src_rgb[0] + 0.7152 * src_rgb[1] + 0.0722 * src_rgb[2]) / 255.0
                tint = 0.05 + 0.10 * src_lum + 0.12 * min(1.0, edge_glow + rune_i)
                color = self._palette_color(bright, tint=tint)
                out.append((x, y, ch, color, bright))
        return out

    def render_lines(self, width: int, height: int, t: float = 0.0, ansi: bool = True) -> List[str]:
        cells = self.cells(width, height, t=t)
        rows = [[] for _ in range(height)]
        last_color = [None] * height
        for x, y, ch, color, intensity in cells:
            if ansi:
                if last_color[y] != color:
                    rows[y].append(rgb_fg(color))
                    last_color[y] = color
                rows[y].append(ch)
            else:
                rows[y].append(ch)
        lines = []
        for y in range(height):
            s = "".join(rows[y])
            if ansi:
                s += RESET
            lines.append(s)
        return lines

    def render_braille_lines(self, width: int, height: int, t: float = 0.0, ansi: bool = True,
                             threshold: float = 0.11) -> List[str]:
        """Render with Unicode Braille cells.

        Each terminal cell represents a 2x4 subpixel block, so a 120x36 TUI area
        carries roughly 240x144 binary detail while still returning normal text lines.
        The source aspect ratio is preserved by temporarily adjusting char_aspect for
        the 2x4 supersampled grid.
        """
        width = max(2, int(width))
        height = max(2, int(height))
        sx, sy = 2, 4

        # Preserve the same overall terminal aspect when rendering the supersampled grid.
        old_char_aspect = self.options.char_aspect
        self.options.char_aspect = old_char_aspect * sy / sx
        try:
            hi = self.cells(width * sx, height * sy, t=t)
        finally:
            self.options.char_aspect = old_char_aspect

        grid = [[(0.0, PALETTES[self.options.palette]["bg"]) for _ in range(width * sx)]
                for _ in range(height * sy)]
        for x, y, ch, color, intensity in hi:
            grid[y][x] = (intensity, color)

        rows: List[str] = []
        for y in range(height):
            parts = []
            last_color = None
            for x in range(width):
                bits = 0
                total = 0.0
                r = g = b = 0.0
                count = 0
                # Braille bit order: (0,0),(0,1),(0,2),(0,3),(1,0),(1,1),(1,2),(1,3)
                coords = ((0, 0), (0, 1), (0, 2), (0, 3), (1, 0), (1, 1), (1, 2), (1, 3))
                for i, (dx, dy) in enumerate(coords):
                    inten, col = grid[y * sy + dy][x * sx + dx]
                    # adaptive threshold keeps faint matrix detail but avoids filling the silhouette
                    local_threshold = threshold * (0.75 + 0.25 * ((x + y + i) % 3))
                    if inten > local_threshold:
                        bits |= BRAILLE_DOTS[i]
                    total += inten
                    weight = max(inten, 0.03)
                    r += col[0] * weight
                    g += col[1] * weight
                    b += col[2] * weight
                    count += weight

                if bits == 0:
                    ch = " "
                else:
                    ch = chr(0x2800 + bits)
                avg = total / 8.0
                color = (int(r / count), int(g / count), int(b / count)) if count > 0 else PALETTES[self.options.palette]["bg"]
                # Push bright braille details slightly hotter so they read on dark terminals.
                if avg > 0.30:
                    color = mix(color, PALETTES[self.options.palette]["glow"], min(0.45, avg * 0.35))
                if ansi:
                    if color != last_color:
                        parts.append(rgb_fg(color))
                        last_color = color
                    parts.append(ch)
                else:
                    parts.append(ch)
            line = "".join(parts)
            if ansi:
                line += RESET
            rows.append(line)
        return rows

    def render_string(self, width: int, height: int, t: float = 0.0, ansi: bool = True,
                      mode: str = "char") -> str:
        if mode == "braille":
            return "\n".join(self.render_braille_lines(width, height, t=t, ansi=ansi))
        return "\n".join(self.render_lines(width, height, t=t, ansi=ansi))


def preview(renderer: MatrixSilhouetteRenderer, width: int | None, height: int | None,
            seconds: float = 8.0, fps: int = 16, ansi: bool = True, no_alt: bool = False,
            mode: str = "char") -> None:
    tw, th = terminal_size()
    width = width or tw
    height = height or max(8, th)
    start = time.monotonic()
    dt = 1.0 / max(1, fps)

    if ansi:
        sys.stdout.write(HIDE_CURSOR)
        if not no_alt:
            sys.stdout.write(ALT_ON)
        sys.stdout.flush()

    try:
        while True:
            frame_start = time.monotonic()
            t = frame_start - start
            if seconds > 0 and t >= seconds:
                break
            frame = renderer.render_string(width, height, t=t, ansi=ansi, mode=mode)
            if ansi:
                sys.stdout.write(CLEAR)
            else:
                sys.stdout.write("\n" * 2)
            sys.stdout.write(frame)
            sys.stdout.flush()
            remaining = dt - (time.monotonic() - frame_start)
            if remaining > 0:
                time.sleep(remaining)
    finally:
        if ansi:
            sys.stdout.write(RESET)
            if not no_alt:
                sys.stdout.write(ALT_OFF)
            sys.stdout.write(SHOW_CURSOR)
            sys.stdout.flush()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Render an image as a matrix-silhouette TUI scene.")
    p.add_argument("image", help="Input image path")
    p.add_argument("--width", type=int, default=None)
    p.add_argument("--height", type=int, default=None)
    p.add_argument("--palette", choices=sorted(PALETTES), default="green")
    p.add_argument("--mode", choices=["char", "braille"], default="braille",
                   help="char = classic ANSI glyphs; braille = high-res 2x4 subpixel rendering")
    p.add_argument("--animate", action="store_true")
    p.add_argument("--snapshot", action="store_true")
    p.add_argument("--seconds", type=float, default=8.0)
    p.add_argument("--fps", type=int, default=16)
    p.add_argument("--output", default=None)
    p.add_argument("--no-ansi", action="store_true")
    p.add_argument("--no-alt", action="store_true")
    p.add_argument("--no-rain", action="store_true")
    p.add_argument("--no-rings", action="store_true")
    p.add_argument("--no-ground", action="store_true")
    p.add_argument("--black-point", type=float, default=0.58)
    p.add_argument("--rain-density", type=float, default=0.16)
    p.add_argument("--ring-strength", type=float, default=0.95)
    p.add_argument("--ground-glow", type=float, default=0.75)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    options = RenderOptions(
        palette=args.palette,
        black_point=args.black_point,
        rain_density=args.rain_density,
        ring_strength=args.ring_strength,
        ground_glow=args.ground_glow,
        enable_rain=not args.no_rain,
        enable_rings=not args.no_rings,
        enable_ground=not args.no_ground,
    )
    renderer = MatrixSilhouetteRenderer.from_path(args.image, options=options)

    if args.animate and not args.snapshot:
        preview(renderer, args.width, args.height, seconds=args.seconds, fps=args.fps,
                ansi=not args.no_ansi, no_alt=args.no_alt, mode=args.mode)
        return 0

    tw, th = terminal_size()
    width = args.width or tw
    height = args.height or max(8, th)
    result = renderer.render_string(width, height, t=time.monotonic(), ansi=not args.no_ansi, mode=args.mode)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"Wrote {args.output}")
    else:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
