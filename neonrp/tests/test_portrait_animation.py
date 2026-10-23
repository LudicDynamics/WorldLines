"""The play-mode portrait animation must never starve the input line.

「现在 commandline 输入有点慢」: a braille frame of the wide
banner costs ~0.5-1 s of pure Python and was rendered on the UI thread at
7 fps, so every keystroke queued behind a frame. Three properties now:

- the t-independent PIL fields are computed once per size, not per frame;
- a frame renders on a worker thread and ticks arriving meanwhile are dropped;
- a frame that finishes after the asset changed is thrown away.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from PIL import Image

from neonrp.tui.matrix_silhouette import MatrixSilhouetteRenderer, RenderOptions
from neonrp.tui.portrait import PortraitPanel


def _renderer() -> MatrixSilhouetteRenderer:
    img = Image.new("RGB", (64, 48), (0, 0, 0))
    for x in range(16, 48):
        for y in range(8, 40):
            img.putpixel((x, y), (200, 220, 210))
    return MatrixSilhouetteRenderer(img, RenderOptions())


def test_static_fields_are_computed_once_per_size(monkeypatch):
    r = _renderer()
    calls = []
    orig = r._compute_resized_fields
    monkeypatch.setattr(r, "_compute_resized_fields", lambda w, h: calls.append((w, h)) or orig(w, h))
    r.render_braille_lines(width=20, height=8, t=0.0)
    r.render_braille_lines(width=20, height=8, t=0.14)
    r.render_braille_lines(width=20, height=8, t=0.28)
    assert calls == [(40, 32)], "same size → one PIL pass"
    r.render_braille_lines(width=24, height=8, t=0.42)
    assert len(calls) == 2, "a new size recomputes"


def test_frames_differ_over_time_despite_the_cache():
    r = _renderer()
    a = r.render_braille_lines(width=20, height=8, t=0.0)
    b = r.render_braille_lines(width=20, height=8, t=1.0)
    assert a != b, "the rain must still move"


def _panel() -> PortraitPanel:
    p = PortraitPanel()  # constructed outside an app: no worker, no `app`
    p._renderer = object()
    p._art_box = lambda: (10, 4)
    return p


def test_tick_is_dropped_while_a_frame_is_in_flight():
    p = _panel()
    p._request_frame = MagicMock()
    p._frame_in_flight = True
    p._tick_animation()
    p._request_frame.assert_not_called()
    p._frame_in_flight = False
    p._tick_animation()
    p._request_frame.assert_called_once()


def test_time_follows_the_wall_clock_with_a_cap(monkeypatch):
    import time

    p = _panel()
    p._request_frame = MagicMock()
    clock = [100.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    p._tick_animation()  # first tick: fixed step
    t1 = p._anim_t
    clock[0] += 0.5
    p._tick_animation()
    assert abs((p._anim_t - t1) - 0.5) < 1e-6, "a 0.5 s frame advances the rain by 0.5 s"
    clock[0] += 30.0
    p._tick_animation()
    assert p._anim_t - t1 - 0.5 <= 4 * PortraitPanel._ANIM_INTERVAL + 1e-6, "a long stall does not jump the rain"


def test_stale_frame_is_not_applied():
    p = _panel()
    p.update = MagicMock()
    old = p._renderer
    p._frame_in_flight = True
    p._renderer = object()  # asset changed while the frame was cooking
    p._apply_frame(old, "frame-for-old-asset")
    p.update.assert_not_called()
    assert p._frame_in_flight is False
    p._apply_frame(p._renderer, "fresh")
    p.update.assert_called_once_with("fresh")


def test_request_frame_without_an_app_renders_synchronously():
    p = _panel()
    p.update = MagicMock()
    p._compose_matrix_frame = MagicMock(return_value="sync-frame")
    # no running app: PortraitPanel.app raises → fallback path
    p._request_frame()
    p.update.assert_called_once_with("sync-frame")
    assert p._frame_in_flight is False


def test_typing_holds_the_rain_then_it_resumes(monkeypatch):
    import time

    p = _panel()
    p._request_frame = MagicMock()
    clock = [50.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    p.note_typing()
    p._tick_animation()
    p._request_frame.assert_not_called()
    clock[0] += PortraitPanel._TYPING_PAUSE + 0.01
    p._tick_animation()
    p._request_frame.assert_called_once()


def test_next_frame_waits_as_long_as_the_last_one_took(monkeypatch):
    import time

    p = _panel()
    p._request_frame = MagicMock()
    clock = [10.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    p._frame_started = 10.0
    clock[0] = 10.6  # the frame took 0.6 s
    p._apply_frame(p._renderer, "f")
    assert abs(p._last_frame_cost - 0.6) < 1e-6
    clock[0] = 10.9  # 0.3 s later: still inside the cool-down
    p._tick_animation()
    p._request_frame.assert_not_called()
    clock[0] = 11.3
    p._tick_animation()
    p._request_frame.assert_called_once()


def test_two_expensive_frames_freeze_the_animation(monkeypatch):
    import time

    p = _panel()
    p._anim_timer = MagicMock()
    clock = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    for start in (0.0, 10.0):
        p._frame_started = start
        clock[0] = start + PortraitPanel._AUTO_STATIC_COST + 0.1
        p._apply_frame(p._renderer, "f")
    p._anim_timer.pause.assert_called_once()


def test_one_slow_frame_is_forgiven(monkeypatch):
    import time

    p = _panel()
    p._anim_timer = MagicMock()
    clock = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    p._frame_started = 0.0
    clock[0] = 1.0
    p._apply_frame(p._renderer, "f")
    p._frame_started = 5.0
    clock[0] = 5.1
    p._apply_frame(p._renderer, "f")
    p._anim_timer.pause.assert_not_called()
