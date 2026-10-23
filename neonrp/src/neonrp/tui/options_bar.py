"""The turn's options as buttons above the input (10-08: ``result.options`` used to be only ``1. …`` text lines).

Pressing one sends it as the player's line; sending anything clears the bar."""
from __future__ import annotations

from typing import Any, Callable

from textual.containers import Horizontal
from textual.widgets import Button


class OptionsBar(Horizontal):
    DEFAULT_CSS = """
    OptionsBar { height: auto; width: 100%; display: none; padding: 0 1; }
    OptionsBar .option-btn { width: auto; max-width: 48; height: 3; margin-right: 1; background: #13261b; color: #d1fae5;
                             border: tall #166534; }
    OptionsBar .option-btn:hover { background: #166534; color: #f0fdf4; }
    """

    def __init__(self, *, on_pick: Callable[[str], None] | None = None, **kw: Any) -> None:
        super().__init__(**kw)
        self.on_pick = on_pick
        self.options: list[str] = []

    def set_options(self, options: list[Any]) -> None:
        self.options = [" ".join(str(o).split()) for o in options or [] if str(o).strip()][:5]
        self.remove_children()
        for i, text in enumerate(self.options, 1):
            label = text if len(text) <= 44 else text[:43] + "…"
            self.mount(Button(f"{i} · {label}", id=f"option-{i}", classes="option-btn"))
        self.display = bool(self.options)

    def clear(self) -> None:
        if self.options or self.display:
            self.set_options([])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = str(event.button.id or "")
        if not bid.startswith("option-"):
            return
        event.stop()
        try:
            text = self.options[int(bid.split("-", 1)[1]) - 1]
        except (ValueError, IndexError):
            return
        self.clear()
        if self.on_pick is not None:
            self.on_pick(text)


class QuickBar(Horizontal):
    """The play quick bar above the input (10-23, as the standard front end's): people here (@), the common skills with
    their value (/), things held (#). A click puts the word into the input — nothing is sent."""

    # 10-24: a one-line button is Textual's *compact* button (``-textual-compact``, ``border: none !important``).
    # ``border: none`` in our own rule is not enough: Button's default CSS sets border-top / border-bottom again
    # (and on hover), the two border lines eat the one line of height and the label is never drawn.
    DEFAULT_CSS = """
    QuickBar { height: 1; width: 100%; display: none; padding: 0 1; }
    QuickBar .quick-btn { width: auto; min-width: 3; height: 1; margin-right: 1; padding: 0 1;
                          background: #111827; color: #a7f3d0; text-style: none; }
    QuickBar .quick-btn:hover { background: #1f2937; color: #f0fdf4; }
    """

    def __init__(self, *, on_pick: Callable[[str], None] | None = None, **kw: Any) -> None:
        super().__init__(**kw)
        self.on_pick = on_pick
        self.items: list[tuple[str, str]] = []

    def set_items(self, items: list[tuple[str, str]], *, show: bool = True) -> None:
        items = list(items or [])[:10]
        if items != self.items:
            self.items = items
            self.remove_children()
            for i, (label, _text) in enumerate(items):
                self.mount(Button(label if len(label) <= 18 else label[:17] + "…", id=f"quick-{i}", classes="quick-btn", compact=True))
        self.display = bool(self.items) and show

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = str(event.button.id or "")
        if not bid.startswith("quick-"):
            return
        event.stop()
        try:
            text = self.items[int(bid.split("-", 1)[1])][1]
        except (ValueError, IndexError):
            return
        if self.on_pick is not None:
            self.on_pick(text)
