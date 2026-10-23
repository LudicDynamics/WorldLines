"""Character/scene portrait panel for the play/mcp TUI.

Always visible in play/mcp mode now. When no NPC asset resolves it falls
back to the bundled ``card-door.png`` (under ``neonrp/assets/``), so the
panel still carries the WorldLines launcher's matrix-braille style instead
of going blank.

Rendering uses ``neonrp.core.image_render`` — same matrix-silhouette
pipeline the WorldHub picker uses, so launcher and play share a coherent
art style. The legacy half-block / ASCII-ramp fallbacks remain in place
for terminals where Pillow can't load or the matrix renderer can't run.

Asset resolution (first hit wins), relative to the game root:

  1. ``portrait`` string field in ``game/npc/<id>.json``
  2. ``game/npc/<id>.{png,jpg,jpeg,webp,gif}``
  3. ``assets/portrait.{png,jpg,jpeg,webp}``  (scene-wide fallback)
  4. last text-to-image generation (``.neonrp/imagegen/latest.png``)
  5. bundled ``card-door.png``  (the universal default)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.align import Align
from rich.console import Group
from rich.text import Text
from textual.widgets import Static

from neonrp.core.image_render import (
    DEFAULT_CARD_PATH,
    make_matrix_renderer,
    render_matrix_lines,
)

_IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")


def _latest_imagegen_path(root: Path | None) -> Path | None:
    if root is None:
        return None
    cand = Path(root) / ".neonrp" / "imagegen" / "latest.png"
    return cand if cand.is_file() else None


def find_portrait_asset(root: Path | None, speaker: str | None) -> Path | None:
    """Return a portrait image path for ``speaker``, falling back through
    the resolution order. Always returns a path (the bundled default is the
    final fallback).
    """
    if root is None:
        # No root at all: jump straight to the universal default.
        return DEFAULT_CARD_PATH if DEFAULT_CARD_PATH.is_file() else None

    raw = str(speaker or "").strip()
    npc_id = raw.lower().replace(" ", "-") if raw else ""
    root = Path(root)

    if npc_id:
        npc_json = root / "game" / "npc" / f"{npc_id}.json"
        try:
            if npc_json.exists():
                payload = json.loads(npc_json.read_text(encoding="utf-8"))
                field = payload.get("portrait")
                if isinstance(field, str) and field.strip():
                    cand = (root / field).expanduser()
                    if cand.exists() and cand.is_file():
                        return cand
        except Exception:
            pass

        for ext in _IMG_EXTS:
            cand = root / "game" / "npc" / f"{npc_id}{ext}"
            if cand.exists() and cand.is_file():
                return cand

    # A freshly generated scene image outranks the bundled cover so
    # text-to-image actually drives the banner once it's wired up.
    latest = _latest_imagegen_path(root)
    if latest is not None:
        return latest

    for ext in _IMG_EXTS:
        cand = root / "assets" / f"portrait{ext}"
        if cand.exists() and cand.is_file():
            return cand
        cand = root / "assets" / f"cover{ext}"
        if cand.exists() and cand.is_file():
            return cand

    return DEFAULT_CARD_PATH if DEFAULT_CARD_PATH.is_file() else None


class PortraitPanel(Static):
    """Side panel that renders the current speaker portrait / scene card.

    Stays visible in play/mcp mode (the launcher and play share the same
    matrix-braille look). Asset misses fall back to the bundled
    ``card-door.png`` rather than hiding the panel.
    """

    # Fallback render box when the widget hasn't been sized yet. Once
    # mounted the box tracks the panel's real cell size (it's a wide top
    # banner now, not a fixed side column).
    _FALLBACK_W = 96
    _FALLBACK_H = 12
    # ~7fps — enough for the matrix rain to read as motion without
    # burning a core re-rendering too often.
    _ANIM_INTERVAL = 0.14
    # If two consecutive frames cost more than this, the machine cannot
    # afford the rain: keep the last frame and stop ticking (the user can
    # still `/portrait` or resize to retry). Typing must never lose.
    _AUTO_STATIC_COST = 0.6

    def __init__(self, **kwargs: Any) -> None:
        super().__init__("", **kwargs)
        self._current_asset: Path | None = None
        # Persist the most recently used speaker so a later refresh
        # (e.g. after text-to-image generates a fresh ``latest.png``) can
        # re-resolve from the same context.
        self._last_speaker: str | None = None
        # Visible by default; the legacy "hide on miss" behavior is gone.
        self.display = True
        # Animation state — a held MatrixSilhouetteRenderer ticked by an
        # interval timer. None when the current asset uses a static
        # fallback (rich-pixels / ASCII ramp) instead of matrix art.
        self._renderer: Any | None = None
        self._anim_t: float = 0.0
        self._anim_label: str = "?"
        self._anim_timer: Any | None = None
        # One frame at a time, rendered on a worker thread. A braille frame
        # of the wide banner is ~0.5-1 s of pure Python; on the UI thread at
        # 7 fps that starved the event loop and every keystroke queued
        # behind a frame (「commandline 输入有点慢」). Ticks
        # that arrive while a frame is still cooking are dropped, and
        # ``_anim_t`` follows the wall clock so the rain keeps real speed
        # at whatever frame rate the machine can afford.
        self._frame_in_flight: bool = False
        self._anim_clock: float | None = None
        # Two more guards against fighting the user for the GIL:
        # - while someone is typing the rain pauses (``_typing_until``);
        # - a new frame never starts sooner than the last one took to
        #   render, so the worker's duty cycle stays under 50%.
        self._typing_until: float = 0.0
        self._frame_started: float = 0.0
        self._last_frame_cost: float = 0.0
        self._next_frame_at: float = 0.0
        self._slow_frames: int = 0

    def on_mount(self) -> None:
        self._anim_timer = self.set_interval(
            self._ANIM_INTERVAL, self._tick_animation, pause=True
        )

    def on_resize(self) -> None:
        # Re-render the matrix frame at the new banner size so the art
        # always fills the full width of the top band.
        if self._renderer is not None:
            self._request_frame()

    def _source_aspect(self) -> float:
        """width/height of the current matrix source image, 0.0 if unknown."""
        try:
            src = getattr(self._renderer, "src", None)
            if src is not None:
                w, h = src.size
                return (w / h) if h else 0.0
        except Exception:
            pass
        return 0.0

    def _art_box(self) -> tuple[int, int]:
        """Cell box for the matrix art — aspect-fit inside the panel.

        The whole source image must be visible (no half-crop), so the box
        keeps the image's aspect ratio and is centered. Braille packs a
        2x4 subpixel grid per cell, hence the target cell ratio is
        ``2 * image_aspect``. One row is reserved for the caption."""
        size = self.size
        w = getattr(size, "width", 0) or 0
        h = getattr(size, "height", 0) or 0
        panel_w = max(24, (w - 2) if w else self._FALLBACK_W)
        panel_h = max(6, (h - 2) if h else self._FALLBACK_H)

        img_ratio = self._source_aspect()
        if img_ratio <= 0:
            # Unknown source — fall back to filling the band.
            return panel_w, panel_h

        target = 2.0 * img_ratio  # desired art_w / art_h
        if panel_w / panel_h >= target:
            # Panel is wider than the image needs → height-bound.
            art_h = panel_h
            art_w = max(24, min(panel_w, round(panel_h * target)))
        else:
            # Panel is taller than the image needs → width-bound.
            art_w = panel_w
            art_h = max(6, min(panel_h, round(panel_w / target)))
        return art_w, art_h

    def update_for(self, root: Path | None, speaker: str | None) -> None:
        """Resolve + render the portrait for ``speaker``. Falls back to
        card-door.png on miss; never hides itself."""
        self._last_speaker = speaker
        try:
            asset = find_portrait_asset(root, speaker)
        except Exception:
            asset = DEFAULT_CARD_PATH if DEFAULT_CARD_PATH.is_file() else None
        if asset is None:
            # Pillow is absent and we can't even reach the bundled default —
            # draw the text placeholder so the layout doesn't pop.
            self._current_asset = None
            self._stop_animation()
            self.update(self._frame(self._placeholder(), str(speaker or "?")))
            self.display = True
            return
        if asset == self._current_asset:
            return  # already showing this image — no churn
        self._current_asset = asset
        renderable = self._render_asset(asset, speaker)
        self.update(renderable)
        self.display = True

    def set_hidden(self, hidden: bool) -> None:
        """Show or hide the panel (Ctrl+I toggle).

        A hidden panel pauses its animation timer so it costs no CPU; the
        conversation view reclaims the freed width on its own.
        """
        if hidden:
            self.display = False
            if self._anim_timer is not None:
                self._anim_timer.pause()
        else:
            self.display = True
            # Resume animation only if there's a live matrix renderer.
            if self._renderer is not None and self._anim_timer is not None:
                self._anim_timer.resume()

    def show_image(self, path: Path, label: str = "") -> None:
        """Render a specific image file directly (bypass speaker resolution).

        Used by the scene text-to-image flow: once a fresh image lands the
        host calls this so the banner switches to it immediately.
        """
        p = Path(path)
        if not p.is_file():
            return
        self._current_asset = p
        renderable = self._render_asset(p, label or None)
        self.update(renderable)
        self.display = True

    def refresh_current(self, root: Path | None) -> None:
        """Re-render whatever's resolved for the last-seen speaker.

        Use this after a generation cycle drops a fresh ``latest.png`` —
        forces re-resolution so the new image lights up immediately.
        """
        self._current_asset = None  # bust the no-churn guard
        self.update_for(root, self._last_speaker)

    # -- rendering ---------------------------------------------------------

    def _caption(self, label: str) -> Text:
        """Single-line VN name plate under the art (no boxed Panel, so the
        image itself gets the vertical room)."""
        t = Text(justify="center")
        t.append("▌ ", style="#18FF82")
        t.append(str(label or "").strip() or "—", style="bold #eafdf1")
        return t

    def _frame(self, art: Any, label: str) -> Group:
        return Group(art, self._caption(label))

    def _placeholder(self) -> Text:
        return Text(
            "\n   ◜◝\n  ( ◠ ◠ )\n   \\___/\n   (立绘)\n",
            style="#5b8a6e",
            justify="center",
        )

    def _tick_animation(self) -> None:
        """Advance the matrix-rain animation by one frame (or skip it)."""
        if self._renderer is None or not self.display:
            return
        if self._frame_in_flight:
            return  # drop this tick; the previous frame is still rendering
        import time

        now = time.monotonic()
        if now < self._typing_until or now < self._next_frame_at:
            return  # the user is typing / the worker has just finished
        if self._anim_clock is None:
            self._anim_t += self._ANIM_INTERVAL
        else:
            # Wall-clock time, capped so a long stall does not jump the rain.
            self._anim_t += min(now - self._anim_clock, 4 * self._ANIM_INTERVAL)
        self._anim_clock = now
        self._request_frame()

    # Pause window after a keystroke: long enough to cover a burst of
    # typing, short enough that the art visibly lives again once you stop.
    _TYPING_PAUSE = 1.0

    @staticmethod
    def _animation_enabled() -> bool:
        """``NEONRP_PORTRAIT_STATIC=1`` keeps the first frame and never ticks:
        the escape hatch for slow machines / SSH sessions."""
        import os

        return os.environ.get("NEONRP_PORTRAIT_STATIC", "").strip().lower() not in ("1", "true", "yes", "on")

    def note_typing(self) -> None:
        """Called by the app on every input change: hold the rain still
        while the user types so a frame never competes with a keystroke."""
        import time

        self._typing_until = time.monotonic() + self._TYPING_PAUSE

    def _request_frame(self) -> None:
        """Render the current frame on a worker thread and apply it on the
        UI thread. Falls back to a synchronous render when there is no
        running app (unit tests, or a panel that is not mounted)."""
        renderer = self._renderer
        if renderer is None:
            return
        box = self._art_box()
        t = self._anim_t
        label = self._anim_label
        import time

        try:
            app = self.app
            self._frame_in_flight = True
            self._frame_started = time.monotonic()
            self.run_worker(
                lambda: self._render_frame_bg(app, renderer, box, t, label),
                thread=True,
                group="portrait-frame",
                exit_on_error=False,
            )
        except Exception:
            self._frame_in_flight = False
            frame = self._compose_matrix_frame()
            if frame is not None:
                self.update(frame)

    def _render_frame_bg(self, app: Any, renderer: Any, box: tuple[int, int], t: float, label: str) -> None:
        frame: Any | None = None
        try:
            frame = self._compose_matrix_frame(renderer=renderer, box=box, t=t, label=label)
        finally:
            app.call_from_thread(self._apply_frame, renderer, frame)

    def _apply_frame(self, renderer: Any, frame: Any | None) -> None:
        import time

        now = time.monotonic()
        self._frame_in_flight = False
        self._last_frame_cost = max(0.0, now - self._frame_started)
        self._next_frame_at = now + self._last_frame_cost
        if self._last_frame_cost > self._AUTO_STATIC_COST:
            self._slow_frames += 1
            if self._slow_frames >= 2 and self._anim_timer is not None:
                try:
                    self._anim_timer.pause()
                except Exception:
                    pass
        else:
            self._slow_frames = 0
        # The asset may have changed while this frame was cooking — a stale
        # face must not overwrite the new one.
        if frame is not None and renderer is self._renderer:
            self.update(frame)

    def _compose_matrix_frame(
        self,
        *,
        renderer: Any | None = None,
        box: tuple[int, int] | None = None,
        t: float | None = None,
        label: str | None = None,
    ) -> Any | None:
        """Render one matrix frame + caption. Defaults to the panel's current
        state; the worker passes an explicit snapshot so it never reads
        widget state off the UI thread."""
        renderer = self._renderer if renderer is None else renderer
        art_w, art_h = self._art_box() if box is None else box
        lines = render_matrix_lines(
            renderer,
            width=art_w,
            height=art_h,
            mode="braille",
            t=self._anim_t if t is None else t,
        )
        if not lines:
            return None
        art = Text()
        for i, line in enumerate(lines):
            if i:
                art.append("\n")
            art.append_text(line)
        return self._frame(Align.center(art), self._anim_label if label is None else label)

    def _stop_animation(self) -> None:
        self._renderer = None
        self._anim_clock = None
        if self._anim_timer is not None:
            self._anim_timer.pause()

    def _render_asset(self, asset: Path, speaker: str | None) -> Any:
        label = str(speaker or "").strip() or asset.stem.replace("-", " ").title()

        # Tier 1: animated matrix-braille rendering (shared art style with
        # the launcher's WorldHub preview). A held renderer is ticked by
        # the interval timer so the matrix rain reads as live motion.
        try:
            renderer = make_matrix_renderer(asset)
            if renderer is not None:
                self._renderer = renderer
                self._anim_t = 0.0
                self._anim_clock = None
                self._anim_label = label
                frame = self._compose_matrix_frame()
                if frame is not None:
                    if self._animation_enabled() and self._anim_timer is not None:
                        self._anim_timer.resume()
                    return frame
        except Exception:
            pass
        # Static fallbacks below — make sure the animation timer is idle.
        self._stop_animation()

        # Tier 2: rich-pixels half-blocks (works on any color terminal).
        try:
            from PIL import Image as _PILImage  # noqa: F401
            from rich_pixels import Pixels

            with _PILImage.open(asset) as im:
                im = im.convert("RGBA")
                target_w = 30
                ratio = im.height / im.width if im.width else 1.0
                target_h = max(1, int(target_w * ratio))
                im = im.resize((target_w, target_h))
                pixels = Pixels.from_image(im)
            return self._frame(Align.center(pixels), label)
        except Exception:
            pass

        # Tier 3: Pillow-only ASCII luminance ramp.
        try:
            from PIL import Image as _PILImage

            ramp = " .:-=+*#%@"
            with _PILImage.open(asset) as im:
                im = im.convert("L")
                target_w = 36
                ratio = im.height / im.width if im.width else 1.0
                target_h = max(1, int(target_w * ratio * 0.5))
                im = im.resize((target_w, target_h))
                px = im.load()
                lines = []
                for y in range(target_h):
                    row = "".join(
                        ramp[min(len(ramp) - 1, px[x, y] * len(ramp) // 256)]
                        for x in range(target_w)
                    )
                    lines.append(row)
            art = Text("\n".join(lines), style="#5BE0B0")
            return self._frame(Align.center(art), label)
        except Exception:
            pass

        return self._frame(self._placeholder(), label)
