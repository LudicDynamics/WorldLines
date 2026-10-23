"""Image → ASCII helper, built on tui/matrix_silhouette.py.

Both the launcher WorldHub preview and the play-mode portrait panel route
through ``render_image_to_text``. It returns a Rich ``Text`` so callers can
``Static.update(...)`` it directly. Pillow is required; missing → ``None``
and callers fall back to a text placeholder.

A bundled ``assets/card-door.png`` is exposed via ``DEFAULT_CARD_PATH`` and
used as the universal fallback (no portrait, no scene, nothing else).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from rich.text import Text


_ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"
DEFAULT_CARD_PATH = _ASSET_DIR / "card-door.png"

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")

# Conventional places worlds keep cover / portrait imagery. Stems are
# matched case-insensitively, anywhere under these directories.
COVER_STEMS = ("cover", "card-door", "poster", "thumbnail", "preview", "title")
COVER_DIRS = ("assets", "art", "media", "images", "img")


def discover_world_images(root: Path) -> list[Path]:
    """Walk a (downloaded) world directory, return up to 6 image paths.

    Order: explicit cover files first (``cover.*``, ``poster.*``, etc.),
    then anything under ``game/npc/*.{png,jpg,...}`` (portraits), then
    anything else under ``assets/`` / ``art/`` / ``media/``.
    """
    root = Path(root)
    if not root.is_dir():
        return []

    covers: list[Path] = []
    portraits: list[Path] = []
    other: list[Path] = []
    seen: set[Path] = set()

    def _add(bucket: list[Path], p: Path) -> None:
        rp = p.resolve()
        if rp in seen or not p.is_file():
            return
        if p.suffix.lower() not in IMAGE_EXTS:
            return
        seen.add(rp)
        bucket.append(p)

    for stem in COVER_STEMS:
        for ext in IMAGE_EXTS:
            for cand in root.glob(f"{stem}{ext}"):
                _add(covers, cand)
            for d in COVER_DIRS:
                for cand in (root / d).glob(f"{stem}{ext}"):
                    _add(covers, cand)

    npc_dir = root / "game" / "npc"
    if npc_dir.is_dir():
        for cand in sorted(npc_dir.iterdir()):
            _add(portraits, cand)

    for d in COVER_DIRS:
        sub = root / d
        if sub.is_dir():
            for cand in sorted(sub.rglob("*")):
                _add(other, cand)

    return (covers + portraits + other)[:6]


def make_matrix_renderer(
    image_path: Path,
    *,
    palette: str = "green",
    rings: bool = False,
) -> Any | None:
    """Build a reusable MatrixSilhouetteRenderer for ``image_path``.

    Hold onto the returned object and call ``render_matrix_lines`` with an
    advancing ``t`` to animate (rain / shimmer / scanline). Returns
    ``None`` if Pillow is missing or the file won't open.
    """
    try:
        from neonrp.tui.matrix_silhouette import (
            MatrixSilhouetteRenderer,
            RenderOptions,
        )
    except Exception:
        return None
    try:
        opts = RenderOptions(palette=palette, enable_rings=rings)
        return MatrixSilhouetteRenderer.from_path(str(image_path), opts)
    except Exception:
        return None


def render_matrix_lines(
    renderer: Any,
    *,
    width: int = 60,
    height: int = 22,
    mode: str = "braille",
    t: float = 0.0,
) -> list[Text] | None:
    """Render one animation frame from a renderer built by
    ``make_matrix_renderer``. Returns per-line Text, or None on error."""
    if renderer is None:
        return None
    try:
        if mode == "braille":
            lines = renderer.render_braille_lines(width=width, height=height, t=t, ansi=True)
        else:
            lines = renderer.render_lines(width=width, height=height, t=t, ansi=True)
    except Exception:
        return None
    return [Text.from_ansi(line) for line in lines]


def render_image_lines(
    image_path: Path,
    *,
    width: int = 60,
    height: int = 22,
    palette: str = "green",
    mode: str = "braille",
    rings: bool = False,
    t: float = 0.0,
) -> list[Text] | None:
    """Render ``image_path`` into one Rich ``Text`` per output row.

    Returning per-line Text objects lets callers stitch them into row-based
    layouts (e.g. the ChoicePickerScreen detail screen) without losing the
    matrix-silhouette ANSI colors. Returns ``None`` on any failure.

    One-shot convenience — for animation, prefer ``make_matrix_renderer``
    + ``render_matrix_lines`` so the source image isn't reopened per frame.
    """
    renderer = make_matrix_renderer(image_path, palette=palette, rings=rings)
    return render_matrix_lines(renderer, width=width, height=height, mode=mode, t=t)


def render_image_to_text(
    image_path: Path,
    *,
    width: int = 60,
    height: int = 22,
    palette: str = "green",
    mode: str = "braille",
    rings: bool = False,
) -> Text | None:
    """Render ``image_path`` as a single joined ``Text`` block.

    Convenience over ``render_image_lines`` for callers that want one
    drop-in renderable (e.g. ``Static.update(...)``).
    """
    lines = render_image_lines(
        image_path,
        width=width, height=height,
        palette=palette, mode=mode, rings=rings,
    )
    if lines is None:
        return None
    out = Text()
    for i, line in enumerate(lines):
        if i:
            out.append("\n")
        out.append_text(line)
    return out


def render_lines(lines: Iterable[str]) -> Text:
    """Tiny helper for plain-text fallbacks (preserves newlines)."""
    return Text("\n".join(lines))
