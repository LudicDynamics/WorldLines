"""Shared flat clickable for the TUI.

Lived in `create_soul_screen.py` until M31 retired the creation screens
(creation moved into build mode and external agents). The widget itself was
never about creation — the settings flow and the launcher use it too — so it
moved here rather than dying with its old neighbours.
"""

from __future__ import annotations

from typing import Any

from textual import events
from textual.message import Message
from textual.widgets import Static


class TuiButton(Static):
    """Our own flat clickable — not the native Button — so buttons are
    visually consistent, fully styleable, and left-alignable.

    Posts ``TuiButton.Pressed`` on click or Enter/Space when focused. The
    message exposes ``.button`` and ``.control`` so ``@on(TuiButton.Pressed,
    "#id")`` selectors work exactly like the native Button.
    """

    can_focus = True

    class Pressed(Message):
        def __init__(self, button: "TuiButton") -> None:
            self.button = button
            super().__init__()

        @property
        def control(self) -> "TuiButton":
            return self.button

    def __init__(
        self,
        label: str = "",
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(label, id=id, classes=classes)
        self._label = label

    @property
    def label(self) -> str:
        """Mirror native Button's ``.label`` so call-sites that read it work."""
        return str(self._label)

    def update(self, renderable: Any = "") -> None:  # type: ignore[override]
        """Keep ``.label`` in sync when the caption is updated in place."""
        self._label = renderable
        super().update(renderable)

    def on_click(self, event: events.Click) -> None:
        event.stop()
        self.post_message(self.Pressed(self))

    def on_key(self, event: events.Key) -> None:
        if event.key in ("enter", "space"):
            event.stop()
            event.prevent_default()
            self.post_message(self.Pressed(self))
